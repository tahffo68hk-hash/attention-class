<script setup lang="ts">
/**
 * 多患者联合排床（P1）—— 只读预览页。
 *
 * 只调用 `POST /api/v1/optimization/preview` 与 `POST /api/v1/assistant/explain-plan`，
 * 后端不会写入任何分配记录；正式预占仍走「床位推荐 → 新建分配」逐个人工确认。
 */
import { computed, onMounted, ref } from 'vue'

import {
  explainPlan,
  fetchAllocations,
  fetchOptimizationPreview,
  fetchProviderStatus,
  fetchQueue,
} from '@/api/business'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'
import type {
  OptimizationPreviewOut,
  PlanExplainOut,
  PreadmissionRead,
  ProviderStatus,
} from '@/api/types'

const MAX_SELECTION = 30

const { canOperateAllocation } = useAuth()

const queue = ref<PreadmissionRead[]>([])
/** 已被活动分配（预占用 / 已入住）占用、因而不属于「未分配待入院」的住院证数量。 */
const blockedCount = ref(0)
const selected = ref<number[]>([])
const preview = ref<OptimizationPreviewOut | null>(null)
const plan = ref<PlanExplainOut | null>(null)

/** P4：方案解释方式与一次性确认；DeepSeek 默认关闭，须服务端启用 + 本次确认。 */
const planMode = ref<'rules' | 'llm'>('rules')
const planConsent = ref(false)
const providerStatus = ref<ProviderStatus | null>(null)

const loading = ref(false)
const previewing = ref(false)
const explaining = ref(false)
const errorMessage = ref('')

/** 真实 AI 方案解释的门槛：服务端已启用 且 本次已勾选确认。 */
const planLlmBlocked = computed(
  () => planMode.value === 'llm' && (!planConsent.value || !providerStatus.value?.enabled),
)

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const [queuePage, reserved, admitted] = await Promise.all([
      fetchQueue({ pending_only: true, page_size: 100 }),
      fetchAllocations({ status: 'RESERVED', page_size: 200 }),
      fetchAllocations({ status: 'ADMITTED', page_size: 200 }),
    ])
    // 后端联合排床只接受「未分配的待入院」住院证：这里预先剔除已持有活动分配的患者，
    // 避免用户选中后拿到 409 而不知原因。
    const blocked = new Set(
      [...reserved.items, ...admitted.items].map((a) => a.admission_request_id),
    )
    const usable = queuePage.items.filter((x) => !blocked.has(x.admission_request_id))
    blockedCount.value = queuePage.items.length - usable.length
    queue.value = usable
    const alive = new Set(usable.map((x) => x.admission_request_id))
    selected.value = selected.value.filter((id) => alive.has(id))
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载待入院队列失败'
  } finally {
    loading.value = false
  }
}

function toggle(id: number) {
  preview.value = null
  plan.value = null
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter((x) => x !== id)
  } else if (selected.value.length < MAX_SELECTION) {
    selected.value = [...selected.value, id]
  }
}

function selectAll() {
  preview.value = null
  plan.value = null
  selected.value = queue.value.slice(0, MAX_SELECTION).map((x) => x.admission_request_id)
}

function clearSelection() {
  selected.value = []
  preview.value = null
  plan.value = null
}

async function runPreview() {
  if (!selected.value.length) return
  previewing.value = true
  errorMessage.value = ''
  preview.value = null
  plan.value = null
  try {
    preview.value = await fetchOptimizationPreview(selected.value, 'auto')
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '联合排床预览失败'
  } finally {
    previewing.value = false
  }
}

async function runExplainPlan() {
  if (!selected.value.length) return
  explaining.value = true
  errorMessage.value = ''
  try {
    plan.value = await explainPlan(selected.value, {
      mode: planMode.value,
      confirmExternalCall: planMode.value === 'llm' && planConsent.value,
    })
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '生成方案解释失败'
  } finally {
    explaining.value = false
  }
}

/** 求解器标识 -> 中文标签。`solver=auto` 后端固定使用精确最小费用流（不调用可选 CP-SAT）。 */
const SOLVER_LABEL: Record<string, string> = {
  exact_min_cost_flow: '精确最小费用流',
  ortools_cp_sat: 'OR-Tools CP-SAT',
  greedy: '贪心回填（不保证最优）',
}

function solverLabel(method: string | undefined | null): string {
  if (!method) return '未知'
  return SOLVER_LABEL[method] ?? method
}

/** 逐项对照：同一住院证在贪心方案与全局方案下分别匹配到哪张床。 */
const pairRows = computed(() => {
  if (!preview.value) return []
  const optimal = new Map(preview.value.optimized.pairs.map((p) => [p.admission_request_id, p]))
  const greedy = new Map(preview.value.baseline.pairs.map((p) => [p.admission_request_id, p]))
  return preview.value.admission_request_ids.map((id) => ({
    id,
    who: queue.value.find((x) => x.admission_request_id === id) ?? null,
    optimal: optimal.get(id) ?? null,
    greedy: greedy.get(id) ?? null,
  }))
})

onMounted(async () => {
  await load()
  try {
    providerStatus.value = await fetchProviderStatus()
  } catch {
    // 旧后端无该接口时静默降级为「仅规则版」。
    providerStatus.value = null
  }
})
</script>

<template>
  <h1 class="page-title">多患者联合排床（预览）</h1>
  <p class="page-subtitle">
    对同一批待入院住院证比较「贪心」与「全局优化」方案，只读计算、不锁定床位。
  </p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <div class="alert alert--info">
    研究型教学原型：仅支持尚未分配的待入院住院证，最多选 {{ MAX_SELECTION }} 人。计算结果只读，
    确认床位仍须回到「床位推荐」逐个人工预占，由后端在事务内重新校验实时状态与硬约束。
  </div>

  <div class="card">
    <div class="toolbar">
      <button class="btn" :disabled="loading" @click="load">刷新队列</button>
      <button class="btn" :disabled="!queue.length" @click="selectAll">选取前 {{ MAX_SELECTION }} 人</button>
      <button class="btn" :disabled="!selected.length" @click="clearSelection">清空选择</button>
      <span class="toolbar__spacer"></span>
      <span class="note">
        已选 {{ selected.length }} / {{ MAX_SELECTION }} 人 · 可选 {{ queue.length }} 人<template
          v-if="blockedCount"
          >（另有 {{ blockedCount }} 人已持有床位预占，不参与联合排床）</template
        >
      </span>
      <button
        class="btn btn--primary"
        :disabled="!canOperateAllocation || previewing || !selected.length"
        @click="runPreview"
      >
        {{ previewing ? '计算中…' : '比较贪心与全局方案' }}
      </button>
    </div>

    <p v-if="loading" class="spinner-text">加载待入院队列…</p>

    <div v-else class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>选择</th>
            <th>排队号</th>
            <th>住院证</th>
            <th>患者</th>
            <th>科室</th>
            <th>优先级</th>
            <th>隔离需求</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in queue" :key="item.id">
            <td>
              <input
                type="checkbox"
                :checked="selected.includes(item.admission_request_id)"
                :disabled="
                  !selected.includes(item.admission_request_id) && selected.length >= MAX_SELECTION
                "
                @change="toggle(item.admission_request_id)"
              />
            </td>
            <td class="mono">{{ item.queue_no }}</td>
            <td class="mono">{{ item.certificate_no || '—' }}</td>
            <td>{{ item.patient_name || '—' }}</td>
            <td>{{ item.department_name || '—' }}</td>
            <td>{{ item.priority_label || item.priority || '—' }}</td>
            <td>
              <span v-if="item.isolation_required" class="tag tag--warn">需隔离</span>
              <span v-else class="note">否</span>
            </td>
          </tr>
          <tr v-if="!queue.length">
            <td colspan="7" class="empty">暂无待入院患者</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <template v-if="preview">
    <div class="grid">
      <div class="stat">
        <span class="stat__label">参与患者</span>
        <span class="stat__value">{{ preview.request_count }}</span>
      </div>
      <div class="stat">
        <span class="stat__label">候选匹配关系</span>
        <span class="stat__value">{{ preview.candidate_edges }}</span>
      </div>
      <div class="stat">
        <span class="stat__label">贪心成功人数</span>
        <span class="stat__value">{{ preview.baseline.admitted }}</span>
      </div>
      <div class="stat">
        <span class="stat__label">全局成功人数</span>
        <span class="stat__value stat__value--ok">{{ preview.optimized.admitted }}</span>
      </div>
    </div>

    <div class="alert alert--info">
      对照算法：贪心（{{ solverLabel(preview.baseline.method) }}） vs 全局优化（{{
        solverLabel(preview.optimized.method)
      }}）·
      {{ preview.optimized.proven_optimal ? '当前冻结候选下已证明最优' : '未证明最优' }} ·
      净增可安排 {{ preview.admitted_gain }} 人 · 适配评分总和差
      {{ Number(preview.score_gain).toFixed(2) }}。
      评分与硬约束口径复用现有五维推荐与 H1–H4 过滤，结果会随实际床位状态变化。
    </div>

    <div class="card">
      <div class="card__title">方案解释</div>
      <p class="note">
        只解释当前计算快照，不执行分配、也不修改求解目标。真实 DeepSeek 仅接收聚合统计数据
        （成功人数、优先级总和、评分总和、算法名称），不发送住院证 ID、床位 ID 或患者姓名。
      </p>
      <div class="toolbar">
        <div class="field">
          <label>解释方式</label>
          <select v-model="planMode" class="select" @change="plan = null; planConsent = false">
            <option value="rules">确定性规则（免费、非 AI）</option>
            <option value="llm">DeepSeek AI 草稿（需确认）</option>
          </select>
        </div>
        <button
          class="btn"
          :disabled="explaining || !selected.length || planLlmBlocked"
          @click="runExplainPlan"
        >
          {{ explaining ? '生成中…' : '生成方案解释' }}
        </button>
        <span v-if="planLlmBlocked" class="note">
          {{ providerStatus?.enabled ? '请先勾选本次确认' : 'DeepSeek 未启用，请改用规则解释' }}
        </span>
      </div>
      <label v-if="planMode === 'llm'" class="checkbox" style="margin-top: 12px">
        <input v-model="planConsent" type="checkbox" />
        我确认此次 DeepSeek 调用可能产生费用，输出必须人工复核；服务状态：{{
          providerStatus?.enabled ? '已启用' : '未启用'
        }}
      </label>
      <template v-if="plan">
        <p>
          <strong>{{ plan.real_ai ? 'DeepSeek AI 草稿 · 待人工复核' : '确定性规则说明 · 非 AI' }}</strong>
        </p>
        <p>{{ plan.explanation }}</p>
        <p v-for="note in plan.recommendations" :key="note" class="note">• {{ note }}</p>
        <p class="note">
          已安排 {{ plan.assigned_count }} 人（贪心 {{ plan.baseline_assigned_count }} 人）·
          未匹配 {{ plan.unmatched_request_ids.length }} 人 ·
          模型 {{ plan.model || '无' }} ·
          Token {{ plan.input_tokens ?? '—' }} / {{ plan.output_tokens ?? '—' }} ·
          费用估算 {{ plan.cost_estimate_cny === null ? '未配置费率' : `¥${plan.cost_estimate_cny}` }} ·
          时延 {{ plan.latency_ms ?? '—' }} ms · 未执行任何分配
        </p>
      </template>
    </div>

    <div class="card">
      <div class="card__title">联合方案逐项对照</div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>住院证</th>
              <th>优先级</th>
              <th>贪心方案床位</th>
              <th>全局方案床位</th>
              <th>全局匹配得分</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in pairRows" :key="row.id">
              <td class="mono">{{ row.who?.certificate_no || `#${row.id}` }}</td>
              <td>{{ row.who?.priority_label || row.who?.priority || '—' }}</td>
              <td>{{ row.greedy ? `#${row.greedy.bed_id}` : '未分配' }}</td>
              <td>
                <span v-if="row.optimal" class="mono">#{{ row.optimal.bed_id }}</span>
                <span v-else class="note">未分配</span>
              </td>
              <td>{{ row.optimal ? row.optimal.score.toFixed(2) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card__title">实验指标</div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>指标</th>
              <th>贪心</th>
              <th>全局优化</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>已安排人数</td>
              <td>{{ preview.baseline.admitted }}</td>
              <td>{{ preview.optimized.admitted }}</td>
            </tr>
            <tr>
              <td>优先级总和</td>
              <td>{{ preview.baseline.priority_sum }}</td>
              <td>{{ preview.optimized.priority_sum }}</td>
            </tr>
            <tr>
              <td>适配评分总和</td>
              <td>{{ preview.baseline.score_sum.toFixed(2) }}</td>
              <td>{{ preview.optimized.score_sum.toFixed(2) }}</td>
            </tr>
            <tr>
              <td>计算耗时（ms）</td>
              <td>{{ preview.baseline.runtime_ms }}</td>
              <td>{{ preview.optimized.runtime_ms }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        目标为字典序：成功人数 → 优先级总和 → 适配评分总和。该目标是教学原型目标，
        不是临床收治原则；指标仅适用于本次冻结的数据快照。
      </p>
    </div>
  </template>
</template>

<style scoped>
.mono {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
</style>
