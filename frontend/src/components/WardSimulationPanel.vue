<script setup lang="ts">
/**
 * 三维调度沙盘面板（Spatial / Simulation V1）——**完全只读**。
 *
 * 真实性边界（与页面文案一致）：
 * - 面板里的一切申请都是**完全虚构**的，只填写科室/优先级/性别/隔离需求，
 *   不采集姓名、证件号、诊断等任何真实患者字段（服务端同样拒绝）；
 * - 结果来自 `POST /api/v1/ward-map/simulate`：复用正式 H1–H4 硬约束、
 *   五维评分与贪心/精确流求解器，但**零数据库写入**，不是分配承诺；
 * - 参数变化后自动重新求解（360ms 防抖）；异步结果按 epoch 丢弃过期响应，
 *   避免慢的旧请求覆盖新结果；
 * - 真实快照签名变化 → 结果立即标记 stale 并撤回，防止旧结论继续当真；
 * - 演示（合成）模式下 `available=false`，**不会**偷偷调用真实库，也不会
 *   伪造一个「计算成功」。
 *
 * 与交付包的差异（本地适配）：HTTP 走本仓库 `@/api/http`（axios + 统一错误
 * 与鉴权拦截），按钮复用本地 `.btn` 语义，权限判定由外层传入。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import http from '@/api/http'
import type { WardBed } from '@/modules/ward-map/types'
import { supplyDelta, type EditorState } from '@/modules/ward-map/editor'
import type {
  FictionalRequest,
  SandboxInput,
  SandboxOutput,
  SandboxPriority,
} from '@/modules/ward-map/sandbox'

const props = defineProps<{
  /** 完整业务快照的床位（沙盘候选来自真实床位，但假设只作用在服务端临时视图上） */
  beds: WardBed[]
  /** 不可变的真实快照：用于计算「模拟供给增减」的基线 */
  realBeds?: WardBed[]
  /** 编辑器的当前草稿：仅用于把模拟增减折算成供给变化，绝不上送真实写入 */
  editorState?: EditorState | null
  active: boolean
  /** 是否允许运行：真实业务快照 + 账号具备 ADMIN/NURSE 权限 */
  available: boolean
}>()

const emit = defineEmits<{
  (e: 'result', data: SandboxOutput | null, method: 'greedy' | 'optimized'): void
  (e: 'exit'): void
  (e: 'locate', bedId: number): void
}>()

const departments = computed(() => [
  ...new Map(props.beds.map((b) => [b.department_id, b.department_name])).entries(),
])
const wards = computed(() => [...new Map(props.beds.map((b) => [b.ward_id, b.ward_name])).entries()])
const freeBeds = computed(() => props.beds.filter((b) => b.status === 'AVAILABLE'))

/**
 * 编辑器草稿带来的**供给变化**（相对不可变真实快照）：
 * - added：模拟新增床（负数 virtual_id，借用同病房真实床位的**业务评分坐标**作为代理值）；
 * - removed：被临时移除的真实空闲床（只进临时 unavailable 集合，不写库）。
 */
const delta = computed(() =>
  props.editorState ? supplyDelta(props.editorState, props.realBeds ?? []) : { removed: [], added: [] },
)
/** 模拟新增床 → 服务端契约（virtual_id 为负数，绝不对应真实床位） */
const virtualBeds = computed(() =>
  delta.value.added.map((item) => {
    const template = (props.realBeds ?? []).find((b) => b.ward_id === item.pose.wardId)
    return template
      ? {
          virtual_id: item.bed.id,
          template_bed_id: template.id,
          code: item.bed.code,
          ward_id: item.pose.wardId,
        }
      : null
  }),
)

const patients = ref<FictionalRequest[]>([])
const dept = ref<number>(0)
const gender = ref<'MALE' | 'FEMALE'>('FEMALE')
const priority = ref<SandboxPriority>('NORMAL')
const isolation = ref(false)
const hiddenBed = ref<number>(0)
const disabledBeds = ref<number[]>([])
const cutWard = ref<number>(0)
const cutCount = ref(0)
const plan = ref<SandboxOutput | null>(null)
const selectedSolution = ref<'greedy' | 'optimized'>('optimized')
const busy = ref(false)
const error = ref('')
const stale = ref(false)
let epoch = 0

/** 真实快照签名：床位 id/状态/病房任一变化都说明沙盘结论已过期。 */
const actualBedsSignature = computed(() =>
  JSON.stringify(props.beds.map((b) => [b.id, b.status, b.ward_id])),
)
const lastSignature = ref('')

const activeResult = computed(() => (plan.value ? plan.value[selectedSolution.value] : null))

/** 首个虚构申请的前 6 个候选（按分数降序，同分按床位 id）——用于展示五维评分依据。 */
const topCandidates = computed(() =>
  [...(plan.value?.candidates ?? [])]
    .filter((c) => c.scenario_id === patients.value[0]?.scenario_id)
    .sort((a, b) => b.score - a.score || a.bed_id - b.bed_id)
    .slice(0, 6),
)

const lookupBed = (id: number) => props.beds.find((b) => b.id === id)

function reset() {
  epoch++
  patients.value = []
  disabledBeds.value = []
  cutWard.value = 0
  cutCount.value = 0
  hiddenBed.value = 0
  plan.value = null
  error.value = ''
  stale.value = false
  emit('result', null, selectedSolution.value)
}

function addPatient() {
  if (!dept.value || patients.value.length >= 30) return
  // 序号必须唯一（服务端校验），取当前最小可用正整数
  const used = new Set(patients.value.map((r) => r.scenario_id))
  let id = 1
  while (used.has(id)) id++
  patients.value.push({
    scenario_id: id,
    department_id: dept.value,
    gender: gender.value,
    priority: priority.value,
    isolation_required: isolation.value,
    preferred_ward_id: null,
  })
}

function addUnavailable() {
  if (!hiddenBed.value || disabledBeds.value.includes(hiddenBed.value)) return
  disabledBeds.value.push(hiddenBed.value)
}

/** 退出沙盘：先清空全部假设与结果，再通知外层收起沙盘（外层同时会清 3D 高亮）。 */
function exitAndReset() {
  reset()
  emit('exit')
}

async function run() {
  const thisRun = ++epoch
  error.value = ''
  if (!patients.value.length) {
    plan.value = null
    emit('result', null, selectedSolution.value)
    return
  }
  if (!props.available) {
    error.value = '沙盘需要真实业务快照，且当前账号需具备管理员或护士权限（模拟申请本身仍为完全虚构）。'
    return
  }
  busy.value = true
  stale.value = false
  try {
    // 模拟新增床必须能找到同病房的真实床位模板，否则借用不到评分坐标 —— 宁可报错也不降级。
    if (virtualBeds.value.some((b) => b === null))
      throw new Error('模拟新增床缺少同病房真实床位模板，无法使用现有评分坐标')
    const payload: SandboxInput = {
      scenario_kind: 'SYNTHETIC_ONLY',
      synthetic_requests: patients.value.map((r) => ({ ...r })),
      synthetic_beds: virtualBeds.value.filter((b): b is NonNullable<typeof b> => b !== null),
      unavailable_bed_ids: [...new Set([...disabledBeds.value, ...delta.value.removed])],
      ward_supply_cut:
        cutWard.value && cutCount.value > 0
          ? { ward_id: cutWard.value, count: cutCount.value }
          : null,
    }
    const { data: result } = await http.post<SandboxOutput>(
      '/api/v1/ward-map/simulate',
      payload,
    )
    if (thisRun !== epoch) return
    // 只读契约自检：三个标志位任一不符即视为不可信结果，直接丢弃
    if (
      result.scenario_kind !== 'SYNTHETIC_ONLY' ||
      !result.preview_only ||
      !result.no_database_writes
    )
      throw new Error('沙盘只读契约校验失败')
    plan.value = result
    lastSignature.value = actualBedsSignature.value
    emit('result', result, selectedSolution.value)
  } catch (e) {
    if (thisRun === epoch) {
      plan.value = null
      emit('result', null, selectedSolution.value)
      error.value = (e as Error).message
    }
  } finally {
    if (thisRun === epoch) busy.value = false
  }
}

let schedule: number | undefined

// 参数一变，先把旧结果撤回（连同 3D 高亮），再防抖重算
watch(
  [patients, disabledBeds, cutWard, cutCount],
  () => {
    if (schedule !== undefined) window.clearTimeout(schedule)
    if (!props.active) return
    plan.value = null
    emit('result', null, selectedSolution.value)
    if (patients.value.length) schedule = window.setTimeout(() => void run(), 360)
  },
  { deep: true },
)

watch(selectedSolution, () => emit('result', plan.value, selectedSolution.value))

// 编辑草稿一变，供给基线就变了：旧结论立即撤回，等用户重新计算（或下次参数变化触发）
watch(
  () => props.editorState,
  () => {
    if (plan.value) {
      plan.value = null
      stale.value = true
      emit('result', null, selectedSolution.value)
    }
  },
  { deep: true },
)

watch(actualBedsSignature, () => {
  if (plan.value && actualBedsSignature.value !== lastSignature.value) {
    stale.value = true
    emit('result', null, selectedSolution.value)
  }
})

watch(
  () => props.active,
  (active) => {
    if (!active) {
      epoch++
      if (schedule !== undefined) window.clearTimeout(schedule)
      emit('result', null, selectedSolution.value)
    }
  },
)

onBeforeUnmount(() => {
  epoch++
  if (schedule !== undefined) window.clearTimeout(schedule)
})
</script>

<template>
  <section v-if="active" class="wm-sandbox" aria-label="三维智能调度沙盘">
    <div class="wm-sandbox-head">
      <div>
        <strong>智能调度沙盘</strong>
        <p>完全虚构的申请 · 真实 H1–H4 与五维评分 · 无数据库写入</p>
      </div>
      <button class="btn btn--sm" type="button" @click="exitAndReset">退出模拟</button>
    </div>

    <p class="wm-sandbox-notice">
      仅用于教学推演：红色为业务预占/入住；青色轮廓为候选；金色轮廓为模拟方案，不代表实际完成分配。
    </p>

    <p v-if="editorState" class="wm-sandbox-note">
      编辑器供给变化：模拟新增 {{ delta.added.length }} 张，临时移除空闲床
      {{ delta.removed.length }} 张。模拟新床的评分沿用同病房真实床位模板的业务评分坐标（代理值），
      并非建筑 3D 展示坐标；这些都只在服务端临时视图里生效。
    </p>

    <div class="wm-sandbox-form">
      <label>
        模拟科室
        <select v-model.number="dept">
          <option :value="0">选择科室</option>
          <option v-for="[id, name] in departments" :key="id" :value="id">{{ name }}</option>
        </select>
      </label>
      <label>
        模拟优先级
        <select v-model="priority">
          <option value="CRITICAL">危重</option>
          <option value="SEVERE">重症</option>
          <option value="URGENT">急症</option>
          <option value="NORMAL">普通</option>
          <option value="MILD">轻症</option>
        </select>
      </label>
      <label>
        模拟性别
        <select v-model="gender">
          <option value="FEMALE">女</option>
          <option value="MALE">男</option>
        </select>
      </label>
      <label class="wm-sandbox-check">
        <input v-model="isolation" type="checkbox" />
        模拟需要隔离
      </label>
      <button
        class="btn btn--sm"
        type="button"
        :disabled="!dept || patients.length >= 30 || busy"
        @click="addPatient"
      >
        + 添加虚构申请
      </button>
    </div>

    <div v-if="patients.length" class="wm-sandbox-patients">
      <span v-for="person in patients" :key="person.scenario_id">
        模拟 #{{ person.scenario_id }} · {{ person.priority }}
        <button
          type="button"
          :aria-label="'删除模拟申请' + person.scenario_id"
          @click="patients = patients.filter((p) => p.scenario_id !== person.scenario_id)"
        >
          ×
        </button>
      </span>
    </div>

    <div class="wm-sandbox-form">
      <label>
        What-if：临时停用空床
        <select v-model.number="hiddenBed">
          <option :value="0">不新增</option>
          <option v-for="b in freeBeds" :key="b.id" :value="b.id">{{ b.code }}</option>
        </select>
      </label>
      <button class="btn btn--sm" type="button" :disabled="!hiddenBed" @click="addUnavailable">
        加入假设
      </button>
      <label>
        What-if：减少病房供给
        <select v-model.number="cutWard">
          <option :value="0">不减少</option>
          <option v-for="[id, name] in wards" :key="id" :value="id">{{ name }}</option>
        </select>
      </label>
      <label>
        减少数量
        <input v-model.number="cutCount" type="number" min="0" max="20" step="1" />
      </label>
    </div>

    <p v-if="disabledBeds.length" class="wm-sandbox-note">
      临时不可用：{{ disabledBeds.map((id) => lookupBed(id)?.code ?? id).join('、') }}
      <button type="button" @click="disabledBeds = []">清除</button>
    </p>

    <div class="wm-sandbox-actions">
      <button
        class="btn btn--sm btn--primary"
        type="button"
        :disabled="!patients.length || busy || !available"
        @click="run"
      >
        {{ busy ? '正在计算…' : '重新计算模拟方案' }}
      </button>
      <button class="btn btn--sm" type="button" @click="reset">重置全部假设</button>
      <span v-if="stale" class="wm-warning">真实床位快照已变化，请重新计算</span>
    </div>

    <p v-if="error" class="wm-error" role="alert">{{ error }}</p>

    <div v-if="plan && !stale" class="wm-sandbox-results">
      <div class="wm-view-switch" role="group" aria-label="切换求解方案">
        <button
          type="button"
          :class="{ 'is-active': selectedSolution === 'greedy' }"
          @click="selectedSolution = 'greedy'"
        >
          Greedy
        </button>
        <button
          type="button"
          :class="{ 'is-active': selectedSolution === 'optimized' }"
          @click="selectedSolution = 'optimized'"
        >
          精确优化
        </button>
      </div>

      <div class="wm-sandbox-metrics">
        <div>
          <small>模拟安排人数</small>
          <strong>{{ activeResult?.admitted }} / {{ plan.request_count }}</strong>
        </div>
        <div>
          <small>优先级和</small>
          <strong>{{ activeResult?.priority_sum }}</strong>
        </div>
        <div>
          <small>评分合计</small>
          <strong>{{ activeResult?.score_sum }}</strong>
        </div>
        <div>
          <small>求解时间</small>
          <strong>{{ activeResult?.runtime_ms }} ms</strong>
        </div>
      </div>

      <p class="wm-sandbox-note">
        {{ activeResult?.method }} ·
        {{ activeResult?.proven_optimal ? '已证明该模拟目标最优' : '启发式方案，无最优性保证' }} · 零写入
      </p>

      <div class="wm-sandbox-pairs">
        <button
          v-for="pair in activeResult?.pairs"
          :key="pair.scenario_id"
          class="wm-sandbox-locate"
          type="button"
          @click="emit('locate', pair.bed_id)"
        >
          模拟 #{{ pair.scenario_id }} → {{ lookupBed(pair.bed_id)?.code ?? pair.bed_id }}（{{
            pair.score
          }}）↗
        </button>
      </div>

      <details>
        <summary>单患者床位候选与五维评分依据</summary>
        <div v-for="c in topCandidates" :key="c.bed_id" class="wm-sandbox-row">
          <button class="wm-sandbox-locate" type="button" @click="emit('locate', c.bed_id)">
            {{ c.bed_code }} ↗
          </button>
          <span>{{ c.score }} 分</span>
          <small>{{ Object.entries(c.score_items).map(([k, v]) => `${k} ${v}`).join(' / ') }}</small>
        </div>
      </details>
    </div>
  </section>
</template>
