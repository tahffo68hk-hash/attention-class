/**
 * Ward Map 参数化空间 + 只读调度沙盘的真实 WebGL 冒烟用例。
 *
 * 只对 localhost 演示后端运行；需要 E2E_USERNAME / E2E_PASSWORD。
 * 不提交任何真实分配、患者，也不调用 DeepSeek。
 *
 * 本地适配（与交付包的差异）：
 * - 交付版假设登录页有「请输入演示账号 / 请输入密码」占位符与「登录工作台」按钮；
 *   本仓库登录页使用 `#username` / `#password` 与「登 录」按钮，故选择器按 id 定位，
 *   断言与业务语义完全不变；
 * - 截图落到 docs/screenshots/，与本轮其余真实浏览器证据放在一起。
 *
 * 注意：本机未安装 Playwright 浏览器二进制，本用例**仍未运行过**；
 * 真实 WebGL 验收由 docs/WARD_MAP_SPATIAL_SIMULATION_INTEGRATION.md 记录的
 * agent-browser / Chromium 流程完成，不依赖本文件。
 */
import { test, expect } from '@playwright/test'

const base = process.env.E2E_URL || 'http://127.0.0.1:5173'

test('Ward Map 参数化空间与只读沙盘 / 真正 WebGL', async ({ page }) => {
  test.skip(
    !process.env.E2E_USERNAME || !process.env.E2E_PASSWORD,
    'Need local demonstration account',
  )

  const jsErrors: string[] = []
  page.on('pageerror', (e) => jsErrors.push(String(e)))

  await page.goto(`${base}/login`)
  await page.locator('#username').fill(process.env.E2E_USERNAME!)
  await page.locator('#password').fill(process.env.E2E_PASSWORD!)
  await page.getByRole('button', { name: /登\s*录/ }).click()

  await page.goto(`${base}/ward-map`)
  await expect(page.getByText('病区床位态势图').first()).toBeVisible()

  const realCanvas = page.locator('.ward-scene-canvas canvas')
  await expect(realCanvas).toBeVisible()
  const gl = await realCanvas.evaluate((node) =>
    Boolean(
      (node as HTMLCanvasElement).getContext('webgl2') ||
        (node as HTMLCanvasElement).getContext('webgl'),
    ),
  )
  expect(gl).toBe(true)

  await page.getByRole('button', { name: /调度模拟/ }).click()
  await expect(page.getByText('智能调度沙盘')).toBeVisible()
  await expect(page.getByText(/无数据库写入/).first()).toBeVisible()

  await page.screenshot({
    path: 'docs/screenshots/ward-spatial-sandbox-real-webgl.png',
    fullPage: true,
  })
  expect(jsErrors).toEqual([])
})
