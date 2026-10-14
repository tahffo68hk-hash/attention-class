"""API v1 路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admissions,
    allocations,
    audit,
    auth,
    base_data,
    dashboard,
    queue,
    recommendations,
    system,
    optimization,
    assistant,
    ward_map,
)

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(optimization.router)
api_router.include_router(assistant.router)
api_router.include_router(auth.router)
api_router.include_router(admissions.router)
api_router.include_router(recommendations.router)
api_router.include_router(queue.router)
api_router.include_router(allocations.router)
api_router.include_router(allocations.beds_release_router)
api_router.include_router(base_data.departments_router)
api_router.include_router(base_data.wards_router)
api_router.include_router(base_data.beds_router)
api_router.include_router(base_data.patients_router)
api_router.include_router(base_data.doctors_router)
api_router.include_router(dashboard.router)
api_router.include_router(audit.router)
# 病区床位态势图（只读；模拟空间布局 + 真实业务状态）
api_router.include_router(ward_map.router)

__all__ = ["api_router"]
