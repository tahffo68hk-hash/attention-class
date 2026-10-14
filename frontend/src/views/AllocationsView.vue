<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  admitAllocation,
  cancelAllocation,
  createAllocation,
  dischargeAllocation,
  fetchAdmissionRequests,
  fetchAllocations,
  fetchBeds,
  fetchDepartments,
  fetchRecommendations,
  reassignAllocation,
} from '@/api/business'
import { ApiError } from '@/api/http'
import { useAuth } from '@/stores/auth'
import type {
  AdmissionRequestRead,
  AllocationRead,
  BedRead,
  BedRecommendation,
  DepartmentRead,
} from '@/api/types'

import Modal from '@/components/Modal.vue'
import Pager from '@/components/Pager.vue'
import StatusBadge from '@/components/StatusBadge.vue'

const { canOperateAllocation } = useAuth()

const STATUS_OPTIONS = [
  { value: 'RESERVED', label: '预占用' },
  { value: 'ADMITTED', label: '已入住' },
  { value: 'DISCHARGED', label: '已出院' },
  { value: 'CANCELLED', label: '已取消' },
]

const MODE_OPTIONS = [
  { value: 'RECOMMENDED', label: '采纳推荐' },
  { value: 'MANUAL', label: '人工选择' },
]

const rows = ref<AllocationRead[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const feedback = ref('')

const departments = ref<DepartmentRead[]>([])

const filters = reactive({
  status: '',
  department_id: '' as number | '',
  mode: '',
})

const page = ref(1)
const pageSize = ref(20)

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchAllocations({
      page: page.value,
      page_size: pageSize.value,
      status: filters.status || undefined,
      department_id: filters.department_id || undefined,
      mode: filters.mode || undefined,
    })
    rows.value = data.items
    total.value = data.total
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载分配记录失败'
  } finally {
    loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  load()
}

function changePage(next: number) {
  page.value = next
  load()
}

/* ------------------------------ 行内动作 ------------------------------ */

const busyId = ref<number | null>(null)

async function guaedRun(id: number, fn: () => Promise<AllocationRead>, okText: string) {
  busyId.value = id
  errorMessage.value = ''
  feedback.value = ''
  try {
    const alloc = await fn()
    feedback.value = `${okText}（分配 #${alloc.id}，床位 ${alloc.bed_code ?? '—'}）`
    await load()
  } catch (err) {
    errorMessage.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '操作失败'
  } finally {
    busyId.value = null
  }
}

function onAdmit(row: AllocationRead) {
  guaedRun(row.id, () => admitAllocation(row.id), '已办理入住')
}

function onDischarge(row: AllocationRead) {
  const reason = window.prompt('请输入出院说明（可留空）：', '') ?? undefined
  guaedRun(row.id, () => dischargeAllocation(row.id, reason), '已办理出院，床位转入清洁中')
}

function onCancel(row: AllocationRead) {
  if (!window.confirm(`确认取消分配 #${row.id}（床位 ${row.bed_code ?? '—'}）的预占用？`)) return
  const reason = window.prompt('请输入取消原因（可留空）：', '') ?? undefined
  guaedRun(row.id, () => cancelAllocation(row.id, reason), '已取消预占用，床位回到空闲')
}

/* ------------------------------ 人工换床 ------------------------------ */

const reassignOpen = ref(false)
const reassignRow = ref<AllocationRead | null>(null)
const reassignCandidates = ref<BedRecommendation[]>([])
const reassignLoading = ref(false)
const reassignBusy = ref(false)
const reassignError = ref('')
const reassignForm = reactive({ bedId: '' as number | '', reason: '' })

async function openReassign(row: AllocationRead) {
  reassignOpen.value = true
  reassignRow.value = row
  reassignError.value = ''
  reassignCandidates.value = []
  reassignForm.bedId = ''
  reassignForm.reason = ''
  reassignLoading.value = true
  try {
    // 复用推荐接口拿到「合规且当前可用」的候选床位，排除当前占用的那张
    const data = await fetchRecommendations(row.admission_request_id, 50)
    reassignCandidates.value = data.recommendations.filter((b) => b.bed_id !== row.bed_id)
  } catch (err) {
    reassignError.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载候选床位失败'
  } finally {
    reassignLoading.value = false
  }
}

async function submitReassign() {
  if (!reassignRow.value || !reassignForm.bedId || !reassignForm.reason.trim()) return
  reassignBusy.value = true
  reassignError.value = ''
  try {
    const alloc = await reassignAllocation(
      reassignRow.value.id,
      Number(reassignForm.bedId),
      reassignForm.reason.trim(),
    )
    reassignOpen.value = false
    feedback.value = `已换床到 ${alloc.bed_code ?? '—'}（新分配 #${alloc.id}，原分配已置为已取消）`
    await load()
  } catch (err) {
    reassignError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '换床失败'
  } finally {
    reassignBusy.value = false
  }
}

/* ------------------------------ 新建分配 ------------------------------ */

const createOpen = ref(false)
const createStep = reactive({
  requestId: '' as number | '',
  mode: 'RECOMMENDED' as 'RECOMMENDED' | 'MANUAL',
  bedId: '' as number | '',
  note: '',
})
const pendingRequests = ref<AdmissionRequestRead[]>([])
const availableBeds = ref<BedRead[]>([])
const createLoading = ref(false)
const createBusy = ref(false)
const createError = ref('')

const selectedRequest = computed(
  () => pendingRequests.value.find((r) => r.id === createStep.requestId) ?? null,
)

/**
 * 幂等键：同一次「新建分配」意图只生成一次，重试复用同一键，
 * 后端据此保证网络重试不会重复占用床位（同键同参返回原分配）。
 */
const createIdempotencyKey = ref('')

function newIdempotencyKey(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `alloc-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

async function openCreate() {
  createOpen.value = true
  createError.value = ''
  createStep.requestId = ''
  createStep.mode = 'RECOMMENDED'
  createStep.bedId = ''
  createStep.note = ''
  createIdempotencyKey.value = newIdempotencyKey()
  availableBeds.value = []
  createLoading.value = true
  try {
    const data = await fetchAdmissionRequests({ status: 'PRE_ADMITTED', page_size: 100 })
    pendingRequests.value = data.items
  } catch (err) {
    createError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载待入院列表失败'
  } finally {
    createLoading.value = false
  }
}

// 选择住院证 / 切换为人工选择时，拉取同科室空闲床位
watch(
  () => [createStep.requestId, createStep.mode] as const,
  async () => {
    createStep.bedId = ''
    availableBeds.value = []
    if (createStep.mode !== 'MANUAL' || !selectedRequest.value) return
    try {
      const data = await fetchBeds({
        status: 'AVAILABLE',
        department_id: selectedRequest.value.department_id,
        page_size: 200,
      })
      availableBeds.value = data.items
    } catch (err) {
      createError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载空闲床位失败'
    }
  },
)

async function submitCreate() {
  if (!createStep.requestId) return
  createBusy.value = true
  createError.value = ''
  try {
    const alloc = await createAllocation(
      {
        admission_request_id: createStep.requestId,
        bed_id: createStep.mode === 'MANUAL' ? Number(createStep.bedId) || null : null,
        confirm_top_recommendation: createStep.mode === 'RECOMMENDED',
        note: createStep.note || undefined,
      },
      createIdempotencyKey.value || undefined,
    )
    createOpen.value = false
    feedback.value = `已预占用床位 ${alloc.bed_code ?? '—'}（分配 #${alloc.id}）。可在下方列表中办理入住。`
    await load()
  } catch (err) {
    createError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '预占用失败'
  } finally {
    createBusy.value = false
  }
}

onMounted(async () => {
  try {
    departments.value = await fetchDepartments()
  } catch {
    // 忽略
  }
  load()
})

function fmtTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}
</script>

<template>
  <h1 class="page-title">分配与住院办理</h1>
  <p class="page-subtitle">床位预占用、办理入住、办理出院、取消预占用全流程留痕。</p>

  <div v-if="errorMessage" class="alert alert--danger">{{ errorMessage }}</div>
  <div v-if="feedback" class="alert alert--ok">{{ feedback }}</div>

  <div class="card">
    <div class="form-grid">
      <div class="field">
        <label>分配状态</label>
        <select v-model="filters.status" class="select" @change="applyFilters">
          <option value="">全部状态</option>
          <option v-for="o in STATUS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>科室</label>
        <select v-model="filters.department_id" class="select" @change="applyFilters">
          <option value="">全部科室</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>
      <div class="field">
        <label>分配方式</label>
        <select v-model="filters.mode" class="select" @change="applyFilters">
          <option value="">全部方式</option>
          <option v-for="o in MODE_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
    </div>
    <div class="toolbar" style="margin-bottom: 0">
      <button
        v-if="canOperateAllocation"
        class="btn btn--primary"
        @click="openCreate"
      >
        新建床位分配
      </button>
      <button class="btn" :disabled="loading" @click="load">刷新</button>
      <span class="toolbar__spacer"></span>
      <span class="note">共 {{ total }} 条分配记录</span>
    </div>
  </div>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>#</th>
          <th>住院证</th>
          <th>患者</th>
          <th>床位 / 病房</th>
          <th>科室</th>
          <th>方式</th>
          <th>状态</th>
          <th>操作人</th>
          <th>预占用时间</th>
          <th>入住时间</th>
          <th>出院时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td>{{ row.id }}</td>
          <td class="mono">{{ row.certificate_no || '—' }}</td>
          <td>{{ row.patient_name || `患者 #${row.patient_id}` }}</td>
          <td>
            <span class="mono">{{ row.bed_code || '—' }}</span><br />
            <span class="note">{{ row.ward_name || '—' }}</span>
          </td>
          <td>{{ row.department_name || '—' }}</td>
          <td>
            <span class="badge" :class="row.mode === 'RECOMMENDED' ? 'badge--info' : 'badge--muted'">
              {{ row.mode_label || row.mode }}
            </span>
          </td>
          <td><StatusBadge kind="allocation" :value="row.status" :label="row.status_label" /></td>
          <td>{{ row.operator_name || '—' }}</td>
          <td>{{ fmtTime(row.reserved_at) }}</td>
          <td>{{ fmtTime(row.admitted_at) }}</td>
          <td>{{ fmtTime(row.discharged_at) }}</td>
          <td style="white-space: nowrap">
            <template v-if="canOperateAllocation">
              <button
                v-if="row.status === 'RESERVED'"
                class="btn btn--sm btn--primary"
                :disabled="busyId === row.id"
                @click="onAdmit(row)"
              >
                办理入住
              </button>
              <button
                v-if="row.status === 'RESERVED'"
                class="btn btn--sm"
                :disabled="busyId === row.id"
                @click="openReassign(row)"
              >
                换床
              </button>
              <button
                v-if="row.status === 'RESERVED'"
                class="btn btn--sm"
                :disabled="busyId === row.id"
                @click="onCancel(row)"
              >
                取消
              </button>
              <button
                v-if="row.status === 'ADMITTED'"
                class="btn btn--sm btn--primary"
                :disabled="busyId === row.id"
                @click="onDischarge(row)"
              >
                办理出院
              </button>
            </template>
            <span v-else class="note">只读</span>
          </td>
        </tr>
        <tr v-if="!rows.length && !loading">
          <td colspan="12" class="empty">暂无分配记录</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pager :page="page" :page-size="pageSize" :total="total" @update:page="changePage" />

  <!-- 新建分配 -->
  <Modal :open="createOpen" title="新建床位分配" width="640px" @close="createOpen = false">
    <div v-if="createError" class="alert alert--danger">{{ createError }}</div>

    <p v-if="createLoading" class="spinner-text">加载待入院住院证…</p>
    <template v-else>
      <div class="field">
        <label>待入院住院证</label>
        <select v-model="createStep.requestId" class="select">
          <option value="">请选择…</option>
          <option v-for="r in pendingRequests" :key="r.id" :value="r.id">
            {{ r.certificate_no }} · {{ r.patient_name }} · {{ r.department_name }}
            · {{ r.priority_label }}<template v-if="r.isolation_required"> · 需隔离</template>
          </option>
        </select>
        <p v-if="!pendingRequests.length" class="note">
          当前没有待入院住院证，请先在「住院证与预登记」完成预登记。
        </p>
      </div>

      <div v-if="selectedRequest" class="field">
        <label>分配方式</label>
        <div>
          <label class="checkbox">
            <input v-model="createStep.mode" type="radio" value="RECOMMENDED" /> 采纳推荐排序第一名
          </label>
          <label class="checkbox" style="margin-left: 16px">
            <input v-model="createStep.mode" type="radio" value="MANUAL" /> 人工选择床位
          </label>
        </div>
      </div>

      <div v-if="selectedRequest && createStep.mode === 'MANUAL'" class="field">
        <label>选择床位（{{ selectedRequest.department_name }} · 空闲）</label>
        <select v-model="createStep.bedId" class="select">
          <option value="">请选择床位…</option>
          <option v-for="b in availableBeds" :key="b.id" :value="b.id">
            {{ b.code }} · {{ b.ward_name }} · {{ b.bed_type_label }}
            <template v-if="b.is_isolation"> · 隔离床</template>
            · {{ b.gender_limit_label }}
          </option>
        </select>
        <p class="note">
          人工选择同样受硬约束校验（科室 / 性别 / 隔离），不满足时后端返回 422 并列出违反项。
        </p>
      </div>

      <div v-if="selectedRequest" class="field">
        <label>操作说明（可选）</label>
        <input v-model.trim="createStep.note" class="input" placeholder="如：家属在场确认" />
      </div>
    </template>

    <template #footer>
      <button class="btn" @click="createOpen = false">取消</button>
      <button
        class="btn btn--primary"
        :disabled="
          createBusy ||
          !createStep.requestId ||
          (createStep.mode === 'MANUAL' && !createStep.bedId)
        "
        @click="submitCreate"
      >
        {{ createBusy ? '提交中…' : '确认预占用' }}
      </button>
    </template>
  </Modal>

  <!-- 人工换床 -->
  <Modal
    :open="reassignOpen"
    title="人工换床（仅预占用状态）"
    width="620px"
    @close="reassignOpen = false"
  >
    <div v-if="reassignError" class="alert alert--danger">{{ reassignError }}</div>

    <p class="note">
      分配 #{{ reassignRow?.id }} · 床位 {{ reassignRow?.bed_code || '—' }} ·
      患者 {{ reassignRow?.patient_name || '—' }}
    </p>

    <p v-if="reassignLoading" class="spinner-text">加载合规候选床位…</p>
    <template v-else>
      <div class="field">
        <label>新床位（同科室、当前空闲、通过硬约束校验）</label>
        <select v-model="reassignForm.bedId" class="select">
          <option value="">请选择床位…</option>
          <option v-for="b in reassignCandidates" :key="b.bed_id" :value="b.bed_id">
            {{ b.bed_code }} · {{ b.ward_name }} · {{ b.bed_type_label }} ·
            {{ b.score }} 分<template v-if="b.is_isolation"> · 隔离床</template>
          </option>
        </select>
        <p v-if="!reassignCandidates.length" class="note">
          当前没有其他合规可用床位，无法换床。
        </p>
      </div>

      <div class="field">
        <label>换床原因（必填）</label>
        <input
          v-model.trim="reassignForm.reason"
          class="input"
          maxlength="255"
          placeholder="如：原床位邻近感染区，调整位置"
        />
      </div>

      <p class="note">
        提交后原分配会置为「已取消」，并生成一条新的预占用记录；床位状态与审计在同一事务内，
        任一步失败都会整体回滚。
      </p>
    </template>

    <template #footer>
      <button class="btn" @click="reassignOpen = false">取消</button>
      <button
        class="btn btn--primary"
        :disabled="reassignBusy || !reassignForm.bedId || !reassignForm.reason.trim()"
        @click="submitReassign"
      >
        {{ reassignBusy ? '提交中…' : '确认换床' }}
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
