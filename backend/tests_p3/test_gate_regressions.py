"""P3 targeted regressions; isolated SQLite checks, NOT the MySQL concurrency gate."""
from __future__ import annotations

import pytest
from fastapi import Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.v1.allocations import bed_status_logs
from app.api.v1.base_data import set_bed_status
from app.core.errors import NotFoundError, StateTransitionError
from app.models import Base
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.audit import AuditLog
from app.models.enums import (
    AllocationStatus, BedStatus, BedType, GenderLimit, UserRole,
)
from app.models.facility import Bed, Department, Ward
from app.models.user import User
from app.schemas.facility import BedStatusUpdate
from app.services.global_optimization import EdgeCandidate, optimize


@pytest.fixture
def fixture_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p3_regressions.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        dept = Department(code='P3', name='模拟内科', anchor_floor=1, anchor_x=0, anchor_y=0)
        user = User(username='operator_p3', full_name='模拟管理员甲',
                    hashed_password='unused', role=UserRole.ADMIN)
        db.add_all([dept, user])
        db.flush()
        ward = Ward(code='P3-W1', name='模拟病区', department_id=dept.id, floor=1)
        db.add(ward)
        db.flush()
        bed = Bed(code='P3-W1-01', department_id=dept.id, ward_id=ward.id,
                  bed_type=BedType.NORMAL, gender_limit=GenderLimit.ANY,
                  is_isolation=False, status=BedStatus.AVAILABLE)
        db.add(bed)
        db.commit()
        yield db, bed, user
    engine.dispose()


def _req():
    return Request({'type': 'http', 'method': 'PATCH', 'path': '/api/v1/beds/1/status',
                    'headers': [], 'client': ('127.0.0.1', 12345), 'scheme': 'http'})


def test_g1_operator_and_bed_code_are_real(fixture_db):
    db, bed, user = fixture_db
    db.add(BedStatusLog(bed_id=bed.id, from_status=BedStatus.AVAILABLE,
                        to_status=BedStatus.MAINTENANCE, operator_id=user.id,
                        reason='模拟操作'))
    db.commit()
    out = bed_status_logs(bed.id, db, user, limit=10)
    assert len(out) == 1
    assert out[0].bed_code == 'P3-W1-01'
    assert out[0].operator_name == '模拟管理员甲'
    assert out[0].from_status == 'AVAILABLE' and out[0].to_status == 'MAINTENANCE'


def test_g1_historical_missing_operator_is_not_falsely_assigned_to_system(fixture_db):
    db, bed, user = fixture_db
    db.add(BedStatusLog(bed_id=bed.id, from_status=BedStatus.OCCUPIED,
                        to_status=BedStatus.CLEANING, operator_id=None))
    db.commit()
    log = bed_status_logs(bed.id, db, user, limit=10)[0]
    assert log.bed_code == 'P3-W1-01'
    assert log.operator_name == '未记录（历史）'


def test_g1_nonexistent_bed_returns_404(fixture_db):
    db, bed, user = fixture_db
    with pytest.raises(NotFoundError) as exc:
        bed_status_logs(999999, db, user, limit=10)
    assert exc.value.status_code == 404


def test_manual_maintenance_transition_audit_preserves_actual_from_status(fixture_db):
    db, bed, user = fixture_db
    result = set_bed_status(bed.id, BedStatusUpdate(status='MAINTENANCE', reason='计划维护'),
                            _req(), db, user)
    assert result.status == 'MAINTENANCE'
    entry = db.scalars(select(AuditLog).where(AuditLog.object_type == 'bed')).one()
    assert entry.detail['from'] == 'AVAILABLE'
    assert entry.detail['to'] == 'MAINTENANCE'
    logs = db.scalars(select(BedStatusLog)).all()
    assert len(logs) == 1 and str(logs[0].from_status) == 'AVAILABLE'


@pytest.mark.parametrize('start,target', [
    (BedStatus.AVAILABLE, 'RESERVED'),
    (BedStatus.RESERVED, 'OCCUPIED'),
    (BedStatus.OCCUPIED, 'CLEANING'),
    (BedStatus.CLEANING, 'AVAILABLE'),
    (BedStatus.CLEANING, 'MAINTENANCE'),
    (BedStatus.RESERVED, 'AVAILABLE'),
])
def test_manual_api_cannot_bypass_allocation_lifecycle(fixture_db, start, target):
    db, bed, user = fixture_db
    bed.status = start
    db.commit()
    with pytest.raises(StateTransitionError) as exc:
        set_bed_status(bed.id, BedStatusUpdate(status=target, reason='误操作'),
                       _req(), db, user)
    assert exc.value.status_code == 409
    assert str(db.get(Bed, bed.id).status) == str(start)
    assert db.scalar(select(func.count(BedStatusLog.id))) == 0
    assert db.scalar(select(func.count(AuditLog.id))) == 0


def test_manual_maintenance_refuses_bed_with_active_allocation(fixture_db):
    db, bed, user = fixture_db
    # This is intentionally an inconsistent data fixture: fail closed rather than
    # allowing maintenance to hide a live allocation.
    # Avoid inserting an invalid allocation: mock the DB's active-allocation result
    # through an equivalent minimal test of the guard in a separate scenario.
    from app.models.patient import Patient
    from app.models.user import Doctor
    from app.models.admission import AdmissionRequest
    from app.models.enums import Gender, PatientPriority, AdmissionRequestStatus, AllocationMode
    patient = Patient(name='虚构患者', medical_record_no='P3-001', gender=Gender.MALE)
    doctor = Doctor(name='模拟医生', department_id=bed.department_id)
    db.add_all([patient, doctor]); db.flush()
    admission = AdmissionRequest(certificate_no='P3-CERT-01', patient_id=patient.id,
                                 department_id=bed.department_id, doctor_id=doctor.id,
                                 priority=PatientPriority.NORMAL,
                                 status=AdmissionRequestStatus.PRE_ADMITTED, isolation_required=False)
    db.add(admission); db.flush()
    db.add(BedAllocation(admission_request_id=admission.id, patient_id=patient.id,
                         bed_id=bed.id, active_bed_id=bed.id, status=AllocationStatus.RESERVED,
                         mode=AllocationMode.MANUAL))
    db.commit()
    with pytest.raises(StateTransitionError) as exc:
        set_bed_status(bed.id, BedStatusUpdate(status='MAINTENANCE'), _req(), db, user)
    assert exc.value.status_code == 409
    assert str(db.get(Bed, bed.id).status) == 'AVAILABLE'
    assert db.scalar(select(func.count(AuditLog.id))) == 0


def test_solver_auto_contract_is_exact_not_heuristic():
    edges = [EdgeCandidate(1, 10, 5, 99), EdgeCandidate(1, 20, 5, 98),
             EdgeCandidate(2, 10, 1, 97)]
    answer = optimize(edges, [1, 2], backend='auto')
    assert answer.method == 'exact_min_cost_flow'
    assert answer.proven_optimal is True
    assert answer.admitted == 2
    assert {(p.request_id, p.bed_id) for p in answer.pairs} == {(1, 20), (2, 10)}
