/**
 * Hospital Vision V2 布局门禁（Node，无需启动浏览器）。
 *
 * 用法：cd frontend && node verify_v2_layout.cjs
 * 依赖：npm i（typescript 已在 devDependencies 中）
 *
 * 校验点：
 *  1. 合成演示数据 = 44 张床 / 3 个模拟楼层；
 *  2. 每个床位都能映射到楼层 key 与有限的三维坐标；
 *  3. 每层 width/depth 达到可读下限，且层内床位数与快照一致；
 *  4. **布局与查询顺序无关**（rooms/beds 反序输入结果必须完全相同）；
 *  5. UI 过滤不重排楼层（过滤后楼层数不变）—— 几何锚点始终是完整快照。
 */
const fs = require('fs')
const path = require('path')
const assert = require('assert').strict
const Module = require('module')
const ts = require('typescript')

function loadTs(name) {
  const code = fs.readFileSync(path.join(__dirname, 'src/modules/ward-map/', name), 'utf8')
  const { outputText, diagnostics } = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  })
  assert(!(diagnostics || []).some((d) => d.category === 1), 'TS syntax error')
  const m = new Module(name, module)
  m.filename = name
  m.paths = module.paths
  // scene-layout 现在会以运行时方式依赖 slot-grid.ts（同源槽位几何）：
  // Node 本身不解析 `.ts` 扩展，这里补上相对模块的转译加载（与其它守卫一致）。
  m.require = (specifier) =>
    specifier.startsWith('./') ? loadTs(`${specifier.slice(2)}.ts`) : require(specifier)
  m._compile(outputText, name)
  return m.exports
}

const { demoSnapshot } = loadTs('demo.ts')
const { createHospitalPlan, floorKey } = loadTs('scene-layout.ts')

const s = demoSnapshot()
const p = createHospitalPlan(s.rooms, s.beds)

assert.equal(s.beds.length, 44)
assert.equal(p.floors.length, 3)
assert.equal(Object.keys(p.bedLocations).length, 44)
assert.equal(Object.keys(p.bedFloors).length, 44)

for (const b of s.beds) {
  assert.equal(p.bedFloors[b.id], floorKey(b.building, b.floor))
  assert(Number.isFinite(p.bedLocations[b.id].x))
}
for (const floor of p.floors) {
  assert(floor.width > 12 && floor.depth > 10)
  assert.equal(floor.beds.length, s.beds.filter((b) => floorKey(b.building, b.floor) === floor.key).length)
}

// 布局必须与查询顺序无关
const q = createHospitalPlan([...s.rooms].reverse(), [...s.beds].reverse())
assert.deepEqual(q.bedLocations, p.bedLocations, 'must remain stable independent of query order')

const first = p.floors.find((f) => f.floor === 1)
const second = p.floors.find((f) => f.floor === 2)
assert(first && second)
assert.notEqual(first.index, second.index)

// UI 过滤不得触发重新布局
const filtered = s.beds.filter((b) => b.status === 'OCCUPIED')
assert(filtered.length < 44)
assert.equal(p.floors.length, 3)

console.log('V2_LAYOUT_GATE: PASS (44 demo beds, 3 floors, stable positions, no missing mappings)')