"""P1/P2 实际 ORM + 规则说明测试（SQLite only）。"""
from __future__ import annotations
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models import Base
from app.models.enums import BedStatus, BedType, Gender, GenderLimit, PatientPriority, AdmissionRequestStatus
from app.models.facility import Department, Ward, Bed
from app.models.patient import Patient
from app.models.user import Doctor
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedAllocation
from app.core.errors import BizError
from app.services.optimization_preview import preview
from app.services.assistant_explanation import explain, safe_payload
from app.schemas.assistant import EvidenceScore
from app.core.config import settings


@pytest.fixture
def synthetic(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'p1p2.db'}")
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as db:
        dept=Department(code='SIM',name='模拟内科',anchor_floor=1,anchor_x=0,anchor_y=0)
        patient=Patient(name='模拟患者甲', medical_record_no='SIM001',gender=Gender.FEMALE)
        db.add_all([dept,patient]);db.flush()
        ward=Ward(code='SIM-W',name='模拟一病房',department_id=dept.id,floor=1)
        doctor=Doctor(name='虚构医生',department_id=dept.id)
        db.add_all([ward,doctor]);db.flush()
        for i in range(3):
            db.add(Bed(code=f'BED-{i}',department_id=dept.id,ward_id=ward.id,
                       status=BedStatus.AVAILABLE,bed_type=BedType.NORMAL,
                       gender_limit=GenderLimit.ANY,is_isolation=False,
                       floor=1,position_x=i*7,daily_rate=100+i*10))
        requests=[]
        for i,p in enumerate((PatientPriority.CRITICAL,PatientPriority.NORMAL)):
            req=AdmissionRequest(certificate_no=f'SIM-CERT-{i}',patient_id=patient.id,
                                 doctor_id=doctor.id,department_id=dept.id,
                                 priority=p,isolation_required=False,
                                 status=AdmissionRequestStatus.PRE_ADMITTED)
            db.add(req);db.flush()
            db.add(Preadmission(admission_request_id=req.id,queue_no=f'SIM-Q-{i}',queue_sequence=i+1))
            requests.append(req.id)
        db.commit()
        yield db,requests
    engine.dispose()


def test_preview_is_readonly_and_uses_existing_score(synthetic):
    db, ids=synthetic
    result=preview(db,ids,solver='flow')
    assert result.preview_only and result.optimized.proven_optimal
    assert result.optimized.admitted==2
    assert result.admission_request_ids == sorted(ids)
    assert result.candidate_edges==6
    assert db.scalar(select(func.count(BedAllocation.id)))==0
    assert len({p.bed_id for p in result.optimized.pairs})==2


def test_preview_rejects_non_waiting(synthetic):
    db,ids=synthetic
    req=db.get(AdmissionRequest,ids[0]);req.status=AdmissionRequestStatus.ADMITTED
    db.commit()
    with pytest.raises(BizError) as exc:
        preview(db,ids,solver='flow')
    assert exc.value.status_code==409


def test_rule_explanation_truth_and_no_write(synthetic):
    db,ids=synthetic
    bed= db.scalars(select(Bed).order_by(Bed.id)).first()
    result=explain(db,ids[0],bed.id)
    assert result.real_ai is False and result.provider=='deterministic_rules'
    assert '非 AI' in result.message
    assert result.review_required and result.performed_allocation is False
    assert len(result.evidence)==5
    assert result.hard_constraints_passed
    assert db.scalar(select(func.count(BedAllocation.id)))==0


def test_no_ai_call_without_explicit_confirmation(synthetic):
    db,ids=synthetic
    bed=db.scalars(select(Bed)).first()
    with pytest.raises(BizError) as exc:
        explain(db,ids[0],bed.id,mode='llm')
    assert exc.value.status_code==403
    with pytest.raises(BizError):
        explain(db,ids[0],bed.id,mode='llm',confirm_external_call=True)


def test_excluded_bed_not_explained_as_recommended(synthetic):
    db,ids=synthetic
    bed=db.scalars(select(Bed)).first();bed.status=BedStatus.OCCUPIED;db.commit()
    with pytest.raises(BizError) as exc:
        explain(db,ids[0],bed.id)
    assert exc.value.status_code==409


def test_prompt_minimization_omits_sensitive_identifiers():
    payload=safe_payload(5,False,'NORMAL',87.5,[EvidenceScore(key='distance',raw_score=90,contribution=28.8)],[])
    blob=str(payload)
    assert '模拟患者甲' not in blob
    for field in ['name','diagnosis','medical_record_no','phone','bed_code','admission_request_id']:
        assert field not in payload


def test_deepseek_adapter_with_mocked_provider_only(synthetic, monkeypatch):
    """P4 replaces legacy generic provider and keeps this test network-free."""
    from app.services.deepseek_provider import DeepSeekResult
    import app.services.assistant_explanation as adapter
    db,ids=synthetic
    bed=db.scalars(select(Bed)).first()
    monkeypatch.setattr(settings,'DEEPSEEK_EXTERNAL_ENABLED',True)
    monkeypatch.setattr(settings,'DEEPSEEK_API_KEY','fake-test-token')
    payloads=[]
    def fake_generate(kind,payload):
        payloads.append(payload)
        assert kind=='bed'
        return DeepSeekResult('真实 DeepSeek 说明草稿',['仅供模拟'],
                              {'prompt_tokens':100,'completion_tokens':20},3.5,
                              'deepseek-flash',None)
    monkeypatch.setattr(adapter,'generate',fake_generate)
    resp=explain(db,ids[0],bed.id,mode='llm',confirm_external_call=True)
    assert resp.provider=='deepseek' and resp.real_ai and resp.externally_sent
    assert resp.input_tokens==100 and resp.model=='deepseek-flash' and resp.review_required
    blob=str(payloads[0])
    assert '模拟患者甲' not in blob and 'SIM-CERT' not in blob and 'BED-' not in blob

def test_new_paths_have_schemas():
    from app.main import app
    routes=app.openapi()['paths']
    assert '/api/v1/optimization/preview' in routes
    assert '/api/v1/assistant/explain' in routes


def test_global_plan_explanation_is_non_ai_and_readonly(synthetic):
    from app.services.assistant_explanation import explain_plan
    db,ids=synthetic
    out=explain_plan(db,ids)
    assert out.provider=='deterministic_rules' and not out.real_ai
    assert out.assigned_count==2 and out.preview_only
    assert db.scalar(select(func.count(BedAllocation.id)))==0


def test_explain_refuses_completed_request(synthetic):
    db, ids = synthetic
    req = db.get(AdmissionRequest, ids[0])
    req.status = AdmissionRequestStatus.COMPLETED
    db.commit()
    bed = db.scalars(select(Bed)).first()
    with pytest.raises(BizError) as exc:
        explain(db, ids[0], bed.id)
    assert exc.value.status_code == 409


def test_explain_refuses_already_allocated_request(synthetic):
    db, ids = synthetic
    req = db.get(AdmissionRequest, ids[0])
    bed = db.scalars(select(Bed)).first()
    db.add(BedAllocation(admission_request_id=req.id, patient_id=req.patient_id,
                         bed_id=bed.id, status=__import__('app.models.enums', fromlist=['AllocationStatus']).AllocationStatus.RESERVED,
                         active_bed_id=bed.id))
    db.commit()
    with pytest.raises(BizError) as exc:
        explain(db, ids[0], bed.id)
    assert exc.value.status_code == 409


def test_explain_does_not_truncate_valid_candidate_after_101(synthetic):
    # There are 107 eligible beds; the requested bed is deliberately outside top101.
    from app.services.recommendation import recommend_beds
    db, ids = synthetic
    first = db.scalars(select(Bed)).first()
    newest = None
    for i in range(104):
        newest = Bed(code=f'FAR-{i}', department_id=first.department_id,
                     ward_id=first.ward_id, status=BedStatus.AVAILABLE,
                     bed_type=BedType.NORMAL, gender_limit=GenderLimit.ANY,
                     is_isolation=False, floor=1, position_x=100 + i,
                     daily_rate=200)
        db.add(newest)
    db.commit()
    result = recommend_beds(db, db.get(AdmissionRequest, ids[0]), limit=101)
    assert all(item.bed_id != newest.id for item in result.recommendations)
    explained = explain(db, ids[0], newest.id)
    assert explained.hard_constraints_passed and explained.score >= 0


def test_preview_rejects_more_than_100_real_candidates_without_truncating(synthetic):
    # Silent top-k truncation would make a supposedly globally optimal solution
    # depend on an arbitrary candidate cutoff. Fail explicitly instead.
    db, ids = synthetic
    first = db.scalars(select(Bed)).first()
    for i in range(100):
        db.add(Bed(code=f'MANY-{i}', department_id=first.department_id,
                   ward_id=first.ward_id, status=BedStatus.AVAILABLE,
                   bed_type=BedType.NORMAL, gender_limit=GenderLimit.ANY,
                   is_isolation=False, floor=1, position_x=i, daily_rate=100))
    db.commit()
    with pytest.raises(BizError) as exc:
        preview(db, ids, solver='flow')
    assert exc.value.status_code == 422
    assert db.scalar(select(func.count(BedAllocation.id))) == 0


def test_deepseek_global_plan_only_gets_anonymous_aggregates(synthetic, monkeypatch):
    from app.services.deepseek_provider import DeepSeekResult
    import app.services.assistant_explanation as adapter
    db,ids=synthetic
    seen=[]
    def mock_llm(kind,payload):
        seen.append((kind,payload))
        return DeepSeekResult('调度汇总说明',['仅供演示'],
                              {'prompt_tokens':30,'completion_tokens':15},2.0,
                              'deepseek-flash',None)
    monkeypatch.setattr(adapter,'generate',mock_llm)
    with pytest.raises(BizError):
        adapter.explain_plan(db,ids,mode='llm',confirm_external_call=False)
    assert seen==[]
    output=adapter.explain_plan(db,ids,mode='llm',confirm_external_call=True)
    assert output.real_ai and output.provider=='deepseek' and output.review_required
    assert output.assigned_count==2 and len(seen)==1
    kind,payload=seen[0]
    assert kind=='plan'
    blob=str(payload)
    assert 'SIM-CERT' not in blob and 'admission_request_ids' not in blob
    assert 'bed_id' not in blob and 'patient' not in blob
    assert db.scalar(select(func.count(BedAllocation.id)))==0
