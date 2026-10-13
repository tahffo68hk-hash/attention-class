"""患者实体。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum as SAEnum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import Gender

if TYPE_CHECKING:
    from app.models.admission import AdmissionRequest


class Patient(Base, TimestampMixin):
    """患者档案（原型系统仅使用虚构数据）。"""

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    medical_record_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, comment="病案号"
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="姓名")
    gender: Mapped[Gender] = mapped_column(
        SAEnum(Gender, name="gender"), nullable=False, comment="性别"
    )
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="出生日期")
    id_card: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="证件号码")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="联系电话")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="联系地址")
    blood_type: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="血型")
    is_infectious: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否存在传染风险"
    )
    allergy: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="过敏史")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    admission_requests: Mapped[list["AdmissionRequest"]] = relationship(back_populates="patient")

    __table_args__ = (
        Index("ix_patients_name", "name"),
        Index("ix_patients_gender", "gender"),
        {"comment": "患者表（虚构数据）"},
    )
