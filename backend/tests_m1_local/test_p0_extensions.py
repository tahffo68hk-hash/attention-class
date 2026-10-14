"""SQLite-only tests for additive API changes; NOT a MySQL concurrency test."""
from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from app.api.v1.allocations import bed_status_logs
from app.api.v1.queue import list_queue
from app.api.v1.admissions import list_requests
from app.api.v1.audit import list_audit_logs
from app.models import Base
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedStatusLog
from app.models.audit import AuditLog
from app.models.enums import (AdmissionRequestStatus, BedStatus, PatientPriority,
    Gender, GenderLimit, BedType, UserRole, AuditResult)
from app.models.facility import Department, Ward, Bed
from app.models.patient import Patient
from app.models.user import User, Doctor


@pytest.fixture
def data(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'extension.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        d=Department(code='TEST',name='模拟科室',anchor_floor=1,anchor_x=0,anchor_y=0)
        u=User(username='sim-admin',full_name='模拟管理员',hashed_password='unused',role=UserRole.ADMIN)
        p=Patient(name='模拟患者甲',medical_record_no='FAKE-001',gender=Gender.FEMALE)
        db.add_all([d,u,p]);db.flush()
        doctor=Doctor(name='医生乙',department_id=d.id)
        room=Ward(code='W1',name='模拟病房',department_id=d.id,floor=1)
        db.add_all([doctor,room]);db.flush()
        bed=Bed(code='B-01',ward_id=room.id,department_id=d.id,bed_type=BedType.NORMAL,
                gender_limit=GenderLimit.ANY,is_isolation=False,status=BedStatus.CLEANING)
        db.add(bed);db.flush()
        db.add(BedStatusLog(bed_id=bed.id,operator_id=u.id,from_status=BedStatus.OCCUPIED,
                            to_status=BedStatus.CLEANING,reason='模拟出院'))
        priorities=[PatientPriority.MILD,PatientPriority.CRITICAL,PatientPriority.NORMAL,
                    PatientPriority.SEVERE,PatientPriority.URGENT]
        for i,priority in enumerate(priorities):
            req=AdmissionRequest(certificate_no=f'ZY-TEST-{i}',patient_id=p.id,department_id=d.id,
                  doctor_id=doctor.id,status=AdmissionRequestStatus.PRE_ADMITTED,
                  priority=priority,isolation_required=False)
            db.add(req);db.flush()
            db.add(Preadmission(admission_request_id=req.id,queue_no=f'Q-TEST-{i}',queue_sequence=i+1))
        now=datetime.now()
        db.add_all([
            AuditLog(username='sim-admin',user_id=u.id,role='ADMIN',action='A',result=AuditResult.SUCCESS,created_at=now-timedelta(days=8)),
            AuditLog(username='sim-admin',user_id=u.id,role='ADMIN',action='B',result=AuditResult.SUCCESS,created_at=now),
        ])
        db.commit()
        yield db, bed.id, u
    engine.dispose()


def test_bed_log_includes_bed_code_and_operator(data):
    db,bed_id,user=data
    logs=bed_status_logs(bed_id,db,user,limit=20)
    assert len(logs)==1
    assert logs[0].bed_code=='B-01'
    assert logs[0].operator_name=='模拟管理员'
    assert logs[0].to_status=='CLEANING'


def test_queue_priority_order(data):
    db,_,user=data
    page=list_queue(db,user,page=1,page_size=30,pending_only=True)
    assert [x.priority for x in page.items]==['CRITICAL','SEVERE','URGENT','NORMAL','MILD']


def test_request_search_by_patient_name(data):
    db,_,user=data
    page=list_requests(db,user,keyword='模拟患者甲',page=1,page_size=30)
    assert page.total==5
    assert all(x.patient_name is not None and x.patient_name != '模拟患者甲' for x in page.items)  # 输出仍必须脱敏


def test_audit_time_window(data):
    db,_,_=data
    start=datetime.now()-timedelta(days=1)
    page=list_audit_logs(db,start_at=start,page=1,page_size=50)
    assert page.total==1
    assert page.items[0].action=='B'


def test_audit_invalid_window(data):
    db,_,_=data
    # 项目统一错误契约（{code,message,detail,request_id}）要求抛 BizError，而非 FastAPI HTTPException。
    from app.core.errors import BizError, ErrorCode
    with pytest.raises(BizError) as exc:
        list_audit_logs(db,start_at=datetime.now(),end_at=datetime.now()-timedelta(days=1),page=1,page_size=50)
    assert exc.value.status_code==422
    assert exc.value.code==ErrorCode.VALIDATION_ERROR
