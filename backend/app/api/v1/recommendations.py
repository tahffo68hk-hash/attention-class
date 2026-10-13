"""智能床位推荐接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, DbSession, client_ip, user_agent
from app.core.errors import NotFoundError
from app.models.admission import AdmissionRequest
from app.models.enums import AuditAction, AuditResult
from app.models.user import User
from app.schemas.recommendation import RecommendationResponse
from app.services.audit import record_audit
from app.services.recommendation import recommend_beds

router = APIRouter(prefix="/admission-requests", tags=["智能床位推荐"])


@router.get(
    "/{request_id}/bed-recommendations",
    response_model=RecommendationResponse,
    summary="获取床位推荐（硬约束过滤 + 可解释软约束评分）",
    description=(
        "先执行硬约束过滤（空闲 / 科室匹配 / 性别限制 / 隔离需求），"
        "再按「距离、优先级-床型适配、病房负载均衡、成本、期望病房」五项软约束打分排序。\n\n"
        "**优先级不是常数**：不同优先级会改变距离方向（危重越近越好、轻症让出近端）、"
        "床型适配矩阵与成本敏感度，因此同一床位对不同优先级患者得分不同。\n\n"
        "**隔离床策略**：隔离患者只能使用隔离床；隔离床只对隔离患者开放，"
        "空置时也不会进入非隔离患者的候选集。\n\n"
        "无合适床位时返回 `recommendations: []` 与 `no_result_reasons` 明确原因。"
    ),
)
def get_bed_recommendations(
    request_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    req = db.execute(
        select(AdmissionRequest)
        .options(
            joinedload(AdmissionRequest.patient),
            joinedload(AdmissionRequest.department),
            joinedload(AdmissionRequest.preadmission),
        )
        .where(AdmissionRequest.id == request_id)
    ).unique().scalar_one_or_none()
    if req is None:
        raise NotFoundError(f"住院证 #{request_id} 不存在")

    result = recommend_beds(db, req, limit=limit)

    record_audit(
        db,
        action=AuditAction.RECOMMEND.value,
        user=user,
        object_type="admission_request",
        object_id=req.id,
        result=AuditResult.SUCCESS,
        detail={
            "certificate_no": req.certificate_no,
            "candidates_evaluated": result.candidates_evaluated,
            "returned": len(result.recommendations),
            "top_bed": result.recommendations[0].bed_code if result.recommendations else None,
            "top_score": result.recommendations[0].score if result.recommendations else None,
        },
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return result
