"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers

DESCRIPTION = """
**医院床位智能分配与住院入院预办理原型系统**（模块化单体）。

核心能力：
1. 基础数据：科室 / 病房 / 床位（含性别限制、隔离属性、位置、状态）/ 患者 / 医生
2. 住院证：开具、开具草稿、取消，记录病情优先级与隔离需求
3. 预入院：登记补充信息 + **模拟**预交金（不接入真实支付），生成待入院队列
4. 智能床位推荐：硬约束过滤 + 可解释软约束评分（优先级与床位条件交互，不是常数分）
5. 床位分配：推荐确认 / 人工选择（同样受硬约束约束），
   `SELECT ... FOR UPDATE` + 唯一索引双重并发保护，全流程状态留痕
6. 管理看板：总床位 / 空床 / 预占用 / 已入住 / 待入院人数与分科室统计
7. 安全与审计：基础登录认证与角色权限、患者信息脱敏、关键操作全量审计

> 本系统仅使用**虚构**患者数据，不含任何真实医疗数据，不含真实支付与付费 AI 服务。
"""

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["系统"], summary="服务信息")
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
    }


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    return {"status": "ok"}
