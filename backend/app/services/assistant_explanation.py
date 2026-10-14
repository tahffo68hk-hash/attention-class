"""P2 辅助决策说明。

RULES 输出完全确定性，明确不是真实 AI。
LLM 输出是可选的、用户显式确认后才允许的 OpenAI-compatible 调用；默认关闭。
外发最小化：不发送姓名、住院证号、诊断、手机号、床位号、自由文本。
LLM 不能给出结构化硬约束结论，也不能触发任何写操作。
"""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BizError, ErrorCode, NotFoundError
from app.models.admission import AdmissionRequest
from app.models.allocation import BedAllocation
from app.models.enums import AdmissionRequestStatus, AllocationStatus
from app.schemas.assistant import EvidenceScore, ExplainOut
from app.services.recommendation import recommend_beds
from app.services.deepseek_provider import generate, PROMPT_VERSION


def safe_payload(priority_rank: int, is_isolation: bool, bed_type: str, score: float,
                 evidence: list[EvidenceScore], warnings: list[str]) -> dict:
    """Only categorical/numeric data leave the server. No identifiers or free text."""
    return {
        "priority_rank": priority_rank,
        "requires_isolation": is_isolation,
        "bed_type": bed_type,
        "final_score": score,
        "score_dimensions": [e.model_dump() for e in evidence],
        "warning_count": len(warnings),
        "scope": "fictional teaching prototype, not medical advice",
    }



def explain(db: Session, request_id: int, bed_id: int, *, mode: str = "rules", confirm_external_call: bool = False) -> ExplainOut:
    req = db.execute(select(AdmissionRequest).options(
        joinedload(AdmissionRequest.patient), joinedload(AdmissionRequest.department),
        joinedload(AdmissionRequest.preferred_ward), joinedload(AdmissionRequest.preadmission),
    ).where(AdmissionRequest.id == request_id)).unique().scalar_one_or_none()
    if req is None:
        raise NotFoundError(f"住院证 #{request_id} 不存在")
    if mode not in ("rules", "llm"):
        raise BizError(ErrorCode.VALIDATION_ERROR, "未知解释模式", 422)
    if mode == "llm" and not confirm_external_call:
        raise BizError(ErrorCode.PERMISSION_DENIED, "调用真实模型前必须单独确认外部调用", 403)
    # A recommendation explanation must not make an already admitted, cancelled
    # or discharged request appear to be eligible for a new allocation.
    active = db.execute(select(BedAllocation.id).where(
        BedAllocation.admission_request_id == request_id,
        BedAllocation.status.in_([AllocationStatus.RESERVED, AllocationStatus.ADMITTED]),
    ).limit(1)).scalar_one_or_none()
    if (req.status != AdmissionRequestStatus.PRE_ADMITTED
            or req.preadmission is None or active is not None):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION,
                       "住院证当前不是未分配的待入院状态，不能生成正向床位推荐解释", 409)
    # All existing H1-H4 and five-dimensional scores are reused verbatim.
    # Do not truncate the candidate list: a valid bed outside the first 101
    # would otherwise receive a false hard-constraint violation.
    recommended = recommend_beds(db, req, limit=None)
    item = next((b for b in recommended.recommendations if b.bed_id == bed_id), None)
    if item is None:
        raise BizError(ErrorCode.HARD_CONSTRAINT_VIOLATION,
                       "床位不在当前合格候选中，无法生成正向推荐说明", 409)
    evidence = [EvidenceScore(key=e.key, raw_score=e.raw_score, contribution=e.contribution)
                for e in item.score_items]
    ordered = sorted(item.score_items, key=lambda e: -e.contribution)
    explanation = (
        f"该床位通过科室、性别、隔离与空闲状态四项硬约束，综合评分 {item.score:.2f}/100。"
        f"主要得分来自{ordered[0].label}（贡献 {ordered[0].contribution:.2f} 分）和"
        f"{ordered[1].label}（贡献 {ordered[1].contribution:.2f} 分）。"
        "该结果是模拟资源分配评分，不代表临床适宜性或实际医疗建议。"
    )
    cautions = ["需由有权限的管理人员核查实际床位情况并确认", "推荐仅供教学模拟，确认时须重新校验硬约束"]
    latency = None
    usage: dict = {}
    model = None
    cost_cny = None
    if mode == "llm":
        payload = safe_payload(recommended.priority_rank, req.isolation_required,
                               item.bed_type, item.score, evidence, item.warnings)
        ai = generate("bed", payload)
        explanation, usage, latency, model, cost_cny = (
            ai.explanation, ai.usage, ai.latency_ms, ai.model, ai.cost_estimate_cny)
        cautions.extend(ai.cautions)
        cautions.insert(0, "以下文字由真实大模型生成，未经独立事实核验，不得作为临床决策依据")
    return ExplainOut(
        provider="deterministic_rules" if mode == "rules" else "deepseek",
        model=model,
        real_ai=mode == "llm", externally_sent=mode == "llm",
        status="RULES_ONLY" if mode == "rules" else "AI_DRAFT_REVIEW_REQUIRED",
        message="规则生成（非 AI）" if mode == "rules" else "真实 AI 草稿，须人工核对",
        explanation=explanation, cautions=cautions,
        hard_constraints_passed=True, score=item.score, evidence=evidence,
        warnings=item.warnings, prompt_version=None if mode == "rules" else PROMPT_VERSION,
        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
        cost_usd=None, cost_estimate_cny=cost_cny, latency_ms=latency,
    )


def explain_plan(db: Session, request_ids: list[int], *, mode: str = "rules",
                 confirm_external_call: bool = False):
    """P2 global explanation: one immutable read-only optimizer snapshot.

    DeepSeek sees *only aggregated numeric results*; never admission IDs,
    patient names, free text, bed IDs or raw pairs.
    """
    from app.schemas.assistant import PlanExplainOut
    from app.services.optimization_preview import preview
    if mode not in ("rules", "llm"):
        raise BizError(ErrorCode.VALIDATION_ERROR, "未知解释模式", 422)
    if mode == "llm" and not confirm_external_call:
        raise BizError(ErrorCode.PERMISSION_DENIED, "必须单独确认本次 DeepSeek 调用", 403)
    plan = preview(db, request_ids, solver="auto")
    matched = plan.optimized.admitted
    total = plan.request_count
    gain = plan.admitted_gain
    explanation = (
        f"在当前虚构病床快照下，共分析 {total} 个待入院申请与 {plan.candidate_edges} 条合规候选关系。"
        f"贪心方案安排 {plan.baseline.admitted} 人，联合优化方案安排 {matched} 人"
        f"（增加 {gain} 人）。本算法按成功人数、优先级总和、原五维适配评分依次优化。"
        "所有候选先通过科室、性别、隔离及床位空闲状态过滤。"
    )
    recommendations = ["正式床位分配必须由人工确认，确认时重新校验数据库状态",
                       "优化结果不代表临床收治决策，不应跳过业务审核"]
    if plan.optimized.unmatched_request_ids:
        recommendations.append(f"仍有 {len(plan.optimized.unmatched_request_ids)} 个住院申请未获得合格床位，须继续排队或由管理员检查资源")
    result_kwargs = {}
    if mode == "llm":
        evidence = {
            "kind": "aggregate_bed_allocation_preview",
            "fictional_teaching_only": True,
            "request_count": total,
            "candidate_edges": plan.candidate_edges,
            "greedy": {"admitted": plan.baseline.admitted, "priority_sum": plan.baseline.priority_sum,
                       "score_sum": plan.baseline.score_sum},
            "optimized": {"admitted": matched, "priority_sum": plan.optimized.priority_sum,
                          "score_sum": plan.optimized.score_sum,
                          "method": plan.optimized.method,
                          "proven_optimal": plan.optimized.proven_optimal},
            "admitted_gain": gain,
        }
        ai = generate("plan", evidence)
        explanation = ai.explanation
        recommendations.extend(ai.cautions)
        recommendations.insert(0, "DeepSeek 生成内容仅为待审核草稿，不能替代确定性求解或人工审批")
        result_kwargs = dict(provider="deepseek", real_ai=True, externally_sent=True,
                             status="AI_DRAFT_REVIEW_REQUIRED", model=ai.model,
                             prompt_version=PROMPT_VERSION,
                             input_tokens=ai.usage.get("prompt_tokens"),
                             output_tokens=ai.usage.get("completion_tokens"),
                             cost_estimate_cny=ai.cost_estimate_cny,
                             latency_ms=ai.latency_ms)
    return PlanExplainOut(explanation=explanation, recommendations=recommendations,
                          assigned_count=matched, unmatched_request_ids=plan.optimized.unmatched_request_ids,
                          baseline_assigned_count=plan.baseline.admitted, **result_kwargs)
