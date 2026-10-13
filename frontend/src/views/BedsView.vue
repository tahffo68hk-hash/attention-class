<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  fetchBedStatusLogs,
  fetchBeds,
  fetchDepartments,
  fetchWards,
  releaseBed,
  updateBedStatus,
} from '@/api/business'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'
import type { BedRead, BedStatusLogRead, DepartmentRead, WardRead } from '@/api/types'

import Modal from '@/components/Modal.vue'
import Pager from '@/components/Pager.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const { canOperateAllocation } = useAuth()

const STATUS_OPTIONS = [
  { value: 'AVAILABLE', label: '空闲' },
  { value: 'RESERVED', label: '预占用' },
  { value: 'OCCUPIED', label: '已入住' },
  { value: 'CLEANING', label: '清洁中' },
  { value: 'MAINTENANCE', label: '维护中' },
]

const BED_TYPE_OPTIONS = [
  { value: 'NORMAL', label: '普通床' },
  { value: 'ISOLATION', label: '隔离床' },
  { value: 'MONITOR', label: '监护床' },
]

const GENDER_LIMIT_OPTIONS = [
  { value: 'MALE', label: '仅限男性' },
  { value: 'FEMALE', label: '仅限女性' },
  { value: 'ANY', label: '不限' },
]

/** 与后端 BED_STATUS_TRANSITIONS 保持一致（仅用于 UI 下拉；后端仍会校验）。 */
const TRANSITIONS: Record<string, string[]> = {
  AVAILABLE: ['RESERVED', 'MAINTENANCE'],
  RESERVED: ['OCCUPIED', 'AVAILABLE'],
  OCCUPIED: ['CLEANING'],
  CLEANING: ['AVAILABLE', 'MAINTENANCE'],
  MAINTENANCE: ['AVAILABLE'],
}

const beds = ref<BedRead[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')

const departments = ref<DepartmentRead[]>([])
const wards = ref<WardRead[]>([])

const filters = reactive({
  keyword: '',
  department_id: '' as number | '',
  ward_id: '' as number | '',
  status: '',
  bed_type: '',
  gender_limit: '',
  is_isolation: '' as '' | 'true' | 'false',
})

const page = ref(1)
const pageSize = ref(20)

const wardOptions = computed(() => {
  if (!filters.department_id) return wards.value
  return wards.value.filter((w) => w.department_id === filters.department_id)
})

function buildQuery(): Record<string, string | number | boolean> {
  const q: Record<string, string | number | boolean> = {
    page: page.value,
    page_size: pageSize.value,
  }
  if (filters.keyword) q.keyword = filters.keyword
  if (filters.department_id) q.department_id = filters.department_id
  if (filters.ward_id) q.ward_id = filters.ward_id
  if (filters.status) q.status = filters.status
  if (filters.bed_type) q.bed_type = filters.bed_type
  if (filters.gender_limit) q.gender_limit = filters.gender_limit
  if (filters.is_isolation) q.is_isolation = filters.is_isolation === 'true'
  return q
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchBeds(buildQuery())
    beds.value = data.items
    total.value = data.total
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载床位失败'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  load()
}

function resetFilters() {
  filters.keyword = ''
  filters.department_id = ''
  filters.ward_id = ''
  filters.status = ''
  filters.bed_type = ''
  filters.gender_limit = ''
  filters.is_isolation = ''
  page.value = 1
  load()
}

function changePage(next: number) {
  page.value = next
  load()
}

async function loadBaseData() {
  try {
    const [deps, ws] = await Promise.all([fetchDepartments(), fetchWards()])
    departments.value = deps
    wards.value = ws
  } catch {
    // 基础数据加载失败不阻塞床位列表
  }
}

/* ------------------------------ 状态流水 ------------------------------ */

const logsOpen = ref(false)
const logsLoading = ref(false)
const logsError = ref('')
const logs = ref<BedStatusLogRead[]>([])
const logsBed = ref<BedRead | null>(null)

async function openLogs(bed: BedRead) {
  logsBed.value = bed
  logsOpen.value = true
  logsLoading.value = true
  logsError.value = ''
  logs.value = []
  try {
    logs.value = await fetchBedStatusLogs(bed.id, 50)
  } catch (err) {
    logsError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载流水失败'
  } finally {
    logsLoading.value = false
  }
}

/* ------------------------------ 手工调状态 ------------------------------ */

const statusOpen = ref(false)
const statusBed = ref<BedRead | null>(null)
const statusForm = reactive({ status: '', reason: '' })
const statusBusy = ref(false)
const statusError = ref('')

const allowedTransitions = computed(() => {
  const from = statusBed.value?.status ?? ''
  return TRANSITIONS[from] ?? []
})

function openStatus(bed: BedRead) {
  statusBed.value = bed
  statusForm.status = (TRANSITIONS[bed.status] ?? [])[0] ?? ''
  statusForm.reason = ''
  statusError.value = ''
  statusOpen.value = true
}

async function submitStatus() {
  if (!statusBed.value || !statusForm.status) return
  statusBusy.value = true
  statusError.value = ''
  try {
    await updateBedStatus(statusBed.value.id, statusForm.status, statusForm.reason || undefined)
    statusOpen.value = false
    await load()
  } catch (err) {
    statusError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '状态调整失败'
  } finally {
    statusBusy.value = false
  }
}

/* ------------------------------ 释放床位 ------------------------------ */

const releaseBusyId = ref<number | null>(null)

async function onRelease(bed: BedRead) {
  if (!window.confirm(`确认将床位 ${bed.code} 从「清洁中」释放为空闲？`)) return
  releaseBusyId.value = bed.id
  errorMessage.value = ''
  try {
    await releaseBed(bed.id, '管理端手工释放')
    await load()
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '释放床位失败'
  } finally {
    releaseBusyId.value = null
  }
}

onMounted(() => {
  loadBaseData()
  load()
})

function fmtTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

function statusLabelOf(v: string) {
  return STATUS_OPTIONS.find((o) => o.value === v)?.label ?? v
}
</script>

<template>
  <h1 class="page-title">床位管理</h1>
  <p class="page-subtitle">按科室 / 病房 / 状态 / 床型 / 隔离 / 性别限制筛选床位，查看状态流水。</p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>

  <div class="card">
    <div class="form-grid">
      <div class="field">
        <label>关键字（床位号 / 病房号）</label>
        <input v-model.trim="filters.keyword" class="input" placeholder="如 C-101-01" @keyup.enter="applyFilters" />
      </div>
      <div class="field">
        <label>科室</label>
        <select v-model="filters.department_id" class="select" @change="filters.ward_id = ''; applyFilters()">
          <option value="">全部科室</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>
      <div class="field">
        <label>病房</label>
        <select v-model="filters.ward_id" class="select" @change="applyFilters">
          <option value="">全部病房</option>
          <option v-for="w in wardOptions" :key="w.id" :value="w.id">
            {{ w.code }} · {{ w.name }}
          </option>
        </select>
      </div>
      <div class="field">
        <label>床位状态</label>
        <select v-model="filters.status" class="select" @change="applyFilters">
          <option value="">全部状态</option>
          <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>床型</label>
        <select v-model="filters.bed_type" class="select" @change="applyFilters">
          <option value="">全部床型</option>
          <option v-for="o in BED_TYPE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>性别限制</label>
        <select v-model="filters.gender_limit" class="select" @change="applyFilters">
          <option value="">全部</option>
          <option v-for="o in GENDER_LIMIT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>隔离属性</label>
        <select v-model="filters.is_isolation" class="select" @change="applyFilters">
          <option value="">全部</option>
          <option value="true">仅隔离床</option>
          <option value="false">仅非隔离床</option>
        </select>
      </div>
    </div>
    <div class="toolbar" style="margin-bottom: 0">
      <button class="btn btn--primary" :disabled="loading" @click="applyFilters">查询</button>
      <button class="btn" @click="resetFilters">重置</button>
      <span class="toolbar__spacer"></span>
      <span class="note">共 {{ total }} 张床位</span>
    </div>
  </div>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>床位号</th>
          <th>科室 / 病房</th>
          <th>楼层</th>
          <th>床型</th>
          <th>性别限制</th>
          <th>隔离</th>
          <th>状态</th>
          <th>当前患者</th>
          <th class="num">日费用</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="bed in beds" :key="bed.id">
          <td class="mono">{{ bed.code }}</td>
          <td>
            {{ bed.department_name }}<br />
            <span class="note">{{ bed.ward_code }} · {{ bed.ward_name }}</span>
          </td>
          <td>{{ bed.floor }} 层</td>
          <td><StatusBadge kind="bedType" :value="bed.bed_type" :label="bed.bed_type_label" /></td>
          <td>
            <StatusBadge kind="gender" :value="bed.gender_limit" :label="bed.gender_limit_label" />
          </td>
          <td>
            <span v-if="bed.is_isolation" class="badge badge--danger">隔离床</span>
            <span v-else class="note">—</span>
          </td>
          <td><StatusBadge kind="bed" :value="bed.status" :label="bed.status_label" /></td>
          <td>{{ bed.current_patient_name || '—' }}</td>
          <td class="num">¥{{ Number(bed.daily_rate).toFixed(2) }}</td>
          <td style="white-space: nowrap">
            <button class="btn btn--sm" @click="openLogs(bed)">流水</button>
            <button
              v-if="canOperateAllocation"
              class="btn btn--sm"
              @click="openStatus(bed)"
            >
              调状态
            </button>
            <button
              v-if="canOperateAllocation && bed.status === 'CLEANING'"
              class="btn btn--sm btn--primary"
              :disabled="releaseBusyId === bed.id"
              @click="onRelease(bed)"
            >
              {{ releaseBusyId === bed.id ? '释放中…' : '释放' }}
            </button>
          </td>
        </tr>
        <tr v-if="!beds.length && !loading">
          <td colspan="10" class="empty">没有符合条件的床位</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pager :page="page" :page-size="pageSize" :total="total" @update:page="changePage" />

  <!-- 状态流水 -->
  <Modal :open="logsOpen" :title="`床位状态流水 · ${logsBed?.code ?? ''}`" width="720px" @close="logsOpen = false">
    <p v-if="logsLoading" class="spinner-text">加载中…</p>
    <div v-else-if="logsError" class="alert alert--danger">{{ logsError }}</div>
    <table v-else class="score-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>变更</th>
          <th>原因</th>
          <th>关联分配</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="log in logs" :key="log.id">
          <td>{{ fmtTime(log.created_at) }}</td>
          <td>
            <span class="note">{{ log.from_status ? statusLabelOf(log.from_status) : '—' }}</span>
            →
            <strong>{{ statusLabelOf(log.to_status) }}</strong>
          </td>
          <td>{{ log.reason || '—' }}</td>
          <td>{{ log.allocation_id ? `#${log.allocation_id}` : '—' }}</td>
        </tr>
        <tr v-if="!logs.length">
          <td colspan="4" class="empty">暂无状态流水</td>
        </tr>
      </tbody>
    </table>
  </Modal>

  <!-- 手工调状态 -->
  <Modal :open="statusOpen" :title="`调整床位状态 · ${statusBed?.code ?? ''}`" @close="statusOpen = false">
    <div v-if="statusError" class="alert alert--danger">{{ statusError }}</div>
    <div class="field">
      <label>当前状态</label>
      <div><StatusBadge kind="bed" :value="statusBed?.status ?? ''" :label="statusBed?.status_label" /></div>
    </div>
    <div class="field">
      <label>目标状态（仅列出合法流转）</label>
      <select v-model="statusForm.status" class="select">
        <option v-for="s in allowedTransitions" :key="s" :value="s">{{ statusLabelOf(s) }}</option>
      </select>
    </div>
    <div class="field">
      <label>调整说明（可选）</label>
      <input v-model.trim="statusForm.reason" class="input" placeholder="如：设备保养 / 消毒完成" />
    </div>
    <p class="note">状态流转受后端状态机约束，非法流转会返回 409。</p>
    <template #footer>
      <button class="btn" @click="statusOpen = false">取消</button>
      <button class="btn btn--primary" :disabled="statusBusy || !statusForm.status" @click="submitStatus">
        {{ statusBusy ? '提交中…' : '确认调整' }}
      </button>
    </template>
  </Modal>
</template>

<style scoped>
.mono {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
</style>
