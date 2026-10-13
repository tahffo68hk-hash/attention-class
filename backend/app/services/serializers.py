"""ORM -> 读模型 的序列化辅助（含脱敏与中文标签）。"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.core.masking import (
    mask_address,
    mask_id_card,
    mask_name,
    mask_medical_record_no,
    mask_phone,
)
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedAllocation, BedStatusLog
from app.models.enums import (
    ADMISSION_REQUEST_STATUS_LABEL,
    ALLOCATION_STATUS_LABEL,
    BED_STATUS_LABEL,
    BED_TYPE_LABEL,
    GENDER_LABEL,
    PRIORITY_LABEL,
    USER_ROLE_LABEL,
)
from app.models.facility import Bed
from app.models.patient import Patient
from app.models.user import Doctor, User
from app.schemas.admission import AdmissionRequestRead, PreadmissionRead
from app.schemas.allocation import AllocationRead, BedStatusLogRead
from app.schemas.auth import UserRead
from app.schemas.facility import BedRead, DepartmentRead, WardRead
from app.schemas.people import DoctorRead, PatientRead

ALLOCATION_MODE_LABEL = {"RECOMMENDED": "采纳推荐", "MANUAL": "人工选择"}
DEPOSIT_STATUS_LABEL = {"PENDING": "待缴纳（模拟）", "PAID": "已缴纳（模拟）", "REFUNDED": "已退还（模拟）"}

GENDER_LIMIT_LABEL = {"MALE": "仅限男性", "FEMALE": "仅限女性", "ANY": "不限性别"}


def user_read(user: User) -> UserRead:
    doctor = getattr(user, "doctor", None)
    return UserRead(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        role_label=USER_ROLE_LABEL.get(str(user.role)),
        is_active=user.is_active,
        doctor_id=doctor.id if doctor else None,
        department_id=doctor.department_id if doctor else None,
    )


def patient_read(patient: Patient, reveal: bool = False) -> PatientRead:
    gender = str(patient.gender)
    if reveal:
        name, id_card, phone, address, mrn = (
            patient.name,
            patient.id_card,
            patient.phone,
            patient.address,
            patient.medical_record_no,
        )
    else:
        name = mask_name(patient.name)
        id_card = mask_id_card(patient.id_card)
        phone = mask_phone(patient.phone)
        address = mask_address(patient.address)
        mrn = mask_medical_record_no(patient.medical_record_no)
    return PatientRead(
        id=patient.id,
        medical_record_no=mrn,
        name=name,
        gender=gender,
        gender_label=GENDER_LABEL.get(gender),
        birth_date=patient.birth_date,
        id_card=id_card,
        phone=phone,
        address=address,
        blood_type=patient.blood_type,
        is_infectious=patient.is_infectious,
        allergy=patient.allergy,
        note=patient.note,
        masked=not reveal,
    )


def doctor_read(doctor: Doctor) -> DoctorRead:
    return DoctorRead(
        id=doctor.id,
        name=doctor.name,
        department_id=doctor.department_id,
        department_name=doctor.department.name if doctor.department else None,
        title=doctor.title,
        phone=mask_phone(doctor.phone),
        is_active=doctor.is_active,
        user_id=doctor.user_id,
    )


def department_read(dept) -> DepartmentRead:
    return DepartmentRead.model_validate(dept)


def ward_read(ward, total_beds: int = 0, available_beds: int = 0) -> WardRead:
    return WardRead(
        id=ward.id,
        code=ward.code,
        name=ward.name,
        department_id=ward.department_id,
        department_name=ward.department.name if ward.department else None,
        building=ward.building,
        floor=ward.floor,
        description=ward.description,
        total_beds=total_beds,
        available_beds=available_beds,
    )


def bed_read(
    bed: Bed,
    current_patient: Patient | None = None,
) -> BedRead:
    return BedRead(
        id=bed.id,
        code=bed.code,
        ward_id=bed.ward_id,
        ward_code=bed.ward.code if bed.ward else None,
        ward_name=bed.ward.name if bed.ward else None,
        department_id=bed.department_id,
        department_name=bed.department.name if bed.department else None,
        bed_type=str(bed.bed_type),
        bed_type_label=BED_TYPE_LABEL.get(str(bed.bed_type)),
        gender_limit=str(bed.gender_limit),
        gender_limit_label=GENDER_LIMIT_LABEL.get(str(bed.gender_limit)),
        is_isolation=bed.is_isolation,
        floor=bed.floor,
        position_x=bed.position_x,
        position_y=bed.position_y,
        status=str(bed.status),
        status_label=BED_STATUS_LABEL.get(str(bed.status)),
        daily_rate=bed.daily_rate,
        note=bed.note,
        current_patient_name=mask_name(current_patient.name) if current_patient else None,
        current_patient_id=current_patient.id if current_patient else None,
    )


def admission_request_read(req: AdmissionRequest) -> AdmissionRequestRead:
    pre = req.preadmission
    return AdmissionRequestRead(
        id=req.id,
        certificate_no=req.certificate_no,
        patient_id=req.patient_id,
        patient_name=mask_name(req.patient.name) if req.patient else None,
        patient_gender=str(req.patient.gender) if req.patient else None,
        patient_gender_label=GENDER_LABEL.get(str(req.patient.gender)) if req.patient else None,
        department_id=req.department_id,
        department_name=req.department.name if req.department else None,
        doctor_id=req.doctor_id,
        doctor_name=req.doctor.name if req.doctor else None,
        priority=str(req.priority),
        priority_label=PRIORITY_LABEL.get(str(req.priority)),
        isolation_required=req.isolation_required,
        infection_type=req.infection_type,
        diagnosis=req.diagnosis,
        preferred_ward_id=req.preferred_ward_id,
        preferred_ward_name=req.preferred_ward.name if req.preferred_ward else None,
        notes=req.notes,
        status=str(req.status),
        status_label=ADMISSION_REQUEST_STATUS_LABEL.get(str(req.status)),
        issued_at=req.issued_at,
        queue_no=pre.queue_no if pre else None,
        deposit_status=str(pre.deposit_status) if pre else None,
        deposit_status_label=DEPOSIT_STATUS_LABEL.get(str(pre.deposit_status)) if pre else None,
        deposit_amount=pre.deposit_amount if pre else None,
        created_at=req.created_at,
    )


def preadmission_read(pre: Preadmission) -> PreadmissionRead:
    req = pre.admission_request
    return PreadmissionRead(
        id=pre.id,
        admission_request_id=pre.admission_request_id,
        certificate_no=req.certificate_no if req else None,
        queue_no=pre.queue_no,
        queue_sequence=pre.queue_sequence,
        patient_id=req.patient_id if req else None,
        patient_name=mask_name(req.patient.name) if req and req.patient else None,
        department_name=req.department.name if req and req.department else None,
        contact_phone=mask_phone(pre.contact_phone),
        emergency_contact=mask_name(pre.emergency_contact),
        emergency_phone=mask_phone(pre.emergency_phone),
        deposit_amount=pre.deposit_amount,
        deposit_status=str(pre.deposit_status),
        deposit_status_label=DEPOSIT_STATUS_LABEL.get(str(pre.deposit_status)),
        deposit_ref_no=pre.deposit_ref_no,
        supplement_notes=pre.supplement_notes,
        registered_at=pre.registered_at,
        priority=str(req.priority) if req else None,
        priority_label=PRIORITY_LABEL.get(str(req.priority)) if req else None,
        isolation_required=req.isolation_required if req else None,
        created_at=pre.created_at,
    )


def allocation_read(
    alloc: BedAllocation,
    certificate_no: str | None = None,
    department_name: str | None = None,
) -> AllocationRead:
    return AllocationRead(
        id=alloc.id,
        admission_request_id=alloc.admission_request_id,
        certificate_no=certificate_no
        or (alloc.admission_request.certificate_no if alloc.admission_request else None),
        patient_id=alloc.patient_id,
        patient_name=mask_name(alloc.patient.name) if alloc.patient else None,
        department_name=department_name
        or (
            alloc.admission_request.department.name
            if alloc.admission_request and alloc.admission_request.department
            else None
        ),
        bed_id=alloc.bed_id,
        bed_code=alloc.bed.code if alloc.bed else None,
        ward_name=alloc.bed.ward.name if alloc.bed and alloc.bed.ward else None,
        mode=str(alloc.mode),
        mode_label=ALLOCATION_MODE_LABEL.get(str(alloc.mode)),
        score=alloc.score,
        reason=alloc.reason,
        status=str(alloc.status),
        status_label=ALLOCATION_STATUS_LABEL.get(str(alloc.status)),
        operator_name=mask_name(alloc.operator.full_name) if alloc.operator else None,
        reserved_at=alloc.reserved_at,
        admitted_at=alloc.admitted_at,
        discharged_at=alloc.discharged_at,
        released_at=alloc.released_at,
        cancel_reason=alloc.cancel_reason,
        created_at=alloc.created_at,
    )


def bed_status_log_read(log: BedStatusLog, bed_code: str | None = None) -> BedStatusLogRead:
    return BedStatusLogRead(
        id=log.id,
        bed_id=log.bed_id,
        bed_code=bed_code,
        from_status=str(log.from_status) if log.from_status else None,
        to_status=str(log.to_status),
        reason=log.reason,
        allocation_id=log.allocation_id,
        admission_request_id=log.admission_request_id,
        operator_name=None,
        created_at=log.created_at,
    )


def rates_range(rates: Iterable[Decimal]) -> tuple[Decimal, Decimal]:
    values = list(rates)
    if not values:
        return Decimal("0"), Decimal("0")
    return min(values), max(values)
