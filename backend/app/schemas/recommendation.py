"""床位推荐模型（可解释性输出）。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ScoreItem(BaseModel):
    key: str = Field(..., description="评分项标识")
    label: str = Field(..., description="评分项中文名")
    raw_score: float = Field(..., description="该项原始得分（0-100）")
    weight: float = Field(..., description="该项权重")
    contribution: float = Field(..., description="对总分的加权贡献")
    note: str = Field("", description="该项的解释")


class BedRecommendation(BaseModel):
    bed_id: int
    bed_code: str
    ward_id: int
    ward_code: str
    ward_name: str
    floor: int
    bed_type: str
    bed_type_label: str
    gender_limit: str
    gender_limit_label: str
    is_isolation: bool
    daily_rate: Decimal
    distance: float = Field(..., description="到科室护士站的加权距离")
    score: float = Field(..., description="综合得分（0-100）")
    score_items: list[ScoreItem]
    reasons: list[str]
    warnings: list[str] = Field(default_factory=list)


class HardConstraintStats(BaseModel):
    """硬约束过滤统计，用于解释"为什么没有床位"。"""

    department_total_beds: int = 0
    department_available_beds: int = 0
    candidates_after_status: int = 0
    excluded_by_status: int = 0
    excluded_by_gender: int = 0
    excluded_by_isolation: int = 0
    status_breakdown: dict[str, int] = Field(default_factory=dict)


class RecommendationResponse(BaseModel):
    admission_request_id: int
    certificate_no: str
    patient_id: int
    patient_name: str
    patient_gender: str
    patient_gender_label: str
    department_id: int
    department_name: str
    priority: str
    priority_label: str
    priority_rank: int
    isolation_required: bool
    candidates_evaluated: int
    recommendations: list[BedRecommendation]
    hard_constraint_stats: HardConstraintStats
    no_result_reasons: list[str] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)
    generated_at: str
