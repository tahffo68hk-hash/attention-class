import http from './http'

export interface HealthResponse {
  status: string
}

export interface ServiceInfo {
  name: string
  version: string
  docs: string
  api_prefix: string
}

/** 健康检查（M0 阶段用于验证前后端连通性）。 */
export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/health')
  return data
}

/** 服务信息。 */
export async function fetchServiceInfo(): Promise<ServiceInfo> {
  const { data } = await http.get<ServiceInfo>('/')
  return data
}
