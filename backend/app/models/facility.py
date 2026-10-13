"""科室、病房、床位实体。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import BedStatus, BedType, GenderLimit

if TYPE_CHECKING:
    from app.models.user import Doctor


class Department(Base, TimestampMixin):
    """科室。

    anchor_* 为该科室护士站/急救区在院内坐标网格上的位置，
    用于计算床位与该科室业务中心的距离（软约束评分输入）。
    """

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="科室编码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="科室名称")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    anchor_floor: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="护士站楼层")
    anchor_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="护士站 X 坐标")
    anchor_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="护士站 Y 坐标")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    wards: Mapped[list["Ward"]] = relationship(back_populates="department")
    beds: Mapped[list["Bed"]] = relationship(back_populates="department")
    doctors: Mapped[list["Doctor"]] = relationship(back_populates="department")

    __table_args__ = ({"comment": "科室表"},)


class Ward(Base, TimestampMixin):
    """病房。"""

    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="病房号")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="病房名称")
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    building: Mapped[str] = mapped_column(String(32), nullable=False, default="住院楼")
    floor: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="楼层")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    department: Mapped["Department"] = relationship(back_populates="wards")
    beds: Mapped[list["Bed"]] = relationship(back_populates="ward")

    __table_args__ = (
        Index("ix_wards_dept_floor", "department_id", "floor"),
        {"comment": "病房表"},
    )


class Bed(Base, TimestampMixin):
    """床位。"""

    __tablename__ = "beds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, comment="床位号")
    ward_id: Mapped[int] = mapped_column(
        ForeignKey("wards.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    bed_type: Mapped[BedType] = mapped_column(
        SAEnum(BedType, name="bed_type"), nullable=False, default=BedType.NORMAL
    )
    gender_limit: Mapped[GenderLimit] = mapped_column(
        SAEnum(GenderLimit, name="bed_gender_limit"),
        nullable=False,
        default=GenderLimit.ANY,
        comment="床位的性别限制",
    )
    is_isolation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否隔离床"
    )
    floor: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="楼层")
    position_x: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="X 坐标")
    position_y: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="Y 坐标")
    status: Mapped[BedStatus] = mapped_column(
        SAEnum(BedStatus, name="bed_status"),
        nullable=False,
        default=BedStatus.AVAILABLE,
        comment="床位状态",
    )
    daily_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), comment="日费用（元）"
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    ward: Mapped["Ward"] = relationship(back_populates="beds")
    department: Mapped["Department"] = relationship(back_populates="beds")

    __table_args__ = (
        CheckConstraint(
            "(bed_type = 'ISOLATION' AND is_isolation = 1) "
            "OR (bed_type <> 'ISOLATION' AND is_isolation = 0)",
            name="ck_beds_isolation_consistent",
        ),
        Index("ix_beds_dept_status", "department_id", "status"),
        Index("ix_beds_status_isolation", "status", "is_isolation"),
        Index("ix_beds_ward_status", "ward_id", "status"),
        {"comment": "床位表"},
    )
