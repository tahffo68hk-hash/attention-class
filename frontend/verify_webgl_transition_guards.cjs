/**
 * Ward Map —— 楼层过渡 / 标签页可见性 源码级守卫。
 *
 * 来源：交付包 `Attention_UIUX_WebGL_Transition_Followup_20261015` 的
 * `verify_webgl_transition_guards.cjs`，本地适配（断言强度不降）：
 * 1. typescript 从本仓库 node_modules 解析（交付包写死
 *    `/opt/nvm/.../typescript`，在本机必然 MODULE_NOT_FOUND）；
 * 2. 源码断言改为容忍本仓库的缩进与空格风格（交付包断言的是压缩写法，
 *    例如 `hoveredId!==null||props.selectedId!==null`，本机格式化后不匹配）；
 * 3. 新增两条本轮合并要点：
 *    - 遮挡目标选择必须能回退到 `props.selectedId`（交付包 baseline 特性，
 *      本机 V3 原本只认 hoveredId —— 不回退则「选中态过渡更新」是空转）；
 *    - `visibilitychange` 必须成对注册/反注册（本机 V3 原本完全没有该监听）。
 *
 * 【重要】本脚本只验证源码不变量，**不构成 Chromium/WebGL 行为验收**。
 * 真实浏览器证据见 docs/UIUX_WEBGL_TRANSITION_FOLLOWUP_INTEGRATION.md。
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

const componentPath = path.join(__dirname, 'src/components/WardScene3D.vue')
const source = fs.readFileSync(componentPath, 'utf8')
const script = source.split('<script setup lang="ts">')[1]?.split('</script>')[0]
assert(script, 'WardScene3D script setup not found')

const parsed = ts.createSourceFile(
  'WardScene3D.ts',
  script,
  ts.ScriptTarget.ES2022,
  true,
  ts.ScriptKind.TS,
)
assert.equal(parsed.parseDiagnostics.length, 0, 'WardScene3D TypeScript parsing failed')

let count = 0
const check = (label, condition) => {
  assert(condition, label)
  count++
  console.log('PASS', label)
}

/** 按花括号配对取出函数体，便于做「仅在该函数内成立」的断言。 */
function fnBody(name) {
  const start = script.indexOf(`function ${name}(`)
  assert(start >= 0, `missing ${name}`)
  const begin = script.indexOf('{', start)
  let depth = 0
  for (let i = begin; i < script.length; i++) {
    if (script[i] === '{') depth++
    else if (script[i] === '}' && --depth === 0) return script.slice(begin, i + 1)
  }
  throw new Error(`unterminated ${name}`)
}

const floorBody = fnBody('applyMode')
const occBody = fnBody('updateOcclusionTargets')
const effectsBody = fnBody('startEffects')
const visBody = fnBody('onDocumentVisibility')
const destroyBody = fnBody('destroy')

check(
  '点击选中的床在楼层动画中也更新遮挡',
  /if\s*\(\s*hoveredId\s*!==\s*null\s*\|\|\s*props\.selectedId\s*!==\s*null\s*\)/.test(floorBody),
)
check(
  '更新遮挡前同步场景世界矩阵',
  /root\.updateWorldMatrix\(\s*true\s*,\s*true\s*\)/.test(occBody),
)
check('更新遮挡前同步相机世界矩阵', /camera\.updateMatrixWorld\(\)/.test(occBody))
check(
  '遮挡目标优先悬停、其次回退到选中床',
  /const\s+targetId\s*=\s*hoveredId\s*\?\?\s*props\.selectedId/.test(occBody),
)
check(
  '隐藏页面时不重新启动效果 RAF',
  /if\s*\(\s*document\.hidden\s*\)\s*\{\s*stopEffects\(\)\s*;?\s*return\s*\}/.test(effectsBody),
)
check(
  '隐藏页面时取消相机 RAF',
  /cancelAnimationFrame\(animationFrame\)/.test(visBody) &&
    /animationFrame\s*=\s*0/.test(visBody),
)
check(
  '隐藏页面时取消楼层 RAF',
  /cancelAnimationFrame\(sceneTween\)/.test(visBody) && /sceneTween\s*=\s*0/.test(visBody),
)
check(
  '页面恢复时完成一致楼层状态',
  /resumeTransitionAfterVisibility/.test(visBody) && /applyMode\(false\)/.test(visBody),
)
check('页面恢复时恢复点击目标聚焦', /focusBed\(props\.selectedId\)/.test(visBody))
check(
  'visibilitychange 成对注册与反注册',
  script.includes("document.addEventListener('visibilitychange', onDocumentVisibility)") &&
    destroyBody.includes("document.removeEventListener('visibilitychange', onDocumentVisibility)"),
)
check(
  '卸载时取消 pending 过渡记号',
  /resumeTransitionAfterVisibility\s*=\s*false/.test(destroyBody),
)

// 回归护栏：本轮只做过渡与可见性加固，不得顺手删掉 V2/V3 的既有渲染加固
const legacy = [
  ['阴影仅在几何/楼层变化时重算', 'renderer.shadowMap.autoUpdate = false'],
  ['床位不投影的软阴影路径', 'markShadowsDirty()'],
  ['床垫基色随床传入', 'surfaceRest: new THREE.Color(sceneBedPalette[bed.status].surfaceBase)'],
  ['悬停床垫色随床传入', 'surfaceHover: new THREE.Color(sceneBedPalette[bed.status].surfaceHover)'],
  ['拾取体跟随筛选隐藏', 'item.pick.visible = ids.has(id)'],
  ['遮挡构造逐对象克隆材质', 'blocked.has(surface.mesh) ? surface.faded : surface.original'],
]
for (const [label, needle] of legacy) check(`回归护栏：${label}`, script.includes(needle))

console.log(
  `WEBGL_TRANSITION_STATIC_GUARDS ${count}/${count} PASS — source check only, NOT Chromium/WebGL acceptance`,
)
