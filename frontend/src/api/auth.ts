import http from './http'
import type { LoginResponse, MessageOut, UserRead } from './types'

/** 登录获取访问令牌。 */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await http.post<LoginResponse>('/api/v1/auth/login', { username, password })
  return data
}

/** 获取当前登录用户。 */
export async function fetchMe(): Promise<UserRead> {
  const { data } = await http.get<UserRead>('/api/v1/auth/me')
  return data
}

/** 退出登录（后端会记录审计）。 */
export async function logout(): Promise<MessageOut> {
  const { data } = await http.post<MessageOut>('/api/v1/auth/logout', {})
  return data
}
