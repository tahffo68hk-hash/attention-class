/**
 * P2.5 浏览器烟测（前端为 WorkBuddy 自建 UI，已按本仓库路由/登录选择器改造）。
 *
 * 只做登录 + 路由可达性 + 后端连通性检查，不创建业务记录、不调用付费 AI。
 * 运行前需：
 *   1. 已启动后端（:8000）与前端 dev server（:5173）
 *   2. `npm i -D @playwright/test && npx playwright install chromium`
 *   3. 设置演示专用账号（仅本机虚构数据）：
 *        E2E_USERNAME=admin  E2E_PASSWORD=admin123  E2E_URL=http://127.0.0.1:5173
 *      然后 `npm run test:e2e`
 */
import { test, expect } from '@playwright/test'

const base = process.env.E2E_URL || 'http://127.0.0.1:5173'
const username = process.env.E2E_USERNAME
const password = process.env.E2E_PASSWORD

const ROUTES = [
  '/dashboard',
  '/admissions',
  '/recommendations',
  '/beds',
  '/allocations',
  '/optimization',
  '/assistant',
  '/audit',
  '/system-status',
]

test('登录、业务路由与真实后端连通性', async ({ page }) => {
  test.skip(!username || !password, '请设置仅供演示的 E2E_USERNAME / E2E_PASSWORD')

  await page.goto(`${base}/login`)
  await page.locator('#username').fill(username!)
  await page.locator('#password').fill(password!)
  await page.getByRole('button', { name: /登\s*录/ }).click()
  await expect(page).not.toHaveURL(/\/login(?:\?|$)/)

  for (const path of ROUTES) {
    await page.goto(`${base}${path}`)
    await expect(page).not.toHaveURL(/\/login(?:\?|$)/)
    await expect(page.locator('body')).not.toContainText('Internal Server Error')
    await expect(page.locator('body')).not.toContainText('无法连接后端服务')
  }
})
