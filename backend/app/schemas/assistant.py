"""P2 结构化证据和辅助说明契约。"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class ExplainIn(BaseModel):
    admission_request_id: int = Field(gt=0)
    bed_id: int = Field(gt=0)
    mode: Literal["rules", "llm"] = "rules"
    confirm_external_call: bool = False

class EvidenceScore(BaseModel):
    key: str
    raw_score: float
    contribution: float

class ExplainOut(BaseModel):
    version: str = "bed-explanation-v1"
    provider: str
    model: str | None = None
    real_ai: bool
    externally_sent: bool
    status: str
    message: str
    explanation: str
    cautions: list[str]
    hard_constraints_passed: bool
    score: float
    evidence: list[EvidenceScore]
    warnings: list[str] = Field(default_factory=list)
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    cost_estimate_cny: float | None = None
    latency_ms: float | None = None
    review_required: bool = True
    performed_allocation: bool = False

class PlanExplainIn(BaseModel):
    admission_request_ids: list[int] = Field(min_length=1, max_length=30)
    mode: Literal["rules", "llm"] = "rules"
    confirm_external_call: bool = False


class PlanExplainOut(BaseModel):
    version: str = "global-plan-explanation-v1"
    provider: str = "deterministic_rules"
    real_ai: bool = False
    externally_sent: bool = False
    status: str = "RULES_ONLY"
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_estimate_cny: float | None = None
    latency_ms: float | None = None
    preview_only: bool = True
    explanation: str
    recommendations: list[str]
    assigned_count: int
    unmatched_request_ids: list[int]
    baseline_assigned_count: int
    review_required: bool = True
