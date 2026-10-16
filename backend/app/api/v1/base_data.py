"""基础数据接口：科室 / 病房 / 床位 / 患者 / 医生。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import CurrentUser, DbSession, client_ip, require_roles, user_agent
from app.core.errors import ConflictError, NotFoundError
from app.core.masking import mask_name, mask_phone
from app.models.enums import (
    BED_STATUS_TRANSITIONS,
    AuditAction,
    AuditResult,
    BedStatus,
    BedType,
    GenderLimit,
    UserRole,
)
from app.models.allocation import BedAllocation
from app.models.facility import Bed, BedSceneSlot, Department, Ward
from app.models.patient import Patient
from app.models.user import Doctor, User
from app.schemas.common import MessageOut, Page
from app.schemas.facility import (
    BedCreate,
    BedRead,
    BedStatusUpdate,
    BedUpdate,
    DepartmentCreate,
    DepartmentRead,
    WardCreate,
    WardRead,
)
from app.schemas.people import DoctorCreate, DoctorRead, PatientCreate, PatientRead, PatientUpdate
from app.services.audit import record_audit
from app.services.serializers import (
    bed_read,
    department_read,
    doctor_read,
    patient_read,
    ward_read,
)

# --------------------------------------------------------------------------- #
# 科室
# --------------------------------------------------------------------------- #
departments_router = APIRouter(prefix="/departments", tags=["基础数据-科室"])


@departments_router.get("", response_model=list[DepartmentRead], summary="科室列表")
def list_departments(db: DbSession, user: CurrentUser, is_active: bool | None = None):
    stmt = select(Department).order_by(Department.id)
    if is_active is not None:
        stmt = stmt.where(Department.is_active == is_active)
    return [department_read(d) for d in db.execute(stmt).scalars()]


@departments_router.post(
    "",
    response_model=DepartmentRead,
    status_code=201,
    summary="新增科室（仅管理员）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_department(payload: DepartmentCreate, request: Request, db: DbSession, user: CurrentUser):
    exists = db.execute(select(Department).where(Department.code == payload.code)).scalar_one_or_none()
    if exists:
        raise ConflictError(message=f"科室编码 {payload.code} 已存在", detail={"code": payload.code})
    dept = Department(**payload.model_dump())
    db.add(dept)
    db.flush()
    record_audit(
        db,
        action=AuditAction.CREATE.value,
        user=user,
        object_type="department",
        object_id=dept.id,
        detail=payload.model_dump(),
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return department_read(dept)


# --------------------------------------------------------------------------- #
# 病房
# --------------------------------------------------------------------------- #
wards_router = APIRouter(prefix="/wards", tags=["基础数据-病房"])


@wards_router.get("", response_model=list[WardRead], summary="病房列表（含床位统计）")
def list_wards(
    db: DbSession,
    user: CurrentUser,
    department_id: int | None = None,
):
    stmt = (
        select(Ward)
        .options(joinedload(Ward.department))
        .order_by(Ward.department_id, Ward.code)
    )
    if department_id:
        stmt = stmt.where(Ward.department_id == department_id)
    wards = list(db.execute(stmt).unique().scalars())

    counts = dict(
        db.execute(
            select(Bed.ward_id, func.count(Bed.id)).where(Bed.retired_at.is_(None)).group_by(Bed.ward_id)
        ).all()
    )
    avail = dict(
        db.execute(
            select(Bed.ward_id, func.count(Bed.id))
            .where(Bed.status == BedStatus.AVAILABLE, Bed.retired_at.is_(None))
            .group_by(Bed.ward_id)
        ).all()
    )
    return [
        ward_read(w, counts.get(w.id, 0), avail.get(w.id, 0))
        for w in wards
    ]


@wards_router.post(
    "",
    response_model=WardRead,
    status_code=201,
    summary="新增病房（仅管理员）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_ward(payload: WardCreate, request: Request, db: DbSession, user: CurrentUser):
    dept = db.get(Department, payload.department_id)
    if dept is None:
        raise NotFoundError(f"科室 #{payload.department_id} 不存在")
    if db.execute(select(Ward).where(Ward.code == payload.code)).scalar_one_or_none():
        raise ConflictError(message=f"病房号 {payload.code} 已存在")
    ward = Ward(**payload.model_dump())
    db.add(ward)
    db.flush()
    record_audit(
        db,
        action=AuditAction.CREATE.value,
        user=user,
        object_type="ward",
        object_id=ward.id,
        detail=payload.model_dump(),
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    db.refresh(ward)
    return ward_read(ward, 0, 0)


# --------------------------------------------------------------------------- #
# 床位
# --------------------------------------------------------------------------- #
beds_router = APIRouter(prefix="/beds", tags=["基础数据-床位"])


def _active_patient_map(db: Session, bed_ids: list[int]) -> dict[int, Patient]:
    if not bed_ids:
        return {}
    rows = db.execute(
        select(BedAllocation.bed_id, Patient)
        .join(Patient, Patient.id == BedAllocation.patient_id)
        .where(
            BedAllocation.bed_id.in_(bed_ids),
            BedAllocation.status.in_(["RESERVED", "ADMITTED"]),
        )
    ).all()
    return {bed_id: patient for bed_id, patient in rows}


@beds_router.get("", response_model=Page[BedRead], summary="床位列表（支持多维筛选）")
def list_beds(
    db: DbSession,
    user: CurrentUser,
    department_id: int | None = None,
    ward_id: int | None = None,
    status: str | None = Query(None, description="AVAILABLE/RESERVED/OCCUPIED/CLEANING/MAINTENANCE"),
    bed_type: str | None = None,
    is_isolation: bool | None = None,
    gender_limit: str | None = None,
    keyword: str | None = Query(None, description="按床位号/病房号模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(Bed).options(joinedload(Bed.ward), joinedload(Bed.department)).where(Bed.retired_at.is_(None))
    if department_id:
        stmt = stmt.where(Bed.department_id == department_id)
    if ward_id:
        stmt = stmt.where(Bed.ward_id == ward_id)
    if status:
        stmt = stmt.where(Bed.status == status)
    if bed_type:
        stmt = stmt.where(Bed.bed_type == bed_type)
    if is_isolation is not None:
        stmt = stmt.where(Bed.is_isolation == is_isolation)
    if gender_limit:
        stmt = stmt.where(Bed.gender_limit == gender_limit)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Bed.code.like(like) | Bed.ward_id.in_(
            select(Ward.id).where(Ward.code.like(like))
        ))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    beds = list(
        db.execute(
            stmt.order_by(Bed.department_id, Bed.code).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .scalars()
    )
    patient_map = _active_patient_map(db, [b.id for b in beds])
    return Page[BedRead](
        items=[bed_read(b, patient_map.get(b.id)) for b in beds],
        total=total,
        page=page,
        page_size=page_size,
    )


@beds_router.get("/{bed_id}", response_model=BedRead, summary="床位详情")
def get_bed_detail(bed_id: int, db: DbSession, user: CurrentUser):
    bed = db.execute(
        select(Bed).options(joinedload(Bed.ward), joinedload(Bed.department)).where(Bed.id == bed_id)
    ).unique().scalar_one_or_none()
    if bed is None:
        raise NotFoundError(f"床位 #{bed_id} 不存在")
    pmap = _active_patient_map(db, [bed.id])
    return bed_read(bed, pmap.get(bed.id))


@beds_router.post(
    "",
    response_model=BedRead,
    status_code=201,
    summary="新增床位（仅管理员）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_bed(payload: BedCreate, request: Request, db: DbSession, user: CurrentUser):
    ward = db.execute(select(Ward).where(Ward.id == payload.ward_id).with_for_update()).scalar_one_or_none()
    if ward is None:
        raise NotFoundError(f"病房 #{payload.ward_id} 不存在")
    if db.execute(select(Bed).where(Bed.code == payload.code)).scalar_one_or_none():
        raise ConflictError(message=f"床位号 {payload.code} 已存在")

    bed_type = BedType(payload.bed_type)
    is_isolation = payload.is_isolation if payload.is_isolation is not None else bed_type == BedType.ISOLATION
    bed = Bed(
        code=payload.code,
        ward_id=ward.id,
        department_id=ward.department_id,
        bed_type=bed_type,
        gender_limit=GenderLimit(payload.gender_limit),
        is_isolation=is_isolation,
        floor=payload.floor if payload.floor is not None else ward.floor,
        position_x=payload.position_x,
        position_y=payload.position_y,
        daily_rate=payload.daily_rate,
        note=payload.note,
        status=BedStatus.AVAILABLE,
    )
    db.add(bed)
    db.flush()
    existing_slots=set(db.scalars(select(BedSceneSlot.slot).where(BedSceneSlot.ward_id==ward.id)).all())
    scene_slot=0
    while scene_slot in existing_slots:scene_slot+=1
    if scene_slot>=max(12,((len(existing_slots)+2)//3)*3):
        raise ConflictError(message='当前病房的 3D 槽位已满，请先明确扩容布局')
    db.add(BedSceneSlot(bed_id=bed.id,ward_id=ward.id,slot=scene_slot,rotation=0))
    db.flush()
    record_audit(
        db,
        action=AuditAction.CREATE.value,
        user=user,
        object_type="bed",
        object_id=bed.id,
        detail={"code": bed.code, "ward_id": ward.id, "is_isolation": is_isolation},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return get_bed_detail(bed.id, db, user)


@beds_router.patch(
    "/{bed_id}",
    response_model=BedRead,
    summary="修改床位属性（仅管理员）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def update_bed(bed_id: int, payload: BedUpdate, request: Request, db: DbSession, user: CurrentUser):
    bed = db.get(Bed, bed_id)
    if bed is None:
        raise NotFoundError(f"床位 #{bed_id} 不存在")
    data = payload.model_dump(exclude_unset=True)

    if "bed_type" in data and data["bed_type"] is not None:
        bed.bed_type = BedType(data.pop("bed_type"))
    if "gender_limit" in data and data["gender_limit"] is not None:
        bed.gender_limit = GenderLimit(data.pop("gender_limit"))
    if "is_isolation" in data:
        iso = data.pop("is_isolation")
        if iso is not None:
            bed.is_isolation = bool(iso)
    if bed.bed_type == BedType.ISOLATION:
        bed.is_isolation = True
    elif bed.is_isolation and bed.bed_type != BedType.ISOLATION:
        bed.bed_type = BedType.ISOLATION
    for field in ("floor", "position_x", "position_y", "daily_rate", "note"):
        if field in data and data[field] is not None:
            setattr(bed, field, data[field])

    record_audit(
        db,
        action=AuditAction.UPDATE.value,
        user=user,
        object_type="bed",
        object_id=bed.id,
        detail=payload.model_dump(exclude_unset=True, mode="json"),
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return get_bed_detail(bed.id, db, user)


@beds_router.post(
    "/{bed_id}/status",
    response_model=BedRead,
    summary="手工调整床位状态（仅管理员，受状态机约束）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def set_bed_status(
    bed_id: int, payload: BedStatusUpdate, request: Request, db: DbSession, user: CurrentUser
):
    from app.services.allocation import _transition_bed  # 复用状态机与流水写入
    from app.core.errors import StateTransitionError
    from app.models.enums import AllocationStatus

    # 手工状态修改只允许维护类转移。RESERVED/OCCUPIED 相关的状态变更
    # 必须通过 reserve/admit/discharge/cancel；清洁释放必须通过 release，
    # 避免绕过分配记录、审计和清洁锚点检查。
    manual_allowed = {
        BedStatus.AVAILABLE.value: {BedStatus.MAINTENANCE.value},
        BedStatus.MAINTENANCE.value: {BedStatus.AVAILABLE.value},
    }
    bed = db.execute(select(Bed).where(Bed.id == bed_id).with_for_update()).scalar_one_or_none()
    if bed is None:
        raise NotFoundError(f"床位 #{bed_id} 不存在")
    if bed.retired_at is not None:
        raise StateTransitionError('已停用床位不能直接修改状态，请先通过床位管理恢复')
    from_status = str(bed.status)
    allowed = manual_allowed.get(from_status, set()) & BED_STATUS_TRANSITIONS.get(from_status, set())
    if payload.status not in allowed:
        raise StateTransitionError(
            "该状态变化属于分配、入住、出院或清洁释放流程，不能直接手工修改",
            detail={"bed_id": bed.id, "from": from_status, "to": payload.status, "allowed": sorted(allowed)},
        )
    active = db.execute(
        select(BedAllocation.id).where(
            BedAllocation.bed_id == bed.id,
            BedAllocation.status.in_((AllocationStatus.RESERVED, AllocationStatus.ADMITTED)),
        ).limit(1)
    ).scalar_one_or_none()
    if active is not None:
        raise StateTransitionError(
            "床位仍有关联的有效分配，必须先通过正式业务流程处理",
            detail={"bed_id": bed.id, "allocation_id": active},
        )
    _transition_bed(
        db,
        bed,
        BedStatus(payload.status),
        reason=payload.reason or "管理员手工调整",
        operator=user,
    )
    record_audit(
        db,
        action=AuditAction.UPDATE.value,
        user=user,
        object_type="bed",
        object_id=bed.id,
        detail={"from": from_status, "to": payload.status, "reason": payload.reason},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return get_bed_detail(bed.id, db, user)


# --------------------------------------------------------------------------- #
# 患者
# --------------------------------------------------------------------------- #
patients_router = APIRouter(prefix="/patients", tags=["基础数据-患者"])


@patients_router.get("", response_model=Page[PatientRead], summary="患者列表（默认脱敏）")
def list_patients(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    keyword: str | None = None,
    gender: str | None = None,
    reveal: bool | None = Query(None, description="管理员可传 true 查看明文（会写入审计）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    stmt = select(Patient)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Patient.name.like(like) | Patient.medical_record_no.like(like))
    if gender:
        stmt = stmt.where(Patient.gender == gender)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = list(
        db.execute(stmt.order_by(Patient.id).offset((page - 1) * page_size).limit(page_size)).scalars()
    )

    can_reveal = _has_reveal_permission(user)
    if reveal and not can_reveal:
        return _deny_reveal(db, user, request)

    items = [patient_read(p, reveal=bool(reveal and can_reveal)) for p in rows]
    if reveal and can_reveal:
        record_audit(
            db,
            action=AuditAction.REVEAL_SENSITIVE.value,
            user=user,
            object_type="patient",
            object_id="list",
            detail={"count": len(items), "reason": "管理员查看患者明文信息"},
            ip=client_ip(request),
            user_agent=user_agent(request),
        )
        db.commit()
    return Page[PatientRead](items=items, total=total, page=page, page_size=page_size)


def _deny_reveal(db: Session, user: User, request: Request):
    from app.core.errors import PermissionDeniedError

    record_audit(
        db,
        action=AuditAction.REVEAL_SENSITIVE.value,
        user=user,
        object_type="patient",
        object_id="list",
        result=AuditResult.FAILURE,
        detail={"reason": "无查看明文权限"},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    raise PermissionDeniedError("只有系统管理员可以查看患者明文信息")


def _has_reveal_permission(user: User) -> bool:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return role == UserRole.ADMIN.value


@patients_router.post(
    "",
    response_model=PatientRead,
    status_code=201,
    summary="新增患者（管理员/护士）",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
)
def create_patient(payload: PatientCreate, request: Request, db: DbSession, user: CurrentUser):
    mrn = payload.medical_record_no or _next_medical_record_no(db)
    if db.execute(select(Patient).where(Patient.medical_record_no == mrn)).scalar_one_or_none():
        raise ConflictError(message=f"病案号 {mrn} 已存在")
    data = payload.model_dump()
    data["medical_record_no"] = mrn
    patient = Patient(**data)
    db.add(patient)
    db.flush()
    record_audit(
        db,
        action=AuditAction.CREATE.value,
        user=user,
        object_type="patient",
        object_id=patient.id,
        detail={"medical_record_no": mrn, "gender": str(patient.gender)},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return patient_read(patient)


def _next_medical_record_no(db: Session) -> str:
    count = db.execute(select(func.count(Patient.id))).scalar_one()
    return f"MR{count + 1:06d}"


@patients_router.patch(
    "/{patient_id}",
    response_model=PatientRead,
    summary="修改患者（管理员/护士）",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.NURSE))],
)
def update_patient(
    patient_id: int, payload: PatientUpdate, request: Request, db: DbSession, user: CurrentUser
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"患者 #{patient_id} 不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, field, value)
    record_audit(
        db,
        action=AuditAction.UPDATE.value,
        user=user,
        object_type="patient",
        object_id=patient.id,
        detail=payload.model_dump(exclude_unset=True, mode="json"),
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    return patient_read(patient)


# --------------------------------------------------------------------------- #
# 医生
# --------------------------------------------------------------------------- #
doctors_router = APIRouter(prefix="/doctors", tags=["基础数据-医生"])


@doctors_router.get("", response_model=list[DoctorRead], summary="医生列表")
def list_doctors(db: DbSession, user: CurrentUser, department_id: int | None = None):
    stmt = select(Doctor).options(joinedload(Doctor.department)).order_by(Doctor.id)
    if department_id:
        stmt = stmt.where(Doctor.department_id == department_id)
    return [doctor_read(d) for d in db.execute(stmt).unique().scalars()]


@doctors_router.post(
    "",
    response_model=DoctorRead,
    status_code=201,
    summary="新增医生（仅管理员，可选同时创建登录账号）",
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def create_doctor(payload: DoctorCreate, request: Request, db: DbSession, user: CurrentUser):
    from app.core.security import hash_password

    if db.get(Department, payload.department_id) is None:
        raise NotFoundError(f"科室 #{payload.department_id} 不存在")

    data = payload.model_dump(exclude={"username", "password"})
    doctor = Doctor(**data)
    if payload.username:
        from app.models.enums import UserRole as UR

        if db.execute(select(User).where(User.username == payload.username)).scalar_one_or_none():
            raise ConflictError(message=f"登录名 {payload.username} 已存在")
        account = User(
            username=payload.username,
            hashed_password=hash_password(payload.password or "doctor123"),
            full_name=payload.name,
            role=UR.DOCTOR,
        )
        db.add(account)
        db.flush()
        doctor.user_id = account.id

    db.add(doctor)
    db.flush()
    record_audit(
        db,
        action=AuditAction.CREATE.value,
        user=user,
        object_type="doctor",
        object_id=doctor.id,
        detail={"name": doctor.name, "department_id": doctor.department_id},
        ip=client_ip(request),
        user_agent=user_agent(request),
    )
    db.commit()
    db.refresh(doctor)
    return doctor_read(doctor)
