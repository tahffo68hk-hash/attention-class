/**
 * [LOCAL HARDENING 2026-10-15] 沙盘轮廓在两条动效分支之间的一致性守卫。
 *
 * 背景：WardScene3D.vue 有两条高亮落地路径
 *   - animateEffects()        正常动效（RAF 缓动）
 *   - animateEffectsReduced() 用户开启「减弱动效」时的直接落地路径
 * 交付版本里 animateEffectsReduced 的透明度优先级链漏掉了 `unavailable`（沙盘临时
 * 停用）与 `top`（沙盘首选），于是**仅被 What-if 停用、又不在候选集**的床位会拿到
 * 灰色色值却 alpha=0 —— 3D 上灰色轮廓整块消失。颜色链是对的、透明度链是错的，
 * 单看颜色链根本发现不了，所以需要一条专门盯「两条链优先级顺序」的守卫。
 *
 * 本脚本只做源码结构检查（不启动浏览器），断言：
 *   1. 两条分支的**颜色**优先级顺序一致：unavailable > assigned > candidate
 *   2. 两条分支的**透明度**优先级顺序一致：hover > selected > unavailable > assigned > top > candidate > 0
 *   3. 透明度链里每一项的取值与另一条分支相同（0.92 / 0.75 / 0.64 / 0.82 / 0.75 / 0.5 / 0）
 *
 * 运行：NODE_PATH=frontend/node_modules node frontend/verify_reduced_motion_parity.cjs
 */
const fs = require('fs')
const path = require('path')

const SRC = process.env.WM_SCENE_SRC
  ? path.resolve(process.env.WM_SCENE_SRC)
  : path.join(__dirname, 'src', 'components', 'WardScene3D.vue')
const text = fs.readFileSync(SRC, 'utf8')

const RESULTS = []
function check(name, ok, detail) {
  RESULTS.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`)
}

function bodyOf(startMarker, endMarker) {
  const a = text.indexOf(startMarker)
  const b = text.indexOf(endMarker)
  if (a < 0 || b < 0 || b <= a) return null
  return text.slice(a, b)
}

const animated = bodyOf('function animateEffects(', 'function animateEffectsReduced(')
const reduced = bodyOf('function animateEffectsReduced(', 'function startEffects(')

check('定位到 animateEffects() 函数体', !!animated)
check('定位到 animateEffectsReduced() 函数体', !!reduced)

/**
 * 只取**透明度链所在的那段表达式**：颜色链在同函数里更靠前，若不切掉，
 * `unavailable ? / assigned ? / candidate ?` 会被重复计入，顺序就乱了。
 * 两条分支的写法还不同（动效路径用局部量 selected，减弱动效路径用 props.selectedId），
 * 所以这里把 token 归一成同一套名字再比顺序。
 */
function alphaRegion(body) {
  const m = body.match(/const\s+(outlineAlpha|alpha)\s*=/)
  return m ? body.slice(m.index) : null
}

function orderOf(region) {
  if (!region) return []
  const hits = []
  const push = (re, name) => {
    const r = new RegExp(re, 'g')
    let m
    while ((m = r.exec(region)) !== null) hits.push({ at: m.index, name })
  }
  push('\\bhovering\\s*\\?', 'hover')
  push('\\bon\\s*\\?', 'hover')
  push('props\\.selectedId\\s*\\?', 'selected')
  push('\\bselected\\s*\\?', 'selected')
  push('\\bunavailable\\s*\\?', 'unavailable')
  push('\\bassigned\\s*\\?', 'assigned')
  push('\\btop\\s*\\?', 'top')
  push('\\bcandidate\\s*\\?', 'candidate')
  hits.sort((x, y) => x.at - y.at)
  const seen = []
  for (const h of hits) if (!seen.includes(h.name)) seen.push(h.name)
  return seen
}

const animRegion = alphaRegion(animated || '')
const redRegion = alphaRegion(reduced || '')
check('定位到 animateEffects 的透明度链', !!animRegion)
check('定位到 animateEffectsReduced 的透明度链', !!redRegion)

const animOrder = orderOf(animRegion)
const redOrder = orderOf(redRegion)

// 两条分支各自应该出现的优先级顺序（透明度链）
const EXPECT = ['hover', 'selected', 'unavailable', 'assigned', 'top', 'candidate']

check(
  'animateEffects 透明度优先级含 unavailable 与 top',
  animOrder.includes('unavailable') && animOrder.includes('top'),
  animOrder.join(' > '),
)
check(
  'animateEffectsReduced 透明度优先级含 unavailable 与 top',
  redOrder.includes('unavailable') && redOrder.includes('top'),
  redOrder.join(' > '),
)
check(
  '两条分支优先级顺序完全一致',
  animOrder.join(',') === redOrder.join(','),
  `${animOrder.join(' > ')}  ||  ${redOrder.join(' > ')}`,
)
check(
  '顺序符合预期 hover>selected>unavailable>assigned>top>candidate',
  animOrder.join(',') === EXPECT.join(',') && redOrder.join(',') === EXPECT.join(','),
  `期望 ${EXPECT.join(' > ')}`,
)
check(
  'unavailable 优先于 assigned（停用必须压过命中）',
  animOrder.indexOf('unavailable') < animOrder.indexOf('assigned') &&
    redOrder.indexOf('unavailable') < redOrder.indexOf('assigned'),
)

// 透明度常量集合应完全一致（0.92/0.75/0.64/0.82/0.5/0）
/** 抽取形如 `? 0.64` / `: 0.92` 的透明度常量，只看透明度链区域。 */
function alphaConstants(region) {
  const vals = []
  if (!region) return vals
  const re = /[?:]\s*(0\.92|0\.75|0\.64|0\.82|0\.5|0)\b/g
  let m
  while ((m = re.exec(region)) !== null) vals.push(m[1])
  return vals
}

const animA = alphaConstants(animRegion)
const redA = alphaConstants(redRegion)
const setOf = (a) => [...new Set(a)].sort().join(',')
check(
  '两条分支的透明度常量集合一致',
  setOf(animA) === setOf(redA),
  `animateEffects=[${setOf(animA)}]  reduced=[${setOf(redA)}]`,
)
check(
  'unavailable 的透明度取 0.64（与动效路径一致）',
  /unavailable\s*\?\s*0\.64/.test(animated || '') && /unavailable\s*\?\s*0\.64/.test(reduced || ''),
)

// 颜色链：两条分支都必须按 unavailable > assigned > candidate 着色
const colorOrder = (body) => {
  const seg = (body || '').match(/outlineMaterial\.color\.set\(([\s\S]*?)\)/)
  if (!seg) return []
  const s = seg[1]
  const idx = (re) => {
    const m = s.match(re)
    return m ? m.index : 1e9
  }
  return [
    { n: 'unavailable', i: idx(/unavailable/) },
    { n: 'assigned', i: idx(/assigned/) },
    { n: 'candidate', i: idx(/candidate/) },
  ]
    .sort((a, b) => a.i - b.i)
    .map((x) => x.n)
}
const animColor = colorOrder(animated)
const redColor = colorOrder(reduced)
check(
  '两条分支颜色优先级一致（unavailable > assigned > candidate）',
  animColor.join(',') === 'unavailable,assigned,candidate' && redColor.join(',') === 'unavailable,assigned,candidate',
  `${animColor.join('>')}  ||  ${redColor.join('>')}`,
)

const failed = RESULTS.filter((r) => !r.ok)
console.log(
  `\nREDUCED_MOTION_PARITY ${RESULTS.length - failed.length}/${RESULTS.length} PASS — source check only, NOT Chromium acceptance`,
)
process.exit(failed.length ? 1 : 0)
