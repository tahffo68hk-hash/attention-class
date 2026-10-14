"""新病区三维态势 API 的真实 ORM / HTTP 用例；SQLite，不代表 MySQL 并发。"""
import json
from collections import Counter
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import pytest

from app.models import Base
from app.models.facility import Bed, Department, Ward
from app.models.patient import Patient
from app.models.user import User, Doctor
from app.models.allocation import BedAllocation
from app.models.admission import AdmissionRequest
from app.models.audit import AuditLog
from app.models.enums import (BedStatus, BedType, GenderLimit, Gender, UserRole,
                              PatientPriority, AdmissionRequestStatus, AllocationStatus, AllocationMode)
from app.api.v1.ward_map import get_ward_map
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app

@pytest.fixture
def db(tmp_path):
    eng=create_engine(f'sqlite:///{tmp_path / "wardmap.db"}')
    Base.metadata.create_all(eng)
    with Session(eng,expire_on_commit=False) as session:
        admin=User(username='ward_reader',full_name='虚构管理员',hashed_password='unused',role=UserRole.VIEWER)
        dept=Department(code='WM',name='模拟心内科')
        session.add_all([admin,dept]);session.flush()
        ward=Ward(code='WM-101',name='心内病区',department_id=dept.id,floor=3)
        session.add(ward);session.flush()
        for num,status in enumerate([BedStatus.AVAILABLE,BedStatus.RESERVED,BedStatus.OCCUPIED,
                                    BedStatus.CLEANING,BedStatus.MAINTENANCE],1):
            session.add(Bed(code=f'WM-{num:03}',ward_id=ward.id,department_id=dept.id,
                            bed_type=BedType.NORMAL,gender_limit=GenderLimit.ANY,
                            is_isolation=False,status=status,floor=3))
        patient=Patient(medical_record_no='MOCK-ONLY',name='张模拟',gender=Gender.FEMALE,
                        phone='18812349999')
        doc=Doctor(name='虚构医生',department_id=dept.id)
        session.add_all([patient,doc]);session.flush()
        request=AdmissionRequest(certificate_no='PRIVATE-CERT-001',patient_id=patient.id,
                                 department_id=dept.id,doctor_id=doc.id,priority=PatientPriority.SEVERE,
                                 diagnosis='TEST DIAGNOSIS NEVER LEAVE SERVER',status=AdmissionRequestStatus.PRE_ADMITTED)
        session.add(request);session.flush()
        beds=session.scalars(select(Bed).order_by(Bed.code)).all()
        session.add(BedAllocation(admission_request_id=request.id,patient_id=patient.id,bed_id=beds[2].id,
                                  active_bed_id=beds[2].id,status=AllocationStatus.ADMITTED,
                                  mode=AllocationMode.MANUAL))
        session.commit()
        yield eng,session,admin
    eng.dispose()


def test_api_snapshot_five_states_and_confirmed_patient_only(db):
    _,session,user=db
    result=get_ward_map(session,user)
    assert len(result.beds)==5 and len(result.rooms)==1
    assert result.layout_kind=='SIMULATED_GRID_V1'
    assert result.counts=={status.value:1 for status in BedStatus}
    occupied=next(b for b in result.beds if b.status=='OCCUPIED')
    assert occupied.patient is not None and occupied.patient.allocation_status=='ADMITTED'
    assert occupied.patient.priority=='SEVERE'
    assert occupied.patient.masked_name!='张模拟'
    reserved=next(b for b in result.beds if b.status=='RESERVED')
    assert reserved.patient is None and reserved.state_warning
    assert all(b.floor==3 for b in result.beds)
    serialized=result.model_dump_json()
    for secret in ['18812349999','PRIVATE-CERT-001','TEST DIAGNOSIS','MOCK-ONLY','张模拟']:
        assert secret not in serialized


def test_no_db_mutation_and_batched_queries(db):
    eng,session,user=db
    before=(session.scalar(select(func.count(Bed.id))),session.scalar(select(func.count(BedAllocation.id))),
            session.scalar(select(func.count(AuditLog.id))))
    statements=[]
    def capture(_conn,_cursor,statement,*args):
        if statement.strip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(eng,'before_cursor_execute',capture)
    try:
        result=get_ward_map(session,user)
    finally:event.remove(eng,'before_cursor_execute',capture)
    assert len(statements)==2,statements
    assert before==(session.scalar(select(func.count(Bed.id))),session.scalar(select(func.count(BedAllocation.id))),
                    session.scalar(select(func.count(AuditLog.id))))
    assert len(result.beds)==5


def test_large_bedlist_no_api_page_truncation(db):
    _,session,user=db
    original=session.scalars(select(Bed)).first()
    for i in range(210):
        session.add(Bed(code=f'X-{i:04}',ward_id=original.ward_id,department_id=original.department_id,
                        bed_type=BedType.NORMAL,gender_limit=GenderLimit.ANY,is_isolation=False,
                        status=BedStatus.AVAILABLE,floor=3))
    session.commit()
    result=get_ward_map(session,user)
    assert len(result.beds)==215
    assert result.rooms[0].bed_count==215
    assert len({(b.simulated_position.x,b.simulated_position.z) for b in result.beds})==215


def test_stable_layout_and_auth_required(db):
    _,session,user=db
    x=get_ward_map(session,user); y=get_ward_map(session,user)
    assert [(b.id,b.simulated_position) for b in x.beds]==[(b.id,b.simulated_position) for b in y.beds]
    def override_db(): yield session
    app.dependency_overrides[get_db]=override_db
    try:
        with TestClient(app) as client:
            response=client.get('/api/v1/ward-map')
            assert response.status_code==401
    finally:
        app.dependency_overrides.clear()


def test_authorized_get_is_readonly_http(db):
    _,session,user=db
    def override_db():
        yield session
    def override_user():
        return user
    app.dependency_overrides[get_db]=override_db
    app.dependency_overrides[get_current_user]=override_user
    try:
        with TestClient(app) as client:
            response=client.get('/api/v1/ward-map')
            assert response.status_code==200,response.text
            data=response.json()
            assert data['layout_kind']=='SIMULATED_GRID_V1'
            assert len(data['beds'])==5
            assert 'phone' not in response.text
            assert 'diagnosis' not in response.text
            assert response.headers['content-type'].startswith('application/json')
    finally:
        app.dependency_overrides.clear()

def test_multiple_floors_have_distinct_simulated_geometry(db):
    _,session,user=db
    base=session.scalars(select(Department)).first()
    room=Ward(code='WM-F4',name='模拟四楼病区',department_id=base.id,floor=4)
    session.add(room);session.flush()
    session.add(Bed(code='WM-F4-01',ward_id=room.id,department_id=base.id,
                    bed_type=BedType.NORMAL,gender_limit=GenderLimit.ANY,is_isolation=False,
                    status=BedStatus.AVAILABLE,floor=4))
    session.commit()
    data=get_ward_map(session,user)
    a=next(b for b in data.beds if b.floor==3)
    b=next(b for b in data.beds if b.floor==4)
    assert b.simulated_position.z > a.simulated_position.z
    assert len(data.rooms)==2


def test_inconsistent_bed_state_no_fabricated_patient(db):
    _,session,user=db
    bed=session.scalar(select(Bed).where(Bed.status==BedStatus.OCCUPIED))
    allocation=session.scalar(select(BedAllocation))
    allocation.status=AllocationStatus.DISCHARGED
    allocation.active_bed_id=None
    session.commit()
    result=get_ward_map(session,user)
    found=next(b for b in result.beds if b.id==bed.id)
    assert found.status=='OCCUPIED' and found.patient is None
    assert found.state_warning and '核对' in found.state_warning
