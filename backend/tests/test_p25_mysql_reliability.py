"""P2.5 MySQL-only checks. WARNING: tests/conftest.py destroys hospital_test tables.

NEVER run against hospital or any non-disposable schema. The tests in this file
need two real DB connections and InnoDB row locks; SQLite cannot substitute.
"""
from __future__ import annotations

import threading

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import BizError
from app.db.session import get_engine, get_session_factory
from app.models.allocation import BedAllocation
from app.models.enums import AllocationMode, AllocationStatus, BedStatus
from app.models.facility import Bed
from app.models.user import User
from app.services.allocation import reserve_bed, reassign_reserved_bed
from tests.conftest import make_request


def _worker_move(allocation_id, target_id, operator_id, barrier, out, index):
    with get_session_factory()() as db:
        try:
            operator = db.get(User, operator_id)
            barrier.wait(timeout=15)
            result = reassign_reserved_bed(db, allocation_id=allocation_id,
                        new_bed_id=target_id, reason='模拟并发换床', operator=operator)
            out[index] = ('OK', result.id)
        except BizError as exc:
            out[index] = ('BIZ', exc.code, exc.status_code)
        except Exception as exc:
            out[index] = ('EXC', type(exc).__name__, str(exc)[:180])


def test_two_reassignments_to_same_target_only_one_commits(client, ds):
    assert get_engine().dialect.name == 'mysql'
    req1 = make_request(ds, patient_name='男患者甲', department_code='CARD', seq=95)
    req2 = make_request(ds, patient_name='男患者丙', department_code='CARD', seq=96)
    old_beds = [ds.bed('C-W1-01'), ds.bed('C-W1-02')]
    target = ds.bed('C-W1-04')
    operator_id = ds.users['nurse01']
    with get_session_factory()() as db:
        operator = db.get(User, operator_id)
        originals = [reserve_bed(db, request_id=req, bed_id=bed, operator=operator).id
                     for req, bed in zip([req1,req2],old_beds)]
    barrier = threading.Barrier(2)
    out = {}
    workers = [threading.Thread(target=_worker_move,
               args=(originals[i],target,operator_id,barrier,out,i), daemon=True)
               for i in range(2)]
    for w in workers: w.start()
    for w in workers: w.join(timeout=40)
    assert all(not w.is_alive() for w in workers), out
    assert len(out) == 2, out
    assert sum(v[0] == 'OK' for v in out.values()) == 1, out
    assert sum(v[0] == 'BIZ' and v[2] == 409 for v in out.values()) == 1, out
    with get_session_factory()() as db:
        assert str(db.get(Bed,target).status) == 'RESERVED'
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.bed_id == target, BedAllocation.status == AllocationStatus.RESERVED)) == 1
        # Failed swap keeps its original reservation; successful swap cancels only its own old record.
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.admission_request_id.in_([req1,req2]),
            BedAllocation.status == AllocationStatus.RESERVED)) == 2
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.admission_request_id.in_([req1,req2]),
            BedAllocation.status == AllocationStatus.CANCELLED)) == 1
        assert sum(str(db.get(Bed,b).status) == 'RESERVED' for b in old_beds) == 1


def test_mysql_generated_unique_active_request_blocks_direct_duplicate_insert(client,ds):
    """Even if application guards are skipped, database must reject a second active bed."""
    assert get_engine().dialect.name == 'mysql'
    req = make_request(ds, patient_name='男患者甲', department_code='CARD', seq=97)
    with get_session_factory()() as db:
        db.add(BedAllocation(admission_request_id=req, patient_id=ds.patients['男患者甲'],
                             bed_id=ds.bed('C-W1-01'), active_bed_id=ds.bed('C-W1-01'),
                             status=AllocationStatus.RESERVED, mode=AllocationMode.MANUAL))
        db.commit()
        db.add(BedAllocation(admission_request_id=req, patient_id=ds.patients['男患者甲'],
                             bed_id=ds.bed('C-W1-02'), active_bed_id=ds.bed('C-W1-02'),
                             status=AllocationStatus.RESERVED, mode=AllocationMode.MANUAL))
        try:
            db.commit()
            raise AssertionError('数据库未阻止同一住院申请重复占床')
        except IntegrityError:
            db.rollback()
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.admission_request_id == req)) == 1
