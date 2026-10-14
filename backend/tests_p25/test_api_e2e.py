"""SQLite-backed FastAPI TestClient journeys with real routes and ORM.

No MySQL or external API is called. Real MySQL concurrency is a separate gate.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from tests_m1_local.test_m1_sequential import case
from app.main import app
from app.api import deps
from app.db.session import get_db
from app.models.enums import UserRole, BedStatus, AllocationStatus
from app.models.user import User
from app.models.facility import Bed
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.audit import AuditLog
from app.services.audit import record_audit


@pytest.fixture
def api_env(case, monkeypatch):
    engine, ids = case
    user_id = ids[2]
    def local_db():
        with Session(engine, expire_on_commit=False, autoflush=False) as s:
            yield s
    def local_user():
        with Session(engine,expire_on_commit=False) as s:
            user=s.get(User,user_id)
            s.expunge(user)
            return user
    def denied_audit(**kwargs):
        with Session(engine) as s:
            record_audit(s,**kwargs)
            s.commit()
    app.dependency_overrides[get_db]=local_db
    app.dependency_overrides[deps.get_current_user]=local_user
    monkeypatch.setattr(deps,'record_audit_standalone',denied_audit)
    try:
        with TestClient(app) as client:
            yield client,engine,ids
    finally:
        app.dependency_overrides.clear()


def test_rest_business_journey_and_history(api_env):
    client,engine,(request_id,beds,user_id)=api_env
    first=client.post('/api/v1/allocations',json={'admission_request_id':request_id,'bed_id':beds[0]},
                      headers={'Idempotency-Key':'p25-api-journey-0001'})
    assert first.status_code==201,first.text
    alloc=first.json()['id']
    replay=client.post('/api/v1/allocations',json={'admission_request_id':request_id,'bed_id':beds[0]},
                       headers={'Idempotency-Key':'p25-api-journey-0001'})
    assert replay.status_code==201 and replay.json()['id']==alloc
    conflict=client.post('/api/v1/allocations',json={'admission_request_id':request_id,'bed_id':beds[1]},
                         headers={'Idempotency-Key':'p25-api-journey-0001'})
    assert conflict.status_code==409 and conflict.json()['code']=='IDEMPOTENCY_KEY_CONFLICT'
    moved=client.post(f'/api/v1/allocations/{alloc}/reassign',
                      json={'new_bed_id':beds[1],'reason':'模拟病房调整'})
    assert moved.status_code==201,moved.text
    new_id=moved.json()['id']
    admitted=client.post(f'/api/v1/allocations/{new_id}/admit')
    assert admitted.status_code==200,admitted.text
    discharged=client.post(f'/api/v1/allocations/{new_id}/discharge',json={'reason':'模拟出院'})
    assert discharged.status_code==200,discharged.text
    with Session(engine) as db:
        assert str(db.get(Bed,beds[1]).status)==BedStatus.CLEANING.value
    released=client.post(f'/api/v1/beds/{beds[1]}/release')
    assert released.status_code==200,released.text
    with Session(engine) as db:
        assert str(db.get(Bed,beds[1]).status)==BedStatus.AVAILABLE.value
        assert db.scalar(select(func.count(BedAllocation.id)))==2
        assert db.scalar(select(func.count(BedAllocation.id)).where(
            BedAllocation.status.in_([AllocationStatus.RESERVED,AllocationStatus.ADMITTED])))==0
        assert db.scalar(select(func.count(BedStatusLog.id)))==6
        assert db.scalar(select(func.count(AuditLog.id))) >= 5


def test_api_bad_input_does_not_write(api_env):
    client,engine,(request_id,beds,_)=api_env
    response=client.post('/api/v1/allocations',json={'admission_request_id':request_id,'bed_id':-1})
    assert response.status_code in (404,422),response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count(BedAllocation.id)))==0


def test_api_no_request_and_unauthorized_role_leaves_audit(api_env):
    client,engine,(request_id,beds,operator_id)=api_env
    with Session(engine) as db:
        user=db.get(User,operator_id)
        user.role=UserRole.VIEWER
        db.commit()
    response=client.post('/api/v1/allocations',json={'admission_request_id':request_id,'bed_id':beds[0]})
    assert response.status_code==403,response.text
    assert response.json()['code']=='PERMISSION_DENIED'
    with Session(engine) as db:
        assert db.scalar(select(func.count(BedAllocation.id)))==0
        assert db.scalar(select(func.count(AuditLog.id))) >= 1


def test_optimization_and_explanation_api_are_readonly(api_env):
    client,engine,(request_id,beds,_)=api_env
    optimization=client.post('/api/v1/optimization/preview',json={
        'admission_request_ids':[request_id],'solver':'flow'})
    assert optimization.status_code==200,optimization.text
    assert optimization.json()['preview_only'] is True
    explained=client.post('/api/v1/assistant/explain',json={
        'admission_request_id':request_id,'bed_id':beds[0]})
    assert explained.status_code==200,explained.text
    assert explained.json()['real_ai'] is False
    with Session(engine) as db:
        assert db.scalar(select(func.count(BedAllocation.id)))==0
