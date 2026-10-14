"""床位分配接口：预占用 / 入住 / 出院 / 释放 / 取消。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles, user_agent
from app.models.admission import AdmissionRequest
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.enums import AllocationStatus, UserRole
from app.models.facility import Bed
from app.models.user import User
from app.models.patient import Patient
from app.schemas.allocation import (
    AllocationCreate,
    AllocationRead,
    BedStatusLogRead,
    CancelRequest,
    DischargeRequest,
    ReassignRequest,
)
from app.schemas.common import Page
from app.services import allocation as allocation_service
from app.services.serializers import allocation_read

router = APIRouter(prefix="/allocations", tags=["床位分配"])

ALLOCATION_OPERATOR_ROLES = (UserRole.NURSE, UserRole.ADMIN)


@router.get("", response_model=Page[AllocationRead], summary="分配记录列表（支持筛选）")
def list_allocations(
    db: DbSession,
    user: CurrentUser,
    status: str | None = None,
    department_id: int | None = None,
    bed_id: int | None = None,
    patient_id: int | None = None,
    mode: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = (
        select(BedAllocation)
        .options(
            joinedload(BedAllocation.bed).joinedload(Bed.ward),
            joinedload(BedAllocation.patient),
            joinedload(BedAllocation.operator),
            joinedload(BedAllocation.admission_request).joinedload(AdmissionRequest.department),
        )
    )
    if status:
        stmt = stmt.where(BedAllocation.status == status)
    if bed_id:
        stmt = stmt.where(BedAllocation.bed_id == bed_id)
    if patient_id:
        stmt = stmt.where(BedAllocation.patient_id == patient_id)
    if mode:
        stmt = stmt.where(BedAllocation.mode == mode)
    if department_id:
        stmt = stmt.where(
            BedAllocation.admission_request_id.in_(
                select(AdmissionRequest.id).where(AdmissionRequest.department_id == department_id)
            )
        )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(BedAllocation.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .scalars()
    )
    return Page[AllocationRead](
        items=[allocation_read(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{allocation_id}", response_model=AllocationRead, summary="分配记录详情")
def get_allocation_detail(allocation_id: int, db: DbSession, user: CurrentUser):
    return allocation_read(allocation_service.get_allocation(db, allocation_id))


@router.post(
    "",
    response_model=AllocationRead,
    status_code=201,
    summary="预占用床位（采纳推荐或人工选择，护士 / 管理员）",
    description=(
        "**采纳推荐**：不传 bed_id，系统取推荐排序第一名。\n\n"
        "**人工选择**：传 bed_id，系统仍会执行全部硬约束校验，"
        "不满足时返回 422 `HARD_CONSTRAINT_VIOLATION` 并列出具体违反项。\n\n"
        "**并发安全**：使用 `SELECT ... FOR UPDATE` 行级锁 + `active_bed_id` 唯一索引双重保护，"
        "同一床位被并发抢用时会稳定返回 409。"
    ),
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def create_allocation(
    payload: AllocationCreate, request: Request, db: DbSession, user: CurrentUser,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", min_length=8, max_length=128),
):
    alloc = allocation_service.reserve_bed(
        db,
        request_id=payload.admission_request_id,
        bed_id=payload.bed_id,
        operator=user,
        confirm_top_recommendation=payload.confirm_top_recommendation,
        note=payload.note,
        idempotency_key=idempotency_key,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return allocation_read(alloc)


@router.post(
    "/{allocation_id}/reassign",
    response_model=AllocationRead,
    status_code=201,
    summary="原子人工换床（旧预占释放 + 新床预占，在同一事务）",
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def reassign(
    allocation_id: int, payload: ReassignRequest, request: Request, db: DbSession, user: CurrentUser
):
    alloc = allocation_service.reassign_reserved_bed(
        db, allocation_id=allocation_id, new_bed_id=payload.new_bed_id,
        reason=payload.reason, operator=user, ip=client_ip(request), user_agent=user_agent(request),
    )
    return allocation_read(alloc)


@router.post(
    "/{allocation_id}/admit",
    response_model=AllocationRead,
    summary="办理入住（预占用 -> 已入住）",
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def admit(allocation_id: int, request: Request, db: DbSession, user: CurrentUser):
    alloc = allocation_service.admit_patient(
        db, allocation_id=allocation_id, operator=user, ip=client_ip(request), user_agent=user_agent(request)
    )
    return allocation_read(alloc)


@router.post(
    "/{allocation_id}/discharge",
    response_model=AllocationRead,
    summary="办理出院（已入住 -> 已出院，床位转清洁中）",
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def discharge(
    allocation_id: int, payload: DischargeRequest, request: Request, db: DbSession, user: CurrentUser
):
    alloc = allocation_service.discharge_patient(
        db,
        allocation_id=allocation_id,
        operator=user,
        reason=payload.reason,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return allocation_read(alloc)


@router.post(
    "/{allocation_id}/cancel",
    response_model=AllocationRead,
    summary="取消预占用（预占用 -> 已取消，床位回到空闲）",
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def cancel(
    allocation_id: int, payload: CancelRequest, request: Request, db: DbSession, user: CurrentUser
):
    alloc = allocation_service.cancel_allocation(
        db,
        allocation_id=allocation_id,
        operator=user,
        reason=payload.reason,
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    return allocation_read(alloc)


# --------------------------------------------------------------------------- #
# 床位释放（清洁中 -> 空闲）
# --------------------------------------------------------------------------- #
beds_release_router = APIRouter(prefix="/beds", tags=["床位分配"])


@beds_release_router.post(
    "/{bed_id}/release",
    summary="床位释放（清洁中 -> 空闲）",
    dependencies=[Depends(require_roles(*ALLOCATION_OPERATOR_ROLES))],
)
def release(
    bed_id: int,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    reason: str | None = Query(None, description="释放说明"),
):
    bed = allocation_service.release_bed(
        db, bed_id=bed_id, operator=user, reason=reason,
        ip=client_ip(request), user_agent=user_agent(request),
    )
    from app.services.serializers import bed_read

    return bed_read(bed)


@beds_release_router.get(
    "/{bed_id}/status-logs",
    response_model=list[BedStatusLogRead],
    summary="床位状态流水（每次状态变化都留痕）",
)
def bed_status_logs(bed_id: int, db: DbSession, user: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    # 直接关联床位与操作者，修复 G1：原 API 总是返回 null。
    rows = db.execute(
        select(BedStatusLog, Bed.code, User.full_name)
        .join(Bed, Bed.id == BedStatusLog.bed_id)
        .outerjoin(User, User.id == BedStatusLog.operator_id)
        .where(BedStatusLog.bed_id == bed_id)
        .order_by(BedStatusLog.id.desc())
        .limit(limit)
    ).all()
    return [
        BedStatusLogRead(
            id=log.id,
            bed_id=log.bed_id,
            bed_code=bed_code,
            from_status=str(log.from_status) if log.from_status else None,
            to_status=str(log.to_status),
            reason=log.reason,
            allocation_id=log.allocation_id,
            admission_request_id=log.admission_request_id,
            operator_name=operator_name or "系统操作",
            created_at=log.created_at,
        )
        for log, bed_code, operator_name in rows
    ]
