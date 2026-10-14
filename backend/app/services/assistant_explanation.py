"""P2 辅助决策说明。

RULES 输出完全确定性，明确不是真实 AI。
LLM 输出是可选的、用户显式确认后才允许的 OpenAI-compatible 调用；默认关闭。
外发最小化：不发送姓名、住院证号、诊断、手机号、床位号、自由文本。
LLM 不能给出结构化硬约束结论，也不能触发任何写操作。
"""
from __future__ import annotations
import json
from time import perf_counter
from urllib.parse import urlparse
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import BizError, ErrorCode, NotFoundError
from app.models.admission import AdmissionRequest
from app.models.allocation import BedAllocation
from app.models.enums import AdmissionRequestStatus, AllocationStatus
from app.schemas.assistant import EvidenceScore, ExplainOut
from app.services.recommendation import recommend_beds
from app.core.config import settings

PROMPT_VERSION = "bed-explanation-safe-v1"


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


def _external_explain(payload: dict) -> tuple[str, list[str], dict, float]:
    if not settings.ASSISTANT_EXTERNAL_ENABLED or not settings.ASSISTANT_API_KEY or not settings.ASSISTANT_MODEL:
        raise BizError(ErrorCode.PERMISSION_DENIED, "真实 AI 服务尚未启用或未配置", 403)
    url = settings.ASSISTANT_ENDPOINT
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise BizError(ErrorCode.VALIDATION_ERROR, "外部模型地址必须为 HTTPS", 422)
    system = (
        "你是教学原型的解释工具，不提供临床建议，也不决定实际床位分配。"
        "只能根据输入的评分维度解释结果，不得杜撰诊断、患者身份、医院规定、疗效、医疗建议。"
        "仅输出 JSON: {\"explanation\":\"...\",\"cautions\":[\"...\"]}，解释不超过200字。"
    )
    started = perf_counter()
    try:
        with httpx.Client(timeout=12.0, follow_redirects=False) as client:
            result = client.post(url,
                headers={"Authorization": f"Bearer {settings.ASSISTANT_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": settings.ASSISTANT_MODEL, "temperature": 0,
                      "max_tokens": 300, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]},
            )
            result.raise_for_status()
            envelope = result.json()
            content = envelope["choices"][0]["message"]["content"]
            data = json.loads(content)
            explanation = data["explanation"]
            cautions = data.get("cautions", [])
            if not isinstance(explanation, str) or not 1 <= len(explanation) <= 500:
                raise ValueError("模型解释缺失或过长")
            if not isinstance(cautions, list) or len(cautions) > 5 or not all(isinstance(c, str) and len(c) <= 200 for c in cautions):
                raise ValueError("模型注意事项格式错误")
            return explanation, cautions, envelope.get("usage", {}), round((perf_counter() - started) * 1000, 2)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        # Do not echo URL, credentials, headers, or raw provider content.
        raise BizError(ErrorCode.INTERNAL_ERROR, "外部模型调用或响应校验失败，请使用规则解释", 502) from exc


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
    if mode == "llm" and not settings.ASSISTANT_EXTERNAL_ENABLED:
        raise BizError(ErrorCode.PERMISSION_DENIED, "真实 AI 服务未授权启用", 403)
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
    if mode == "llm":
        payload = safe_payload(recommended.priority_rank, req.isolation_required,
                               item.bed_type, item.score, evidence, item.warnings)
        explanation, model_cautions, usage, latency = _external_explain(payload)
        cautions.extend(model_cautions)
        cautions.insert(0, "以下文字由真实大模型生成，未经独立事实核验，不得作为临床决策依据")
    return ExplainOut(
        provider="deterministic_rules" if mode == "rules" else "openai_compatible",
        model=None if mode == "rules" else settings.ASSISTANT_MODEL,
        real_ai=mode == "llm", externally_sent=mode == "llm",
        status="RULES_ONLY" if mode == "rules" else "AI_DRAFT_REVIEW_REQUIRED",
        message="规则生成（非 AI）" if mode == "rules" else "真实 AI 草稿，须人工核对",
        explanation=explanation, cautions=cautions,
        hard_constraints_passed=True, score=item.score, evidence=evidence,
        warnings=item.warnings, prompt_version=None if mode == "rules" else PROMPT_VERSION,
        input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
        cost_usd=None, latency_ms=latency,
    )


def explain_plan(db: Session, request_ids: list[int]):
    """P2 多患者方案的非 AI 确定性解释；复算同一 P1 优化快照。"""
    from app.schemas.assistant import PlanExplainOut
    from app.services.optimization_preview import preview
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
    recommendations = ["正式床位分配必须由人工确认，确认时重新校验数据库状态", "优化结果不代表临床收治决策，不应跳过业务审核"]
    if plan.optimized.unmatched_request_ids:
        recommendations.append(f"仍有 {len(plan.optimized.unmatched_request_ids)} 个住院申请未获得合格床位，须继续排队或由管理员检查资源")
    return PlanExplainOut(explanation=explanation, recommendations=recommendations,
                          assigned_count=matched, unmatched_request_ids=plan.optimized.unmatched_request_ids,
                          baseline_assigned_count=plan.baseline.admitted)
