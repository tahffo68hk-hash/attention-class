"""住院证与预入院登记实体。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    AdmissionRequestStatus,
    DepositStatus,
    PatientPriority,
)

if TYPE_CHECKING:
    from app.models.facility import Department, Ward
    from app.models.patient import Patient
    from app.models.user import Doctor


class AdmissionRequest(Base, TimestampMixin):
    """住院证（住院申请单）。"""

    __tablename__ = "admission_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    certificate_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, comment="住院证编号"
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    priority: Mapped[PatientPriority] = mapped_column(
        SAEnum(PatientPriority, name="patient_priority"),
        nullable=False,
        default=PatientPriority.NORMAL,
        comment="病情优先级",
    )
    isolation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否需要隔离"
    )
    infection_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="感染类型")
    diagnosis: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="初步诊断")
    preferred_ward_id: Mapped[int | None] = mapped_column(
        ForeignKey("wards.id", ondelete="SET NULL"), nullable=True, comment="患者期望病房"
    )
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AdmissionRequestStatus] = mapped_column(
        SAEnum(AdmissionRequestStatus, name="admission_request_status"),
        nullable=False,
        default=AdmissionRequestStatus.DRAFT,
        index=True,
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开具时间")

    patient: Mapped["Patient"] = relationship(back_populates="admission_requests")
    department: Mapped["Department"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    preferred_ward: Mapped["Ward | None"] = relationship()
    preadmission: Mapped["Preadmission | None"] = relationship(
        back_populates="admission_request", uselist=False
    )

    __table_args__ = (
        Index("ix_admission_requests_dept_status", "department_id", "status"),
        Index("ix_admission_requests_priority", "priority"),
        {"comment": "住院证表"},
    )


class Preadmission(Base, TimestampMixin):
    """预入院登记（补充信息 + 模拟预交金）。"""

    __tablename__ = "preadmissions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    admission_request_id: Mapped[int] = mapped_column(
        ForeignKey("admission_requests.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    queue_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="排队号")
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deposit_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="预交金（模拟，不接入真实支付）"
    )
    deposit_status: Mapped[DepositStatus] = mapped_column(
        SAEnum(DepositStatus, name="deposit_status"),
        nullable=False,
        default=DepositStatus.PENDING,
        index=True,
    )
    deposit_ref_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="模拟缴费流水号"
    )
    supplement: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="补充信息（既往史/陪护等）"
    )
    supplement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    registered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    queue_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="队列序号（越小越靠前）"
    )

    admission_request: Mapped["AdmissionRequest"] = relationship(back_populates="preadmission")

    __table_args__ = (
        Index("ix_preadmissions_status_seq", "deposit_status", "queue_sequence"),
        {"comment": "预入院登记表"},
    )
