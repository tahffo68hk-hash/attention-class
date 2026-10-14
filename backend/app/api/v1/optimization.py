"""P1 计算预览，不执行实际床位分配。"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from app.api.deps import DbSession, CurrentUser, require_roles
from app.models.enums import UserRole
from app.schemas.optimization import OptimizationPreviewIn, OptimizationPreviewOut
from app.services.optimization_preview import preview

router = APIRouter(prefix="/optimization", tags=["多患者联合排床（预览）"])

@router.post("/preview", response_model=OptimizationPreviewOut,
             dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
             summary="对同一批待入院患者比较贪心与全局优化（无写入）")
def preview_batch(payload: OptimizationPreviewIn, db: DbSession, user: CurrentUser):
    return preview(db, payload.admission_request_ids, solver=payload.solver)
