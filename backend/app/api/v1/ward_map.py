"""病区床位态势图：授权只读快照；不修改真实床位或患者业务状态。"""
from __future__ import annotations
from datetime import datetime, timezone
from collections import Counter
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.core.masking import mask_name
from app.models.facility import Bed
from app.models.allocation import BedAllocation
from app.models.admission import AdmissionRequest
from app.models.patient import Patient
from app.models.enums import AllocationStatus, BedStatus
from app.schemas.ward_map import WardMapResponse, WardMapBed, WardMapRoom, PatientSummary
from app.services.ward_map import simulated_positions

router = APIRouter(prefix='/ward-map', tags=['床位态势图（只读）'])

@router.get('', response_model=WardMapResponse, summary='全院/病区床位态势快照（模拟空间、真实业务状态）')
def get_ward_map(db: DbSession, user: CurrentUser) -> WardMapResponse:
    # Query 1: all beds and their departments/wards, without page truncation.
    beds = list(db.execute(
        select(Bed).options(joinedload(Bed.ward), joinedload(Bed.department), joinedload(Bed.scene_slot))
        .where(Bed.retired_at.is_(None)).order_by(Bed.department_id, Bed.ward_id, Bed.code, Bed.id)
    ).unique().scalars())
    # Query 2: all ACTIVE allocations for visible beds, without N+1 queries.
    # No raw diagnosis, certificate number, phone number or identification data is selected.
    active: dict[int, tuple[BedAllocation, str, str]] = {}
    if beds:
        rows = db.execute(
            select(BedAllocation, Patient.name, AdmissionRequest.priority)
            .join(Patient, Patient.id == BedAllocation.patient_id)
            .join(AdmissionRequest, AdmissionRequest.id == BedAllocation.admission_request_id)
            .where(BedAllocation.bed_id.in_([b.id for b in beds]),
                   BedAllocation.status.in_((AllocationStatus.RESERVED, AllocationStatus.ADMITTED)))
        ).all()
        for alloc, patient_name, priority in rows:
            # Database unique active_bed_id guarantees at most one valid active allocation.
            active[alloc.bed_id] = (alloc, mask_name(patient_name), str(priority))

    room_pos, bed_pos = simulated_positions([
        (b.id, b.ward_id, b.ward.building, b.ward.code, b.ward.floor, b.code)
        for b in beds
    ])
    rooms: dict[int, WardMapRoom] = {}
    counts: Counter[str] = Counter()
    result_beds: list[WardMapBed] = []
    for b in beds:
        status = str(b.status)
        counts[status] += 1
        room = rooms.get(b.ward_id)
        if room is None:
            room = WardMapRoom(
                ward_id=b.ward_id, code=b.ward.code, name=b.ward.name,
                department_id=b.department_id, department_name=b.department.name,
                building=b.ward.building, floor=b.ward.floor,
                simulated_position=room_pos[b.ward_id], bed_count=0
            )
            rooms[b.ward_id] = room
        room.bed_count += 1
        alloc_info = active.get(b.id)
        patient = None
        warning = None
        if alloc_info:
            alloc, masked, priority = alloc_info
            patient = PatientSummary(masked_name=masked, priority=priority,
                                     allocation_status=str(alloc.status),
                                     admission_request_id=alloc.admission_request_id)
        # A mismatch is visible rather than manufacturing an avatar / implying an admission.
        if status == BedStatus.OCCUPIED.value and (not patient or patient.allocation_status != 'ADMITTED'):
            warning = '床位显示已入住，但缺少对应的有效入住分配；请核对正式业务记录'
        elif status == BedStatus.RESERVED.value and (not patient or patient.allocation_status != 'RESERVED'):
            warning = '床位显示已预占，但缺少对应的有效预占分配；请核对正式业务记录'
        elif status not in (BedStatus.OCCUPIED.value, BedStatus.RESERVED.value) and patient:
            warning = '床位状态与活动分配不一致；请核对正式业务记录'
        result_beds.append(WardMapBed(
            id=b.id, code=b.code, status=status, bed_type=str(b.bed_type),
            is_isolation=b.is_isolation, ward_id=b.ward_id, ward_code=b.ward.code,
            ward_name=b.ward.name, department_id=b.department_id,
            department_name=b.department.name, building=b.ward.building,
            floor=b.floor, simulated_position=bed_pos[b.id], patient=patient,
            state_warning=warning, scene_slot=b.scene_slot.slot if b.scene_slot else None,
            scene_rotation=b.scene_slot.rotation if b.scene_slot else None,
        ))
    return WardMapResponse(generated_at=datetime.now(timezone.utc),
                           beds=result_beds, rooms=list(rooms.values()),
                           counts={state.value: counts[state.value] for state in BedStatus})
