/**
 * 调度沙盘的**前端契约**（Spatial / Simulation V1）。
 *
 * 边界：这里只描述「完全虚构的申请」与只读结果，
 * 不采集姓名、证件号、病历号或任何真实患者标识；
 * 服务端也以 `extra="forbid"` 拒绝这些字段（见 backend/app/schemas/ward_sandbox.py）。
 * 沙盘结果**不是**分配承诺：正式分配/入住/换床仍走原业务 API。
 */

export type SandboxPriority = 'CRITICAL' | 'SEVERE' | 'URGENT' | 'NORMAL' | 'MILD'

export interface FictionalRequest {
  scenario_id: number
  department_id: number
  gender: 'MALE' | 'FEMALE'
  priority: SandboxPriority
  isolation_required: boolean
  preferred_ward_id: number | null
}

export interface SandboxInput {
  scenario_kind: 'SYNTHETIC_ONLY'
  synthetic_requests: FictionalRequest[]
  unavailable_bed_ids: number[]
  ward_supply_cut: { ward_id: number; count: number } | null
}

export interface SandboxCandidate {
  scenario_id: number
  bed_id: number
  bed_code: string
  score: number
  score_items: Record<string, number>
  hard_constraints: 'PASS'
}

export interface SandboxPair {
  scenario_id: number
  bed_id: number
  score: number
  priority_rank: number
}

export interface SandboxSolution {
  method: string
  proven_optimal: boolean
  admitted: number
  priority_sum: number
  score_sum: number
  runtime_ms: number
  pairs: SandboxPair[]
  unmatched_scenario_ids: number[]
}

export interface SandboxOutput {
  scenario_kind: 'SYNTHETIC_ONLY'
  preview_only: true
  snapshot_at: string
  snapshot_fingerprint: string
  applied_unavailable_bed_ids: number[]
  request_count: number
  candidate_count: number
  candidates: SandboxCandidate[]
  greedy: SandboxSolution
  optimized: SandboxSolution
  no_database_writes: true
}
