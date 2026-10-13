"""审计日志接口（仅管理员）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require_roles
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.schemas.common import Page
from app.schemas.dashboard import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["安全与审计"])


@router.get(
    "",
    response_model=Page[AuditLogRead],
    summary="审计日志查询（仅管理员）",
    description="记录关键操作的操作人、时间、对象、动作与结果。",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def list_audit_logs(
    db: DbSession,
    username: str | None = None,
    action: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    result: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(AuditLog)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    if result:
        stmt = stmt.where(AuditLog.result == result)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        ).scalars()
    )
    return Page[AuditLogRead](
        items=[AuditLogRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
