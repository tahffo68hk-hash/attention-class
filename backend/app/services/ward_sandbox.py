"""Read-only What-if optimizer using production H1-H4, score parts and exact flow engine.

Does not construct or commit BedAllocation, Patient, AdmissionRequest or AuditLog.
Only accepts typed fictional request descriptors, not real certificates/patient IDs.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from json import dumps
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.errors import BizError, ErrorCode
from app.models.facility import Bed, Department
from app.models.enums import PRIORITY_RANK
from app.services import bed_policy
from app.services.global_optimization import EdgeCandidate, greedy, optimize
from app.services import recommendation as score
from app.schemas.ward_sandbox import WardSandboxInput, WardSandboxOutput, SandboxCandidate, SandboxSolution, SandboxPair


def preview_sandbox(db: Session, request: WardSandboxInput) -> WardSandboxOutput:
    # Queries are read-only; no ORM objects are mutated, even in a test transaction.
    beds = list(db.execute(select(Bed).options(joinedload(Bed.ward), joinedload(Bed.department))
                           .where(Bed.retired_at.is_(None)).order_by(Bed.code, Bed.id)).unique().scalars())
    original_beds = list(beds)
    ids={b.id for b in beds}
    by_id={b.id:b for b in beds}
    # Production optimizer accepts only positive IDs. Virtual negative IDs are mapped
    # to private positive solver IDs, then translated BACK before returning data.
    # These IDs are never database primary keys and must never reach allocation APIs.
    surrogate_to_virtual={}
    surrogate=max(ids,default=0)+1
    for new_bed in request.synthetic_beds:
        template=by_id.get(new_bed.template_bed_id)
        if template is None or template.ward_id!=new_bed.ward_id:
            raise BizError(ErrorCode.VALIDATION_ERROR,'新增模拟床必须引用同病房的真实床模板',422)
        if any(b.code.lower()==new_bed.code.lower() for b in original_beds):
            raise BizError(ErrorCode.VALIDATION_ERROR,'模拟床号与真实床号冲突',422)
        copy=SimpleNamespace(
            id=surrogate,code=new_bed.code,status='AVAILABLE',department_id=template.department_id,
            ward_id=template.ward_id,is_isolation=template.is_isolation,
            gender_limit=template.gender_limit,bed_type=template.bed_type,
            floor=template.floor,position_x=template.position_x,position_y=template.position_y,
            daily_rate=template.daily_rate,ward=template.ward,department=template.department,
        )
        beds.append(copy)
        surrogate_to_virtual[surrogate]=new_bed.virtual_id
        surrogate+=1
    if any(i not in ids for i in request.unavailable_bed_ids):
        raise BizError(ErrorCode.VALIDATION_ERROR,'模拟禁用床位必须来自当前床位快照',422)
    dept_ids={r.department_id for r in request.synthetic_requests}
    depts={d.id:d for d in db.execute(select(Department).where(Department.id.in_(dept_ids))).scalars()}
    if dept_ids-set(depts):
        raise BizError(ErrorCode.VALIDATION_ERROR,'模拟患者所属科室不存在',422)
    if request.ward_supply_cut and request.ward_supply_cut.ward_id not in {b.ward_id for b in beds}:
        raise BizError(ErrorCode.VALIDATION_ERROR,'模拟病区不存在',422)
    disabled=set(request.unavailable_bed_ids)
    if request.ward_supply_cut:
        free=sorted((b for b in beds if b.ward_id==request.ward_supply_cut.ward_id
                     and str(b.status)=='AVAILABLE' and b.id not in disabled),key=lambda b:(b.code,b.id))
        if request.ward_supply_cut.count > len(free):
            raise BizError(ErrorCode.VALIDATION_ERROR,'病区可用床位不足，无法执行此供给削减假设',422)
        disabled.update(b.id for b in free[:request.ward_supply_cut.count])
    # Mutations below are on UNMAPPED ephemeral views, never on SQLAlchemy model instances.
    views={b.id:SimpleNamespace(
        id=b.id,code=b.code,status=('MAINTENANCE' if b.id in disabled else str(b.status)),
        department_id=b.department_id,ward_id=b.ward_id,is_isolation=b.is_isolation,
        gender_limit=b.gender_limit,bed_type=b.bed_type,floor=b.floor,
        position_x=b.position_x,position_y=b.position_y,daily_rate=b.daily_rate,
    ) for b in beds}
    totals=Counter(b.ward_id for b in beds)
    frees=Counter(b.ward_id for b in beds if views[b.id].status=='AVAILABLE')
    # Work with solver-safe positive IDs, but the API always exposes synthetic negative IDs.
    public_id=lambda identifier:surrogate_to_virtual.get(identifier,identifier)
    edges=[];candidates=[]
    for patient in sorted(request.synthetic_requests,key=lambda r:r.scenario_id):
        dept=depts[patient.department_id]
        valid=[]
        for b in beds:
            v=views[b.id]
            if not bed_policy.hard_constraint_violations(v,department_id=patient.department_id,
                   patient_gender=patient.gender,isolation_required=patient.isolation_required):
                valid.append(v)
        low=min((b.daily_rate for b in valid),default=Decimal('0'))
        high=max((b.daily_rate for b in valid),default=Decimal('0'))
        profile=score.PRIORITY_PROFILE[patient.priority]
        for bed in valid:
            distance=bed_policy.distance_to_department(bed,dept)
            parts={
              'distance':score._score_distance(distance,profile)[0],
              'priority_fit':score._score_priority_fit(bed,PRIORITY_RANK[patient.priority],patient.priority)[0],
              'ward_balance':score._score_ward_balance(frees[bed.ward_id],totals[bed.ward_id])[0],
              'cost':score._score_cost(bed.daily_rate,low,high,profile)[0],
              'preference':score._score_preference(bed,patient.preferred_ward_id)[0],
            }
            # Exact same rounding and weight rules as production recommend_beds.
            value=round(min(100,max(0,sum(round(v*score.WEIGHTS[k],4) for k,v in parts.items()))),2)
            candidates.append(SandboxCandidate(scenario_id=patient.scenario_id,bed_id=public_id(bed.id),bed_code=bed.code,
                  score=value,score_items={k:round(v,2) for k,v in parts.items()}))
            edges.append(EdgeCandidate(patient.scenario_id,bed.id,PRIORITY_RANK[patient.priority],value))
    if len(edges)>2000:
        raise BizError(ErrorCode.VALIDATION_ERROR,'模拟候选关系超过 2000，请减少模拟人数',422)
    scenario_ids=[r.scenario_id for r in request.synthetic_requests]
    try:
        base=greedy(edges,scenario_ids);best=optimize(edges,scenario_ids,backend='flow')
    except (ValueError,RuntimeError) as exc:
        raise BizError(ErrorCode.VALIDATION_ERROR,str(exc),422) from exc
    def serialize(solution):
        return SandboxSolution(method=solution.method,proven_optimal=solution.proven_optimal,
             admitted=solution.admitted,priority_sum=solution.priority_sum,score_sum=solution.score_sum,
             runtime_ms=solution.runtime_ms,pairs=[SandboxPair(scenario_id=p.request_id,bed_id=public_id(p.bed_id),
                  score=p.score,priority_rank=p.priority_rank) for p in solution.pairs],
             unmatched_scenario_ids=list(solution.unmatched_request_ids))
    # Fingerprint of snapshot inputs, for comparison; API does not claim concurrency-free validity.
    facts=[(public_id(b.id),b.code,str(b.status),b.ward_id,b.department_id,str(b.gender_limit),b.is_isolation,
            str(b.bed_type),b.floor,b.position_x,b.position_y,str(b.daily_rate)) for b in beds]
    fingerprint=sha256(dumps(facts,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    # Candidate edges use solver IDs and only the public return value uses virtual IDs.
    return WardSandboxOutput(snapshot_at=datetime.now(timezone.utc).isoformat(),snapshot_fingerprint=fingerprint,
          applied_unavailable_bed_ids=sorted(disabled),request_count=len(scenario_ids),candidate_count=len(edges),
          candidates=candidates,greedy=serialize(base),optimized=serialize(best))
