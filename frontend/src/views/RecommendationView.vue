<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createAllocation,
  fetchAdmissionRequests,
  fetchAllocations,
  fetchRecommendations,
} from '@/api/business'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'
import type {
  AdmissionRequestRead,
  BedRecommendation,
  RecommendationResponse,
} from '@/api/types'

import StatusBadge from '@/components/StatusBadge.vue'

const { canOperateAllocation } = useAuth()

const candidates = ref<AdmissionRequestRead[]>([])
const listLoading = ref(false)
const listError = ref('')

const selectedId = ref<number | null>(null)
const result = ref<RecommendationResponse | null>(null)
const recLoading = ref(false)
const recError = ref('')

const busyBedId = ref<number | null>(null)
const actionMessage = ref('')
const actionError = ref('')

const limit = ref(10)

const selected = computed(
  () => candidates.value.find((item) => item.id === selectedId.value) ?? null,
)

async function loadCandidates() {
  listLoading.value = true
  listError.value = ''
  try {
    // 同时取「待入院住院证」与「分配记录」：已有活动分配（预占用 / 已入住）的住院证
    // 即使状态仍是 PRE_ADMITTED，也不应再出现在推荐队列里 —— 否则用户选中后点
    // 「采纳推荐」，只会拿到后端 409 REQUEST_ALREADY_ALLOCATED。
    const [page, allocations] = await Promise.all([
      fetchAdmissionRequests({ status: 'PRE_ADMITTED', page_size: 100 }),
      fetchAllocations({ page_size: 200 }),
    ])
    const taken = new Set(
      allocations.items
        .filter((item) => item.status === 'RESERVED' || item.status === 'ADMITTED')
        .map((item) => item.admission_request_id),
    )
    const pending = page.items.filter((item) => !taken.has(item.id))
    candidates.value = pending

    if (selectedId.value !== null && !pending.some((item) => item.id === selectedId.value)) {
      // 当前选中项已不在队列中（刚分配掉 / 被取消），清空右侧并回退到首条
      selectedId.value = null
      result.value = null
    }
    if (!selectedId.value && pending.length) {
      selectRequest(pending[0].id)
    }
  } catch (err) {
    listError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载待入院列表失败'
  } finally {
    listLoading.value = false
  }
}

async function loadRecommendations() {
  if (!selectedId.value) return
  recLoading.value = true
  recError.value = ''
  // 注意：这里不能清 actionMessage —— 采纳成功后正是先刷新推荐再展示结果，
  // 清掉会把「已预占用床位 #N」的成功提示立刻抹掉，用户看不到反馈。
  actionError.value = ''
  try {
    result.value = await fetchRecommendations(selectedId.value, limit.value)
  } catch (err) {
    result.value = null
    recError.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '获取推荐结果失败'
  } finally {
    recLoading.value = false
  }
}

function selectRequest(id: number) {
  if (selectedId.value === id) return
  selectedId.value = id
  result.value = null
  actionMessage.value = ''
  loadRecommendations()
}

function reselect() {
  loadRecommendations()
}

async function adopt(bedId?: number) {
  if (!selectedId.value) return
  const bedIdSafe = bedId ?? null
  busyBedId.value = bedIdSafe
  actionMessage.value = ''
  actionError.value = ''
  try {
    const alloc = await createAllocation({
      admission_request_id: selectedId.value,
      bed_id: bedIdSafe,
    })
    const message = `已预占用床位 ${alloc.bed_code ?? ''}（分配 #${alloc.id}，状态：${
      alloc.status_label ?? alloc.status
    }）。请前往「分配与住院办理」办理入住。`
    // 该住院证已离开可推荐队列，重新拉列表与推荐；成功提示在刷新之后写入，
    // 否则会被队列刷新 / 推荐重算过程中的状态清理覆盖掉。
    await loadCandidates()
    if (selectedId.value) await loadRecommendations()
    actionMessage.value = message
  } catch (err) {
    actionError.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '预占用失败'
  } finally {
    busyBedId.value = null
  }
}

onMounted(loadCandidates)

function scorePct(score: number) {
  // 后端 score 为 0–100 分制（各评分项 contribution 之和），不是 0–1 归一值
  return `${Math.round(Math.max(0, Math.min(100, score)))}%`
}

function fmtNum(v: number) {
  return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

function fmtRate(v: string) {
  const n = Number(v)
  return Number.isFinite(n) ? `¥${n.toFixed(2)}` : v
}

function rankTone(index: number) {
  return index === 0 ? 'rec-card rec-card--top' : 'rec-card'
}

function cardReasonLines(rec: BedRecommendation) {
  return rec.reasons ?? []
}
</script>

<template>
  <h1 class="page-title">床位推荐</h1>
  <p class="page-subtitle">
    选择一张待入院住院证，系统先执行硬约束过滤，再按五项软约束给出可解释评分。
  </p>

  <div v-if="actionError" class="alert alert--danger">{{ actionError }}</div>
  <div v-if="actionMessage" class="alert alert--ok">{{ actionMessage }}</div>

  <div class="split">
    <!-- 左侧：待入院住院证 -->
    <div>
      <div class="toolbar" style="margin-bottom: 8px">
        <strong style="font-size: 13px">待入院住院证（{{ candidates.length }}）</strong>
        <span class="toolbar__spacer"></span>
        <button class="btn btn--sm" :disabled="listLoading" @click="loadCandidates">刷新</button>
      </div>

      <div v-if="listError" class="alert alert--danger">{{ listError }}</div>

      <div class="list-pane">
        <div v-if="listLoading" class="empty">加载中…</div>
        <div v-else-if="!candidates.length" class="empty">
          队列中没有「待入院且尚未占用床位」的住院证。<br />请先在「住院证与预登记」完成预登记。
        </div>
        <div
          v-for="item in candidates"
          v-else
          :key="item.id"
          class="list-item"
          :class="{ 'list-item--active': item.id === selectedId }"
          @click="selectRequest(item.id)"
        >
          <div class="list-item__title">
            <span>{{ item.patient_name || `患者 #${item.patient_id}` }}</span>
            <StatusBadge kind="priority" :value="item.priority" :label="item.priority_label" />
          </div>
          <div class="list-item__meta">
            {{ item.certificate_no }} · {{ item.department_name || '—' }}
            <span v-if="item.isolation_required"> · 需隔离</span>
          </div>
          <div class="list-item__meta">
            <StatusBadge
              kind="gender"
              :value="item.patient_gender || ''"
              :label="item.patient_gender_label"
            />
            <span v-if="item.queue_no"> · 队列号 {{ item.queue_no }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：推荐结果 -->
    <div>
      <template v-if="!selected">
        <div class="card"><div class="empty">请选择左侧的住院证</div></div>
      </template>

      <template v-else>
        <div class="card">
          <div class="rec-card__head">
            <strong>{{ selected.patient_name || `患者 #${selected.patient_id}` }}</strong>
            <StatusBadge kind="priority" :value="selected.priority" :label="selected.priority_label" />
            <StatusBadge
              v-if="selected.isolation_required"
              kind="bedType"
              value="ISOLATION"
              label="需隔离"
            />
            <span class="toolbar__spacer"></span>
            <button class="btn btn--sm" :disabled="recLoading" @click="reselect">重新推荐</button>
          </div>
          <div class="kv-inline">
            <span>住院证：{{ selected.certificate_no }}</span>
            <span>科室：{{ selected.department_name || '—' }}</span>
            <span>开具医生：{{ selected.doctor_name || '—' }}</span>
            <span v-if="selected.infection_type">感染类型：{{ selected.infection_type }}</span>
            <span v-if="selected.preferred_ward_name">期望病房：{{ selected.preferred_ward_name }}</span>
          </div>
          <div v-if="selected.diagnosis" class="kv-inline">
            <span>诊断：{{ selected.diagnosis }}</span>
          </div>
        </div>

        <div v-if="recError" class="alert alert--danger">{{ recError }}</div>

        <p v-if="recLoading" class="spinner-text">正在计算推荐结果…</p>

        <template v-else-if="result">
          <!-- 无候选 -->
          <div v-if="!result.recommendations.length" class="card">
            <h2 class="card__title">暂无可用床位</h2>
            <p class="note">系统未找到满足全部硬约束的床位，原因如下：</p>
            <ul class="plain">
              <li v-for="(reason, i) in result.no_result_reasons" :key="i">{{ reason }}</li>
            </ul>
            <div class="kv-inline">
              <span>科室床位总数：{{ result.hard_constraint_stats.department_total_beds }}</span>
              <span>科室空闲：{{ result.hard_constraint_stats.department_available_beds }}</span>
              <span>通过状态筛选：{{ result.hard_constraint_stats.candidates_after_status }}</span>
              <span>因状态排除：{{ result.hard_constraint_stats.excluded_by_status }}</span>
              <span>因性别排除：{{ result.hard_constraint_stats.excluded_by_gender }}</span>
              <span>因隔离排除：{{ result.hard_constraint_stats.excluded_by_isolation }}</span>
            </div>
          </div>

          <template v-else>
            <div class="toolbar">
              <span class="note">
                共评估 {{ result.candidates_evaluated }} 张候选床，返回前
                {{ result.recommendations.length }} 名（按综合得分降序）
              </span>
              <span class="toolbar__spacer"></span>
              <label class="note">
                返回条数
                <select v-model.number="limit" class="select" style="width: 78px" @change="reselect">
                  <option :value="5">5</option>
                  <option :value="10">10</option>
                  <option :value="20">20</option>
                </select>
              </label>
              <button
                v-if="canOperateAllocation"
                class="btn btn--primary btn--sm"
                :disabled="busyBedId !== null"
                @click="adopt(undefined)"
              >
                {{ busyBedId === null ? '采纳推荐第一名' : '处理中…' }}
              </button>
            </div>

            <div
              v-for="(rec, index) in result.recommendations"
              :key="rec.bed_id"
              :class="rankTone(index)"
            >
              <div class="rec-card__head">
                <span class="rec-card__rank">{{ index + 1 }}</span>
                <span class="rec-card__code">{{ rec.bed_code }}</span>
                <span class="badge badge--muted">{{ rec.ward_name }}</span>
                <StatusBadge kind="bedType" :value="rec.bed_type" :label="rec.bed_type_label" />
                <StatusBadge
                  kind="gender"
                  :value="rec.gender_limit"
                  :label="rec.gender_limit_label"
                />
                <span v-if="rec.is_isolation" class="badge badge--danger">隔离床</span>
                <span class="rec-card__score">{{ scorePct(rec.score) }}</span>
              </div>

              <div class="bar"><div class="bar__fill" :style="{ width: scorePct(rec.score) }"></div></div>

              <div class="kv-inline">
                <span>所在楼层：{{ rec.floor }} 层</span>
                <span>距科室距离：{{ fmtNum(rec.distance) }}</span>
                <span>日费用：{{ fmtRate(rec.daily_rate) }}</span>
              </div>

              <details v-if="cardReasonLines(rec).length || rec.warnings.length">
                <summary class="note" style="cursor: pointer">评分明细与理由</summary>
                <table class="score-table">
                  <thead>
                    <tr>
                      <th>评分项</th>
                      <th class="num">原始分</th>
                      <th class="num">权重</th>
                      <th class="num">贡献</th>
                      <th>说明</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in rec.score_items" :key="s.key">
                      <td>{{ s.label }}</td>
                      <td class="num">{{ fmtNum(s.raw_score) }}</td>
                      <td class="num">{{ fmtNum(s.weight) }}</td>
                      <td class="num">{{ fmtNum(s.contribution) }}</td>
                      <td>{{ s.note }}</td>
                    </tr>
                  </tbody>
                </table>
                <ul v-if="cardReasonLines(rec).length" class="plain" style="margin-top: 8px">
                  <li v-for="(r, i) in cardReasonLines(rec)" :key="`r${i}`">{{ r }}</li>
                </ul>
                <ul
                  v-if="rec.warnings.length"
                  class="plain"
                  style="margin-top: 8px; color: var(--color-warning)"
                >
                  <li v-for="(w, i) in rec.warnings" :key="`w${i}`">提醒：{{ w }}</li>
                </ul>
              </details>

              <div class="card-actions">
                <span class="toolbar__spacer"></span>
                <button
                  v-if="canOperateAllocation"
                  class="btn btn--sm"
                  :disabled="busyBedId !== null"
                  @click="adopt(rec.bed_id)"
                >
                  {{ busyBedId === rec.bed_id ? '处理中…' : '预占用此床位' }}
                </button>
              </div>
            </div>

            <p v-if="!canOperateAllocation" class="note">
              当前角色可查看推荐结果，但预占用床位需「护士 / 管理员」权限。
            </p>

            <details class="card" style="margin-top: 12px">
              <summary style="cursor: pointer"><strong>推荐策略说明</strong></summary>
              <ul class="plain">
                <li v-for="(p, i) in result.policy_notes" :key="i">{{ p }}</li>
              </ul>
            </details>
          </template>
        </template>
      </template>
    </div>
  </div>
</template>
