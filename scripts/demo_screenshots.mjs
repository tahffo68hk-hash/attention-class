// 演示截图脚本（Playwright + 本机 chromium）
// 用法：先启动 MySQL 3307 / 后端 8000 / 前端 5173，然后在仓库根目录执行
//   node scripts/demo_screenshots.mjs
// 输出：demo-screenshots/*.png
// 说明：脚本只使用 README 中公开的演示账号，不含任何真实凭据。

let chromium
try {
  // 常规情况：playwright 装在当前 node_modules 里
  ;({ chromium } = await import('playwright'))
} catch {
  // 本仓库把 playwright 放在 frontend/node_modules（前端 E2E 依赖）
  ;({ chromium } = await import(new URL('../frontend/node_modules/playwright/index.mjs', import.meta.url).href))
}
import { mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = resolve(ROOT, 'demo-screenshots')
const FRONT = process.env.FRONT_URL ?? 'http://127.0.0.1:5173'
const BACK = process.env.BACK_URL ?? 'http://127.0.0.1:8000'

mkdirSync(OUT, { recursive: true })

const shot = async (page, name) => {
  const path = resolve(OUT, name)
  await page.screenshot({ path })
  console.log('saved', name)
}

const settle = (page, ms = 900) => page.waitForTimeout(ms)

const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  locale: 'zh-CN',
})
const page = await ctx.newPage()
const consoleErrors = []
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text())
})
page.on('pageerror', (e) => consoleErrors.push(String(e)))

// 01 登录页
await page.goto(`${FRONT}/login`, { waitUntil: 'networkidle' })
await settle(page)
await shot(page, '01-login.png')

// 登录（演示账号）
await page.fill('#username', 'admin')
await page.fill('#password', 'admin123')
await page.click('button[type=submit], form button.btn--primary')
await page.waitForURL(/\/(dashboard|beds)/, { timeout: 20000 }).catch(() => {})
await settle(page, 1500)

// 02 床位列表
await page.goto(`${FRONT}/beds`, { waitUntil: 'networkidle' })
await settle(page, 1800)
await shot(page, '02-bed-list.png')

// 03 床位推荐 + 分配（选中第一条待入院住院证，采纳推荐第一名）
await page.goto(`${FRONT}/recommendations`, { waitUntil: 'networkidle' })
await page.waitForSelector('.list-item', { timeout: 20000 })
await page.click('.list-item')
await page.waitForTimeout(2500)
const adoptBtn = page.locator('button', { hasText: '采纳推荐第一名' })
if (await adoptBtn.count()) {
  await adoptBtn.first().click()
  // 只有真正写出分配记录后，页面才出现成功提示
  await page.waitForSelector('.alert--ok', { timeout: 15000 }).catch(() => {})
  await page.waitForTimeout(800)
}
await shot(page, '03-allocate.png')

// 04 审计日志
await page.goto(`${FRONT}/audit`, { waitUntil: 'networkidle' })
await settle(page, 2000)
await shot(page, '04-audit-log.png')

// 05 OpenAPI /docs
await page.goto(`${BACK}/docs`, { waitUntil: 'networkidle' })
await page.waitForSelector('.swagger-ui .opblock', { timeout: 20000 }).catch(() => {})
await settle(page, 1200)
await shot(page, '05-openapi-docs.png')

await browser.close()

if (consoleErrors.length) {
  console.log('\n--- console errors ---')
  consoleErrors.slice(0, 20).forEach((e) => console.log(e))
} else {
  console.log('\nno console errors')
}
