"""Administrator-only bed create/archive/restore and stable display-slot management.

Everything runs in the caller's transaction. Caller commits exactly once together
with the audit entry. Existing bed allocation transaction code is unchanged.
"""
from __future__ import annotations
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.errors import ConflictError,NotFoundError,StateTransitionError
from app.models.enums import BedStatus,AllocationStatus,BedType,GenderLimit
from app.models.facility import Bed,Ward,BedSceneSlot
from app.models.allocation import BedAllocation
from app.schemas.ward_editor import ManagedBedCreate,ManagedBedPose


def _room(db:Session,ward_id:int)->Ward:
    # Serialize competing edits to a room BEFORE claiming a slot.
    ward=db.execute(select(Ward).where(Ward.id==ward_id).with_for_update()).scalar_one_or_none()
    if not ward:raise NotFoundError(f'病房 #{ward_id} 不存在')
    return ward


def _slot_free(db:Session,ward_id:int,slot:int,ignore_bed:int|None=None)->None:
    # Fixed 3-column rows with a small spare margin. Avoid slots that extend beyond
    # the floor geometry; this is separate from medical/clinical ward capacity.
    slots=list(db.scalars(select(BedSceneSlot.slot).where(BedSceneSlot.ward_id==ward_id)))
    room_count=len(slots)
    capacity=max(12,((room_count+2)//3)*3,max(slots,default=-1)+1)
    if slot<0 or slot>=capacity:
        raise ConflictError(message=f'槽位超出模拟病房布局范围（当前最大 {capacity} 格）')
    existing=db.execute(select(BedSceneSlot).where(BedSceneSlot.ward_id==ward_id,
                   BedSceneSlot.slot==slot)).scalar_one_or_none()
    if existing and existing.bed_id!=ignore_bed:
        raise ConflictError(message=f'病房槽位 {slot+1} 已被床位占用')


def _bed(db:Session,bed_id:int)->Bed:
    bed=db.execute(select(Bed).where(Bed.id==bed_id).with_for_update()).scalar_one_or_none()
    if not bed:raise NotFoundError(f'床位 #{bed_id} 不存在')
    return bed


def _ensure_no_active(db:Session,bed:Bed)->None:
    found=db.execute(select(BedAllocation.id).where(BedAllocation.bed_id==bed.id,
        BedAllocation.status.in_((AllocationStatus.RESERVED,AllocationStatus.ADMITTED))).limit(1)).scalar_one_or_none()
    if found is not None:raise StateTransitionError('床位仍有关联的有效分配，不能停用或调整位置',{'allocation_id':found})


def create_bed(db:Session,p:ManagedBedCreate)->Bed:
    ward=_room(db,p.ward_id)
    template=db.get(Bed,p.template_bed_id)
    if not template or template.ward_id!=ward.id or template.retired_at is not None:
        raise ConflictError(message='仅可引用同一病房的有效床位模板')
    exists=db.execute(select(Bed).where(Bed.code==p.code)).scalar_one_or_none()
    if exists:
        pose=db.execute(select(BedSceneSlot).where(BedSceneSlot.bed_id==exists.id)).scalar_one_or_none()
        # Repeated identical creation requests are idempotent; mismatches are conflict.
        if (pose and exists.retired_at is None and exists.ward_id==ward.id and pose.slot==p.scene_slot
            and pose.rotation==p.rotation and str(exists.bed_type)==p.bed_type
            and str(exists.gender_limit)==p.gender_limit and exists.daily_rate==p.daily_rate
            and exists.note==p.note and exists.is_isolation==(p.bed_type=='ISOLATION')):
            return exists
        raise ConflictError(message=f'床位号 {p.code} 已存在或请求参数不一致')
    _slot_free(db,ward.id,p.scene_slot)
    bed_type=BedType(p.bed_type)
    bed=Bed(code=p.code,ward_id=ward.id,department_id=ward.department_id,
        bed_type=bed_type,gender_limit=GenderLimit(p.gender_limit),
        is_isolation=bed_type==BedType.ISOLATION,floor=ward.floor,
        # A 3D display pose is NEVER written into scoring coordinates.
        position_x=template.position_x,position_y=template.position_y,
        daily_rate=p.daily_rate,note=p.note,status=BedStatus.AVAILABLE)
    db.add(bed);db.flush()
    db.add(BedSceneSlot(bed_id=bed.id,ward_id=ward.id,slot=p.scene_slot,rotation=p.rotation));db.flush()
    return bed


def archive_bed(db:Session,bed_id:int,reason:str)->Bed:
    bed=_bed(db,bed_id)
    if bed.retired_at is not None:return bed # repeated archive is idempotent
    if str(bed.status) not in (BedStatus.AVAILABLE.value,BedStatus.MAINTENANCE.value):
        raise StateTransitionError('只能停用空闲或维护床位；预占、入住、清洁床位必须先完成正常流程')
    _ensure_no_active(db,bed)
    bed.retired_at=datetime.now(timezone.utc).replace(tzinfo=None)
    bed.retired_reason=reason
    db.flush()
    return bed


def restore_bed(db:Session,bed_id:int)->Bed:
    bed=_bed(db,bed_id)
    if bed.retired_at is None:return bed
    if str(bed.status) not in (BedStatus.AVAILABLE.value,BedStatus.MAINTENANCE.value):
        raise StateTransitionError('床位状态不支持恢复，请先核对业务流水')
    _ensure_no_active(db,bed)
    # BedSceneSlot remains reserved through retirement, so original location is stable.
    bed.retired_at=None;bed.retired_reason=None
    db.flush()
    return bed


def change_pose(db:Session,bed_id:int,p:ManagedBedPose)->Bed:
    initial=db.get(Bed,bed_id)
    if initial is None:raise NotFoundError(f'床位 #{bed_id} 不存在')
    if initial.ward_id!=p.ward_id:raise ConflictError(message='正式空间编辑不得跨病房移动床位')
    _room(db,p.ward_id)
    bed=_bed(db,bed_id)
    if bed.retired_at is not None:raise StateTransitionError('已停用床位不允许空间移动')
    if str(bed.status) in (BedStatus.RESERVED.value,BedStatus.OCCUPIED.value,BedStatus.CLEANING.value):
        raise StateTransitionError('已有预占、入住或清洁中的床位不可移动')
    _ensure_no_active(db,bed)
    if bed.ward_id!=p.ward_id:raise ConflictError(message='正式空间编辑不得跨病房移动床位')
    _slot_free(db,p.ward_id,p.scene_slot,bed.id)
    slot=db.execute(select(BedSceneSlot).where(BedSceneSlot.bed_id==bed.id)).scalar_one_or_none()
    if not slot:
        slot=BedSceneSlot(bed_id=bed.id,ward_id=p.ward_id,slot=p.scene_slot,rotation=p.rotation)
        db.add(slot)
    else:slot.slot=p.scene_slot;slot.rotation=p.rotation
    db.flush()
    return bed


def out(db:Session,bed:Bed)->dict:
    slot=db.execute(select(BedSceneSlot).where(BedSceneSlot.bed_id==bed.id)).scalar_one()
    return dict(id=bed.id,code=bed.code,ward_id=bed.ward_id,scene_slot=slot.slot,rotation=slot.rotation,
                retired=bed.retired_at is not None,status=str(bed.status))
