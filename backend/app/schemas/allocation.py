"""床位分配模型。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AllocationCreate(BaseModel):
    admission_request_id: int
    bed_id: int | None = Field(
        None, description="留空表示采纳推荐排序第一名；填写则为人工选择（同样受硬约束校验）"
    )
    note: str | None = Field(None, max_length=500, description="操作说明")
    confirm_top_recommendation: bool = Field(
        False, description="显式确认采纳推荐结果（与 bed_id 二选一）"
    )


class AllocationRead(ORMModel):
    id: int
    admission_request_id: int
    certificate_no: str | None = None
    patient_id: int
    patient_name: str | None = None
    department_name: str | None = None
    bed_id: int
    bed_code: str | None = None
    ward_name: str | None = None
    mode: str
    mode_label: str | None = None
    score: Decimal | None = None
    reason: str | None = None
    status: str
    status_label: str | None = None
    operator_name: str | None = None
    reserved_at: datetime | None = None
    admitted_at: datetime | None = None
    discharged_at: datetime | None = None
    released_at: datetime | None = None
    cancel_reason: str | None = None
    created_at: datetime | None = None


class DischargeRequest(BaseModel):
    reason: str | None = Field(None, max_length=255, description="出院说明")


class CancelRequest(BaseModel):
    reason: str | None = Field(None, max_length=255, description="取消原因")


class BedStatusLogRead(ORMModel):
    id: int
    bed_id: int
    bed_code: str | None = None
    from_status: str | None = None
    to_status: str
    reason: str | None = None
    allocation_id: int | None = None
    admission_request_id: int | None = None
    operator_name: str | None = None
    created_at: datetime | None = None


class ReassignRequest(BaseModel):
    new_bed_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=255)
