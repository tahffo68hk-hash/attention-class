// 用真实 pytest 输出生成「测试通过」终端截图：demo-screenshots/06-pytest-pass.png
// 用法（仓库根目录）：
//   node scripts/pytest_shot.mjs            # 自动跑后端测试套件
//   PYTHON=/path/to/python node scripts/pytest_shot.mjs
// 说明：截图内容来自本次真实执行 stdout，不做任何改写；失败时同样如实截图。

let chromium
try {
  ;({ chromium } = await import('playwright'))
} catch {
  ;({ chromium } = await import(new URL('../frontend/node_modules/playwright/index.mjs', import.meta.url).href))
}
import { spawnSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = resolve(ROOT, 'demo-screenshots')
mkdirSync(OUT, { recursive: true })

const PY = process.env.PYTHON || 'python'
const args = ['-m', 'pytest', '-q', 'tests', 'tests_ward_map']
console.log('$ python ' + args.join(' '))

const started = Date.now()
const run = spawnSync(PY, args, {
  cwd: resolve(ROOT, 'backend'),
  encoding: 'utf8',
  timeout: 15 * 60 * 1000,
})
const raw = `${run.stdout ?? ''}${run.stderr ?? ''}`.trim()
const seconds = ((Date.now() - started) / 1000).toFixed(1)

// 截图要能直接放进作品集：去掉依赖噪声（warnings summary 里全是 site-packages 绝对路径），
// 并把残留的本机绝对路径换成占位符，避免暴露个人目录结构。
const sanitize = (text) => {
  const lines = text.split('\n')
  const start = lines.findIndex((l) => /warnings summary/.test(l))
  const end = start === -1 ? -1 : lines.findIndex((l, i) => i > start && /^-- Docs:/.test(l))
  return lines
    .filter((_, i) => start === -1 || i < start || (end !== -1 && i > end))
    .map((line) => {
      if (/^rootdir:/.test(line)) return 'rootdir: <repo>/backend'
      return line.replace(/[A-Za-z]:[\\/][^\r\n]*/g, '<path>')
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

const output = sanitize(raw)
console.log(output.split('\n').filter(Boolean).slice(-3).join('\n'))

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const colorize = (line) => {
  const e = esc(line)
  if (/^\s*\d+ passed/.test(e) || /\bpassed\b/.test(e) && !/failed|error/.test(e)) return `<span class="ok">${e}</span>`
  if (/FAILED|ERROR|failed|error/i.test(e)) return `<span class="bad">${e}</span>`
  if (/^=+ .* =+$/.test(e)) return `<span class="dim">${e}</span>`
  if (/^collected|^configfile|^plugins/.test(e)) return `<span class="dim">${e}</span>`
  return e
}

const html = `<!doctype html><meta charset="utf-8">
<style>
  html,body{margin:0;background:#0d1117;}
  .win{font:14px/1.55 "Cascadia Mono","Consolas",monospace;color:#c9d1d9;background:#0d1117;
       padding:0 0 22px;width:1180px;}
  .bar{display:flex;align-items:center;gap:8px;padding:10px 14px;background:#161b22;
       border-bottom:1px solid #21262d;font:13px "Segoe UI",sans-serif;color:#8b949e;}
  .dot{width:12px;height:12px;border-radius:50%;display:inline-block}
  .cmd{padding:14px 22px 6px;color:#e6edf3}
  .cmd b{color:#7ee787;font-weight:600}
  pre{margin:0;padding:4px 22px 0;white-space:pre-wrap;word-break:break-all}
  .ok{color:#3fb950;font-weight:600}
  .bad{color:#f85149;font-weight:600}
  .dim{color:#8b949e}
  .foot{padding:14px 22px 0;color:#8b949e;font:12px "Segoe UI",sans-serif}
</style>
<div class="win">
  <div class="bar">
    <span class="dot" style="background:#ff5f57"></span>
    <span class="dot" style="background:#febc2e"></span>
    <span class="dot" style="background:#28c840"></span>
    <span style="margin-left:10px">attention-class / backend — pytest</span>
  </div>
  <div class="cmd"><b>backend&gt;</b> python ${esc(args.join(' '))}</div>
  <pre>${output.split('\n').map(colorize).join('\n')}</pre>
  <div class="foot">真实执行输出 · 耗时 ${seconds}s · 生成于 ${new Date().toLocaleString('zh-CN')}</div>
</div>`

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1180, height: 400 }, deviceScaleFactor: 2 })
await page.setContent(html, { waitUntil: 'load' })
const box = await page.locator('.win').boundingBox()
await page.setViewportSize({ width: 1180, height: Math.ceil(box.height) })
await page.screenshot({ path: resolve(OUT, '06-pytest-pass.png') })
await browser.close()
console.log('saved 06-pytest-pass.png')
process.exit(run.status === 0 ? 0 : 1)
