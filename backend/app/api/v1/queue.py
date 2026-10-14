"""待入院队列接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.models.admission import AdmissionRequest, Preadmission
from app.models.enums import AdmissionRequestStatus, PatientPriority
from app.schemas.admission import PreadmissionRead
from app.schemas.common import Page
from app.services.serializers import preadmission_read

router = APIRouter(prefix="/preadmissions", tags=["待入院队列"])


@router.get(
    "",
    response_model=Page[PreadmissionRead],
    summary="待入院队列（五级优先级优先，同级登记顺序）",
    description="已完成预入院登记、尚未入住的住院证构成待入院队列；"
    "可用 priority 参数筛选特定优先级。",
)
def list_queue(
    db: DbSession,
    user: CurrentUser,
    department_id: int | None = None,
    priority: str | None = None,
    isolation_required: bool | None = None,
    pending_only: bool = Query(True, description="仅显示仍在等待床位的患者"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = (
        select(Preadmission)
        .join(AdmissionRequest, AdmissionRequest.id == Preadmission.admission_request_id)
        .options(
            joinedload(Preadmission.admission_request).joinedload(AdmissionRequest.patient),
            joinedload(Preadmission.admission_request).joinedload(AdmissionRequest.department),
        )
    )
    if pending_only:
        stmt = stmt.where(AdmissionRequest.status == AdmissionRequestStatus.PRE_ADMITTED)
    if department_id:
        stmt = stmt.where(AdmissionRequest.department_id == department_id)
    if priority:
        stmt = stmt.where(AdmissionRequest.priority == priority)
    if isolation_required is not None:
        stmt = stmt.where(AdmissionRequest.isolation_required == isolation_required)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(
                case(
                    (AdmissionRequest.priority == PatientPriority.CRITICAL, 5),
                    (AdmissionRequest.priority == PatientPriority.SEVERE, 4),
                    (AdmissionRequest.priority == PatientPriority.URGENT, 3),
                    (AdmissionRequest.priority == PatientPriority.NORMAL, 2),
                    (AdmissionRequest.priority == PatientPriority.MILD, 1),
                    else_=0,
                ).desc(),
                Preadmission.queue_sequence.asc(),
                Preadmission.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .scalars()
    )
    return Page[PreadmissionRead](
        items=[preadmission_read(p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
