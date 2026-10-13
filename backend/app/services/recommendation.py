"""智能床位推荐引擎。

流程
----
1. 硬约束过滤（H1-H4，见 ``bed_policy``），产出候选集并统计每一层排除原因；
2. 对候选集执行软约束打分（0-100，可解释）；
3. 按分数倒序输出，附每项得分明细与中文推荐理由；
4. 候选集为空时给出明确原因。

软约束评分模型（权重合计 1.00）
--------------------------------
| 评分项 | 权重 | 说明 |
| --- | --- | --- |
| 距离适配 distance | 0.32 | 床位到科室护士站的加权距离，**方向随优先级反转** |
| 优先级-床型适配 priority_fit | 0.28 | 危重/重症偏好监护床与低楼层，轻症/普通让出监护床与近端床位 |
| 病房负载均衡 ward_balance | 0.18 | 优先分配到空床率更高的病房，避免单病房过载 |
| 成本适配 cost | 0.12 | 日费用越低得分越高，**敏感度随优先级变化** |
| 期望病房 preference | 0.10 | 命中患者/科室期望病房时加分 |

优先级不是常数：``PRIORITY_PROFILE`` 同时影响距离方向、床型匹配矩阵与成本敏感度，
因此同一张床对不同优先级患者会得到**不同**的分数与不同的排序结果。
"""

from __future__ import annotations

import math  # noqa: F401  (保留：距离计算辅助)
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.masking import mask_name
from app.models.enums import (
    BED_STATUS_LABEL,
    BED_TYPE_LABEL,
    GENDER_LABEL,
    PRIORITY_LABEL,
    PRIORITY_RANK,
    BedStatus,
    BedType,
    GenderLimit,
    PatientPriority,
)
from app.models.admission import AdmissionRequest
from app.models.facility import Bed
from app.schemas.recommendation import (
    BedRecommendation,
    HardConstraintStats,
    RecommendationResponse,
    ScoreItem,
)
from app.services import bed_policy

#: 各评分项权重，合计 1.00
WEIGHTS: dict[str, float] = {
    "distance": 0.32,
    "priority_fit": 0.28,
    "ward_balance": 0.18,
    "cost": 0.12,
    "preference": 0.10,
}

SCORE_LABELS: dict[str, str] = {
    "distance": "距离适配",
    "priority_fit": "优先级-床型适配",
    "ward_balance": "病房负载均衡",
    "cost": "成本适配",
    "preference": "期望病房",
}

#: 距离归一化上限（加权距离单位）
MAX_DISTANCE = 60.0

#: 床型适配矩阵：优先级 -> 床型 -> 原始分
BED_TYPE_FIT: dict[str, dict[str, float]] = {
    PatientPriority.CRITICAL.value: {BedType.MONITOR.value: 100.0, BedType.ISOLATION.value: 86.0, BedType.NORMAL.value: 30.0},
    PatientPriority.SEVERE.value: {BedType.MONITOR.value: 94.0, BedType.ISOLATION.value: 86.0, BedType.NORMAL.value: 46.0},
    PatientPriority.URGENT.value: {BedType.MONITOR.value: 76.0, BedType.ISOLATION.value: 84.0, BedType.NORMAL.value: 72.0},
    PatientPriority.NORMAL.value: {BedType.MONITOR.value: 34.0, BedType.ISOLATION.value: 84.0, BedType.NORMAL.value: 100.0},
    PatientPriority.MILD.value: {BedType.MONITOR.value: 20.0, BedType.ISOLATION.value: 84.0, BedType.NORMAL.value: 100.0},
}


@dataclass(frozen=True)
class PriorityProfile:
    """优先级画像：决定距离方向、楼层偏好与成本敏感度。"""

    distance_mode: str          # "near"（越近越好） / "far"（让出近端）
    distance_sensitivity: float  # near 模式下的惩罚倍率
    cost_sensitivity: float      # 0-1，越大越在意费用
    floor_bonus: float           # 低楼层加分（-1/1 层）
    label: str


PRIORITY_PROFILE: dict[str, PriorityProfile] = {
    PatientPriority.CRITICAL.value: PriorityProfile("near", 1.60, 0.30, 9.0, "危重"),
    PatientPriority.SEVERE.value: PriorityProfile("near", 1.35, 0.45, 6.0, "重症"),
    PatientPriority.URGENT.value: PriorityProfile("near", 1.00, 0.70, 3.0, "急症"),
    PatientPriority.NORMAL.value: PriorityProfile("far", 0.55, 0.90, 0.0, "普通"),
    PatientPriority.MILD.value: PriorityProfile("far", 0.35, 1.00, 0.0, "轻症"),
}


@dataclass
class _Candidate:
    bed: Bed
    distance: float
    ward_free: int
    ward_total: int


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _score_distance(distance: float, profile: PriorityProfile) -> tuple[float, str]:
    if profile.distance_mode == "near":
        raw = 100.0 - distance * profile.distance_sensitivity * (100.0 / MAX_DISTANCE)
        raw = _clamp(raw)
        note = (
            f"{profile.label}患者优先靠近护士站：加权距离 {distance:.1f}，"
            f"距离敏感度 ×{profile.distance_sensitivity:.2f}，得分 {raw:.1f}"
        )
    else:
        ratio = min(distance, MAX_DISTANCE) / MAX_DISTANCE
        raw = _clamp(55.0 + ratio * 45.0)
        note = (
            f"{profile.label}患者让出近端床位给重症：加权距离 {distance:.1f}，"
            f"越远得分越高，得分 {raw:.1f}"
        )
    return raw, note


def _score_priority_fit(bed: Bed, rank: int, priority: str) -> tuple[float, str]:
    table = BED_TYPE_FIT[priority]
    base = table.get(str(bed.bed_type), 60.0)
    type_label = BED_TYPE_LABEL.get(str(bed.bed_type), str(bed.bed_type))

    floor_delta = 0.0
    profile = PRIORITY_PROFILE[priority]
    if profile.floor_bonus > 0:
        if bed.floor <= 1:
            floor_delta = profile.floor_bonus
        elif bed.floor >= 3:
            floor_delta = -profile.floor_bonus

    raw = _clamp(base + floor_delta)
    parts = [f"{profile.label}患者对「{type_label}」的基础适配 {base:.0f}"]
    if floor_delta:
        parts.append(
            f"位于 {bed.floor} 层{'（低楼层，转运更快）' if floor_delta > 0 else '（高楼层，转运较慢）'}"
            f" {floor_delta:+.0f}"
        )
    parts.append(f"该项得分 {raw:.1f}")
    return raw, "；".join(parts)


def _score_ward_balance(free: int, total: int) -> tuple[float, str]:
    if total <= 0:
        return 0.0, "病房无床位数据"
    ratio = free / total
    raw = _clamp(100.0 * ratio)
    return raw, f"该病房 {free}/{total} 张空闲，空床率 {ratio * 100:.0f}%，得分 {raw:.1f}"


def _score_cost(rate: Decimal, low: Decimal, high: Decimal, profile: PriorityProfile) -> tuple[float, str]:
    if high <= low:
        cheapness = 100.0
    else:
        cheapness = 100.0 * float((high - rate) / (high - low))
    raw = _clamp(100.0 - (100.0 - cheapness) * (1.0 - profile.cost_sensitivity))
    note = (
        f"日费用 ¥{rate:.2f}（候选区间 ¥{low:.2f}-¥{high:.2f}），"
        f"{profile.label}患者成本敏感度 {profile.cost_sensitivity:.2f}，得分 {raw:.1f}"
    )
    return raw, note


def _score_preference(bed: Bed, preferred_ward_id: int | None) -> tuple[float, str]:
    if preferred_ward_id is None:
        return 60.0, "未指定期望病房，取中性分 60"
    if bed.ward_id == preferred_ward_id:
        return 100.0, "命中患者/科室期望病房，得 100"
    return 55.0, "非期望病房，得 55"


def scan_candidates(
    db: Session,
    request: AdmissionRequest,
) -> tuple[list[_Candidate], HardConstraintStats]:
    """执行硬约束过滤并返回候选集与分层统计。"""
    beds: list[Bed] = list(
        db.execute(
            select(Bed)
            .options(joinedload(Bed.ward), joinedload(Bed.department))
            .where(Bed.department_id == request.department_id)
        )
        .unique()
        .scalars()
    )

    status_breakdown: dict[str, int] = {}
    for bed in beds:
        key = str(bed.status)
        status_breakdown[key] = status_breakdown.get(key, 0) + 1

    stats = HardConstraintStats(
        department_total_beds=len(beds),
        department_available_beds=status_breakdown.get(BedStatus.AVAILABLE.value, 0),
        status_breakdown=status_breakdown,
    )

    available = [b for b in beds if str(b.status) == BedStatus.AVAILABLE.value]
    stats.excluded_by_status = len(beds) - len(available)
    stats.candidates_after_status = len(available)

    isolation_required = bool(request.isolation_required)
    if isolation_required:
        after_isolation = [b for b in available if b.is_isolation]
    else:
        after_isolation = [b for b in available if not b.is_isolation]
    stats.excluded_by_isolation = len(available) - len(after_isolation)

    patient_gender = str(request.patient.gender)
    after_gender = [
        b
        for b in after_isolation
        if str(b.gender_limit) == GenderLimit.ANY.value or str(b.gender_limit) == patient_gender
    ]
    stats.excluded_by_gender = len(after_isolation) - len(after_gender)

    # 病房负载快照
    ward_totals: dict[int, int] = {}
    ward_free: dict[int, int] = {}
    for bed in beds:
        ward_totals[bed.ward_id] = ward_totals.get(bed.ward_id, 0) + 1
        if str(bed.status) == BedStatus.AVAILABLE.value:
            ward_free[bed.ward_id] = ward_free.get(bed.ward_id, 0) + 1

    candidates = [
        _Candidate(
            bed=bed,
            distance=bed_policy.distance_to_department(bed, request.department),
            ward_free=ward_free.get(bed.ward_id, 0),
            ward_total=ward_totals.get(bed.ward_id, 0),
        )
        for bed in after_gender
    ]
    return candidates, stats


def _build_no_result_reasons(
    request: AdmissionRequest,
    stats: HardConstraintStats,
) -> list[str]:
    dept = request.department.name
    reasons: list[str] = []
    if stats.department_total_beds == 0:
        reasons.append(f"科室「{dept}」尚未配置任何床位，无法分配。")
        return reasons

    if stats.department_available_beds == 0:
        detail = "、".join(
            f"{BED_STATUS_LABEL.get(k, k)} {v} 张" for k, v in sorted(stats.status_breakdown.items())
        )
        reasons.append(
            f"科室「{dept}」当前没有任何空闲床位：共 {stats.department_total_beds} 张（{detail}）。"
        )

    if request.isolation_required:
        if stats.candidates_after_status > 0 and stats.excluded_by_isolation == stats.candidates_after_status:
            reasons.append(
                f"患者需要隔离，但科室「{dept}」当前 {stats.candidates_after_status} 张空闲床位"
                f"全部为普通床，没有可用隔离床（策略 P5：不降级到普通床）。"
            )
        elif stats.candidates_after_status > 0 and stats.excluded_by_gender > 0:
            reasons.append(
                "科室存在空闲隔离床，但其性别限制与患者性别不一致（H3）。"
            )
    else:
        if stats.candidates_after_status > 0 and stats.excluded_by_isolation == stats.candidates_after_status:
            reasons.append(
                f"科室「{dept}」的空闲床位全部为隔离床。按策略 P2，隔离床只对隔离患者开放，"
                "非隔离患者不得占用。"
            )
        elif stats.excluded_by_gender > 0:
            patient_label = GENDER_LABEL.get(str(request.patient.gender), str(request.patient.gender))
            reasons.append(
                f"科室存在空闲普通床 {stats.candidates_after_status} 张，但其中 "
                f"{stats.excluded_by_gender} 张的性别限制与患者（{patient_label}）冲突（H3）。"
            )

    if not reasons:
        reasons.append(
            f"科室「{dept}」没有同时满足「空闲 + 科室匹配 + 性别匹配 + 隔离匹配」的床位。"
        )
    return reasons


def recommend_beds(
    db: Session,
    request: AdmissionRequest,
    limit: int = 10,
) -> RecommendationResponse:
    """对住院证生成可解释的床位推荐列表。"""
    candidates, stats = scan_candidates(db, request)

    priority = str(request.priority)
    rank = PRIORITY_RANK.get(priority, 2)
    profile = PRIORITY_PROFILE.get(priority, PRIORITY_PROFILE[PatientPriority.NORMAL.value])
    preferred_ward_id = request.preferred_ward_id

    rates = [c.bed.daily_rate for c in candidates]
    low_rate = min(rates) if rates else Decimal("0")
    high_rate = max(rates) if rates else Decimal("0")

    results: list[BedRecommendation] = []
    for cand in candidates:
        bed = cand.bed

        d_raw, d_note = _score_distance(cand.distance, profile)
        p_raw, p_note = _score_priority_fit(bed, rank, priority)
        w_raw, w_note = _score_ward_balance(cand.ward_free, cand.ward_total)
        c_raw, c_note = _score_cost(bed.daily_rate, low_rate, high_rate, profile)
        f_raw, f_note = _score_preference(bed, preferred_ward_id)

        items = [
            ScoreItem(
                key="distance",
                label=SCORE_LABELS["distance"],
                raw_score=round(d_raw, 2),
                weight=WEIGHTS["distance"],
                contribution=round(d_raw * WEIGHTS["distance"], 4),
                note=d_note,
            ),
            ScoreItem(
                key="priority_fit",
                label=SCORE_LABELS["priority_fit"],
                raw_score=round(p_raw, 2),
                weight=WEIGHTS["priority_fit"],
                contribution=round(p_raw * WEIGHTS["priority_fit"], 4),
                note=p_note,
            ),
            ScoreItem(
                key="ward_balance",
                label=SCORE_LABELS["ward_balance"],
                raw_score=round(w_raw, 2),
                weight=WEIGHTS["ward_balance"],
                contribution=round(w_raw * WEIGHTS["ward_balance"], 4),
                note=w_note,
            ),
            ScoreItem(
                key="cost",
                label=SCORE_LABELS["cost"],
                raw_score=round(c_raw, 2),
                weight=WEIGHTS["cost"],
                contribution=round(c_raw * WEIGHTS["cost"], 4),
                note=c_note,
            ),
            ScoreItem(
                key="preference",
                label=SCORE_LABELS["preference"],
                raw_score=round(f_raw, 2),
                weight=WEIGHTS["preference"],
                contribution=round(f_raw * WEIGHTS["preference"], 4),
                note=f_note,
            ),
        ]
        total = _clamp(sum(i.contribution for i in items))

        reasons = [
            f"硬约束全部通过：状态空闲、科室「{request.department.name}」匹配、"
            f"性别限制为「{'不限' if str(bed.gender_limit) == 'ANY' else GENDER_LABEL.get(str(bed.gender_limit), str(bed.gender_limit)) + '性' if False else ('不限性别' if str(bed.gender_limit) == GenderLimit.ANY.value else ('仅限男性' if str(bed.gender_limit) == GenderLimit.MALE.value else '仅限女性'))}」"
            f"（患者{GENDER_LABEL.get(str(request.patient.gender), '')}）、"
            f"{'隔离床满足隔离需求' if request.isolation_required else '非隔离患者使用普通床'}。",
            f"距离：{bed_policy.distance_to_department(bed, request.department):.1f} 加权距离单位"
            f"（{bed.ward.name if bed.ward else ''} {bed.floor} 层 {bed.code} 床）。",
            p_note + "。",
            w_note + "。",
            f"成本：{c_note}。",
        ]
        if f_raw >= 100:
            reasons.append("该床位属于患者/科室期望病房，优先级提升。")

        warnings: list[str] = []
        if str(bed.bed_type) == BedType.MONITOR.value and rank <= 2:
            warnings.append("监护床资源紧张，轻症/普通患者占用会挤占重症资源（评分已下调）。")
        if bed.floor >= 3 and rank >= 4:
            warnings.append("楼层偏高，危重患者转运时间较长。")
        if cand.ward_free <= 1:
            warnings.append("该病房仅剩 1 张空床，收满后无法再收同一病房的患者。")

        results.append(
            BedRecommendation(
                bed_id=bed.id,
                bed_code=bed.code,
                ward_id=bed.ward_id,
                ward_code=bed.ward.code if bed.ward else "",
                ward_name=bed.ward.name if bed.ward else "",
                floor=bed.floor,
                bed_type=str(bed.bed_type),
                bed_type_label=BED_TYPE_LABEL.get(str(bed.bed_type), str(bed.bed_type)),
                gender_limit=str(bed.gender_limit),
                gender_limit_label={"MALE": "仅限男性", "FEMALE": "仅限女性", "ANY": "不限性别"}.get(
                    str(bed.gender_limit), str(bed.gender_limit)
                ),
                is_isolation=bed.is_isolation,
                daily_rate=bed.daily_rate,
                distance=round(cand.distance, 2),
                score=round(total, 2),
                score_items=items,
                reasons=reasons,
                warnings=warnings,
            )
        )

    results.sort(key=lambda r: (-r.score, r.distance, r.bed_id))
    results = results[:limit]

    return RecommendationResponse(
        admission_request_id=request.id,
        certificate_no=request.certificate_no,
        patient_id=request.patient_id,
        patient_name=mask_name(request.patient.name),
        patient_gender=str(request.patient.gender),
        patient_gender_label=GENDER_LABEL.get(str(request.patient.gender), ""),
        department_id=request.department_id,
        department_name=request.department.name,
        priority=priority,
        priority_label=PRIORITY_LABEL.get(priority, priority),
        priority_rank=rank,
        isolation_required=bool(request.isolation_required),
        candidates_evaluated=len(candidates),
        recommendations=results,
        hard_constraint_stats=stats,
        no_result_reasons=[] if results else _build_no_result_reasons(request, stats),
        policy_notes=bed_policy.POLICY_NOTES,
        generated_at=datetime.now().isoformat(timespec="seconds"),
    )
