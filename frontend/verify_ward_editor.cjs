/**
 * Ward Map Editor V2 —— 模拟编辑器离线门禁（Node，无需浏览器，不联网）。
 *
 * 用法：cd frontend && NODE_PATH=./node_modules node verify_ward_editor.cjs
 *
 * 覆盖两件事：
 *  A. 交付包声明的 18 项断言（原样保留，便于与交付结果逐项对照）：
 *     起稿、增删、槽位碰撞、床号重复、旋转、**原有床位坐标不被挤动**、撤销/重做、
 *     以及三个 Vue 文件的 script AST 可解析。
 *  B. [LOCAL HARDENING] 只读边界审计：编辑模块与编辑器组件里**不得出现任何
 *     业务写接口 / 网络调用**，且合成床位 id 必须是负数 —— 交付包明确声明
 *     「正式入库能力未实现、未启用」，这条断言把这个声明钉成可回归的门禁。
 *
 * 与交付包的差异（本地适配，已记入集成报告）：
 *  - 交付版本 `require('/opt/nvm/.../typescript.js')` 写死了作者机器的 Linux 路径，
 *    本地改为 `require('typescript')`（走 NODE_PATH 指向 frontend/node_modules）；
 *  - 追加上述只读边界审计。
 */
const fs = require('fs')
const Module = require('module')
const path = require('path')
const assert = require('assert')
const ts = require('typescript')

/** 载入 `src/modules/ward-map/*.ts`：先转译再编译，保证断言跑在真实实现上。 */
function load(rel, cache = {}) {
  const file = path.join(__dirname, 'src/modules/ward-map', rel + '.ts')
  if (cache[file]) return cache[file].exports
  const m = new Module(file, module)
  cache[file] = m
  m.filename = file
  m.paths = module.paths
  m.require = (name) => (name.startsWith('./') ? load(name.slice(2), cache) : require(name))
  const source = fs.readFileSync(file, 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    reportDiagnostics: true,
  })
  assert.equal(
    (compiled.diagnostics || []).filter((x) => x.category === ts.DiagnosticCategory.Error).length,
    0,
    `${rel}.ts TS 转译应无错误`,
  )
  m._compile(compiled.outputText, file)
  return m.exports
}

const E = load('editor')
const L = load('scene-layout')

let n = 0
function ok(cond, msg) {
  assert(cond, msg)
  n++
}

/* ------------------------- A. 交付包声明的 18 项断言 ------------------------- */
const rooms = [
  {
    ward_id: 1,
    code: '101',
    name: '101室',
    department_id: 1,
    department_name: '内科',
    building: 'A',
    floor: 1,
    simulated_position: { x: 0, z: 0 },
    bed_count: 2,
  },
]
const bed = (id) => ({
  id,
  code: `C-101-0${id}`,
  status: 'AVAILABLE',
  ward_id: 1,
  ward_code: '101',
  ward_name: '101室',
  department_id: 1,
  department_name: '内科',
  building: 'A',
  floor: 1,
  patient: null,
  state_warning: null,
  simulated_position: { x: 0, z: 0 },
})

let state = E.initialEditor(rooms, [bed(1), bed(2)])
ok(state.items.length === 2, 'initial')

const posesOf = (s) => Object.fromEntries(s.items.map((i) => [i.bed.id, i.pose]))
const before = L.createHospitalPlan(rooms, E.editorBeds(state), posesOf(state)).bedLocations[1]

state = E.addDraft(state, rooms, 1, 4, 'SIM-01')
ok(state.items.length === 3, 'added')
ok(state.items.at(-1).synthetic, 'synthetic')
ok(!!E.validatePose(state, rooms, 'new', { wardId: 1, slot: 4, rotation: 0 }), 'collision')
try {
  E.addDraft(state, rooms, 1, 4, 'SIM-02')
  throw Error('collision allowed')
} catch (e) {
  ok(String(e).includes('已有床位'), 'collision blocked')
}
try {
  E.addDraft(state, rooms, 1, 6, 'SIM-01')
  throw Error('duplicate allowed')
} catch (e) {
  ok(String(e).includes('重复'), 'duplicate blocked')
}

const synthetic = state.items.at(-1)
state = E.moveDraft(state, rooms, synthetic.key, { wardId: 1, slot: 5, rotation: 90 })
ok(state.items.at(-1).pose.rotation === 90, 'rotation')

const after = L.createHospitalPlan(rooms, E.editorBeds(state), posesOf(state)).bedLocations[1]
ok(before.x === after.x && before.y === after.y && before.z === after.z, 'original unchanged')

state = E.undo(state)
ok(state.items.at(-1).pose.slot === 4, 'undo')
state = E.redo(state)
ok(state.items.at(-1).pose.slot === 5, 'redo')
state = E.removeDraft(state, synthetic.key)
ok(state.items.length === 2, 'remove')
state = E.undo(state)
ok(state.items.length === 3, 'undo remove')

const tsFiles = [
  'src/components/WardScene3D.vue',
  'src/components/WardBedEditor.vue',
  'src/views/WardMapView.vue',
]
for (const f of tsFiles) {
  const src = fs.readFileSync(path.join(__dirname, f), 'utf8')
  const match = src.match(/<script setup lang="ts">([\s\S]*?)<\/script>/)
  ok(!!match, 'vue script exists ' + f)
  const sf = ts.createSourceFile(f, match[1], ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  ok(sf.parseDiagnostics.length === 0, 'Vue script AST ' + f)
}

/* --------------------- B. [LOCAL HARDENING] 只读边界审计 --------------------- */
const FORBIDDEN = [
  /\bfetch\s*\(/,
  /\baxios\b/,
  /\bapi\s*[<(]/,
  /XMLHttpRequest/,
  /\/ward-map\/simulate/,
  /\/beds\/[^'"`]*\/(status|archive|restore)/,
]
const boundaryFiles = [
  'src/modules/ward-map/editor.ts',
  'src/components/WardBedEditor.vue',
  'src/components/WardScene3D.vue',
]
for (const rel of boundaryFiles) {
  const text = fs.readFileSync(path.join(__dirname, rel), 'utf8')
  const hit = FORBIDDEN.filter((re) => re.test(text)).map((re) => re.source)
  ok(hit.length === 0, `${rel} 不应出现业务写/网络调用，命中：${hit.join(', ')}`)
}

const editorSrc = fs.readFileSync(path.join(__dirname, 'src/modules/ward-map/editor.ts'), 'utf8')
// 合成床位 id 必须是负数 —— 用**运行时**断言（不绑死具体写法）：
// V2 用 `-1-Math.max(...)`，V2 Next 改用 `Math.min(0,...)-1`，两者等价，
// 真正要守的不变量是「草稿床 id 恒 < 0，永不与真实床位 id 空间冲突」。
const syntheticIds = state.items.filter((i) => i.synthetic).map((i) => i.bed.id)
ok(syntheticIds.length > 0 && syntheticIds.every((id) => id < 0), '合成床位 id 必须为负数（不与真实床位冲突）')
// 草稿必须有上限，避免历史栈无限增长
ok(/history\.slice\(-49\)/.test(editorSrc), '历史栈应裁剪到 50 步以内')

console.log(`WARD_EDITOR_OFFLINE=${n}/${n} PASS`)
