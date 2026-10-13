"""看板与审计模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DepartmentBedStat(BaseModel):
    department_id: int
    department_name: str
    total: int
    available: int
    reserved: int
    occupied: int
    cleaning: int
    maintenance: int
    occupancy_rate: float


class PriorityQueueStat(BaseModel):
    priority: str
    priority_label: str
    count: int


class DashboardSummary(BaseModel):
    total_beds: int
    available_beds: int
    reserved_beds: int
    occupied_beds: int
    cleaning_beds: int
    maintenance_beds: int
    occupancy_rate: float = Field(..., description="占用率 =（已入住 + 预占用）/ 总床位")
    pending_admission_patients: int = Field(..., description="待入院队列人数")
    isolation_beds_total: int
    isolation_beds_available: int
    isolation_beds_in_use: int
    active_allocations: int
    admitted_today: int
    discharged_today: int
    department_stats: list[DepartmentBedStat]
    pending_queue_by_priority: list[PriorityQueueStat]
    generated_at: datetime


class AuditLogRead(ORMModel):
    id: int
    user_id: int | None = None
    username: str | None = None
    role: str | None = None
    action: str
    object_type: str | None = None
    object_id: str | None = None
    result: str
    detail: dict | None = None
    ip: str | None = None
    created_at: datetime | None = None
