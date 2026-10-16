"""床位硬约束与隔离床使用策略（推荐与分配共用，保证口径一致）。

硬约束（必须全部满足，任一不满足即不可分配）：

H1 床位状态必须为 AVAILABLE（空闲）。RESERVED / OCCUPIED / CLEANING / MAINTENANCE
   一律不可分配。
H2 科室必须与住院证开具的科室一致。
H3 性别限制必须匹配：床位 gender_limit 为 ANY，或与患者性别相同。
H4 隔离需求必须匹配：见下方隔离床使用策略。

隔离床使用策略（显式文档化，实现与文档同源）
------------------------------------------------
P1 住院证 isolation_required=True 的患者（隔离患者）**只能**分配到 is_isolation=True 的
   床位；分配到普通床属于违规，被 H4 拒绝。
P2 is_isolation=True 的床位（隔离床）**只对隔离患者开放**。非隔离患者即使本科室
   普通床已满、隔离床空置，也不得占用隔离床——这是为了避免隔离资源被挤占、
   并保持隔离单元的感染控制完整性。
P3 隔离床空置时状态仍为 AVAILABLE，但在推荐阶段会被硬约束过滤掉，不出现在
   非隔离患者的候选中；它会作为"因隔离属性被排除"计入过滤统计并出现在
   无床位原因说明里。
P4 隔离床的性别限制仍按 H3 生效：单间隔离床通常为 ANY，如设置为仅限某一性别，
   则另一性别患者不可使用该隔离床。
P5 隔离患者 + 无可用隔离床时，系统返回明确原因，不做降级到普通床的处理。
"""

from __future__ import annotations

import math

from app.models.enums import BedStatus, GenderLimit
from app.models.facility import Bed, Department

#: 一层楼折算成多少平面距离单位（用于把楼层差并入欧氏距离）
FLOOR_DISTANCE_UNIT = 3.0

POLICY_NOTES: list[str] = [
    "H1 只有状态为「空闲」的床位参与分配。",
    "H2 床位所属科室必须与住院证科室一致。",
    "H3 床位性别限制须为「不限性别」或与患者性别一致。",
    "H4 隔离患者只能使用隔离床；隔离床只对隔离患者开放（P1/P2）。",
    "P3 隔离床空置时仍显示为空闲，但不会进入非隔离患者的候选集。",
    "P4 隔离床的性别限制单独生效。",
    "P5 隔离患者无可用隔离床时直接返回原因，不降级到普通床。",
]


def distance_to_department(bed: Bed, department: Department) -> float:
    """床位到科室护士站的加权距离（楼层差按 FLOOR_DISTANCE_UNIT 折算）。"""
    dx = float(bed.position_x - department.anchor_x)
    dy = float(bed.position_y - department.anchor_y)
    df = float(bed.floor - department.anchor_floor) * FLOOR_DISTANCE_UNIT
    return math.sqrt(dx * dx + dy * dy + df * df)


def hard_constraint_violations(
    bed: Bed,
    *,
    department_id: int,
    patient_gender: str,
    isolation_required: bool,
) -> list[str]:
    """返回该床位对该住院证违反的硬约束描述；空列表表示通过。"""
    violations: list[str] = []
    if getattr(bed,'retired_at',None) is not None:
        violations.append('床位已正式停用，不得参与新的分配')

    if str(bed.status) != BedStatus.AVAILABLE.value:
        from app.models.enums import BED_STATUS_LABEL

        violations.append(
            f"H1 床位状态为「{BED_STATUS_LABEL.get(str(bed.status), str(bed.status))}」，非空闲，不可分配"
        )

    if bed.department_id != department_id:
        violations.append(f"H2 床位属于科室 ID {bed.department_id}，与住院证科室 ID {department_id} 不一致")

    if str(bed.gender_limit) != GenderLimit.ANY.value and str(bed.gender_limit) != patient_gender:
        limit_label = "男" if str(bed.gender_limit) == GenderLimit.MALE.value else "女"
        patient_label = "男" if patient_gender == "MALE" else "女"
        violations.append(f"H3 床位仅限{limit_label}性，患者为{patient_label}性，性别冲突")

    if isolation_required and not bed.is_isolation:
        violations.append("H4 患者需要隔离，但该床位不是隔离床（P1）")

    if not isolation_required and bed.is_isolation:
        violations.append("H4 该床位为隔离床，隔离床不向非隔离患者开放（P2）")

    return violations
