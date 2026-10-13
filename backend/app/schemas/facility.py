"""科室 / 病房 / 床位模型。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DepartmentCreate(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    description: str | None = Field(None, max_length=255)
    anchor_floor: int = 1
    anchor_x: int = 0
    anchor_y: int = 0
    is_active: bool = True


class DepartmentRead(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    anchor_floor: int
    anchor_x: int
    anchor_y: int
    is_active: bool = True


class WardCreate(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    department_id: int
    building: str = Field("住院楼", max_length=32)
    floor: int = 1
    description: str | None = Field(None, max_length=255)


class WardRead(ORMModel):
    id: int
    code: str
    name: str
    department_id: int
    department_name: str | None = None
    building: str
    floor: int
    description: str | None = None
    total_beds: int = 0
    available_beds: int = 0


class BedCreate(BaseModel):
    code: str = Field(..., max_length=32)
    ward_id: int
    bed_type: str = Field("NORMAL", description="NORMAL / ISOLATION / MONITOR")
    gender_limit: str = Field("ANY", description="MALE / FEMALE / ANY")
    is_isolation: bool | None = Field(
        None, description="留空时按 bed_type 自动推导：ISOLATION -> true"
    )
    floor: int | None = Field(None, description="留空时继承病房楼层")
    position_x: int = 0
    position_y: int = 0
    daily_rate: Decimal = Decimal("0.00")
    note: str | None = Field(None, max_length=255)


class BedUpdate(BaseModel):
    bed_type: str | None = None
    gender_limit: str | None = None
    is_isolation: bool | None = None
    floor: int | None = None
    position_x: int | None = None
    position_y: int | None = None
    daily_rate: Decimal | None = None
    note: str | None = Field(None, max_length=255)


class BedStatusUpdate(BaseModel):
    status: str = Field(..., description="目标状态：AVAILABLE / MAINTENANCE 等")
    reason: str | None = Field(None, max_length=255)


class BedRead(ORMModel):
    id: int
    code: str
    ward_id: int
    ward_code: str | None = None
    ward_name: str | None = None
    department_id: int
    department_name: str | None = None
    bed_type: str
    bed_type_label: str | None = None
    gender_limit: str
    gender_limit_label: str | None = None
    is_isolation: bool
    floor: int
    position_x: int
    position_y: int
    status: str
    status_label: str | None = None
    daily_rate: Decimal
    note: str | None = None
    current_patient_name: str | None = None
    current_patient_id: int | None = None
