import axios, { type AxiosInstance, type AxiosError } from 'axios'

/** 后端统一错误响应结构（与 backend/app/core/errors.py 保持一致）。 */
export interface ApiErrorBody {
  code: string
  message: string
  detail?: unknown
  request_id?: string
}

export class ApiError extends Error {
  code: string
  status: number
  requestId?: string
  detail?: unknown

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || '请求失败')
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.requestId = body.request_id
    this.detail = body.detail
  }
}

const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    if (error.response) {
      const body = error.response.data ?? { code: 'HTTP_ERROR', message: '请求失败' }
      return Promise.reject(new ApiError(error.response.status, body))
    }
    return Promise.reject(
      new ApiError(0, { code: 'NETWORK_ERROR', message: '无法连接后端服务，请确认服务已启动' }),
    )
  },
)

export default http
