"""审计日志实体。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Enum as SAEnum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import AuditResult


class AuditLog(Base, TimestampMixin):
    """关键操作审计：操作人、时间、对象、动作、结果。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True, comment="操作人 ID")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="操作人登录名")
    role: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="操作人角色")
    action: Mapped[str] = mapped_column(String(64), nullable=False, comment="动作")
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="对象类型")
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="对象 ID")
    result: Mapped[AuditResult] = mapped_column(
        SAEnum(AuditResult, name="audit_result"), nullable=False, default=AuditResult.SUCCESS
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="上下文详情")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_created", "created_at"),
        Index("ix_audit_logs_user", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_object", "object_type", "object_id"),
        {"comment": "审计日志表"},
    )
