"""P3 integration checks, run ONLY on disposable MySQL `hospital_test`.

`tests/conftest.py` drops and recreates the entire test database. These tests
must never target the demonstration database `hospital`.
"""
from __future__ import annotations

from sqlalchemy import select, func

from app.db.session import get_engine, get_session_factory
from app.models.allocation import BedStatusLog
from app.models.audit import AuditLog
from app.models.facility import Bed
from tests.conftest import make_request


def test_p3_bed_status_logs_include_real_operator_and_code(client, ds, nurse_headers):
    assert get_engine().dialect.name == 'mysql'
    request_id = make_request(ds, patient_name='男患者甲', department_code='CARD', seq=131)
    bed_id = ds.bed('C-W1-01')
    saved = client.post('/api/v1/allocations', json={
        'admission_request_id': request_id, 'bed_id': bed_id,
    }, headers=nurse_headers)
    assert saved.status_code == 201, saved.text
    response = client.get(f'/api/v1/beds/{bed_id}/status-logs', headers=nurse_headers)
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row['bed_code'] == 'C-W1-01'
    assert row['operator_name'] == '王芳'
    assert row['from_status'] == 'AVAILABLE' and row['to_status'] == 'RESERVED'


def test_p3_manual_status_cannot_skip_allocation_flow(client, ds, nurse_headers, admin_headers):
    assert get_engine().dialect.name == 'mysql'
    request_id = make_request(ds, patient_name='男患者甲', department_code='CARD', seq=132)
    bed_id = ds.bed('C-W1-01')
    reserved = client.post('/api/v1/allocations', json={
        'admission_request_id': request_id, 'bed_id': bed_id,
    }, headers=nurse_headers)
    assert reserved.status_code == 201, reserved.text
    with get_session_factory()() as db:
        before_logs = db.scalar(select(func.count(BedStatusLog.id)).where(BedStatusLog.bed_id == bed_id))
    forbidden = client.post(f'/api/v1/beds/{bed_id}/status', json={
        'status': 'OCCUPIED', 'reason': '绕过入院流程',
    }, headers=admin_headers)
    assert forbidden.status_code == 409, forbidden.text
    assert forbidden.json()['code'] == 'ILLEGAL_STATE_TRANSITION'
    with get_session_factory()() as db:
        assert str(db.get(Bed, bed_id).status) == 'RESERVED'
        assert db.scalar(select(func.count(BedStatusLog.id)).where(BedStatusLog.bed_id == bed_id)) == before_logs


def test_p3_maintenance_status_audit_captures_old_state(client, ds, admin_headers):
    assert get_engine().dialect.name == 'mysql'
    bed_id = ds.bed('C-W1-01')
    response = client.post(f'/api/v1/beds/{bed_id}/status', json={
        'status': 'MAINTENANCE', 'reason': '例行检修',
    }, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'MAINTENANCE'
    with get_session_factory()() as db:
        logs = db.scalars(select(AuditLog).where(
            AuditLog.object_type == 'bed', AuditLog.object_id == str(bed_id),
        )).all()
        assert len(logs) == 1
        assert logs[0].detail['from'] == 'AVAILABLE'
        assert logs[0].detail['to'] == 'MAINTENANCE'


def test_p3_auto_solver_api_reports_exact_algorithm(client, ds, nurse_headers):
    assert get_engine().dialect.name == 'mysql'
    r1 = make_request(ds, patient_name='男患者甲', department_code='CARD', seq=133)
    r2 = make_request(ds, patient_name='男患者丙', department_code='CARD', seq=134)
    response = client.post('/api/v1/optimization/preview', json={
        'admission_request_ids': [r1, r2], 'solver': 'auto',
    }, headers=nurse_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['preview_only'] is True
    assert data['optimized']['method'] == 'exact_min_cost_flow'
    assert data['optimized']['proven_optimal'] is True
    assert data['optimized']['admitted'] >= data['baseline']['admitted']
