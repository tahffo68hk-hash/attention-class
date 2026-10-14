<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchDashboardSummary } from '@/api/business'
import { ApiError } from '@/api/http'
import type { DashboardSummary } from '@/api/types'

const summary = ref<DashboardSummary | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const priorityTone: Record<string, string> = {
  CRITICAL: 'badge--danger',
  SEVERE: 'badge--warn',
  URGENT: 'badge--info',
  NORMAL: 'badge--muted',
  MILD: 'badge--muted',
}

const occupancyTone = computed(() => {
  const rate = summary.value?.occupancy_rate ?? 0
  if (rate >= 90) return 'stat__value--bad'
  if (rate >= 70) return 'stat__value--warn'
  return 'stat__value--ok'
})

/** Hero 进度条宽度（0–100，防御异常值） */
const occupancyWidth = computed(() => {
  const rate = summary.value?.occupancy_rate ?? 0
  return `${Math.max(0, Math.min(100, rate))}%`
})

const metrics = computed(() => {
  const s = summary.value
  if (!s) return []
  return [
    { key: 'total_beds', label: '总床位', value: s.total_beds, tone: '' },
    { key: 'available_beds', label: '空闲床位', value: s.available_beds, tone: 'stat__value--ok' },
    { key: 'reserved_beds', label: '预占用', value: s.reserved_beds, tone: 'stat__value--warn' },
    { key: 'occupied_beds', label: '已入住', value: s.occupied_beds, tone: '' },
    { key: 'cleaning_beds', label: '清洁中', value: s.cleaning_beds, tone: '' },
    { key: 'maintenance_beds', label: '维护中', value: s.maintenance_beds, tone: 'stat__value--bad' },
    { key: 'occupancy_rate', label: '占用率', value: `${s.occupancy_rate}%`, tone: occupancyTone.value },
    {
      key: 'pending_admission_patients',
      label: '待入院人数',
      value: s.pending_admission_patients,
      tone: 'stat__value--warn',
    },
  ]
})

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    summary.value = await fetchDashboardSummary()
  } catch (err) {
    errorMessage.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载看板数据失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmtTime(value: string | undefined) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="pagehead">
    <div>
      <h1>管理看板</h1>
      <p>床位总量、占用情况、待入院队列与隔离床资源一览（虚构演示数据）。</p>
    </div>
    <button class="btn outline" :disabled="loading" @click="load">
      {{ loading ? '刷新中…' : '刷新数据' }}
    </button>
  </div>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <template v-if="summary">
    <section class="dashboard-hero">
      <div>
        <span class="hero-kicker">CLINICAL OPERATIONS / TODAY</span>
        <h2>床位资源与入院流程，一目了然</h2>
        <p>
          基于当前业务数据库实时汇总 · 数据仅用于教学模拟 · 数据生成时间：{{
            fmtTime(summary.generated_at)
          }}
        </p>
        <div class="dashboard-progress" style="margin-top: 12px; max-width: 420px">
          <span :style="{ width: occupancyWidth }"></span>
        </div>
        <p class="summary-note">
          当前占用率 {{ summary.occupancy_rate }}%（已入住 {{ summary.occupied_beds }} +
          预占用 {{ summary.reserved_beds }}）
        </p>
      </div>
      <div class="hero-action">
        <RouterLink to="/beds" class="btn outline">查看床位资源 ↗</RouterLink>
        <RouterLink to="/optimization" class="btn">全局排床分析 →</RouterLink>
      </div>
    </section>

    <div class="grid" style="margin-bottom: 18px">
      <div v-for="m in metrics" :key="m.key" class="stat metric">
        <div class="stat__label">{{ m.label }}</div>
        <div class="stat__value" :class="m.tone">{{ m.value }}</div>
      </div>
    </div>

    <div class="grid two">
      <section class="card">
        <h2 class="card__title">隔离床资源</h2>
        <div class="kv-inline">
          <span>隔离床总数：<strong>{{ summary.isolation_beds_total }}</strong></span>
          <span>可用：<strong class="stat__value--ok">{{ summary.isolation_beds_available }}</strong></span>
          <span>在用（预占用 + 已入住）：<strong>{{ summary.isolation_beds_in_use }}</strong></span>
        </div>
      </section>

      <section class="card">
        <h2 class="card__title">今日动态</h2>
        <div class="kv-inline">
          <span>活动分配：<strong>{{ summary.active_allocations }}</strong></span>
          <span>今日入住：<strong>{{ summary.admitted_today }}</strong></span>
          <span>今日出院：<strong>{{ summary.discharged_today }}</strong></span>
        </div>
      </section>
    </div>

    <section class="card">
      <h2 class="card__title">待入院队列（按病情优先级）</h2>
      <div>
        <span
          v-for="item in summary.pending_queue_by_priority"
          :key="item.priority"
          class="badge"
          :class="priorityTone[item.priority] || 'badge--muted'"
          style="margin-right: 8px"
        >
          {{ item.priority_label }}：{{ item.count }} 人
        </span>
      </div>
    </section>

    <section class="card">
      <h2 class="card__title">分科室床位统计</h2>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>科室</th>
              <th class="num">总床位</th>
              <th class="num">空闲</th>
              <th class="num">预占用</th>
              <th class="num">已入住</th>
              <th class="num">清洁中</th>
              <th class="num">维护中</th>
              <th class="num">占用率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in summary.department_stats" :key="row.department_id">
              <td>{{ row.department_name }}</td>
              <td class="num">{{ row.total }}</td>
              <td class="num">{{ row.available }}</td>
              <td class="num">{{ row.reserved }}</td>
              <td class="num">{{ row.occupied }}</td>
              <td class="num">{{ row.cleaning }}</td>
              <td class="num">{{ row.maintenance }}</td>
              <td class="num">{{ row.occupancy_rate }}%</td>
            </tr>
            <tr v-if="!summary.department_stats.length">
              <td colspan="8" class="empty">暂无科室床位数据</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </template>

  <p v-else-if="loading" class="spinner-text">正在加载看板数据…</p>
</template>
