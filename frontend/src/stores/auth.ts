import { computed, ref } from 'vue'

import * as authApi from '@/api/auth'
import { USER_STORAGE_KEY, clearSession, readToken, writeToken } from '@/api/http'
import type { LoginResponse, UserRead } from '@/api/types'

function readStoredUser(): UserRead | null {
  const raw = localStorage.getItem(USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserRead
  } catch {
    return null
  }
}

const currentUser = ref<UserRead | null>(readStoredUser())
const isAuthenticated = computed(() => Boolean(readToken()))

const role = computed(() => currentUser.value?.role ?? '')

const isAdmin = computed(() => role.value === 'ADMIN')
const isDoctor = computed(() => role.value === 'DOCTOR')
const isNurse = computed(() => role.value === 'NURSE')
const isViewer = computed(() => role.value === 'VIEWER')

/** 开具住院证（医生 / 管理员） */
const canIssueCertificate = computed(() => isAdmin.value || isDoctor.value)
/** 预入院登记（护士 / 医生 / 管理员） */
const canPreadmit = computed(() => isAdmin.value || isDoctor.value || isNurse.value)
/** 床位预占用 / 入住 / 出院 / 释放（护士 / 管理员） */
const canOperateAllocation = computed(() => isAdmin.value || isNurse.value)
/** 查看患者明文（仅管理员，会写审计） */
const canRevealPatients = computed(() => isAdmin.value)

export function useAuth() {
  return {
    currentUser,
    isAuthenticated,
    role,
    isAdmin,
    isDoctor,
    isNurse,
    isViewer,
    canIssueCertificate,
    canPreadmit,
    canOperateAllocation,
    canRevealPatients,
    signIn,
    signOut,
    refreshUser,
  }
}

async function signIn(username: string, password: string): Promise<UserRead> {
  const res: LoginResponse = await authApi.login(username, password)
  writeToken(res.access_token)
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(res.user))
  currentUser.value = res.user
  return res.user
}

async function signOut(): Promise<void> {
  try {
    await authApi.logout()
  } catch {
    // 退出登录失败不阻塞本地会话清理
  }
  clearSession()
  currentUser.value = null
}

/** 拉取当前用户，令牌失效时会抛错（由 http 拦截器统一跳登录页）。 */
async function refreshUser(): Promise<UserRead> {
  const user = await authApi.fetchMe()
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user))
  currentUser.value = user
  return user
}
