"""系统信息与健康检查路由（M0 工程初始化验收用）。

放在 ``/api/v1`` 前缀下，保证前端经 Vite 代理（只转发 ``/api`` 与 ``/health``）
即可访问；根路径 ``/`` 的同名信息保留给直接访问后端的场景。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/system", tags=["系统"])


@router.get("/info", summary="服务信息")
def service_info() -> dict:
    """返回服务名称、版本、API 前缀与接口文档地址。"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }


@router.get("/health", summary="健康检查")
def health() -> dict:
    """轻量健康检查，前端据此判断后端是否连通。"""
    return {"status": "ok"}
