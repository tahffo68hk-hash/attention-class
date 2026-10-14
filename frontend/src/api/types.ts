/**
 * 后端接口的数据类型（与 backend/app/schemas 一一对应）。
 *
 * 注意：后端 `Decimal` 字段经 Pydantic 序列化为**字符串**（如 "120.00"），
 * 因此 daily_rate / deposit_amount / AllocationRead.score 类型为 string。
 */

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface MessageOut {
  message: string
  detail?: Record<string, unknown> | null
}

/* ------------------------------- 认证 ------------------------------- */

export interface UserRead {
  id: number
  username: string
  full_name: string
  role: string
  role_label: string | null
  is_active: boolean
  doctor_id: number | null
  department_id: number | null
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserRead
}

/* ----------------------------- 基础数据 ----------------------------- */

export interface DepartmentRead {
  id: number
  code: string
  name: string
  description: string | null
  anchor_floor: number
  anchor_x: number
  anchor_y: number
  is_active: boolean
}

export interface WardRead {
  id: number
  code: string
  name: string
  department_id: number
  department_name: string | null
  building: string
  floor: number
  description: string | null
  total_beds: number
  available_beds: number
}

export interface BedRead {
  id: number
  code: string
  ward_id: number
  ward_code: string | null
  ward_name: string | null
  department_id: number
  department_name: string | null
  bed_type: string
  bed_type_label: string | null
  gender_limit: string
  gender_limit_label: string | null
  is_isolation: boolean
  floor: number
  position_x: number
  position_y: number
  status: string
  status_label: string | null
  daily_rate: string
  note: string | null
  current_patient_name: string | null
  current_patient_id: number | null
}

export interface PatientRead {
  id: number
  medical_record_no: string
  name: string
  gender: string
  gender_label: string | null
  birth_date: string | null
  id_card: string | null
  phone: string | null
  address: string | null
  blood_type: string | null
  is_infectious: boolean
  allergy: string | null
  note: string | null
  masked: boolean
}

export interface DoctorRead {
  id: number
  name: string
  department_id: number
  department_name: string | null
  title: string | null
  phone: string | null
  is_active: boolean
  user_id: number | null
}

/* --------------------------- 住院证 / 预入院 --------------------------- */

export interface AdmissionRequestRead {
  id: number
  certificate_no: string
  patient_id: number
  patient_name: string | null
  patient_gender: string | null
  patient_gender_label: string | null
  department_id: number
  department_name: string | null
  doctor_id: number
  doctor_name: string | null
  priority: string
  priority_label: string | null
  isolation_required: boolean
  infection_type: string | null
  diagnosis: string | null
  preferred_ward_id: number | null
  preferred_ward_name: string | null
  notes: string | null
  status: string
  status_label: string | null
  issued_at: string | null
  queue_no: string | null
  deposit_status: string | null
  deposit_status_label: string | null
  deposit_amount: string | null
  active_bed_code: string | null
  allocation_status: string | null
  created_at: string | null
}

export interface AdmissionRequestCreate {
  patient_id: number
  department_id: number
  doctor_id?: number | null
  priority: string
  isolation_required: boolean
  infection_type?: string | null
  diagnosis?: string | null
  preferred_ward_id?: number | null
  notes?: string | null
  issue?: boolean
}

export interface PreadmissionRead {
  id: number
  admission_request_id: number
  certificate_no: string | null
  queue_no: string
  queue_sequence: number
  patient_id: number | null
  patient_name: string | null
  department_name: string | null
  contact_phone: string | null
  emergency_contact: string | null
  emergency_phone: string | null
  deposit_amount: string
  deposit_status: string
  deposit_status_label: string | null
  deposit_ref_no: string | null
  supplement_notes: string | null
  registered_at: string | null
  priority: string | null
  priority_label: string | null
  isolation_required: boolean | null
  created_at: string | null
}

export interface PreadmissionCreate {
  contact_phone?: string | null
  emergency_contact?: string | null
  emergency_phone?: string | null
  deposit_amount?: string | number
  pay_deposit?: boolean
  supplement_notes?: string | null
}

/* ------------------------------ 床位推荐 ------------------------------ */

export interface ScoreItem {
  key: string
  label: string
  raw_score: number
  weight: number
  contribution: number
  note: string
}

export interface BedRecommendation {
  bed_id: number
  bed_code: string
  ward_id: number
  ward_code: string
  ward_name: string
  floor: number
  bed_type: string
  bed_type_label: string
  gender_limit: string
  gender_limit_label: string
  is_isolation: boolean
  daily_rate: string
  distance: number
  score: number
  score_items: ScoreItem[]
  reasons: string[]
  warnings: string[]
}

export interface HardConstraintStats {
  department_total_beds: number
  department_available_beds: number
  candidates_after_status: number
  excluded_by_status: number
  excluded_by_gender: number
  excluded_by_isolation: number
  status_breakdown: Record<string, number>
}

export interface RecommendationResponse {
  admission_request_id: number
  certificate_no: string
  patient_id: number
  patient_name: string
  patient_gender: string
  patient_gender_label: string
  department_id: number
  department_name: string
  priority: string
  priority_label: string
  priority_rank: number
  isolation_required: boolean
  candidates_evaluated: number
  recommendations: BedRecommendation[]
  hard_constraint_stats: HardConstraintStats
  no_result_reasons: string[]
  policy_notes: string[]
  generated_at: string
}

/* ------------------------------ 床位分配 ------------------------------ */

export interface AllocationRead {
  id: number
  admission_request_id: number
  certificate_no: string | null
  patient_id: number
  patient_name: string | null
  department_name: string | null
  bed_id: number
  bed_code: string | null
  ward_name: string | null
  mode: string
  mode_label: string | null
  score: string | null
  reason: string | null
  status: string
  status_label: string | null
  operator_name: string | null
  reserved_at: string | null
  admitted_at: string | null
  discharged_at: string | null
  released_at: string | null
  cancel_reason: string | null
  created_at: string | null
}

export interface AllocationCreate {
  admission_request_id: number
  bed_id?: number | null
  confirm_top_recommendation?: boolean
  note?: string | null
}

export interface BedStatusLogRead {
  id: number
  bed_id: number
  bed_code: string | null
  from_status: string | null
  to_status: string
  reason: string | null
  allocation_id: number | null
  admission_request_id: number | null
  operator_name: string | null
  created_at: string | null
}

/* ------------------------------ 管理看板 ------------------------------ */

export interface DepartmentBedStat {
  department_id: number
  department_name: string
  total: number
  available: number
  reserved: number
  occupied: number
  cleaning: number
  maintenance: number
  occupancy_rate: number
}

export interface PriorityQueueStat {
  priority: string
  priority_label: string
  count: number
}

export interface DashboardSummary {
  total_beds: number
  available_beds: number
  reserved_beds: number
  occupied_beds: number
  cleaning_beds: number
  maintenance_beds: number
  occupancy_rate: number
  pending_admission_patients: number
  isolation_beds_total: number
  isolation_beds_available: number
  isolation_beds_in_use: number
  active_allocations: number
  admitted_today: number
  discharged_today: number
  department_stats: DepartmentBedStat[]
  pending_queue_by_priority: PriorityQueueStat[]
  generated_at: string
}

export interface AuditLogRead {
  id: number
  user_id: number | null
  username: string | null
  role: string | null
  action: string
  object_type: string | null
  object_id: string | null
  result: string
  detail: Record<string, unknown> | null
  ip: string | null
  created_at: string | null
}

/* -------------------------- 多患者联合排床（P1） -------------------------- */

export interface OptimizationPairOut {
  admission_request_id: number
  bed_id: number
  priority_rank: number
  score: number
}

export interface OptimizationResultOut {
  method: string
  pairs: OptimizationPairOut[]
  unmatched_request_ids: number[]
  admitted: number
  priority_sum: number
  score_sum: number
  runtime_ms: number
  proven_optimal: boolean
}

export interface OptimizationPreviewOut {
  optimization_version: string
  score_version: string
  generated_at: string
  admission_request_ids: number[]
  request_count: number
  candidate_edges: number
  baseline: OptimizationResultOut
  optimized: OptimizationResultOut
  admitted_gain: number
  score_gain: number
  preview_only: boolean
  message: string
}

/* --------------------------- 辅助解释（P2） --------------------------- */

export interface EvidenceScore {
  key: string
  raw_score: number
  contribution: number
}

export interface ExplainOut {
  version: string
  provider: string
  model: string | null
  real_ai: boolean
  externally_sent: boolean
  status: string
  message: string
  explanation: string
  cautions: string[]
  hard_constraints_passed: boolean
  score: number
  evidence: EvidenceScore[]
  warnings: string[]
  prompt_version: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: number | null
  /** P4：人民币费用估算（未配置费率时为 null，不是官方账单）。 */
  cost_estimate_cny: number | null
  latency_ms: number | null
  review_required: boolean
  performed_allocation: boolean
}

export interface PlanExplainOut {
  version: string
  provider: string
  real_ai: boolean
  externally_sent: boolean
  status: string
  model: string | null
  prompt_version: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_estimate_cny: number | null
  latency_ms: number | null
  preview_only: boolean
  explanation: string
  recommendations: string[]
  assigned_count: number
  unmatched_request_ids: number[]
  baseline_assigned_count: number
  review_required: boolean
}

/** P4：DeepSeek 服务状态（永不包含密钥）。 */
export interface ProviderStatus {
  provider: string
  model: string
  enabled: boolean
  real_call_requires_confirmation: boolean
  default_mode: string
  no_live_call: boolean
}
