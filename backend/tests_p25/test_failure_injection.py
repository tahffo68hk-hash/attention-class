"""P2.5 fault injection against real ORM/services on SQLite sequentially.

These checks test atomic rollback, NOT real multi-connection MySQL isolation.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from tests_m1_local.test_m1_sequential import case, reserve
from app.models.allocation import BedAllocation, BedStatusLog, AllocationIdempotency
from app.models.enums import BedStatus, AllocationStatus
from app.models.facility import Bed
from app.models.user import User
from app.services import allocation as svc


def _counts(db):
    return (db.scalar(select(func.count(BedAllocation.id))),
            db.scalar(select(func.count(BedStatusLog.id))),
            db.scalar(select(func.count(AllocationIdempotency.id))))


def test_reserve_audit_failure_rolls_back_and_key_reusable(case, monkeypatch):
    engine, ids = case
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        original = svc.record_audit
        def fails(*a, **kw):
            raise RuntimeError('synthetic audit storage outage')
        monkeypatch.setattr(svc, 'record_audit', fails)
        with pytest.raises(RuntimeError, match='audit storage outage'):
            reserve(db, ids, key='fault-on-reserve-0001')
        assert _counts(db) == (0,0,0)
        assert str(db.get(Bed, ids[1][0]).status) == 'AVAILABLE'
        monkeypatch.setattr(svc, 'record_audit', original)
        success = reserve(db, ids, key='fault-on-reserve-0001')
        assert success.id and _counts(db) == (1,1,1)


def test_admit_failure_rolls_back_both_axes_and_log(case, monkeypatch):
    engine, ids = case
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        alloc = reserve(db,ids)
        before = _counts(db)
        def fail(*a, **kw):
            raise RuntimeError('audit unavailable')
        monkeypatch.setattr(svc,'record_audit',fail)
        with pytest.raises(RuntimeError):
            svc.admit_patient(db, allocation_id=alloc.id, operator=db.get(User,ids[2]))
        assert str(db.get(Bed,ids[1][0]).status) == 'RESERVED'
        assert str(db.get(BedAllocation,alloc.id).status) == 'RESERVED'
        assert _counts(db) == before


def test_discharge_failure_rolls_back_status_and_active_flag(case, monkeypatch):
    engine, ids = case
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        alloc = reserve(db, ids)
        svc.admit_patient(db, allocation_id=alloc.id, operator=db.get(User,ids[2]))
        before = _counts(db)
        monkeypatch.setattr(svc,'record_audit',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('no audit')))
        with pytest.raises(RuntimeError):
            svc.discharge_patient(db, allocation_id=alloc.id, operator=db.get(User,ids[2]))
        current = db.get(BedAllocation,alloc.id)
        assert str(current.status) == 'ADMITTED'
        assert current.active_bed_id == ids[1][0]
        assert str(db.get(Bed,ids[1][0]).status) == 'OCCUPIED'
        assert _counts(db) == before


def test_cancel_failure_does_not_release_or_erase_alloc(case, monkeypatch):
    engine, ids = case
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        alloc=reserve(db,ids)
        before=_counts(db)
        monkeypatch.setattr(svc,'record_audit',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('error')))
        with pytest.raises(RuntimeError):
            svc.cancel_allocation(db,allocation_id=alloc.id,operator=db.get(User,ids[2]))
        assert str(db.get(BedAllocation,alloc.id).status)=='RESERVED'
        assert str(db.get(Bed,ids[1][0]).status)=='RESERVED'
        assert _counts(db)==before


def test_release_failure_rolls_back_bed_and_history(case, monkeypatch):
    engine,ids=case
    with Session(engine,expire_on_commit=False,autoflush=False) as db:
        alloc=reserve(db,ids)
        user=db.get(User,ids[2])
        svc.admit_patient(db,allocation_id=alloc.id,operator=user)
        svc.discharge_patient(db,allocation_id=alloc.id,operator=user)
        before=_counts(db)
        monkeypatch.setattr(svc,'record_audit',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('error')))
        with pytest.raises(RuntimeError):
            svc.release_bed(db,bed_id=ids[1][0],operator=user)
        assert str(db.get(Bed,ids[1][0]).status)=='CLEANING'
        assert db.get(BedAllocation,alloc.id).released_at is None
        assert _counts(db)==before


@pytest.mark.parametrize('action', ['admit','discharge','cancel'])
def test_illegal_repeated_terminal_transition_rejected(case, action):
    engine, ids = case
    with Session(engine,expire_on_commit=False,autoflush=False) as db:
        user=db.get(User,ids[2])
        alloc=reserve(db,ids)
        if action=='admit':
            svc.admit_patient(db,allocation_id=alloc.id,operator=user)
            with pytest.raises(svc.BizError):
                svc.admit_patient(db,allocation_id=alloc.id,operator=user)
        elif action=='discharge':
            svc.admit_patient(db,allocation_id=alloc.id,operator=user)
            svc.discharge_patient(db,allocation_id=alloc.id,operator=user)
            with pytest.raises(svc.BizError):
                svc.discharge_patient(db,allocation_id=alloc.id,operator=user)
        else:
            svc.cancel_allocation(db,allocation_id=alloc.id,operator=user)
            with pytest.raises(svc.BizError):
                svc.cancel_allocation(db,allocation_id=alloc.id,operator=user)
