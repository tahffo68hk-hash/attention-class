"""住院证与预入院登记接口。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles, user_agent
from app.core.errors import ConflictError, NotFoundError
from app.models.admission import AdmissionRequest, Preadmission
from app.models.enums import (
    ADMISSION_REQUEST_STATUS_LABEL,
    PRIORITY_LABEL,
    AdmissionRequestStatus,
    AuditAction,
    AuditResult,
    DepositStatus,
    PatientPriority,
    UserRole,
)
from app.models.facility import Department, Ward
from app.models.patient import Patient
from app.models.user import Doctor, User
from app.schemas.admission import (
    AdmissionRequestCreate,
    AdmissionRequestRead,
    PreadmissionCreate,
    PreadmissionRead,
)
from app.schemas.common import MessageOut, Page
from app.services.allocation import assert_request_transition
from app.services.audit import record_audit
from app.services.serializers import admission_request_read, preadmission_read

router = APIRouter(prefix="/admission-requests", tags=["住院证 / 预入院"])


def _next_certificate_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ZY{today}"
    count = db.execute(
        select(func.count(AdmissionRequest.id)).where(AdmissionRequest.certificate_no.like(f"{prefix}%"))
    ).scalar_one()
    return f"{prefix}{count + 1:04d}"


def _next_queue_no(db: Session) -> tuple[str, int]:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"Q{today}"
    seq = db.execute(
        select(func.count(Preadmission.id)).where(Preadmission.queue_no.like(f"{prefix}%"))
    ).scalar_one() + 1
    return f"{prefix}{seq:04d}", seq


def _load_request(db: Session, request_id: int) -> AdmissionRequest:
    req = db.execute(
        select(AdmissionRequest)
        .options(
            joinedload(AdmissionRequest.patient),
            joinedload(AdmissionRequest.department),
            joinedload(AdmissionRequest.doctor),
            joinedload(AdmissionRequest.preadmission),
            joinedload(AdmissionRequest.preferred_ward),
        )
        .where(AdmissionRequest.id == request_id)
    ).unique().scalar_one_or_none()
    if req is None:
        raise NotFoundError(f"住院证 #{request_id} 不存在")
    return req


@router.get("", response_model=Page[AdmissionRequestRead], summary="住院证列表")
def list_requests(
    db: DbSession,
    user: CurrentUser,
    department_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    isolation_required: bool | None = None,
    patient_id: int | None = None,
    keyword: str | None = Query(None, description="按住院证编号模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(AdmissionRequest).options(
        joinedload(AdmissionRequest.patient),
        joinedload(AdmissionRequest.department),
        joinedload(AdmissionRequest.doctor),
        joinedload(AdmissionRequest.preadmission),
        joinedload(AdmissionRequest.preferred_ward),
    )
    if department_id:
        stmt = stmt.where(AdmissionRequest.department_id == department_id)
    if status:
        stmt = stmt.where(AdmissionRequest.status == status)
    if priority:
        stmt = stmt.where(AdmissionRequest.priority == priority)
    if isolation_required is not None:
        stmt = stmt.where(AdmissionRequest.isolation_required == isolation_required)
    if patient_id:
        stmt = stmt.where(AdmissionRequest.patient_id == patient_id)
    if keyword:
        stmt = stmt.where(AdmissionRequest.certificate_no.like(f"%{keyword}%"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(AdmissionRequest.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .scalars()
    )
    return Page[AdmissionRequestRead](
        items=[admission_request_read(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{request_id}", response_model=AdmissionRequestRead, summary="住院证详情")
def get_request_detail(request_id: int, db: DbSession, user: CurrentUser):
    return admission_request_read(_load_request(db, request_id))


@router.post(
    "",
    response_model=AdmissionRequestRead,
    status_code=201,
    summary="开具住院证（医生 / 管理员）",
    description="记录患者、收治科室、隔离需求与病情优先级；issue=true 时直接开具。",
    dependencies=[Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN))],
)
def create_request(
    payload: AdmissionRequestCreate, request: Request, db: DbSession, user: CurrentUser
):
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise NotFoundError(f"患者 #{payload.patient_id} 不存在")
    dept = db.get(Department, payload.department_id)
    if dept is None:
        raise NotFoundError(f"科室 #{payload.department_id} 不存在")
    if payload.preferred_ward_id is not None:
        ward = db.get(Ward, payload.preferred_ward_id)
        if ward is None:
            raise NotFoundError(f"病房 #{payload.preferred_ward_id} 不存在")

    doctor_id = payload.doctor_id
    if doctor_id is None:
        doctor = db.execute(select(Doctor).where(Doctor.user_id == user.id)).scalar_one_or_none()
        if doctor is None:
            raise ConflictError(
                message="当前账号未关联医生档案，请显式指定 doctor_id",
                detail={"user_id": user.id},
            )
        doctor_id = doctor.id
    elif db.get(Doctor, doctor_id) is None:
        raise NotFoundError(f"医生 #{doctor_id} 不存在")

    priority = PatientPriority(payload.priority)
    status = AdmissionRequestStatus.ISSUED if payload.issue else AdmissionRequestStatus.DRAFT

    obj = AdmissionRequest(
        certificate_no=_next_certificate_no(db),
        patient_id=payload.patient_id,
        department_id=payload.department_id,
        doctor_id=doctor_id,
        priority=priority,
        isolation_required=payload.isolation_required,
        infection_type=payload.infection_type,
        diagnosis=payload.diagnosis,
        preferred_ward_id=payload.preferred_ward_id,
        notes=payload.notes,
        status=status,
        issued_at=datetime.now() if payload.issue else None,
    )
    db.add(obj)
    db.flush()
    record_audit(
        db,
        action=AuditAction.ISSUE_CERTIFICATE.value if payload.issue else AuditAction.CREATE.value,
        user=user,
        object_type="admission_request",
        object_id=obj.id,
        detail={
            "certificate_no": obj.certificate_no,
            "patient_id": obj.patient_id,
            "department_id": obj.department_id,
            "priority": priority.value,
            "priority_label": PRIORITY_LABEL.get(priority.value),
            "isolation_required": obj.isolation_required,
            "status": status.value,
        },
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return admission_request_read(_load_request(db, obj.id))


@router.post(
    "/{request_id}/issue",
    response_model=AdmissionRequestRead,
    summary="开具草稿住院证（医生 / 管理员）",
    dependencies=[Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN))],
)
def issue_request(request_id: int, request: Request, db: DbSession, user: CurrentUser):
    obj = _load_request(db, request_id)
    assert_request_transition(obj, AdmissionRequestStatus.ISSUED)
    obj.status = AdmissionRequestStatus.ISSUED
    obj.issued_at = datetime.now()
    record_audit(
        db,
        action=AuditAction.ISSUE_CERTIFICATE.value,
        user=user,
        object_type="admission_request",
        object_id=obj.id,
        detail={"certificate_no": obj.certificate_no},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return admission_request_read(_load_request(db, request_id))


@router.post(
    "/{request_id}/cancel",
    response_model=AdmissionRequestRead,
    summary="取消住院证（医生 / 管理员）",
    dependencies=[Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN))],
)
def cancel_request(request_id: int, request: Request, db: DbSession, user: CurrentUser):
    obj = _load_request(db, request_id)
    assert_request_transition(obj, AdmissionRequestStatus.CANCELLED)
    obj.status = AdmissionRequestStatus.CANCELLED
    record_audit(
        db,
        action=AuditAction.UPDATE.value,
        user=user,
        object_type="admission_request",
        object_id=obj.id,
        detail={"certificate_no": obj.certificate_no, "new_status": "CANCELLED"},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return admission_request_read(_load_request(db, request_id))


@router.post(
    "/{request_id}/preadmission",
    response_model=PreadmissionRead,
    status_code=201,
    summary="预入院登记（护士 / 医生 / 管理员）",
    description="登记补充信息并模拟缴纳预交金，登记后住院证进入「待入院」队列。不接入真实支付。",
    dependencies=[Depends(require_roles(UserRole.NURSE, UserRole.DOCTOR, UserRole.ADMIN))],
)
def create_preadmission(
    request_id: int,
    payload: PreadmissionCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    obj = _load_request(db, request_id)
    if obj.preadmission is not None:
        raise ConflictError(
            message=f"住院证 {obj.certificate_no} 已完成预入院登记",
            detail={"preadmission_id": obj.preadmission.id},
        )
    assert_request_transition(obj, AdmissionRequestStatus.PRE_ADMITTED)

    queue_no, seq = _next_queue_no(db)
    deposit_status = DepositStatus.PAID if payload.pay_deposit else DepositStatus.PENDING
    deposit_ref = f"SIM-PAY-{datetime.now().strftime('%Y%m%d%H%M%S')}" if payload.pay_deposit else None

    pre = Preadmission(
        admission_request_id=obj.id,
        queue_no=queue_no,
        queue_sequence=seq,
        contact_phone=payload.contact_phone,
        emergency_contact=payload.emergency_contact,
        emergency_phone=payload.emergency_phone,
        deposit_amount=payload.deposit_amount,
        deposit_status=deposit_status,
        deposit_ref_no=deposit_ref,
        supplement=payload.supplement,
        supplement_notes=payload.supplement_notes,
        registered_by=user.id,
        registered_at=datetime.now(),
    )
    db.add(pre)
    obj.status = AdmissionRequestStatus.PRE_ADMITTED

    record_audit(
        db,
        action=AuditAction.PRE_ADMISSION.value,
        user=user,
        object_type="preadmission",
        object_id=obj.id,
        detail={
            "certificate_no": obj.certificate_no,
            "queue_no": queue_no,
            "deposit_amount": str(payload.deposit_amount),
            "deposit_status": deposit_status.value,
            "payment_mode": "模拟（未接入真实支付）",
        },
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    db.refresh(pre)
    return preadmission_read(pre)


@router.get(
    "/{request_id}/preadmission",
    response_model=PreadmissionRead,
    summary="查看预入院登记",
)
def get_preadmission(request_id: int, db: DbSession, user: CurrentUser):
    obj = _load_request(db, request_id)
    if obj.preadmission is None:
        raise NotFoundError(f"住院证 {obj.certificate_no} 尚未进行预入院登记")
    return preadmission_read(obj.preadmission)


@router.get(
    "/{request_id}/history",
    response_model=MessageOut,
    summary="住院证状态流转说明（演示辅助）",
)
def get_history(request_id: int, db: DbSession, user: CurrentUser):
    obj = _load_request(db, request_id)
    return MessageOut(
        message=f"住院证 {obj.certificate_no} 当前状态："
        f"{ADMISSION_REQUEST_STATUS_LABEL.get(str(obj.status), str(obj.status))}",
        detail={
            "status": str(obj.status),
            "isolation_required": obj.isolation_required,
            "priority": str(obj.priority),
            "has_preadmission": obj.preadmission is not None,
        },
    )
