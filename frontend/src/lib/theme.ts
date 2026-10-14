/**
 * 主题引导（Clinical SaaS Visual Redesign V1）
 *
 * - 明暗主题持久化在 localStorage 的 `attention-theme`；
 * - 首次访问（无记录）时跟随系统 prefers-color-scheme，但不落盘；
 * - 主题类挂在 <html> 上，保证 Teleport 到 body 的模态框同样跟随主题；
 * - 本模块不触碰任何业务状态与接口。
 */

export type ThemeName = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'attention-theme'

const root = (): HTMLElement | null =>
  typeof document === 'undefined' ? null : document.documentElement

/** 读取已保存的主题；无记录返回 null（表示「跟随系统」）。 */
export function readStoredTheme(): ThemeName | null {
  if (typeof localStorage === 'undefined') return null
  const raw = localStorage.getItem(THEME_STORAGE_KEY)
  return raw === 'dark' || raw === 'light' ? raw : null
}

function systemPrefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** 把主题写入 <html>，返回最终生效的主题。 */
export function applyTheme(theme: ThemeName | null): ThemeName {
  const effective: ThemeName = theme ?? (systemPrefersDark() ? 'dark' : 'light')
  const el = root()
  if (el) {
    el.classList.toggle('theme-dark', effective === 'dark')
    el.setAttribute('data-theme', effective)
  }
  return effective
}

/** 在明暗之间切换、持久化并应用；返回切换后的暗色状态。 */
export function toggleTheme(): boolean {
  const el = root()
  const currentlyDark = el ? el.classList.contains('theme-dark') : systemPrefersDark()
  const next: ThemeName = currentlyDark ? 'light' : 'dark'
  if (typeof localStorage !== 'undefined') localStorage.setItem(THEME_STORAGE_KEY, next)
  applyTheme(next)
  return next === 'dark'
}
