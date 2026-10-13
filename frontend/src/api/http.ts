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

/* ------------------------- 会话存储（localStorage） ------------------------- */

export const TOKEN_STORAGE_KEY = 'hba.token'
export const USER_STORAGE_KEY = 'hba.user'

export function readToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY)
}

export function writeToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
  localStorage.removeItem(USER_STORAGE_KEY)
}

/* --------------------------------- 实例 --------------------------------- */

const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = readToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status ?? 0

    // 令牌失效 / 过期：清理会话并回到登录页（登录接口自身除外，避免死循环）
    if (status === 401 && !window.location.pathname.startsWith('/login')) {
      clearSession()
      window.location.assign('/login')
    }

    if (error.response) {
      const body = error.response.data ?? { code: 'HTTP_ERROR', message: '请求失败' }
      return Promise.reject(new ApiError(status, body))
    }
    return Promise.reject(
      new ApiError(0, { code: 'NETWORK_ERROR', message: '无法连接后端服务，请确认服务已启动' }),
    )
  },
)

export default http
