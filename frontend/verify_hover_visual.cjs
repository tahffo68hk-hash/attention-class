/**
 * Ward Map Hover Visual V3 —— 离线确定性回归（无网络、无浏览器）。
 *
 * 与交付包 verify_hover_visual.cjs 的差异（本地适配，均不降低断言强度）：
 * 1. typescript 从本仓库 node_modules 解析（交付包写死了 Linux 全局路径）；
 * 2. 源码断言改为本仓库的缩进/命名风格（组件里有本机 V2 加固，
 *    例如保留 markShadowsDirty、floorGroup 拾取体坐标等）；
 * 3. 额外断言两条本轮修复项：
 *    - surfaceRest/surfaceHover 必须真的传进 selectable（交付包漏传会运行时抛错）；
 *    - 拾取体必须跟随筛选隐藏（拾取体挂在楼层 Group 上，
 *      若不单独置 visible，被筛掉的床仍能被点开抽屉）。
 *
 * 注意：本脚本**不能替代**真实 WebGL 浏览器验收，详见 docs/WARD_HOVER_V3_INTEGRATION.md。
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

let ts
try {
  ts = require('typescript')
} catch {
  ts = require(path.join(__dirname, 'node_modules', 'typescript'))
}

const base = path.join(__dirname, 'src/modules/ward-map')
const source = fs.readFileSync(path.join(base, 'hover-visual.ts'), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const mod = { exports: {} }
new Function('require', 'module', 'exports', compiled.outputText)(require, mod, mod.exports)
const { sceneBedPalette, fadedOccluderOpacity, easedApproach, isNear, HOVER_LIFT } = mod.exports

let count = 0
const check = (label, fn) => {
  fn()
  count++
  console.log('PASS', label)
}
const channel = (hex) => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
]

check('五态都有独立场景配色', () => assert.equal(Object.keys(sceneBedPalette).length, 5))

check('空闲仍为绿色，hover 转柔和黄色', () => {
  const [r, g] = channel(sceneBedPalette.AVAILABLE.base)
  assert(g > r)
  const [rr, gg, bb] = channel(sceneBedPalette.AVAILABLE.hover)
  assert(rr > 220 && gg > 150 && bb < 150)
})

check('已预占和已入住默认与 hover 都保持红色系', () => {
  for (const s of ['RESERVED', 'OCCUPIED'])
    for (const part of ['base', 'hover']) {
      const [r, g, b] = channel(sceneBedPalette[s][part])
      assert(r > g * 1.2 && r > b * 1.1, `${s} ${part}`)
    }
  assert.notEqual(sceneBedPalette.RESERVED.base, sceneBedPalette.OCCUPIED.base)
  for (const s of ['RESERVED', 'OCCUPIED']) {
    const [r, g, b] = channel(sceneBedPalette[s].surfaceBase)
    assert(r > g && r > b, `bedding ${s}`)
  }
})

check('楼板、地面、墙体、外壳淡化均保留非零空间轮廓', () => {
  for (const s of ['slab', 'floor', 'wall', 'frame', 'glass']) {
    const baseOpacity = s === 'glass' ? 0.105 : 1
    const fade = fadedOccluderOpacity(s, baseOpacity)
    assert(fade > 0 && fade < baseOpacity, s)
  }
})

check('恢复透明对象的目标不超过原始值', () => {
  for (const s of ['slab', 'floor', 'wall', 'frame', 'glass'])
    assert(fadedOccluderOpacity(s, 0.04) <= 0.04)
})

check('缓动值有界且不反向跳变', () => {
  for (const [a, b] of [
    [0, 1],
    [1, 0],
    [0.3, 0.8],
  ]) {
    for (const dt of [0, 0.001, 0.016, 0.033, 0.5]) {
      const x = easedApproach(a, b, dt)
      assert(x >= Math.min(a, b) && x <= Math.max(a, b))
    }
  }
})

check('高频 100 次床位切换后颜色/透明度都可恢复', () => {
  let opacity = 1
  let highlight = 0
  let y = 0
  let velocity = 0
  for (let i = 0; i < 100; i++) {
    const active = i % 2 === 0
    for (let frame = 0; frame < 3; frame++) {
      opacity = easedApproach(opacity, active ? 0.19 : 1, 1 / 60, 10)
      highlight = easedApproach(highlight, active ? 1 : 0, 1 / 60, 13)
      const dt = 1 / 60
      velocity += ((active ? HOVER_LIFT : 0) - y) * 155 * dt
      velocity *= Math.exp(-24 * dt)
      y += velocity * dt
    }
  }
  for (let i = 0; i < 130; i++) {
    opacity = easedApproach(opacity, 1, 1 / 60, 10)
    highlight = easedApproach(highlight, 0, 1 / 60, 13)
    const dt = 1 / 60
    velocity += (0 - y) * 155 * dt
    velocity *= Math.exp(-24 * dt)
    y += velocity * dt
  }
  assert(isNear(opacity, 1, 0.001))
  assert(isNear(highlight, 0, 0.001))
  assert(isNear(y, 0, 0.001))
})

check('拾取体不跟随升降床模型；遮挡物单独记录；无全局改色', () => {
  const v = fs.readFileSync(path.join(__dirname, 'src/components/WardScene3D.vue'), 'utf8')
  // 拾取体挂在楼层 Group，而不是会浮起的 bedGroup
  assert(/const pick = cube\(floorGroup,\s*glass,/.test(v))
  assert(v.includes('occlusionRaycaster.intersectObjects(occlusionMeshes, false)'))
  assert(v.includes('blocked.has(surface.mesh) ? surface.faded : surface.original'))
  assert(v.includes('const accent = status.clone()'))
  assert(v.includes('const surface = padding.clone()'))
  assert(v.includes('stopEffects()'))
  // 共享材质绝不能被就地改色：状态灯与床垫都要克隆
  assert(!/cube\(bedGroup,\s*status,/.test(v))
})

check('本轮修复：床垫基色随床传入，且拾取体跟随筛选隐藏', () => {
  const v = fs.readFileSync(path.join(__dirname, 'src/components/WardScene3D.vue'), 'utf8')
  // 交付包在 selectable.set 里漏传这两个字段，动画循环读到 undefined 会抛 TypeError
  assert(v.includes('surfaceRest: new THREE.Color(sceneBedPalette[bed.status].surfaceBase)'))
  assert(v.includes('surfaceHover: new THREE.Color(sceneBedPalette[bed.status].surfaceHover)'))
  // 拾取体在楼层 Group 上，必须单独跟随 visibleIds，否则被筛掉的床仍可点开
  assert(v.includes('item.pick.visible = ids.has(id)'))
})

check('组件脚本 TS 解析无语法错误', () => {
  for (const pathName of ['src/components/WardScene3D.vue', 'src/views/WardMapView.vue']) {
    const v = fs.readFileSync(path.join(__dirname, pathName), 'utf8')
    const raw = v.split('<script setup lang="ts">')[1]?.split('</script>')[0]
    assert(raw)
    const ast = ts.createSourceFile(pathName, raw, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS)
    assert.equal(ast.parseDiagnostics.length, 0, `${pathName} parse error`)
  }
})

console.log(`WARD_HOVER_VISUAL_TESTS: ${count}/${count} PASS`)