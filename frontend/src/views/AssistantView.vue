<script setup lang="ts">
/**
 * 辅助决策解释（P2）—— 只读页面。
 *
 * 默认走确定性规则说明（不调用任何外部模型）；「真实 AI」模式需要服务端开关
 * 与请求显式确认同时成立，本演示环境两者都未开启。
 */
import { onMounted, ref, watch } from 'vue'

import {
  explainBed,
  fetchAllocations,
  fetchQueue,
  fetchRecommendations,
} from '@/api/business'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'
import type { BedRecommendation, EvidenceScore, ExplainOut, PreadmissionRead } from '@/api/types'

const { canOperateAllocation } = useAuth()

const queue = ref<PreadmissionRead[]>([])
const candidates = ref<BedRecommendation[]>([])

const requestId = ref<number | ''>('')
const bedId = ref<number | ''>('')
const mode = ref<'rules' | 'llm'>('rules')
const consent = ref(false)

const result = ref<ExplainOut | null>(null)
const loadingQueue = ref(false)
const loadingBeds = ref(false)
const busy = ref(false)
const errorMessage = ref('')

const EVIDENCE_LABELS: Record<string, string> = {
  distance: '距离',
  priority_fit: '优先级-床型适配',
  ward_balance: '病房负载',
  cost: '费用',
  preference: '期望病房',
}

function evidenceLabel(key: string) {
  return EVIDENCE_LABELS[key] ?? key
}

function evidenceOf(items: EvidenceScore[]) {
  return items
}

async function loadQueue() {
  loadingQueue.value = true
  errorMessage.value = ''
  try {
    const [queuePage, reserved, admitted] = await Promise.all([
      fetchQueue({ pending_only: true, page_size: 100 }),
      fetchAllocations({ status: 'RESERVED', page_size: 200 }),
      fetchAllocations({ status: 'ADMITTED', page_size: 200 }),
    ])
    // 解释接口只接受「未分配的待入院」住院证，先剔除已持有活动分配的患者。
    const blocked = new Set(
      [...reserved.items, ...admitted.items].map((a) => a.admission_request_id),
    )
    const usable = queuePage.items.filter((x) => !blocked.has(x.admission_request_id))
    queue.value = usable
    if (!requestId.value && usable.length) {
      requestId.value = usable[0].admission_request_id
    }
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载待入院队列失败'
  } finally {
    loadingQueue.value = false
  }
}

async function loadBeds() {
  candidates.value = []
  bedId.value = ''
  result.value = null
  if (!requestId.value) return
  loadingBeds.value = true
  try {
    const data = await fetchRecommendations(Number(requestId.value), 50)
    candidates.value = data.recommendations
    if (data.recommendations.length) bedId.value = data.recommendations[0].bed_id
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载候选床位失败'
  } finally {
    loadingBeds.value = false
  }
}

watch(requestId, loadBeds)
watch(mode, () => {
  result.value = null
  consent.value = false
})

async function run() {
  if (!requestId.value || !bedId.value) return
  busy.value = true
  errorMessage.value = ''
  result.value = null
  try {
    result.value = await explainBed({
      admission_request_id: Number(requestId.value),
      bed_id: Number(bedId.value),
      mode: mode.value,
      confirm_external_call: mode.value === 'llm' && consent.value,
    })
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '生成解释失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await loadQueue()
  await loadBeds()
})
</script>

<template>
  <h1 class="page-title">辅助决策解释</h1>
  <p class="page-subtitle">真实评分证据驱动、需人工复核；仅生成说明，不执行任何床位分配。</p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <div class="alert alert--warn">
    默认是<strong>确定性规则说明</strong>，不是大模型生成。真实模型模式由后端默认关闭，
    本演示环境也没有任何已授权的付费调用；内容仅用于虚构病例的课程演示，不可用于真实临床决策。
  </div>

  <div class="card">
    <div class="form-grid">
      <div class="field">
        <label>待入院住院证</label>
        <select v-model="requestId" class="select" :disabled="loadingQueue">
          <option value="">请选择…</option>
          <option v-for="q in queue" :key="q.id" :value="q.admission_request_id">
            {{ q.certificate_no }} · {{ q.patient_name || '—' }}
          </option>
        </select>
      </div>
      <div class="field">
        <label>当前合规候选床位</label>
        <select v-model="bedId" class="select" :disabled="loadingBeds || !candidates.length">
          <option value="">请选择…</option>
          <option v-for="b in candidates" :key="b.bed_id" :value="b.bed_id">
            {{ b.bed_code }} · {{ b.ward_name }} · {{ b.score }} 分
          </option>
        </select>
      </div>
      <div class="field">
        <label>说明方式</label>
        <select v-model="mode" class="select">
          <option value="rules">确定性规则说明（默认、免费）</option>
          <option value="llm">真实 AI 生成（需服务端配置并另行确认）</option>
        </select>
      </div>
    </div>

    <label v-if="mode === 'llm'" class="checkbox" style="margin: 12px 0">
      <input v-model="consent" type="checkbox" />
      我确认此次真实模型请求可能产生费用，并理解服务端必须另外授权，且只发送去标识化的评分数据。
    </label>

    <p v-if="!loadingBeds && !candidates.length" class="note">
      当前没有合规候选床位，无法生成正向解释。
    </p>

    <div class="toolbar" style="margin-bottom: 0">
      <button
        class="btn btn--primary"
        :disabled="
          !canOperateAllocation || busy || !requestId || !bedId || (mode === 'llm' && !consent)
        "
        @click="run"
      >
        {{ busy ? '生成中…' : '生成解释预览' }}
      </button>
      <span class="note">仅 ADMIN / NURSE 可调用；本操作不写入分配记录。</span>
    </div>
  </div>

  <template v-if="result">
    <div class="card">
      <div class="card__title">
        解释结果
        <span class="tag" :class="result.real_ai ? 'tag--warn' : 'tag--ok'">{{ result.message }}</span>
      </div>
      <p style="line-height: 1.85">{{ result.explanation }}</p>
      <p class="note">
        评分 {{ result.score }} / 100 · 提供者 {{ result.provider }} ·
        {{ result.review_required ? '需要人工核对' : '—' }} ·
        {{ result.performed_allocation ? '已写入分配（不应出现）' : '未执行床位分配' }} ·
        硬约束{{ result.hard_constraints_passed ? '通过' : '未通过' }}
      </p>
      <div v-for="note in result.cautions" :key="note" class="alert alert--info">{{ note }}</div>
      <p v-if="result.warnings.length" class="note">
        现有推荐系统警示：{{ result.warnings.join('；') }}
      </p>
    </div>

    <div class="card">
      <div class="card__title">依据与来源</div>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>评分维度</th>
              <th>原始分</th>
              <th>贡献分</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in evidenceOf(result.evidence)" :key="item.key">
              <td>{{ evidenceLabel(item.key) }}</td>
              <td>{{ item.raw_score }}</td>
              <td>{{ item.contribution }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="note">
        规则版本 {{ result.version }} · 提示版本 {{ result.prompt_version || '无（规则版）' }} ·
        真实 AI {{ result.real_ai ? '是' : '否' }} · 是否外发 {{ result.externally_sent ? '是' : '否' }} ·
        token {{ result.input_tokens ?? '未知' }} / {{ result.output_tokens ?? '未知' }} ·
        成本 {{ result.cost_usd === null ? '未知或未产生' : `$${result.cost_usd}` }}
      </p>
    </div>
  </template>
</template>
