"""床位分配记录与床位状态流水。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Computed,
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
from app.models.enums import AllocationMode, AllocationStatus, BedStatus

if TYPE_CHECKING:
    from app.models.admission import AdmissionRequest
    from app.models.facility import Bed
    from app.models.patient import Patient
    from app.models.user import User


class BedAllocation(Base, TimestampMixin):
    """床位分配记录。

    `active_bed_id` 是并发保护的关键：仅当分配处于 RESERVED / ADMITTED 时
    写入被占用床位的 id，其余状态写 NULL。配合唯一索引，
    数据库层面即可阻止同一床位被两条活动记录同时占用
    （MySQL 唯一索引允许多个 NULL，因此历史记录不受影响）。
    """

    __tablename__ = "bed_allocations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    admission_request_id: Mapped[int] = mapped_column(
        ForeignKey("admission_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bed_id: Mapped[int] = mapped_column(
        ForeignKey("beds.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    active_bed_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, unique=True, comment="活动占用标记（并发保护）"
    )
    # Generated from status: cannot be bypassed by forgetting to clear an application flag.
    active_request_id: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            "CASE WHEN status IN ('RESERVED', 'ADMITTED') "
            "THEN admission_request_id ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
        unique=True,
        comment="有效分配的住院证 ID：DB 保证单申请至多占一床",
    )
    mode: Mapped[AllocationMode] = mapped_column(
        SAEnum(AllocationMode, name="allocation_mode"),
        nullable=False,
        default=AllocationMode.MANUAL,
        comment="推荐确认 / 人工选择",
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True, comment="推荐得分")
    score_detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="得分明细（可解释性）"
    )
    reason: Mapped[Text | None] = mapped_column(Text, nullable=True, comment="推荐理由 / 操作说明")
    status: Mapped[AllocationStatus] = mapped_column(
        SAEnum(AllocationStatus, name="allocation_status"),
        nullable=False,
        default=AllocationStatus.RESERVED,
        index=True,
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="操作人"
    )
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    admission_request: Mapped["AdmissionRequest"] = relationship()
    patient: Mapped["Patient"] = relationship()
    bed: Mapped["Bed"] = relationship()
    operator: Mapped["User | None"] = relationship()

    __table_args__ = (
        Index("ix_allocations_status_time", "status", "created_at"),
        Index("ix_allocations_bed_status", "bed_id", "status"),
        {"comment": "床位分配记录表"},
    )


class BedStatusLog(Base, TimestampMixin):
    """床位状态变化流水（每次状态流转都留痕）。"""

    __tablename__ = "bed_status_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bed_id: Mapped[int] = mapped_column(
        ForeignKey("beds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[BedStatus | None] = mapped_column(
        SAEnum(BedStatus, name="bed_status"), nullable=True
    )
    to_status: Mapped[BedStatus] = mapped_column(SAEnum(BedStatus, name="bed_status"), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("bed_allocations.id", ondelete="SET NULL"), nullable=True
    )
    admission_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("admission_requests.id", ondelete="SET NULL"), nullable=True
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_bed_status_logs_bed_time", "bed_id", "created_at"),
        {"comment": "床位状态流水表"},
    )


class AllocationIdempotency(Base, TimestampMixin):
    """POST /allocations request identity, atomically committed with its result."""

    __tablename__ = "allocation_idempotency"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    allocation_id: Mapped[int | None] = mapped_column(
        ForeignKey("bed_allocations.id", ondelete="RESTRICT"), nullable=True
    )
    allocation: Mapped["BedAllocation | None"] = relationship()
