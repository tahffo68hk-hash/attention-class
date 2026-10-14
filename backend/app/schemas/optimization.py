"""P1 多患者联合优化预览契约；不包含任何可写入状态的命令。"""
from __future__ import annotations
from pydantic import BaseModel, Field


class OptimizationPreviewIn(BaseModel):
    admission_request_ids: list[int] = Field(min_length=1, max_length=30)
    solver: str = Field(default="auto", pattern="^(auto|flow|cp_sat)$")


class OptimizationPairOut(BaseModel):
    admission_request_id: int
    bed_id: int
    priority_rank: int
    score: float


class OptimizationResultOut(BaseModel):
    method: str
    pairs: list[OptimizationPairOut]
    unmatched_request_ids: list[int]
    admitted: int
    priority_sum: int
    score_sum: float
    runtime_ms: float
    proven_optimal: bool


class OptimizationPreviewOut(BaseModel):
    optimization_version: str = "multi-patient-matching-v1"
    score_version: str = "five-dimensional-current"
    generated_at: str
    admission_request_ids: list[int]
    request_count: int
    candidate_edges: int
    baseline: OptimizationResultOut
    optimized: OptimizationResultOut
    admitted_gain: int
    score_gain: float
    preview_only: bool = True
    message: str = "仅供教学模拟的排床预览；没有写入分配。确认前须在事务内重新校验所有约束。"
