"""SQLite transaction/ORM+API tests; MySQL row-lock races must be retested in hospital_test."""
import pytest
from sqlalchemy import select,func
from fastapi.testclient import TestClient
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app
from app.core.errors import ConflictError,StateTransitionError,BizError
from app.models.enums import BedStatus,UserRole
from app.models.facility import Bed,BedSceneSlot,Department
from app.models.allocation import BedAllocation
from app.models.admission import AdmissionRequest
from app.models.audit import AuditLog
from app.services import ward_editor
from app.services.ward_sandbox import preview_sandbox
from app.schemas.ward_editor import ManagedBedCreate,ManagedBedPose
from app.schemas.ward_sandbox import WardSandboxInput
from test_ward_map import db


def payload(session,code='WM-NEW',slot=8):
    bed=session.scalar(select(Bed).where(Bed.status==BedStatus.AVAILABLE))
    return ManagedBedCreate(confirm=True,code=code,ward_id=bed.ward_id,scene_slot=slot,
        template_bed_id=bed.id,bed_type='NORMAL',gender_limit='ANY',daily_rate='0')


def test_create_stable_slot_and_idempotent_replay(db):
    _,session,_=db
    p=payload(session)
    before=session.scalar(select(func.count(Bed.id)))
    first=ward_editor.create_bed(session,p)
    second=ward_editor.create_bed(session,p)
    assert first.id==second.id
    assert session.scalar(select(func.count(Bed.id)))==before+1
    assert first.status==BedStatus.AVAILABLE and first.retired_at is None
    assert ward_editor.out(session,first)['scene_slot']==8
    assert first.position_x==session.get(Bed,p.template_bed_id).position_x
    assert first.position_y==session.get(Bed,p.template_bed_id).position_y
    with pytest.raises(ConflictError):ward_editor.create_bed(session,p.model_copy(update={'code':'WM-OTHER'}))


def test_archive_occupied_and_cleaning_denied(db):
    _,session,_=db
    for status in (BedStatus.OCCUPIED,BedStatus.RESERVED,BedStatus.CLEANING):
        bed=session.scalar(select(Bed).where(Bed.status==status))
        with pytest.raises(StateTransitionError):ward_editor.archive_bed(session,bed.id,'测试')
    assert session.scalar(select(func.count(BedAllocation.id)))==1


def test_archive_excludes_map_and_simulator_then_restore(db):
    from app.api.v1.ward_map import get_ward_map
    _,session,user=db
    p=payload(session);bed=ward_editor.create_bed(session,p);session.commit()
    assert len(get_ward_map(session,user).beds)==6
    ward_editor.archive_bed(session,bed.id,'示例停用');session.commit()
    assert len(get_ward_map(session,user).beds)==5
    dept=session.scalar(select(Department))
    req=WardSandboxInput(scenario_kind='SYNTHETIC_ONLY',synthetic_requests=[{'scenario_id':1,'department_id':dept.id}])
    sandbox=preview_sandbox(session,req)
    assert all(c.bed_id!=bed.id for c in sandbox.candidates)
    assert not bed.retired_at is None
    ward_editor.restore_bed(session,bed.id);session.commit()
    assert len(get_ward_map(session,user).beds)==6
    assert ward_editor.out(session,bed)['scene_slot']==8


def test_move_pose_conflict_and_policy(db):
    _,session,_=db
    p=payload(session);bed=ward_editor.create_bed(session,p)
    slot=session.scalar(select(BedSceneSlot).where(BedSceneSlot.bed_id==bed.id))
    original=session.get(Bed,p.template_bed_id)
    session.add(BedSceneSlot(bed_id=original.id,ward_id=original.ward_id,slot=0,rotation=0));session.flush()
    with pytest.raises(ConflictError):ward_editor.change_pose(session,bed.id,ManagedBedPose(confirm=True,ward_id=bed.ward_id,scene_slot=0,rotation=90))
    ward_editor.change_pose(session,bed.id,ManagedBedPose(confirm=True,ward_id=bed.ward_id,scene_slot=9,rotation=90))
    assert slot.slot==9 and slot.rotation==90
    assert bed.position_x==original.position_x


def test_synthetic_supply_uses_exact_solver_and_never_writes(db):
    _,session,_=db
    before=[session.scalar(select(func.count(x.id))) for x in (Bed,BedAllocation,AdmissionRequest,AuditLog)]
    bed=session.scalar(select(Bed).where(Bed.status==BedStatus.AVAILABLE))
    req=WardSandboxInput.model_validate({'scenario_kind':'SYNTHETIC_ONLY',
      'synthetic_requests':[{'scenario_id':1,'department_id':bed.department_id},
                            {'scenario_id':2,'department_id':bed.department_id}],
      'synthetic_beds':[{'virtual_id':-1,'template_bed_id':bed.id,'ward_id':bed.ward_id,'code':'SIM-01'}]})
    out=preview_sandbox(session,req)
    assert out.optimized.admitted==2 and out.optimized.proven_optimal
    assert any(x.bed_id==-1 for x in out.optimized.pairs)
    assert [session.scalar(select(func.count(x.id))) for x in (Bed,BedAllocation,AdmissionRequest,AuditLog)]==before
    assert not session.dirty and not session.new
    with pytest.raises(BizError):preview_sandbox(session,req.model_copy(update={'synthetic_beds':[
      req.synthetic_beds[0].model_copy(update={'ward_id':999})]}))


def test_admin_enforcement_no_unauthorized_write(db,monkeypatch):
    import app.api.deps as deps
    monkeypatch.setattr(deps,'record_audit_standalone',lambda **kw:None)
    _,session,user=db
    p=payload(session).model_dump(mode='json')
    def db_override():yield session
    app.dependency_overrides[get_db]=db_override
    try:
      with TestClient(app) as client:
        assert client.post('/api/v1/ward-map/managed-beds',json=p).status_code==401
        app.dependency_overrides[get_current_user]=lambda:user
        assert client.post('/api/v1/ward-map/managed-beds',json=p).status_code in (403,404)
        user.role=UserRole.ADMIN
        resp=client.post('/api/v1/ward-map/managed-beds',json=p)
        assert resp.status_code==201,resp.text
        assert resp.json()['scene_slot']==8
    finally:app.dependency_overrides.clear()
