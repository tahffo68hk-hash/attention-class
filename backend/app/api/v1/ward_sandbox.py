"""Independent sandbox endpoint. It never creates/updates a bed allocation."""
from fastapi import APIRouter, Depends
from app.api.deps import DbSession, CurrentUser, require_roles
from app.models.enums import UserRole
from app.schemas.ward_sandbox import WardSandboxInput,WardSandboxOutput
from app.services.ward_sandbox import preview_sandbox

router=APIRouter(prefix='/ward-map',tags=['3D 调度沙盘（只读）'])

@router.post('/simulate',response_model=WardSandboxOutput,
 dependencies=[Depends(require_roles(UserRole.ADMIN,UserRole.NURSE))],
 summary='完全虚构申请的 H1-H4/五维评分 + 贪心/精确流模拟（零写入）')
def simulate(payload:WardSandboxInput,db:DbSession,user:CurrentUser):
    return preview_sandbox(db,payload)
