"""住院证与预入院登记模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AdmissionRequestCreate(BaseModel):
    patient_id: int
    department_id: int
    doctor_id: int | None = Field(None, description="留空时取当前登录医生")
    priority: str = Field("NORMAL", description="CRITICAL/SEVERE/URGENT/NORMAL/MILD")
    isolation_required: bool = False
    infection_type: str | None = Field(None, max_length=64)
    diagnosis: str | None = Field(None, max_length=255)
    preferred_ward_id: int | None = None
    notes: str | None = Field(None, max_length=255)
    issue: bool = Field(True, description="是否直接开具（false 则保存为草稿）")


class AdmissionRequestRead(ORMModel):
    id: int
    certificate_no: str
    patient_id: int
    patient_name: str | None = None
    patient_gender: str | None = None
    patient_gender_label: str | None = None
    department_id: int
    department_name: str | None = None
    doctor_id: int
    doctor_name: str | None = None
    priority: str
    priority_label: str | None = None
    isolation_required: bool
    infection_type: str | None = None
    diagnosis: str | None = None
    preferred_ward_id: int | None = None
    preferred_ward_name: str | None = None
    notes: str | None = None
    status: str
    status_label: str | None = None
    issued_at: datetime | None = None
    queue_no: str | None = None
    deposit_status: str | None = None
    deposit_status_label: str | None = None
    deposit_amount: Decimal | None = None
    active_bed_code: str | None = None
    allocation_status: str | None = None
    created_at: datetime | None = None


class PreadmissionCreate(BaseModel):
    admission_request_id: int | None = Field(
        None, description="住院证 ID（以 URL 路径为准，请求体可省略）"
    )
    contact_phone: str | None = Field(None, max_length=32)
    emergency_contact: str | None = Field(None, max_length=64)
    emergency_phone: str | None = Field(None, max_length=32)
    deposit_amount: Decimal = Field(Decimal("0.00"), ge=0, le=Decimal("999999.99"))
    pay_deposit: bool = Field(False, description="模拟缴纳预交金（不接入真实支付）")
    supplement: dict | None = None
    supplement_notes: str | None = None


class PreadmissionRead(ORMModel):
    id: int
    admission_request_id: int
    certificate_no: str | None = None
    queue_no: str
    queue_sequence: int
    patient_id: int | None = None
    patient_name: str | None = None
    department_name: str | None = None
    contact_phone: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    deposit_amount: Decimal
    deposit_status: str
    deposit_status_label: str | None = None
    deposit_ref_no: str | None = None
    supplement_notes: str | None = None
    registered_at: datetime | None = None
    priority: str | None = None
    priority_label: str | None = None
    isolation_required: bool | None = None
    created_at: datetime | None = None
