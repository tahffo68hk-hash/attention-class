"""P2 显式解释请求：默认规则说明，不进行自动外部调用。"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from app.api.deps import CurrentUser, DbSession, require_roles, client_ip, user_agent
from app.models.enums import UserRole, AuditAction, AuditResult
from app.services.audit import record_audit, record_audit_standalone
from app.core.errors import BizError
from app.services.assistant_explanation import explain
from app.schemas.assistant import ExplainIn, ExplainOut, PlanExplainOut, PlanExplainIn
from app.services.deepseek_provider import is_ready
from app.core.config import settings

router = APIRouter(prefix="/assistant", tags=["辅助解释（教学模拟）"])

@router.post("/explain", response_model=ExplainOut,
             dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
             summary="床位说明：默认确定性规则；真实 AI 须显式确认且服务端启用")
def explain_bed(payload: ExplainIn, request: Request, db: DbSession, user: CurrentUser):
    try:
        output = explain(db, payload.admission_request_id, payload.bed_id,
                         mode=payload.mode, confirm_external_call=payload.confirm_external_call)
    except BizError as exc:
        if payload.mode == "llm" and payload.confirm_external_call:
            record_audit_standalone(action="AI_EXPLANATION_REQUEST", user=user,
                object_type="admission_request", object_id=payload.admission_request_id,
                result=AuditResult.FAILURE,
                detail={"provider": "deepseek", "error_code": exc.code, "no_prompt_logged": True},
                ip=client_ip(request), user_agent=user_agent(request))
        raise
    if payload.mode == "llm":
        record_audit(db, action="AI_EXPLANATION_REQUEST", user=user,
                     object_type="admission_request", object_id=payload.admission_request_id,
                     result=AuditResult.SUCCESS,
                     detail={"mode": "llm", "provider": output.provider, "model": output.model,
                             "prompt_version": output.prompt_version, "tokens_in": output.input_tokens,
                             "tokens_out": output.output_tokens, "latency_ms": output.latency_ms,
                             "no_patient_data_in_prompt": True,
                             "cost_estimate_cny": output.cost_estimate_cny},
                     ip=client_ip(request), user_agent=user_agent(request))
        db.commit()
    return output

@router.get("/provider-status", dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
            summary="DeepSeek 配置状态（不回传密钥）")
def provider_status(user: CurrentUser):
    return {"provider": "deepseek", "model": settings.DEEPSEEK_MODEL,
            "enabled": is_ready(), "real_call_requires_confirmation": True,
            "default_mode": "rules", "no_live_call": True}


@router.post("/explain-plan", response_model=PlanExplainOut,
             dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
             summary="多患者方案解释：默认规则版，DeepSeek 须显式授权（无写入）")
def explain_global_plan(payload: PlanExplainIn, request: Request,
                        db: DbSession, user: CurrentUser):
    from app.services.assistant_explanation import explain_plan
    try:
        output = explain_plan(db, payload.admission_request_ids, mode=payload.mode,
                              confirm_external_call=payload.confirm_external_call)
    except BizError as exc:
        if payload.mode == "llm" and payload.confirm_external_call:
            record_audit_standalone(action="AI_PLAN_EXPLANATION_REQUEST", user=user,
                object_type="optimization_preview", object_id=None,
                result=AuditResult.FAILURE,
                detail={"provider": "deepseek", "error_code": exc.code,
                        "no_request_ids_logged": True},
                ip=client_ip(request), user_agent=user_agent(request))
        raise
    if payload.mode == "llm":
        record_audit(db, action="AI_PLAN_EXPLANATION_REQUEST", user=user,
                     object_type="optimization_preview", object_id=None,
                     result=AuditResult.SUCCESS,
                     detail={"provider": "deepseek", "model": output.model,
                             "prompt_version": output.prompt_version,
                             "tokens_in": output.input_tokens, "tokens_out": output.output_tokens,
                             "cost_estimate_cny": output.cost_estimate_cny,
                             "latency_ms": output.latency_ms, "aggregates_only": True},
                     ip=client_ip(request), user_agent=user_agent(request))
        db.commit()
    return output
