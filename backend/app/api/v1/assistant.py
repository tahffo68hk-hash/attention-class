"""P2 显式解释请求：默认规则说明，不进行自动外部调用。"""
from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from app.api.deps import CurrentUser, DbSession, require_roles, client_ip, user_agent
from app.models.enums import UserRole, AuditAction, AuditResult
from app.services.audit import record_audit
from app.services.assistant_explanation import explain
from app.schemas.assistant import ExplainIn, ExplainOut, PlanExplainOut
from app.schemas.optimization import OptimizationPreviewIn

router = APIRouter(prefix="/assistant", tags=["辅助解释（教学模拟）"])

@router.post("/explain", response_model=ExplainOut,
             dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
             summary="床位说明：默认确定性规则；真实 AI 须显式确认且服务端启用")
def explain_bed(payload: ExplainIn, request: Request, db: DbSession, user: CurrentUser):
    output = explain(db, payload.admission_request_id, payload.bed_id,
                     mode=payload.mode, confirm_external_call=payload.confirm_external_call)
    if payload.mode == "llm":
        record_audit(db, action="AI_EXPLANATION_REQUEST", user=user,
                     object_type="admission_request", object_id=payload.admission_request_id,
                     result=AuditResult.SUCCESS,
                     detail={"mode": "llm", "provider": output.provider, "model": output.model,
                             "prompt_version": output.prompt_version, "tokens_in": output.input_tokens,
                             "tokens_out": output.output_tokens, "latency_ms": output.latency_ms,
                             "no_patient_data_in_prompt": True},
                     ip=client_ip(request), user_agent=user_agent(request))
        db.commit()
    return output

@router.post("/explain-plan", response_model=PlanExplainOut,
             dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
             summary="多患者联合调度结果说明（确定性规则、非 AI、无写入）")
def explain_global_plan(payload: OptimizationPreviewIn,
                        db: DbSession, user: CurrentUser):
    from app.services.assistant_explanation import explain_plan
    return explain_plan(db, payload.admission_request_ids)
