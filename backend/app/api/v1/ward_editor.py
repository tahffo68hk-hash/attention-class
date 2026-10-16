"""Explicitly confirmed administrator actions. No use of simulated negative IDs."""
from fastapi import APIRouter,Depends,Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.api.deps import DbSession,CurrentUser,require_roles,client_ip,user_agent
from app.core.errors import ConflictError
from app.models.enums import UserRole,AuditAction
from app.models.facility import Bed
from app.schemas.ward_editor import ManagedBedCreate,ManagedBedAction,ManagedBedPose,ManagedBedOut
from app.services import ward_editor as ops
from app.services.audit import record_audit

router=APIRouter(prefix='/ward-map/managed-beds',tags=['三维正式床位管理'])

def write_audit(db,user,request,bed,operation:str,detail:dict):
    record_audit(db,action=AuditAction.UPDATE.value if operation!='CREATE' else AuditAction.CREATE.value,
        user=user,object_type='bed',object_id=bed.id,
        detail={'operation':operation,**detail},ip=client_ip(request),user_agent=user_agent(request))

def finish(db,func):
    try:
        result=func()
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message='床位号或病房槽位冲突，请刷新后重试') from exc

@router.post('',response_model=ManagedBedOut,status_code=201,dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create(p:ManagedBedCreate,request:Request,db:DbSession,user:CurrentUser):
    def action():
        bed=ops.create_bed(db,p)
        # Audit includes only meaningful attributes; no patient identity.
        write_audit(db,user,request,bed,'CREATE',{'code':p.code,'ward_id':p.ward_id,'scene_slot':p.scene_slot})
        return ops.out(db,bed)
    return finish(db,action)

@router.post('/{bed_id}/archive',response_model=ManagedBedOut,dependencies=[Depends(require_roles(UserRole.ADMIN))])
def archive(bed_id:int,p:ManagedBedAction,request:Request,db:DbSession,user:CurrentUser):
    def action():
        bed=ops.archive_bed(db,bed_id,p.reason)
        write_audit(db,user,request,bed,'ARCHIVE',{'reason':p.reason})
        return ops.out(db,bed)
    return finish(db,action)

@router.post('/{bed_id}/restore',response_model=ManagedBedOut,dependencies=[Depends(require_roles(UserRole.ADMIN))])
def restore(bed_id:int,p:ManagedBedAction,request:Request,db:DbSession,user:CurrentUser):
    def action():
        bed=ops.restore_bed(db,bed_id)
        write_audit(db,user,request,bed,'RESTORE',{'reason':p.reason})
        return ops.out(db,bed)
    return finish(db,action)

@router.put('/{bed_id}/pose',response_model=ManagedBedOut,dependencies=[Depends(require_roles(UserRole.ADMIN))])
def pose(bed_id:int,p:ManagedBedPose,request:Request,db:DbSession,user:CurrentUser):
    def action():
        bed=ops.change_pose(db,bed_id,p)
        write_audit(db,user,request,bed,'SCENE_POSE',{'scene_slot':p.scene_slot,'rotation':p.rotation})
        return ops.out(db,bed)
    return finish(db,action)


@router.get('/archived',response_model=list[ManagedBedOut],dependencies=[Depends(require_roles(UserRole.ADMIN))])
def list_archived(db:DbSession,user:CurrentUser):
    beds=db.scalars(select(Bed).where(Bed.retired_at.is_not(None)).order_by(Bed.id).limit(100)).all()
    return [ops.out(db,b) for b in beds]
