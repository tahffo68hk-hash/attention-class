<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { fetchAuditLogs } from '@/api/business'
import { ApiError } from '@/api/http'
import type { AuditLogRead } from '@/api/types'

import Pager from '@/components/Pager.vue'

const ACTION_OPTIONS = [
  { value: 'LOGIN', label: '登录成功' },
  { value: 'LOGIN_FAILED', label: '登录失败' },
  { value: 'CREATE', label: '新建' },
  { value: 'UPDATE', label: '修改' },
  { value: 'DELETE', label: '删除' },
  { value: 'ISSUE_CERTIFICATE', label: '开具住院证' },
  { value: 'PRE_ADMISSION', label: '预入院登记' },
  { value: 'RECOMMEND', label: '床位推荐' },
  { value: 'RESERVE_BED', label: '床位预占用' },
  { value: 'ADMIT', label: '办理入住' },
  { value: 'DISCHARGE', label: '办理出院' },
  { value: 'RELEASE_BED', label: '床位释放' },
  { value: 'CANCEL_ALLOCATION', label: '取消分配' },
  { value: 'REVEAL_SENSITIVE', label: '查看患者明文' },
  { value: 'PERMISSION_DENIED', label: '越权访问' },
]

const OBJECT_TYPE_OPTIONS = [
  { value: 'admission_request', label: '住院证' },
  { value: 'bed', label: '床位' },
  { value: 'allocation', label: '分配记录' },
  { value: 'patient', label: '患者' },
  { value: 'department', label: '科室' },
  { value: 'ward', label: '病房' },
  { value: 'doctor', label: '医生' },
  { value: 'user', label: '用户' },
]

const rows = ref<AuditLogRead[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')

const filters = reactive({
  username: '',
  action: '',
  object_type: '',
  result: '',
  start_at: '',
  end_at: '',
})

const page = ref(1)
const pageSize = ref(20)

const expanded = ref<Set<number>>(new Set())

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    if (filters.start_at && filters.end_at && filters.start_at > filters.end_at) {
      errorMessage.value = '开始时间不能晚于结束时间'
      return
    }
    const data = await fetchAuditLogs({
      page: page.value,
      page_size: pageSize.value,
      username: filters.username || undefined,
      action: filters.action || undefined,
      object_type: filters.object_type || undefined,
      result: filters.result || undefined,
      start_at: filters.start_at || undefined,
      end_at: filters.end_at || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载审计日志失败'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  load()
}

function resetFilters() {
  filters.username = ''
  filters.action = ''
  filters.object_type = ''
  filters.result = ''
  filters.start_at = ''
  filters.end_at = ''
  applyFilters()
}

function changePage(next: number) {
  page.value = next
  load()
}

function toggle(id: number) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function fmtTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

function actionLabel(v: string) {
  return ACTION_OPTIONS.find((o) => o.value === v)?.label ?? v
}

function detailText(detail: Record<string, unknown> | null) {
  if (!detail || !Object.keys(detail).length) return '—'
  return JSON.stringify(detail)
}

onMounted(load)
</script>

<template>
  <h1 class="page-title">操作审计</h1>
  <p class="page-subtitle">关键操作的操作人、时间、对象、动作与结果留痕（仅管理员可见）。</p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <div class="card">
    <div class="form-grid">
      <div class="field">
        <label>操作人</label>
        <input v-model.trim="filters.username" class="input" placeholder="登录名" @keyup.enter="applyFilters" />
      </div>
      <div class="field">
        <label>动作</label>
        <select v-model="filters.action" class="select" @change="applyFilters">
          <option value="">全部动作</option>
          <option v-for="o in ACTION_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>对象类型</label>
        <select v-model="filters.object_type" class="select" @change="applyFilters">
          <option value="">全部对象</option>
          <option v-for="o in OBJECT_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>结果</label>
        <select v-model="filters.result" class="select" @change="applyFilters">
          <option value="">全部结果</option>
          <option value="SUCCESS">成功</option>
          <option value="FAILURE">失败</option>
        </select>
      </div>
      <div class="field">
        <label>开始时间</label>
        <input v-model="filters.start_at" class="input" type="datetime-local" @change="applyFilters" />
      </div>
      <div class="field">
        <label>结束时间</label>
        <input v-model="filters.end_at" class="input" type="datetime-local" @change="applyFilters" />
      </div>
    </div>
    <div class="toolbar" style="margin-bottom: 0">
      <button class="btn btn--primary" :disabled="loading" @click="applyFilters">查询</button>
      <button class="btn" @click="resetFilters">重置</button>
      <span class="toolbar__spacer"></span>
      <span class="note">共 {{ total }} 条日志</span>
    </div>
  </div>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>时间</th>
          <th>操作人</th>
          <th>角色</th>
          <th>动作</th>
          <th>对象</th>
          <th>结果</th>
          <th>IP</th>
          <th>详情</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="row.id">
          <tr>
            <td>{{ fmtTime(row.created_at) }}</td>
            <td>{{ row.username || '—' }}</td>
            <td>{{ row.role || '—' }}</td>
            <td>{{ actionLabel(row.action) }}</td>
            <td>
              <span class="note">{{ row.object_type || '—' }}</span>
              <template v-if="row.object_id"> #{{ row.object_id }}</template>
            </td>
            <td>
              <span class="badge" :class="row.result === 'SUCCESS' ? 'badge--ok' : 'badge--danger'">
                {{ row.result === 'SUCCESS' ? '成功' : '失败' }}
              </span>
            </td>
            <td class="mono">{{ row.ip || '—' }}</td>
            <td>
              <button class="btn btn--sm" @click="toggle(row.id)">
                {{ expanded.has(row.id) ? '收起' : '展开' }}
              </button>
            </td>
          </tr>
          <tr v-if="expanded.has(row.id)">
            <td colspan="8" style="white-space: pre-wrap; word-break: break-all">
              <code class="note">{{ detailText(row.detail) }}</code>
            </td>
          </tr>
        </template>
        <tr v-if="!rows.length && !loading">
          <td colspan="8" class="empty">暂无审计日志</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pager :page="page" :page-size="pageSize" :total="total" @update:page="changePage" />
</template>

<style scoped>
.mono {
  font-variant-numeric: tabular-nums;
}
</style>
