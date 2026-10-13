/**
 * 业务接口封装：基础数据 / 住院证 / 预入院 / 推荐 / 分配 / 看板 / 审计。
 *
 * 只调用现有后端接口，不改变任何核心业务规则。
 */
import http from './http'
import type {
  AdmissionRequestCreate,
  AdmissionRequestRead,
  AllocationCreate,
  AllocationRead,
  AuditLogRead,
  BedRead,
  BedStatusLogRead,
  DashboardSummary,
  DepartmentRead,
  DoctorRead,
  Page,
  PatientRead,
  PreadmissionCreate,
  PreadmissionRead,
  RecommendationResponse,
  WardRead,
} from './types'

type Query = Record<string, string | number | boolean | undefined | null>

function clean(params?: Query): Query | undefined {
  if (!params) return undefined
  const out: Query = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') out[k] = v
  }
  return out
}

/* ------------------------------ 基础数据 ------------------------------ */

export async function fetchDepartments(params?: Query): Promise<DepartmentRead[]> {
  const { data } = await http.get<DepartmentRead[]>('/api/v1/departments', { params: clean(params) })
  return data
}

export async function fetchWards(params?: Query): Promise<WardRead[]> {
  const { data } = await http.get<WardRead[]>('/api/v1/wards', { params: clean(params) })
  return data
}

export async function fetchBeds(params?: Query): Promise<Page<BedRead>> {
  const { data } = await http.get<Page<BedRead>>('/api/v1/beds', { params: clean(params) })
  return data
}

export async function fetchBed(bedId: number): Promise<BedRead> {
  const { data } = await http.get<BedRead>(`/api/v1/beds/${bedId}`)
  return data
}

export async function fetchBedStatusLogs(bedId: number, limit = 50): Promise<BedStatusLogRead[]> {
  const { data } = await http.get<BedStatusLogRead[]>(`/api/v1/beds/${bedId}/status-logs`, {
    params: { limit },
  })
  return data
}

/** 管理员手工调整床位状态（受后端状态机约束）。 */
export async function updateBedStatus(
  bedId: number,
  status: string,
  reason?: string,
): Promise<BedRead> {
  const { data } = await http.post<BedRead>(`/api/v1/beds/${bedId}/status`, { status, reason })
  return data
}

/** 释放床位（清洁中 -> 空闲）。 */
export async function releaseBed(bedId: number, reason?: string): Promise<BedRead> {
  const { data } = await http.post<BedRead>(`/api/v1/beds/${bedId}/release`, null, {
    params: clean({ reason }),
  })
  return data
}

export async function fetchPatients(params?: Query): Promise<Page<PatientRead>> {
  const { data } = await http.get<Page<PatientRead>>('/api/v1/patients', { params: clean(params) })
  return data
}

export async function fetchDoctors(params?: Query): Promise<DoctorRead[]> {
  const { data } = await http.get<DoctorRead[]>('/api/v1/doctors', { params: clean(params) })
  return data
}

/* -------------------------- 住院证 / 预入院 -------------------------- */

export async function fetchAdmissionRequests(
  params?: Query,
): Promise<Page<AdmissionRequestRead>> {
  const { data } = await http.get<Page<AdmissionRequestRead>>('/api/v1/admission-requests', {
    params: clean(params),
  })
  return data
}

export async function fetchAdmissionRequest(id: number): Promise<AdmissionRequestRead> {
  const { data } = await http.get<AdmissionRequestRead>(`/api/v1/admission-requests/${id}`)
  return data
}

export async function createAdmissionRequest(
  payload: AdmissionRequestCreate,
): Promise<AdmissionRequestRead> {
  const { data } = await http.post<AdmissionRequestRead>('/api/v1/admission-requests', payload)
  return data
}

export async function issueAdmissionRequest(id: number): Promise<AdmissionRequestRead> {
  const { data } = await http.post<AdmissionRequestRead>(`/api/v1/admission-requests/${id}/issue`)
  return data
}

export async function cancelAdmissionRequest(id: number): Promise<AdmissionRequestRead> {
  const { data } = await http.post<AdmissionRequestRead>(`/api/v1/admission-requests/${id}/cancel`)
  return data
}

export async function fetchPreadmission(requestId: number): Promise<PreadmissionRead> {
  const { data } = await http.get<PreadmissionRead>(
    `/api/v1/admission-requests/${requestId}/preadmission`,
  )
  return data
}

export async function createPreadmission(
  requestId: number,
  payload: PreadmissionCreate,
): Promise<PreadmissionRead> {
  const { data } = await http.post<PreadmissionRead>(
    `/api/v1/admission-requests/${requestId}/preadmission`,
    payload,
  )
  return data
}

/** 待入院队列（已完成预登记、尚未入住）。 */
export async function fetchQueue(params?: Query): Promise<Page<PreadmissionRead>> {
  const { data } = await http.get<Page<PreadmissionRead>>('/api/v1/preadmissions', {
    params: clean(params),
  })
  return data
}

/* ------------------------------ 智能推荐 ------------------------------ */

export async function fetchRecommendations(
  requestId: number,
  limit = 10,
): Promise<RecommendationResponse> {
  const { data } = await http.get<RecommendationResponse>(
    `/api/v1/admission-requests/${requestId}/bed-recommendations`,
    { params: { limit } },
  )
  return data
}

/* ------------------------------ 床位分配 ------------------------------ */

export async function fetchAllocations(params?: Query): Promise<Page<AllocationRead>> {
  const { data } = await http.get<Page<AllocationRead>>('/api/v1/allocations', {
    params: clean(params),
  })
  return data
}

export async function createAllocation(payload: AllocationCreate): Promise<AllocationRead> {
  const { data } = await http.post<AllocationRead>('/api/v1/allocations', payload)
  return data
}

export async function admitAllocation(allocationId: number): Promise<AllocationRead> {
  const { data } = await http.post<AllocationRead>(`/api/v1/allocations/${allocationId}/admit`)
  return data
}

export async function dischargeAllocation(
  allocationId: number,
  reason?: string,
): Promise<AllocationRead> {
  const { data } = await http.post<AllocationRead>(
    `/api/v1/allocations/${allocationId}/discharge`,
    { reason },
  )
  return data
}

export async function cancelAllocation(
  allocationId: number,
  reason?: string,
): Promise<AllocationRead> {
  const { data } = await http.post<AllocationRead>(`/api/v1/allocations/${allocationId}/cancel`, {
    reason,
  })
  return data
}

/* ------------------------------ 看板 / 审计 ------------------------------ */

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await http.get<DashboardSummary>('/api/v1/dashboard/summary')
  return data
}

export async function fetchAuditLogs(params?: Query): Promise<Page<AuditLogRead>> {
  const { data } = await http.get<Page<AuditLogRead>>('/api/v1/audit-logs', {
    params: clean(params),
  })
  return data
}
