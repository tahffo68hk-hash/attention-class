"""管理看板接口。"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.admission import AdmissionRequest, Preadmission
from app.models.allocation import BedAllocation
from app.models.enums import (
    PRIORITY_LABEL,
    AdmissionRequestStatus,
    AllocationStatus,
    BedStatus,
    PatientPriority,
)
from app.models.facility import Bed, Department
from app.schemas.dashboard import DashboardSummary, DepartmentBedStat, PriorityQueueStat

router = APIRouter(prefix="/dashboard", tags=["管理看板"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="看板汇总：总床位 / 空床 / 预占用 / 已入住 / 待入院人数",
)
def summary(db: DbSession, user: CurrentUser) -> DashboardSummary:
    status_rows = db.execute(
        select(Bed.status, func.count(Bed.id)).where(Bed.retired_at.is_(None)).group_by(Bed.status)
    ).all()
    counts = {str(status): count for status, count in status_rows}
    total = sum(counts.values())

    available = counts.get(BedStatus.AVAILABLE.value, 0)
    reserved = counts.get(BedStatus.RESERVED.value, 0)
    occupied = counts.get(BedStatus.OCCUPIED.value, 0)
    cleaning = counts.get(BedStatus.CLEANING.value, 0)
    maintenance = counts.get(BedStatus.MAINTENANCE.value, 0)

    pending = db.execute(
        select(func.count(Preadmission.id))
        .join(AdmissionRequest, AdmissionRequest.id == Preadmission.admission_request_id)
        .where(AdmissionRequest.status == AdmissionRequestStatus.PRE_ADMITTED)
    ).scalar_one()

    iso_total = db.execute(
        select(func.count(Bed.id)).where(Bed.is_isolation.is_(True), Bed.retired_at.is_(None))
    ).scalar_one()
    iso_available = db.execute(
        select(func.count(Bed.id)).where(Bed.is_isolation.is_(True), Bed.status == BedStatus.AVAILABLE, Bed.retired_at.is_(None))
    ).scalar_one()
    iso_in_use = db.execute(
        select(func.count(Bed.id)).where(
            Bed.is_isolation.is_(True),
            Bed.status.in_([BedStatus.RESERVED, BedStatus.OCCUPIED]),Bed.retired_at.is_(None),
        )
    ).scalar_one()

    active_allocations = db.execute(
        select(func.count(BedAllocation.id)).where(
            BedAllocation.status.in_([AllocationStatus.RESERVED, AllocationStatus.ADMITTED])
        )
    ).scalar_one()

    today = date.today()
    admitted_today = db.execute(
        select(func.count(BedAllocation.id)).where(func.date(BedAllocation.admitted_at) == today)
    ).scalar_one()
    discharged_today = db.execute(
        select(func.count(BedAllocation.id)).where(func.date(BedAllocation.discharged_at) == today)
    ).scalar_one()

    # 分科室统计
    dept_rows = db.execute(
        select(
            Department.id,
            Department.name,
            Bed.status,
            func.count(Bed.id),
        )
        .join(Bed, Bed.department_id == Department.id)
        .where(Bed.retired_at.is_(None))
        .group_by(Department.id, Department.name, Bed.status)
    ).all()
    dept_map: dict[int, DepartmentBedStat] = {}
    for dept_id, dept_name, status, count in dept_rows:
        stat = dept_map.get(dept_id)
        if stat is None:
            stat = DepartmentBedStat(
                department_id=dept_id,
                department_name=dept_name,
                total=0,
                available=0,
                reserved=0,
                occupied=0,
                cleaning=0,
                maintenance=0,
                occupancy_rate=0.0,
            )
            dept_map[dept_id] = stat
        stat.total += count
        key = str(status)
        if key == BedStatus.AVAILABLE.value:
            stat.available += count
        elif key == BedStatus.RESERVED.value:
            stat.reserved += count
        elif key == BedStatus.OCCUPIED.value:
            stat.occupied += count
        elif key == BedStatus.CLEANING.value:
            stat.cleaning += count
        elif key == BedStatus.MAINTENANCE.value:
            stat.maintenance += count

    for stat in dept_map.values():
        stat.occupancy_rate = (
            round((stat.occupied + stat.reserved) / stat.total * 100, 2) if stat.total else 0.0
        )

    # 待入院队列按优先级分布
    prio_rows = db.execute(
        select(AdmissionRequest.priority, func.count(Preadmission.id))
        .join(Preadmission, Preadmission.admission_request_id == AdmissionRequest.id)
        .where(AdmissionRequest.status == AdmissionRequestStatus.PRE_ADMITTED)
        .group_by(AdmissionRequest.priority)
    ).all()
    prio_map = {str(p): c for p, c in prio_rows}
    priority_stats = [
        PriorityQueueStat(
            priority=p.value,
            priority_label=PRIORITY_LABEL.get(p.value, p.value),
            count=prio_map.get(p.value, 0),
        )
        for p in PatientPriority
    ]

    return DashboardSummary(
        total_beds=total,
        available_beds=available,
        reserved_beds=reserved,
        occupied_beds=occupied,
        cleaning_beds=cleaning,
        maintenance_beds=maintenance,
        occupancy_rate=round((occupied + reserved) / total * 100, 2) if total else 0.0,
        pending_admission_patients=pending,
        isolation_beds_total=iso_total,
        isolation_beds_available=iso_available,
        isolation_beds_in_use=iso_in_use,
        active_allocations=active_allocations,
        admitted_today=admitted_today,
        discharged_today=discharged_today,
        department_stats=sorted(dept_map.values(), key=lambda s: s.department_id),
        pending_queue_by_priority=priority_stats,
        generated_at=datetime.now(),
    )
