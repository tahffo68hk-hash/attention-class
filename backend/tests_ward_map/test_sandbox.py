"""Sandbox must compute from production rules without ever writing business rows."""
import pytest
from sqlalchemy import select,func
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.api.v1.ward_sandbox import simulate
from app.services.ward_sandbox import preview_sandbox
from app.schemas.ward_sandbox import WardSandboxInput
from app.models.facility import Bed,Department
from app.models.allocation import BedAllocation
from app.models.admission import AdmissionRequest
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.api.deps import get_current_user
from app.db.session import get_db
from app.main import app
from test_ward_map import db


def request(dept,**kw):
 return WardSandboxInput.model_validate({'scenario_kind':'SYNTHETIC_ONLY',
       'synthetic_requests':[{'scenario_id':1,'department_id':dept,'gender':'FEMALE',**kw}]})

def test_sandbox_real_hard_rules_and_no_business_writes(db):
 _,session,_=db
 dept=session.scalar(select(Department)).id
 initial=tuple(session.scalar(select(func.count(model.id))) for model in (Bed,BedAllocation,AdmissionRequest,AuditLog))
 result=preview_sandbox(session,request(dept))
 assert result.scenario_kind=='SYNTHETIC_ONLY' and result.no_database_writes is True
 assert result.request_count==1 and result.candidate_count==1
 assert result.optimized.admitted==1 and result.optimized.proven_optimal
 assert result.optimized.method=='exact_min_cost_flow'
 assert result.candidates[0].score_items.keys()=={'distance','priority_fit','ward_balance','cost','preference'}
 assert initial==tuple(session.scalar(select(func.count(model.id))) for model in (Bed,BedAllocation,AdmissionRequest,AuditLog))
 assert not session.dirty and not session.new


def test_whatif_cut_changes_matches_and_is_repeatable(db):
 _,session,_=db
 dept=session.scalar(select(Department)).id
 bed=session.scalar(select(Bed).where(Bed.status=='AVAILABLE'))
 before=preview_sandbox(session,request(dept))
 cut=preview_sandbox(session,request(dept,**{}).model_copy(update={'unavailable_bed_ids':[bed.id]}))
 assert before.optimized.admitted==1 and cut.optimized.admitted==0
 assert cut.applied_unavailable_bed_ids==[bed.id]
 assert preview_sandbox(session,request(dept)).snapshot_fingerprint==before.snapshot_fingerprint
 assert session.get(Bed,bed.id).status=='AVAILABLE'


def test_policy_gender_isolation_and_two_scenarios(db):
 _,session,_=db
 dept=session.scalar(select(Department)).id
 payload=WardSandboxInput(scenario_kind='SYNTHETIC_ONLY',synthetic_requests=[
    {'scenario_id':1,'department_id':dept,'gender':'MALE','priority':'CRITICAL'},
    {'scenario_id':2,'department_id':dept,'gender':'FEMALE','isolation_required':True}])
 result=preview_sandbox(session,payload)
 assert result.optimized.admitted==1 and result.optimized.priority_sum==5
 assert result.optimized.unmatched_scenario_ids==[2]
 assert result.greedy.admitted==result.optimized.admitted


def test_invalid_payload_rejected(db):
 _,session,_=db
 with pytest.raises(ValidationError):WardSandboxInput(scenario_kind='SYNTHETIC_ONLY',synthetic_requests=[{'scenario_id':1,'department_id':1},{'scenario_id':1,'department_id':1}])
 with pytest.raises(ValidationError):WardSandboxInput(scenario_kind='SYNTHETIC_ONLY',synthetic_requests=[])


def test_http_requires_auth_and_role(db,monkeypatch):
 import app.api.deps as deps
 monkeypatch.setattr(deps,'record_audit_standalone',lambda **kwargs:None)
 _,session,user=db
 payload={'scenario_kind':'SYNTHETIC_ONLY','synthetic_requests':[{'scenario_id':1,'department_id':1}]}
 def override_db():yield session
 app.dependency_overrides[get_db]=override_db
 try:
  with TestClient(app) as client:
   assert client.post('/api/v1/ward-map/simulate',json=payload).status_code==401
   app.dependency_overrides[get_current_user]=lambda:user
   assert client.post('/api/v1/ward-map/simulate',json=payload).status_code in (403,404)
   user.role=UserRole.ADMIN
   answer=client.post('/api/v1/ward-map/simulate',json=payload)
   assert answer.status_code==200,answer.text
   assert answer.json()['no_database_writes'] is True
 finally:app.dependency_overrides.clear()


def test_sandbox_score_parity_with_production_recommendation(db):
 """No alternative scoring logic: identical request and bed snapshot => identical scores."""
 from types import SimpleNamespace
 from app.services.recommendation import recommend_beds
 _,session,_=db
 dept=session.scalar(select(Department))
 request_obj=SimpleNamespace(id=919191,certificate_no='FICTIONAL-ONLY',patient_id=989898,department_id=dept.id,department=dept,
  priority='NORMAL',isolation_required=False,preferred_ward_id=None,
  patient=SimpleNamespace(gender='FEMALE',name='合成'))
 actual=recommend_beds(session,request_obj,limit=None)
 sandbox=preview_sandbox(session,request(dept.id))
 assert [(x.bed_id,x.score) for x in sandbox.candidates]==[(x.bed_id,x.score) for x in actual.recommendations]


def test_ward_supply_cut_and_unknown_bed_rejection(db):
 from app.core.errors import BizError
 _,session,_=db
 dept=session.scalar(select(Department))
 bed=session.scalar(select(Bed).where(Bed.status=='AVAILABLE'))
 scenario=WardSandboxInput.model_validate({'scenario_kind':'SYNTHETIC_ONLY',
    'synthetic_requests':[{'scenario_id':1,'department_id':dept.id}],
    'ward_supply_cut':{'ward_id':bed.ward_id,'count':1}})
 result=preview_sandbox(session,scenario)
 assert bed.id in result.applied_unavailable_bed_ids and result.optimized.admitted==0
 with pytest.raises(BizError):
  preview_sandbox(session,WardSandboxInput.model_validate({'scenario_kind':'SYNTHETIC_ONLY',
   'synthetic_requests':[{'scenario_id':1,'department_id':dept.id}], 'unavailable_bed_ids':[99999]}))


def test_fictional_request_rejects_personal_data_fields():
 with pytest.raises(ValidationError):
  WardSandboxInput.model_validate({'scenario_kind':'SYNTHETIC_ONLY',
   'synthetic_requests':[{'scenario_id':1,'department_id':1,'name':'张三','diagnosis':'secret'}]})
