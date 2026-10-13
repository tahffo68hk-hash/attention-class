"""数据库引擎与会话工厂。"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine: Any | None = None
_SessionLocal: sessionmaker[Session] | None = None


def build_engine(url: str | None = None) -> Any:
    """按 URL 创建引擎；MySQL 走连接池，其它方言走默认配置。"""
    target = url or settings.DATABASE_URL
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if target.startswith("mysql"):
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=1800,
            isolation_level="READ COMMITTED",
        )
    elif target.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(target, echo=settings.SQL_ECHO, **kwargs)


def get_engine() -> Any:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """测试用：重置全局引擎与会话工厂。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
