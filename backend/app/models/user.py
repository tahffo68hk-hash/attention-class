"""用户与医生实体。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.facility import Department


class User(Base, TimestampMixin):
    """系统用户（用于认证与审计）。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="登录名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="口令散列")
    full_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.VIEWER, comment="角色"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近登录时间")

    doctor: Mapped["Doctor | None"] = relationship(
        back_populates="user", uselist=False, foreign_keys="Doctor.user_id"
    )

    __table_args__ = (
        Index("ix_users_role", "role"),
        {"comment": "系统用户表"},
    )


class Doctor(Base, TimestampMixin):
    """医生档案。"""

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True, comment="关联登录账号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, comment="所属科室"
    )
    title: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="职称")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="联系电话")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User | None"] = relationship(back_populates="doctor", foreign_keys=[user_id])
    department: Mapped["Department"] = relationship(back_populates="doctors")

    __table_args__ = (
        Index("ix_doctors_department", "department_id"),
        {"comment": "医生档案表"},
    )
