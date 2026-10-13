"""全局枚举与状态机定义。

所有枚举的 name 与 value 保持一致，便于直接落库为 MySQL ENUM。
"""

from __future__ import annotations

import enum
from typing import Final


class Gender(enum.StrEnum):
    MALE = "MALE"      # 男
    FEMALE = "FEMALE"  # 女


GENDER_LABEL: Final[dict[str, str]] = {"MALE": "男", "FEMALE": "女"}


class GenderLimit(enum.StrEnum):
    MALE = "MALE"      # 仅限男性
    FEMALE = "FEMALE"  # 仅限女性
    ANY = "ANY"        # 不限


class BedType(enum.StrEnum):
    NORMAL = "NORMAL"        # 普通床
    ISOLATION = "ISOLATION"  # 隔离床
    MONITOR = "MONITOR"      # 监护床


BED_TYPE_LABEL: Final[dict[str, str]] = {
    "NORMAL": "普通床",
    "ISOLATION": "隔离床",
    "MONITOR": "监护床",
}


class BedStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"      # 空闲可分配
    RESERVED = "RESERVED"        # 预占用（已锁床未入住）
    OCCUPIED = "OCCUPIED"        # 已入住
    CLEANING = "CLEANING"        # 出院后清洁中
    MAINTENANCE = "MAINTENANCE"  # 维护中


BED_STATUS_LABEL: Final[dict[str, str]] = {
    "AVAILABLE": "空闲",
    "RESERVED": "预占用",
    "OCCUPIED": "已入住",
    "CLEANING": "清洁中",
    "MAINTENANCE": "维护中",
}

#: 合法床位状态流转（from -> 允许的 to 集合）
BED_STATUS_TRANSITIONS: Final[dict[str, set[str]]] = {
    BedStatus.AVAILABLE.value: {BedStatus.RESERVED.value, BedStatus.MAINTENANCE.value},
    BedStatus.RESERVED.value: {BedStatus.OCCUPIED.value, BedStatus.AVAILABLE.value},
    BedStatus.OCCUPIED.value: {BedStatus.CLEANING.value},
    BedStatus.CLEANING.value: {BedStatus.AVAILABLE.value, BedStatus.MAINTENANCE.value},
    BedStatus.MAINTENANCE.value: {BedStatus.AVAILABLE.value},
}


class PatientPriority(enum.StrEnum):
    """病情优先级。数值越大越紧急。"""

    CRITICAL = "CRITICAL"  # 危重
    SEVERE = "SEVERE"      # 重症
    URGENT = "URGENT"      # 急症
    NORMAL = "NORMAL"      # 普通
    MILD = "MILD"          # 轻症


PRIORITY_RANK: Final[dict[str, int]] = {
    PatientPriority.CRITICAL.value: 5,
    PatientPriority.SEVERE.value: 4,
    PatientPriority.URGENT.value: 3,
    PatientPriority.NORMAL.value: 2,
    PatientPriority.MILD.value: 1,
}

PRIORITY_LABEL: Final[dict[str, str]] = {
    "CRITICAL": "危重",
    "SEVERE": "重症",
    "URGENT": "急症",
    "NORMAL": "普通",
    "MILD": "轻症",
}


class AdmissionRequestStatus(enum.StrEnum):
    DRAFT = "DRAFT"                # 草稿
    ISSUED = "ISSUED"              # 已开具
    PRE_ADMITTED = "PRE_ADMITTED"  # 已预入院登记
    ADMITTED = "ADMITTED"          # 已入住
    COMPLETED = "COMPLETED"        # 已出院结案
    CANCELLED = "CANCELLED"        # 已取消


ADMISSION_REQUEST_STATUS_LABEL: Final[dict[str, str]] = {
    "DRAFT": "草稿",
    "ISSUED": "已开具",
    "PRE_ADMITTED": "待入院",
    "ADMITTED": "已入住",
    "COMPLETED": "已出院",
    "CANCELLED": "已取消",
}

ADMISSION_REQUEST_TRANSITIONS: Final[dict[str, set[str]]] = {
    AdmissionRequestStatus.DRAFT.value: {
        AdmissionRequestStatus.ISSUED.value,
        AdmissionRequestStatus.CANCELLED.value,
    },
    AdmissionRequestStatus.ISSUED.value: {
        AdmissionRequestStatus.PRE_ADMITTED.value,
        AdmissionRequestStatus.CANCELLED.value,
    },
    AdmissionRequestStatus.PRE_ADMITTED.value: {
        AdmissionRequestStatus.ADMITTED.value,
        AdmissionRequestStatus.CANCELLED.value,
    },
    AdmissionRequestStatus.ADMITTED.value: {AdmissionRequestStatus.COMPLETED.value},
    AdmissionRequestStatus.COMPLETED.value: set(),
    AdmissionRequestStatus.CANCELLED.value: set(),
}


class AllocationStatus(enum.StrEnum):
    RESERVED = "RESERVED"      # 预占用
    ADMITTED = "ADMITTED"      # 已入住
    DISCHARGED = "DISCHARGED"  # 已出院
    CANCELLED = "CANCELLED"    # 已取消


ALLOCATION_STATUS_LABEL: Final[dict[str, str]] = {
    "RESERVED": "预占用",
    "ADMITTED": "已入住",
    "DISCHARGED": "已出院",
    "CANCELLED": "已取消",
}

ALLOCATION_TRANSITIONS: Final[dict[str, set[str]]] = {
    AllocationStatus.RESERVED.value: {
        AllocationStatus.ADMITTED.value,
        AllocationStatus.CANCELLED.value,
    },
    AllocationStatus.ADMITTED.value: {AllocationStatus.DISCHARGED.value},
    AllocationStatus.DISCHARGED.value: set(),
    AllocationStatus.CANCELLED.value: set(),
}


class AllocationMode(enum.StrEnum):
    RECOMMENDED = "RECOMMENDED"  # 采纳推荐
    MANUAL = "MANUAL"            # 人工选择


class DepositStatus(enum.StrEnum):
    PENDING = "PENDING"    # 待缴纳（模拟）
    PAID = "PAID"          # 已缴纳（模拟）
    REFUNDED = "REFUNDED"  # 已退还（模拟）


class UserRole(enum.StrEnum):
    ADMIN = "ADMIN"    # 系统管理员
    DOCTOR = "DOCTOR"  # 医生
    NURSE = "NURSE"    # 护士
    VIEWER = "VIEWER"  # 只读观察


USER_ROLE_LABEL: Final[dict[str, str]] = {
    "ADMIN": "系统管理员",
    "DOCTOR": "医生",
    "NURSE": "护士",
    "VIEWER": "只读用户",
}


class AuditResult(enum.StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class AuditAction(enum.StrEnum):
    LOGIN = "LOGIN"
    LOGIN_FAILED = "LOGIN_FAILED"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ISSUE_CERTIFICATE = "ISSUE_CERTIFICATE"
    PRE_ADMISSION = "PRE_ADMISSION"
    RECOMMEND = "RECOMMEND"
    RESERVE_BED = "RESERVE_BED"
    ADMIT = "ADMIT"
    DISCHARGE = "DISCHARGE"
    RELEASE_BED = "RELEASE_BED"
    CANCEL_ALLOCATION = "CANCEL_ALLOCATION"
    REVEAL_SENSITIVE = "REVEAL_SENSITIVE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
