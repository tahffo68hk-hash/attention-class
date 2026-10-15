"""Only fictional patient requests; a sandbox can never be submitted as a real allocation."""
from typing import Literal, Annotated
from pydantic import BaseModel, Field, ConfigDict, model_validator

class FictionalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: int = Field(ge=1, le=30, strict=True)
    department_id: int = Field(gt=0, strict=True)
    gender: Literal['MALE', 'FEMALE'] = 'FEMALE'
    priority: Literal['CRITICAL','SEVERE','URGENT','NORMAL','MILD'] = 'NORMAL'
    isolation_required: bool = False
    preferred_ward_id: int | None = Field(default=None, gt=0, strict=True)

class WardSupplyCut(BaseModel):
    ward_id: int = Field(gt=0, strict=True)
    count: int = Field(ge=1, le=20, strict=True)

class WardSandboxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_kind: Literal['SYNTHETIC_ONLY']
    synthetic_requests: list[FictionalRequest] = Field(min_length=1,max_length=30)
    unavailable_bed_ids: list[Annotated[int,Field(gt=0,strict=True)]] = Field(default_factory=list,max_length=100)
    ward_supply_cut: WardSupplyCut | None = None

    @model_validator(mode='after')
    def check_distinct(self):
        if len({r.scenario_id for r in self.synthetic_requests}) != len(self.synthetic_requests):
            raise ValueError('模拟申请序号不可重复')
        if len(set(self.unavailable_bed_ids)) != len(self.unavailable_bed_ids):
            raise ValueError('排除床位 ID 不可重复')
        return self

class SandboxCandidate(BaseModel):
    scenario_id: int
    bed_id: int
    bed_code: str
    score: float
    score_items: dict[str, float]
    hard_constraints: Literal['PASS'] = 'PASS'

class SandboxPair(BaseModel):
    scenario_id: int
    bed_id: int
    score: float
    priority_rank: int

class SandboxSolution(BaseModel):
    method: str
    proven_optimal: bool
    admitted: int
    priority_sum: int
    score_sum: float
    runtime_ms: float
    pairs: list[SandboxPair]
    unmatched_scenario_ids: list[int]

class WardSandboxOutput(BaseModel):
    scenario_kind: Literal['SYNTHETIC_ONLY'] = 'SYNTHETIC_ONLY'
    preview_only: Literal[True] = True
    snapshot_at: str
    snapshot_fingerprint: str
    applied_unavailable_bed_ids: list[int]
    request_count: int
    candidate_count: int
    candidates: list[SandboxCandidate]
    greedy: SandboxSolution
    optimized: SandboxSolution
    no_database_writes: Literal[True] = True
