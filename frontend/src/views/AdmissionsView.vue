<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  cancelAdmissionRequest,
  createAdmissionRequest,
  createPreadmission,
  fetchAdmissionRequests,
  fetchDepartments,
  fetchDoctors,
  fetchPatients,
  fetchWards,
  issueAdmissionRequest,
} from '@/api/business'
import { ApiError } from '@/api/http'
import type {
  AdmissionRequestCreate,
  AdmissionRequestRead,
  DepartmentRead,
  DoctorRead,
  PatientRead,
  WardRead,
} from '@/api/types'
import Modal from '@/components/Modal.vue'
import Pager from '@/components/Pager.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAuth } from '@/stores/auth'

const router = useRouter()
const { canIssueCertificate, canPreadmit, isDoctor, currentUser } = useAuth()

const PRIORITIES = [
  { value: 'CRITICAL', label: '危重' },
  { value: 'SEVERE', label: '重症' },
  { value: 'URGENT', label: '急症' },
  { value: 'NORMAL', label: '普通' },
  { value: 'MILD', label: '轻症' },
]

const STATUSES = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'ISSUED', label: '已开具' },
  { value: 'PRE_ADMITTED', label: '待入院' },
  { value: 'ADMITTED', label: '已入住' },
  { value: 'COMPLETED', label: '已出院' },
  { value: 'CANCELLED', label: '已取消' },
]

/* ------------------------------- 列表数据 ------------------------------- */

const rows = ref<AdmissionRequestRead[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const listError = ref('')

const filters = reactive({
  department_id: '',
  status: '',
  priority: '',
  isolation_required: '',
  keyword: '',
})

const departments = ref<DepartmentRead[]>([])
const doctors = ref<DoctorRead[]>([])
const wards = ref<WardRead[]>([])
const patients = ref<PatientRead[]>([])

async function loadList() {
  loading.value = true
  listError.value = ''
  try {
    const res = await fetchAdmissionRequests({
      department_id: filters.department_id || undefined,
      status: filters.status || undefined,
      priority: filters.priority || undefined,
      isolation_required:
        filters.isolation_required === '' ? undefined : filters.isolation_required === 'true',
      keyword: filters.keyword || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = res.items
    total.value = res.total
  } catch (err) {
    listError.value = err instanceof ApiError ? `[${err.code}] ${err.message}` : '加载住院证失败'
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  try {
    const [deps, docs, wds] = await Promise.all([
      fetchDepartments({ is_active: true }),
      fetchDoctors(),
      fetchWards(),
    ])
    departments.value = deps
    doctors.value = docs
    wards.value = wds
    // 患者列表用于开具住院证时选择
    const ps = await fetchPatients({ page: 1, page_size: 200 })
    patients.value = ps.items
  } catch {
    // 选项加载失败不阻塞主列表
  }
}

function resetFilter() {
  filters.department_id = ''
  filters.status = ''
  filters.priority = ''
  filters.isolation_required = ''
  filters.keyword = ''
  page.value = 1
  loadList()
}

function changePage(p: number) {
  page.value = p
  loadList()
}

onMounted(async () => {
  await Promise.all([loadOptions(), loadList()])
})

/* ------------------------------ 操作反馈 ------------------------------ */

const feedback = ref<{ type: 'ok' | 'danger'; text: string } | null>(null)

function setFeedback(type: 'ok' | 'danger', text: string) {
  feedback.value = { type, text }
}

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const detail = err.detail ? ` · ${JSON.stringify(err.detail)}` : ''
    return `[${err.code}] ${err.message}${detail}`
  }
  return fallback
}

/* --------------------------- 状态流转操作 --------------------------- */

const actionBusy = ref(false)

async function doIssue(row: AdmissionRequestRead) {
  actionBusy.value = true
  try {
    await issueAdmissionRequest(row.id)
    setFeedback('ok', `住院证 ${row.certificate_no} 已开具`)
    await loadList()
  } catch (err) {
    setFeedback('danger', describeError(err, '开具失败'))
  } finally {
    actionBusy.value = false
  }
}

async function doCancel(row: AdmissionRequestRead) {
  if (!window.confirm(`确认取消住院证 ${row.certificate_no}？`)) return
  actionBusy.value = true
  try {
    await cancelAdmissionRequest(row.id)
    setFeedback('ok', `住院证 ${row.certificate_no} 已取消`)
    await loadList()
  } catch (err) {
    setFeedback('danger', describeError(err, '取消失败'))
  } finally {
    actionBusy.value = false
  }
}

function goRecommend(row: AdmissionRequestRead) {
  router.push({ name: 'recommendations', query: { request: String(row.id) } })
}

/* ---------------------------- 开具住院证 ---------------------------- */

const createOpen = ref(false)
const createBusy = ref(false)
const createError = ref('')

const createForm = reactive({
  patient_id: '' as string | number,
  department_id: '' as string | number,
  doctor_id: '' as string | number,
  priority: 'NORMAL',
  isolation_required: false,
  infection_type: '',
  diagnosis: '',
  preferred_ward_id: '' as string | number,
  notes: '',
  issue: true,
})

const filteredWards = computed(() =>
  createForm.department_id
    ? wards.value.filter((w) => w.department_id === Number(createForm.department_id))
    : wards.value,
)

function openCreate() {
  createError.value = ''
  createForm.patient_id = ''
  createForm.department_id = ''
  createForm.doctor_id = currentUser.value?.doctor_id ?? ''
  createForm.priority = 'NORMAL'
  createForm.isolation_required = false
  createForm.infection_type = ''
  createForm.diagnosis = ''
  createForm.preferred_ward_id = ''
  createForm.notes = ''
  createForm.issue = true
  createOpen.value = true
}

async function submitCreate() {
  if (!createForm.patient_id || !createForm.department_id) {
    createError.value = '请选择患者与收治科室'
    return
  }
  if (isDoctor.value && !createForm.doctor_id) {
    createError.value = '当前医生账号未关联医生档案，请选择开具医生'
    return
  }
  createBusy.value = true
  createError.value = ''
  const payload: AdmissionRequestCreate = {
    patient_id: Number(createForm.patient_id),
    department_id: Number(createForm.department_id),
    priority: createForm.priority,
    isolation_required: createForm.isolation_required,
    issue: createForm.issue,
  }
  if (createForm.doctor_id) payload.doctor_id = Number(createForm.doctor_id)
  if (createForm.infection_type) payload.infection_type = createForm.infection_type
  if (createForm.diagnosis) payload.diagnosis = createForm.diagnosis
  if (createForm.preferred_ward_id) payload.preferred_ward_id = Number(createForm.preferred_ward_id)
  if (createForm.notes) payload.notes = createForm.notes

  try {
    const created = await createAdmissionRequest(payload)
    setFeedback('ok', `住院证 ${created.certificate_no} 已创建（${created.status_label}）`)
    createOpen.value = false
    await loadList()
  } catch (err) {
    createError.value = describeError(err, '开具住院证失败')
  } finally {
    createBusy.value = false
  }
}

/* ---------------------------- 预入院登记 ---------------------------- */

const preOpen = ref(false)
const preBusy = ref(false)
const preError = ref('')
const preTarget = ref<AdmissionRequestRead | null>(null)

const preForm = reactive({
  contact_phone: '',
  emergency_contact: '',
  emergency_phone: '',
  deposit_amount: '3000.00',
  pay_deposit: true,
  supplement_notes: '',
})

function openPreadmit(row: AdmissionRequestRead) {
  preTarget.value = row
  preError.value = ''
  preForm.contact_phone = ''
  preForm.emergency_contact = ''
  preForm.emergency_phone = ''
  preForm.deposit_amount = '3000.00'
  preForm.pay_deposit = true
  preForm.supplement_notes = ''
  preOpen.value = true
}

async function submitPreadmit() {
  if (!preTarget.value) return
  preBusy.value = true
  preError.value = ''
  try {
    const pre = await createPreadmission(preTarget.value.id, {
      contact_phone: preForm.contact_phone || null,
      emergency_contact: preForm.emergency_contact || null,
      emergency_phone: preForm.emergency_phone || null,
      deposit_amount: preForm.deposit_amount || '0',
      pay_deposit: preForm.pay_deposit,
      supplement_notes: preForm.supplement_notes || null,
    })
    setFeedback(
      'ok',
      `预入院登记完成：队列号 ${pre.queue_no}，预交金状态「${pre.deposit_status_label}」（模拟）`,
    )
    preOpen.value = false
    await loadList()
  } catch (err) {
    preError.value = describeError(err, '预入院登记失败')
  } finally {
    preBusy.value = false
  }
}

function fmt(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}
</script>

<template>
  <h1 class="page-title">住院证与预登记</h1>
  <p class="page-subtitle">
    开具住院证（记录病情优先级与隔离需求）→ 预入院登记（模拟预交金）→ 进入待入院队列。
  </p>

  <div v-if="feedback" class="alert" :class="`alert--${feedback.type}`">
    {{ feedback.text }}
    <button class="btn btn--sm" style="margin-left: 10px" @click="feedback = null">关闭</button>
  </div>
  <div v-if="listError" class="alert alert--danger">{{ listError }}</div>

  <div class="toolbar">
    <div class="field">
      <label>收治科室</label>
      <select v-model="filters.department_id" class="select" @change="changePage(1)">
        <option value="">全部</option>
        <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
      </select>
    </div>
    <div class="field">
      <label>状态</label>
      <select v-model="filters.status" class="select" @change="changePage(1)">
        <option value="">全部</option>
        <option v-for="s in STATUSES" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
    </div>
    <div class="field">
      <label>优先级</label>
      <select v-model="filters.priority" class="select" @change="changePage(1)">
        <option value="">全部</option>
        <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
      </select>
    </div>
    <div class="field">
      <label>是否需隔离</label>
      <select v-model="filters.isolation_required" class="select" @change="changePage(1)">
        <option value="">全部</option>
        <option value="true">需要隔离</option>
        <option value="false">不需要隔离</option>
      </select>
    </div>
    <div class="field">
      <label>住院证编号 / 患者姓名</label>
      <input
        v-model="filters.keyword"
        class="input"
        placeholder="模糊搜索编号或姓名"
        @keyup.enter="changePage(1)"
      />
    </div>
    <button class="btn" @click="changePage(1)">查询</button>
    <button class="btn" @click="resetFilter">重置</button>
    <span class="toolbar__spacer"></span>
    <button v-if="canIssueCertificate" class="btn btn--primary" @click="openCreate">
      + 开具住院证
    </button>
  </div>

  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>住院证号</th>
          <th>患者</th>
          <th>性别</th>
          <th>科室</th>
          <th>医生</th>
          <th>优先级</th>
          <th>隔离</th>
          <th>状态</th>
          <th>队列号</th>
          <th>预交金</th>
          <th>创建时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td>{{ row.certificate_no }}</td>
          <td>{{ row.patient_name || '—' }}</td>
          <td>{{ row.patient_gender_label || '—' }}</td>
          <td>{{ row.department_name || '—' }}</td>
          <td>{{ row.doctor_name || '—' }}</td>
          <td><StatusBadge kind="priority" :value="row.priority" :label="row.priority_label" /></td>
          <td>
            <span v-if="row.isolation_required" class="badge badge--danger">需隔离</span>
            <span v-else class="badge badge--muted">否</span>
          </td>
          <td><StatusBadge kind="admission" :value="row.status" :label="row.status_label" /></td>
          <td>{{ row.queue_no || '—' }}</td>
          <td>
            <StatusBadge
              v-if="row.deposit_status"
              kind="deposit"
              :value="row.deposit_status"
              :label="row.deposit_status_label"
            />
            <span v-else class="note">—</span>
          </td>
          <td>{{ fmt(row.created_at) }}</td>
          <td>
            <button
              v-if="row.status === 'DRAFT' && canIssueCertificate"
              class="btn btn--sm btn--primary"
              :disabled="actionBusy"
              @click="doIssue(row)"
            >
              开具
            </button>
            <button
              v-if="row.status === 'ISSUED' && canPreadmit"
              class="btn btn--sm btn--primary"
              :disabled="actionBusy"
              @click="openPreadmit(row)"
            >
              预登记
            </button>
            <button
              v-if="row.status === 'PRE_ADMITTED'"
              class="btn btn--sm"
              @click="goRecommend(row)"
            >
              去推荐
            </button>
            <button
              v-if="['DRAFT', 'ISSUED'].includes(row.status) && canIssueCertificate"
              class="btn btn--sm btn--danger"
              :disabled="actionBusy"
              @click="doCancel(row)"
            >
              取消
            </button>
            <span
              v-if="!['DRAFT', 'ISSUED', 'PRE_ADMITTED'].includes(row.status)"
              class="note"
              >—</span
            >
          </td>
        </tr>
        <tr v-if="!rows.length && !loading">
          <td colspan="12" class="empty">暂无住院证数据</td>
        </tr>
      </tbody>
    </table>
  </div>

  <Pager :page="page" :page-size="pageSize" :total="total" @update:page="changePage" />

  <!-- ------------------------- 开具住院证 ------------------------- -->
  <Modal :open="createOpen" title="开具住院证" width="640px" @close="createOpen = false">
    <div v-if="createError" class="alert alert--danger">{{ createError }}</div>
    <div class="form-grid">
      <div class="field">
        <label>患者 *</label>
        <select v-model="createForm.patient_id" class="select">
          <option value="">请选择</option>
          <option v-for="p in patients" :key="p.id" :value="p.id">
            {{ p.name }}（{{ p.gender_label }}，{{ p.medical_record_no }}）
          </option>
        </select>
      </div>
      <div class="field">
        <label>收治科室 *</label>
        <select v-model="createForm.department_id" class="select">
          <option value="">请选择</option>
          <option v-for="d in departments" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>
      <div class="field">
        <label>开具医生</label>
        <select v-model="createForm.doctor_id" class="select">
          <option value="">（当前登录医生，需账号已关联医生档案）</option>
          <option v-for="d in doctors" :key="d.id" :value="d.id">
            {{ d.name }}{{ d.department_name ? `（${d.department_name}）` : '' }}
          </option>
        </select>
        <p class="note">管理员等未关联医生档案的账号，必须在此显式选择开具医生。</p>
      </div>
      <div class="field">
        <label>病情优先级 *</label>
        <select v-model="createForm.priority" class="select">
          <option v-for="p in PRIORITIES" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>
      <div class="field">
        <label>期望病房（可选）</label>
        <select v-model="createForm.preferred_ward_id" class="select">
          <option value="">不指定</option>
          <option v-for="w in filteredWards" :key="w.id" :value="w.id">
            {{ w.name }}（{{ w.department_name }}）
          </option>
        </select>
      </div>
      <div class="field">
        <label>感染类型（需隔离时填写）</label>
        <input v-model="createForm.infection_type" class="input" placeholder="如：空气传播" />
      </div>
      <div class="field field--full">
        <label>诊断</label>
        <input v-model="createForm.diagnosis" class="input" placeholder="简要诊断" />
      </div>
      <div class="field field--full">
        <label>备注</label>
        <input v-model="createForm.notes" class="input" />
      </div>
      <div class="field field--full">
        <label class="checkbox">
          <input v-model="createForm.isolation_required" type="checkbox" />
          需要隔离收治（隔离患者只能使用隔离床）
        </label>
        <label class="checkbox">
          <input v-model="createForm.issue" type="checkbox" />
          立即开具（不勾选则保存为草稿）
        </label>
      </div>
    </div>
    <template #footer>
      <button class="btn" @click="createOpen = false">取消</button>
      <button class="btn btn--primary" :disabled="createBusy" @click="submitCreate">
        {{ createBusy ? '提交中…' : '提交' }}
      </button>
    </template>
  </Modal>

  <!-- ------------------------- 预入院登记 ------------------------- -->
  <Modal
    :open="preOpen"
    :title="`预入院登记 · ${preTarget?.certificate_no || ''}`"
    width="600px"
    @close="preOpen = false"
  >
    <div v-if="preError" class="alert alert--danger">{{ preError }}</div>
    <p class="note" style="margin-top: 0">
      患者：{{ preTarget?.patient_name }} · 科室：{{ preTarget?.department_name }} · 优先级：{{
        preTarget?.priority_label
      }}
      <span v-if="preTarget?.isolation_required" class="badge badge--danger">需隔离</span>
    </p>
    <div class="form-grid">
      <div class="field">
        <label>联系电话</label>
        <input v-model="preForm.contact_phone" class="input" />
      </div>
      <div class="field">
        <label>紧急联系人</label>
        <input v-model="preForm.emergency_contact" class="input" />
      </div>
      <div class="field">
        <label>紧急联系电话</label>
        <input v-model="preForm.emergency_phone" class="input" />
      </div>
      <div class="field">
        <label>预交金金额（元）</label>
        <input v-model="preForm.deposit_amount" class="input" type="number" min="0" step="0.01" />
      </div>
      <div class="field field--full">
        <label>补充说明</label>
        <textarea v-model="preForm.supplement_notes" class="textarea" />
      </div>
      <div class="field field--full">
        <label class="checkbox">
          <input v-model="preForm.pay_deposit" type="checkbox" />
          模拟缴纳预交金（不接入真实支付）
        </label>
      </div>
    </div>
    <template #footer>
      <button class="btn" @click="preOpen = false">取消</button>
      <button class="btn btn--primary" :disabled="preBusy" @click="submitPreadmit">
        {{ preBusy ? '提交中…' : '完成登记' }}
      </button>
    </template>
  </Modal>
</template>
