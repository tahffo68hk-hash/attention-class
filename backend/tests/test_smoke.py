"""M0 工程初始化冒烟测试（基础设施层）。

不依赖任何业务数据，验证：
* 应用可导入、路由已注册；
* /health 与 / 可访问；
* OpenAPI 文档可生成；
* 数据库连接可用、迁移版本表存在；
* 统一错误响应结构生效。

运行：pytest tests/test_smoke.py -v
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_engine


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_service_info(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_prefix"] == "/api/v1"
    assert body["docs"] == "/docs"


def test_openapi_document_is_generated(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == settings.APP_NAME
    assert len(spec["paths"]) > 0


def test_docs_page_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower()


def test_database_connection_and_migration_version():
    """数据库可连接，且 Alembic 已建立版本表。"""
    engine = get_engine()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version, "alembic_version 为空，请先执行 alembic upgrade head"


def test_unified_error_response_shape(client):
    """未携带令牌访问受保护接口时，错误响应结构统一。"""
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 401
    body = resp.json()
    for key in ("code", "message", "detail", "request_id"):
        assert key in body, f"统一错误响应缺少字段: {key}"
    assert body["code"] == "AUTH_TOKEN_INVALID"


def test_unknown_route_returns_unified_error(client):
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"
