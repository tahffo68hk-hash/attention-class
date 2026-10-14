"""Independent SQLite sequential behavior checks; never a MySQL concurrency substitute."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import BizError
from app.models import Base
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedAllocation, BedStatusLog, AllocationIdempotency
from app.models.enums import (
    AdmissionRequestStatus, AllocationMode, AllocationStatus, BedStatus,
    BedType, Gender, GenderLimit, PatientPriority, UserRole,
)
from app.models.facility import Department, Ward, Bed
from app.models.patient import Patient
from app.models.user import User, Doctor
from app.services.allocation import (
    reserve_bed, reassign_reserved_bed, admit_patient, discharge_patient,
    release_bed, cancel_allocation,
)


@pytest.fixture
def case(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'm1.db'}")
    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False, autoflush=False)
    dep = Department(code='CARD',name='Cardiology',anchor_floor=1,anchor_x=0,anchor_y=0)
    db.add(dep);db.flush()
    ward = Ward(code='C1',name='Cardiac W1',department_id=dep.id,floor=1)
    admin = User(username='nurse',full_name='Nurse',hashed_password='dummy',role=UserRole.NURSE)
    patient = Patient(name='Fictional',medical_record_no='TEST-001',gender=Gender.MALE)
    db.add_all([ward,admin,patient]);db.flush()
    doctor=Doctor(name='Doc',department_id=dep.id)
    db.add(doctor);db.flush()
    req = AdmissionRequest(certificate_no='ORD-001',patient_id=patient.id,
                           department_id=dep.id,doctor_id=doctor.id,
                           status=AdmissionRequestStatus.PRE_ADMITTED,
                           priority=PatientPriority.NORMAL,isolation_required=False)
    db.add(req);db.flush()
    pre=Preadmission(admission_request_id=req.id,queue_no='Q001',queue_sequence=1)
    beds=[]
    for i in range(3):
        b=Bed(code=f'B{i+1}',ward_id=ward.id,department_id=dep.id,
              bed_type=BedType.NORMAL,gender_limit=GenderLimit.ANY,
              is_isolation=False,status=BedStatus.AVAILABLE,position_x=i*5)
        db.add(b);beds.append(b)
    db.add(pre);db.commit()
    ids=(req.id,[b.id for b in beds],admin.id)
    db.close()
    yield engine,ids
    engine.dispose()


def reserve(db, ids, bed_idx=0, key=None):
    request_id,beds,user_id=ids
    return reserve_bed(db, request_id=request_id, bed_id=beds[bed_idx],
                       operator=db.get(User,user_id), idempotency_key=key)


def test_reservation_and_replay(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        a=reserve(db,ids,key='idem-unique-001')
        b=reserve(db,ids,key='idem-unique-001')
        assert a.id==b.id
        assert db.scalar(select(func.count(AllocationIdempotency.id)))==1
        assert db.scalar(select(func.count(BedAllocation.id)))==1
        assert str(db.get(Bed,ids[1][0]).status)=='RESERVED'


def test_key_conflict(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        reserve(db,ids,key='idem-unique-002')
        with pytest.raises(BizError) as err:
            reserve(db,ids,bed_idx=1,key='idem-unique-002')
        assert err.value.code=='IDEMPOTENCY_KEY_CONFLICT'
        assert err.value.status_code==409


def test_same_request_different_beds(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        reserve(db,ids,bed_idx=0)
        with pytest.raises(BizError) as err:
            reserve(db,ids,bed_idx=1)
        assert err.value.code=='REQUEST_ALREADY_ALLOCATED'
        assert str(db.get(Bed,ids[1][1]).status)=='AVAILABLE'


def test_database_generated_unique_request(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        req,beds,_=ids
        db.add_all([
            BedAllocation(admission_request_id=req, patient_id=1, bed_id=beds[0],
                          active_bed_id=beds[0],status=AllocationStatus.RESERVED,mode=AllocationMode.MANUAL),
            BedAllocation(admission_request_id=req, patient_id=1, bed_id=beds[1],
                          active_bed_id=beds[1],status=AllocationStatus.RESERVED,mode=AllocationMode.MANUAL),
        ])
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_reassign_atomic_success(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        old=reserve(db,ids,bed_idx=0)
        new=reassign_reserved_bed(db,allocation_id=old.id,new_bed_id=ids[1][1],
                                  reason='better location',operator=db.get(User,ids[2]))
        assert new.id!=old.id
        assert str(db.get(BedAllocation,old.id).status)=='CANCELLED'
        assert str(db.get(Bed,ids[1][0]).status)=='AVAILABLE'
        assert str(db.get(Bed,ids[1][1]).status)=='RESERVED'
        assert db.scalar(select(func.count(BedAllocation.id)))==2


def test_reassign_failure_old_remains(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        old=reserve(db,ids,bed_idx=0)
        target=db.get(Bed,ids[1][1]);target.gender_limit=GenderLimit.FEMALE;db.commit()
        with pytest.raises(BizError) as err:
            reassign_reserved_bed(db,allocation_id=old.id,new_bed_id=ids[1][1],
                                  reason='bad target',operator=db.get(User,ids[2]))
        assert err.value.code=='HARD_CONSTRAINT_VIOLATION'
        assert str(db.get(BedAllocation,old.id).status)=='RESERVED'
        assert str(db.get(Bed,ids[1][0]).status)=='RESERVED'
        assert db.scalar(select(func.count(BedAllocation.id)))==1


def test_admit_discharge_release(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        alloc=reserve(db,ids)
        admit_patient(db,allocation_id=alloc.id,operator=db.get(User,ids[2]))
        discharge_patient(db,allocation_id=alloc.id,operator=db.get(User,ids[2]))
        assert str(db.get(Bed,ids[1][0]).status)=='CLEANING'
        release_bed(db,bed_id=ids[1][0],operator=db.get(User,ids[2]))
        assert str(db.get(Bed,ids[1][0]).status)=='AVAILABLE'


def test_cancel_allows_new_bed(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        old=reserve(db,ids)
        cancel_allocation(db,allocation_id=old.id,operator=db.get(User,ids[2]))
        new=reserve(db,ids,bed_idx=1)
        assert new.id!=old.id


def test_pair_guard(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        alloc=reserve(db,ids)
        bed=db.get(Bed,ids[1][0]);bed.status=BedStatus.AVAILABLE;db.commit()
        with pytest.raises(BizError):
            admit_patient(db,allocation_id=alloc.id,operator=db.get(User,ids[2]))
        assert str(db.get(BedAllocation,alloc.id).status)=='RESERVED'


def test_mid_transaction_reassign_error_rolls_back_old_bed(case, monkeypatch):
    """Force failure AFTER old assignment is invalidated and flushed."""
    import app.services.allocation as svc
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        old=reserve(db,ids,bed_idx=0)
        actual_transition=svc._transition_bed
        def break_on_new_reservation(*args, **kwargs):
            if kwargs.get('reason','').startswith('人工换床从'):
                raise RuntimeError('injected failure after old allocation update')
            return actual_transition(*args,**kwargs)
        monkeypatch.setattr(svc,'_transition_bed',break_on_new_reservation)
        with pytest.raises(RuntimeError,match='injected failure'):
            svc.reassign_reserved_bed(db,allocation_id=old.id,new_bed_id=ids[1][1],
                                      reason='failure injection',operator=db.get(User,ids[2]))
        assert str(db.get(Bed,ids[1][0]).status)=='RESERVED'
        assert str(db.get(Bed,ids[1][1]).status)=='AVAILABLE'
        assert str(db.get(BedAllocation,old.id).status)=='RESERVED'
        assert db.scalar(select(func.count(BedAllocation.id)))==1
        assert db.scalar(select(func.count(BedStatusLog.id)))==1


def test_failed_request_does_not_consume_idempotency_key(case):
    eng,ids=case
    with Session(eng,expire_on_commit=False,autoflush=False) as db:
        db.get(Bed, ids[1][0]).status=BedStatus.MAINTENANCE
        db.commit()
        with pytest.raises(BizError):
            reserve(db,ids,key='retry-after-failure-0001')
        assert db.scalar(select(func.count(AllocationIdempotency.id)))==0
        db.get(Bed, ids[1][0]).status=BedStatus.AVAILABLE
        db.commit()
        new=reserve(db,ids,key='retry-after-failure-0001')
        assert new.id
