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
  <h1 class="page-title">管理看板</h1>
  <p class="page-subtitle">床位总量、占用情况、待入院队列与隔离床资源一览（虚构演示数据）。</p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <div class="toolbar">
    <button class="btn btn--primary" :disabled="loading" @click="load">
      {{ loading ? '刷新中…' : '刷新数据' }}
    </button>
    <span class="toolbar__spacer"></span>
    <span class="note">数据生成时间：{{ fmtTime(summary?.generated_at) }}</span>
  </div>

  <template v-if="summary">
    <div class="grid">
      <div class="stat">
        <div class="stat__label">总床位</div>
        <div class="stat__value">{{ summary.total_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">空闲床位</div>
        <div class="stat__value stat__value--ok">{{ summary.available_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">预占用</div>
        <div class="stat__value stat__value--warn">{{ summary.reserved_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">已入住</div>
        <div class="stat__value">{{ summary.occupied_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">清洁中</div>
        <div class="stat__value">{{ summary.cleaning_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">维护中</div>
        <div class="stat__value stat__value--bad">{{ summary.maintenance_beds }}</div>
      </div>
      <div class="stat">
        <div class="stat__label">占用率（已入住 + 预占用）</div>
        <div class="stat__value" :class="occupancyTone">{{ summary.occupancy_rate }}%</div>
      </div>
      <div class="stat">
        <div class="stat__label">待入院人数</div>
        <div class="stat__value stat__value--warn">{{ summary.pending_admission_patients }}</div>
      </div>
    </div>

    <section class="card" style="margin-top: 16px">
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
        <span>活动分配（预占用 + 已入住）：<strong>{{ summary.active_allocations }}</strong></span>
        <span>今日入住：<strong>{{ summary.admitted_today }}</strong></span>
        <span>今日出院：<strong>{{ summary.discharged_today }}</strong></span>
      </div>
    </section>

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
      <div class="table-wrap" style="border: none; background: none">
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
