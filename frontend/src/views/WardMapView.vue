<script setup lang="ts">
/**
 * 病区床位态势图 —— Ward Map V1 数据契约 + Hospital Vision V2 场景
 *
 * 状态与空间：
 * - 床位状态来自后端只读快照 GET /api/v1/ward-map，**不写入**任何业务数据；
 * - 房间/床位的空间坐标是 SIMULATED_GRID_V1 的模拟排布，不是真实医院平面图；
 *   V2 换的是场景渲染器（医院剖面 / 楼层实体 / 高精度病床），不改变这个数据边界；
 * - 只有「已入住 + ADMITTED 分配 + 无状态矛盾」才渲染人物几何体，预占只画标志；
 *   状态矛盾会显式告警，而不是伪造一个患者。
 *
 * 数据来源边界：演示数据必须手动点击启用；接口报错**不会**自动回退到演示数据，
 * 演示模式也不会用合成床位 ID 去读取真实床位流水。
 *
 * 与交付包的差异（本地适配）：
 * - 数据访问走 `@/modules/ward-map/api`（复用既有 HTTP 分层与鉴权/错误处理）；
 * - 中文标签走 `@/lib/labels`，与床位管理页共用同一套词汇；
 * - 详情仍用共享 `Modal`（drawer 变体），保持全站一致的抽屉与焦点行为；
 * - 按钮复用本地 `.btn` 语义，跟随 Clinical SaaS 明暗主题。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import Modal from '@/components/Modal.vue'
import WardScene3D from '@/components/WardScene3D.vue'
import type { BedStatusLogRead } from '@/api/types'
import { labelOf } from '@/lib/labels'
import { fetchBedLogs, fetchWardMap } from '@/modules/ward-map/api'
import { demoSnapshot } from '@/modules/ward-map/demo'
import { floorKey } from '@/modules/ward-map/scene-layout'
import { filterMap, stateOrder, statusMeta } from '@/modules/ward-map/types'
import type { SceneMode, WardBed, WardMapSnapshot } from '@/modules/ward-map/types'
import '@/modules/ward-map/ward-map.css'

const snapshot = ref<WardMapSnapshot | null>(null)
const mode = ref<'live' | 'demo'>('live')
const loading = ref(true)
const error = ref('')
const webglFailed = ref(false)
const listMode = ref(false)
const department = ref(0)
const ward = ref(0)
const floor = ref('')
const state = ref('')
const keyword = ref('')
const selected = ref<WardBed | null>(null)
const hovered = ref<WardBed | null>(null)
const hoverPos = ref({ x: 0, y: 0 })
const logs = ref<BedStatusLogRead[] | null>(null)
const logsLoading = ref(false)
const logsError = ref('')
const sceneRef = ref<InstanceType<typeof WardScene3D> | null>(null)
const dark = ref(false)
const viewMode = ref<SceneMode>('building')
const activeFloor = ref('')
let requestId = 0

const stats = computed(() => {
  const c = snapshot.value?.counts
  return stateOrder.map((s) => ({
    key: s,
    label: statusMeta[s].label,
    color: statusMeta[s].hex,
    count: c?.[s] ?? 0,
  }))
})

const allBeds = computed(() => snapshot.value?.beds ?? [])

const departments = computed(() => {
  const distinct = new Map<number, string>()
  allBeds.value.forEach((b) => distinct.set(b.department_id, b.department_name))
  return [...distinct].sort((a, b) => a[0] - b[0])
})

const wards = computed(() => {
  const distinct = new Map<number, string>()
  allBeds.value
    .filter((b) => !department.value || b.department_id === department.value)
    .forEach((b) => distinct.set(b.ward_id, `${b.ward_code} · ${b.ward_name}`))
  return [...distinct].sort((a, b) => a[0] - b[0])
})

const floors = computed(() =>
  [
    ...new Set(
      allBeds.value
        .filter((b) => !department.value || b.department_id === department.value)
        .map((b) => `${b.building}·${b.floor}`),
    ),
  ].sort(),
)

const visibleBeds = computed(() =>
  filterMap(
    allBeds.value,
    department.value,
    ward.value,
    floor.value,
    state.value,
    keyword.value,
  ),
)

const visibleIds = computed(() => visibleBeds.value.map((b) => b.id))

/** 楼层 chips 直接从完整快照的 building/floor 去重得到，不受筛选影响。 */
const floorOptions = computed(() =>
  [...new Set(allBeds.value.map((b) => floorKey(b.building, b.floor)))]
    .sort((a, b) => {
      const [ba, fa] = a.split('·')
      const [bb, fb] = b.split('·')
      return ba === bb ? Number(fa) - Number(fb) : ba!.localeCompare(bb!, 'zh-CN')
    })
    .map((key) => ({
      key,
      label: key.replace('·', ' · ').replace(/(\d+)/, '$1F'),
      beds: allBeds.value.filter((b) => floorKey(b.building, b.floor) === key).length,
    })),
)

const activeFloorLabel = computed(
  () => floorOptions.value.find((f) => f.key === activeFloor.value)?.label ?? '全部楼层',
)

const selectedExists = computed(() =>
  selected.value ? (allBeds.value.find((b) => b.id === selected.value!.id) ?? null) : null,
)

const lastUpdated = computed(() =>
  snapshot.value
    ? new Date(snapshot.value.generated_at).toLocaleString('zh-CN', { hour12: false })
    : '—',
)

const detailStatus = computed(() =>
  selectedExists.value ? statusMeta[selectedExists.value.status] : null,
)

const warningCount = computed(() => visibleBeds.value.filter((b) => b.state_warning).length)

const isDemo = computed(() => mode.value === 'demo')

function fmtTime(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}

async function load() {
  if (mode.value === 'demo') snapshot.value = null
  mode.value = 'live'
  loading.value = true
  error.value = ''
  const thisRequest = ++requestId
  try {
    const result = await fetchWardMap()
    if (thisRequest !== requestId) return
    if (result.layout_kind !== 'SIMULATED_GRID_V1' || result.data_source !== 'BUSINESS_API') {
      throw new Error('态势图数据契约不匹配')
    }
    snapshot.value = result
    updateSelected()
    ensureActiveFloor()
  } catch (e) {
    if (thisRequest !== requestId) return
    // 真实数据不可用时不静默回退到演示数据
    error.value = (e as Error).message
  } finally {
    if (thisRequest === requestId) loading.value = false
  }
}

function setDemo() {
  ++requestId
  loading.value = false
  error.value = ''
  mode.value = 'demo'
  snapshot.value = demoSnapshot()
  resetFilters()
  closeDrawer()
  ensureActiveFloor()
}

function ensureActiveFloor() {
  if (!floorOptions.value.some((f) => f.key === activeFloor.value)) {
    activeFloor.value = floorOptions.value[0]?.key ?? ''
  }
}

function resetFilters() {
  department.value = 0
  ward.value = 0
  floor.value = ''
  state.value = ''
  keyword.value = ''
}

watch(department, () => {
  ward.value = 0
  floor.value = ''
})

watch(visibleBeds, (items) => {
  if (hovered.value && !items.some((b) => b.id === hovered.value?.id)) hovered.value = null
})

function updateSelected() {
  if (!selected.value) return
  selected.value = allBeds.value.find((b) => b.id === selected.value?.id) ?? null
}

function onHover(b: WardBed | null, p: { x: number; y: number }) {
  hovered.value = b
  hoverPos.value = p
}

async function selectBed(b: WardBed) {
  selected.value = b
  hovered.value = null
  logs.value = null
  logsError.value = ''
  logsLoading.value = true
  // 选中即切到该床所在楼层，避免抽屉内容与镜头焦点错层
  activeFloor.value = floorKey(b.building, b.floor)
  if (mode.value === 'demo') {
    logs.value = []
    logsLoading.value = false
    logsError.value = '合成演示模式不读取业务流水'
    return
  }
  const id = b.id
  try {
    const result = await fetchBedLogs(id, 30)
    if (selected.value?.id === id) logs.value = result
  } catch (e) {
    if (selected.value?.id === id) logsError.value = (e as Error).message
  } finally {
    if (selected.value?.id === id) logsLoading.value = false
  }
}

function closeDrawer() {
  selected.value = null
  logs.value = null
  logsLoading.value = false
  logsError.value = ''
}

function resetView() {
  sceneRef.value?.resetCamera()
}

function changeViewMode(m: SceneMode) {
  viewMode.value = m
  if (m === 'focus' && !activeFloor.value) activeFloor.value = floorOptions.value[0]?.key ?? ''
}

function chooseFloor(k: string) {
  activeFloor.value = k
  viewMode.value = 'focus'
}

async function locateFirstBed() {
  const bed = visibleBeds.value[0]
  if (!bed) return
  activeFloor.value = floorKey(bed.building, bed.floor)
  viewMode.value = 'focus'
  await nextTick()
  sceneRef.value?.focusBed(bed.id)
}

function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') closeDrawer()
}

/* 主题跟随：<html> 上的 theme-dark 由 AppShell 切换，这里只读不写 */
let themeObserver: MutationObserver | null = null
function syncTheme() {
  dark.value = document.documentElement.classList.contains('theme-dark')
}

onMounted(() => {
  syncTheme()
  themeObserver = new MutationObserver(syncTheme)
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-theme'],
  })
  window.addEventListener('keydown', onEscape)
  void load()
})

onBeforeUnmount(() => {
  ++requestId
  themeObserver?.disconnect()
  themeObserver = null
  window.removeEventListener('keydown', onEscape)
})
</script>

<template>
  <div class="ward-map-page">
    <div class="wm-heading">
      <div>
        <div class="wm-eyebrow">HOSPITAL VISION 3D</div>
        <h1>病区床位态势图 <span class="wm-v2-tag">透明医院剖面</span></h1>
        <p>整栋医院多楼层剖面 · 可交互病床与患者入住状态 · 只读决策工作台</p>
      </div>
      <div class="wm-heading-actions">
        <span class="wm-source">
          <span class="wm-source-dot"></span>
          {{ isDemo ? '合成演示数据' : '业务系统数据' }} · 模拟空间布局
        </span>
        <button class="btn" type="button" @click="setDemo">演示数据</button>
        <button class="btn btn--primary" type="button" :disabled="loading" @click="load">
          ↻ 刷新业务数据
        </button>
      </div>
    </div>

    <div class="wm-note" role="note">
      <strong>空间位置为模拟：</strong>床位状态来自业务记录；房间与床位的 3D
      坐标仅为可视化排布，并非医院真实建筑平面图。此页面不执行临床诊断或床位写入。
    </div>

    <div v-if="loading" class="wm-loading" role="status">正在载入床位态势数据…</div>
    <div v-if="error" class="wm-error" role="alert">
      {{ error }}。真实数据不可用，未自动切换演示数据。
      <button type="button" @click="load">重试</button>
    </div>

    <template v-if="snapshot">
      <section class="wm-stats" aria-label="床位状态统计">
        <div class="wm-total">
          <div class="wm-stat-label">全部床位</div>
          <strong>{{ allBeds.length }}</strong>
          <small>实时读取的业务快照</small>
        </div>
        <button
          v-for="s in stats"
          :key="s.key"
          class="wm-stat"
          type="button"
          :class="{ active: state === s.key }"
          @click="state = state === s.key ? '' : s.key"
        >
          <span class="wm-stat-signal" :style="{ '--signal': s.color }"></span>
          <span class="wm-stat-label">{{ s.label }}</span>
          <strong>{{ s.count }}</strong>
          <small>{{ allBeds.length ? Math.round((s.count / allBeds.length) * 100) : 0 }}% / 全部床位</small>
        </button>
      </section>

      <section class="wm-workspace">
        <div class="wm-toolbar">
          <div class="wm-toolbar-left">
            <span class="wm-toolbar-title">医院建筑剖面</span>
            <span class="wm-count">{{ visibleBeds.length }} / {{ allBeds.length }} 张床位</span>
            <span v-if="warningCount" class="wm-warning">{{ warningCount }} 条状态待核对</span>
          </div>
          <div class="wm-actions">
            <button
              class="btn btn--sm"
              type="button"
              :disabled="webglFailed"
              @click="listMode = !listMode"
            >
              {{ webglFailed ? 'WebGL 不可用 · 二维列表' : listMode ? '⬡ 查看三维' : '☷ 二维列表' }}
            </button>
            <button
              class="btn btn--sm"
              type="button"
              :disabled="listMode || webglFailed"
              @click="resetView"
            >
              ⌖ 重置视角
            </button>
          </div>
        </div>

        <div class="wm-filters">
          <label>
            科室
            <select v-model.number="department">
              <option :value="0">全部科室</option>
              <option v-for="[id, label] in departments" :key="id" :value="id">{{ label }}</option>
            </select>
          </label>
          <label>
            病房
            <select v-model.number="ward">
              <option :value="0">全部病房</option>
              <option v-for="[id, label] in wards" :key="id" :value="id">{{ label }}</option>
            </select>
          </label>
          <label>
            建筑 / 楼层
            <select v-model="floor">
              <option value="">全部楼层</option>
              <option v-for="f in floors" :key="f" :value="f">{{ f }}</option>
            </select>
          </label>
          <label>
            床位状态
            <select v-model="state">
              <option value="">全部状态</option>
              <option v-for="s in stateOrder" :key="s" :value="s">{{ statusMeta[s].label }}</option>
            </select>
          </label>
          <label class="wm-search">
            检索床位
            <input v-model="keyword" placeholder="床号 / 病房号" type="search" />
          </label>
          <button
            class="btn btn--sm"
            type="button"
            :disabled="!visibleBeds.length || listMode || webglFailed"
            @click="locateFirstBed"
          >
            ⌖ 定位首个匹配床位
          </button>
          <button class="btn btn--sm ghost" type="button" @click="resetFilters">清除筛选</button>
        </div>

        <div class="wm-view-controls" aria-label="三维观察模式">
          <div class="wm-view-switch" role="group" aria-label="观察模式">
            <button
              type="button"
              :class="{ 'is-active': viewMode === 'building' }"
              :aria-pressed="viewMode === 'building'"
              @click="changeViewMode('building')"
            >
              ▧ 整栋剖面
            </button>
            <button
              type="button"
              :class="{ 'is-active': viewMode === 'focus' }"
              :aria-pressed="viewMode === 'focus'"
              @click="changeViewMode('focus')"
            >
              ▤ 单层聚焦
            </button>
            <button
              type="button"
              :class="{ 'is-active': viewMode === 'exploded' }"
              :aria-pressed="viewMode === 'exploded'"
              @click="changeViewMode('exploded')"
            >
              ☰ 分层展开
            </button>
          </div>
          <div class="wm-floor-chips" role="group" aria-label="选择模拟楼层">
            <button
              v-for="f in floorOptions"
              :key="f.key"
              type="button"
              :class="{ 'is-active': viewMode === 'focus' && activeFloor === f.key }"
              @click="chooseFloor(f.key)"
            >
              {{ f.label }} <small>{{ f.beds }}床</small>
            </button>
          </div>
        </div>

        <div class="wm-stage">
          <div v-if="visibleBeds.length === 0" class="wm-empty">没有匹配的床位，请调整筛选条件。</div>
          <WardScene3D
            v-else-if="!listMode && !webglFailed"
            ref="sceneRef"
            :beds="allBeds"
            :rooms="snapshot.rooms"
            :visible-ids="visibleIds"
            :view-mode="viewMode"
            :focus-floor="activeFloor"
            :selected-id="selected?.id ?? null"
            :dark="dark"
            @hover="onHover"
            @select="selectBed"
            @unavailable="webglFailed = true"
          />
          <div
            v-if="(listMode || webglFailed) && visibleBeds.length"
            class="wm-list"
            role="list"
            aria-label="可用键盘操作的床位列表"
          >
            <button
              v-for="b in visibleBeds"
              :key="b.id"
              class="wm-list-bed"
              type="button"
              :class="{ 'wm-list-selected': selected?.id === b.id }"
              @click="selectBed(b)"
            >
              <span class="wm-bed-dot" :style="{ background: statusMeta[b.status].hex }"></span>
              <strong>{{ b.code }}</strong>
              <small>{{ b.ward_name }}</small>
              <span>{{ statusMeta[b.status].label }}</span>
              <small v-if="b.status === 'OCCUPIED' && b.patient?.allocation_status === 'ADMITTED'">
                ◉ 已有入住记录
              </small>
            </button>
          </div>
          <div
            v-if="hovered && !listMode && !webglFailed && !selected"
            class="wm-tooltip"
            role="status"
            :style="{
              left: `min(calc(100% - 248px), max(8px, ${hoverPos.x + 16}px))`,
              top: `min(calc(100% - 178px), max(8px, ${hoverPos.y + 12}px))`,
            }"
          >
            <div class="wm-tooltip-head">
              <strong>{{ hovered.code }}</strong>
              <span :style="{ color: statusMeta[hovered.status].hex }">
                ● {{ statusMeta[hovered.status].label }}
              </span>
            </div>
            <p>{{ hovered.department_name }} · {{ hovered.ward_name }}</p>
            <p v-if="hovered.patient">
              关联患者：{{ hovered.patient.masked_name }} · {{ labelOf('priority', hovered.patient.priority) }}
            </p>
            <p v-else>暂无活动分配记录</p>
            <p v-if="hovered.state_warning" class="wm-danger">{{ hovered.state_warning }}</p>
            <small>点击床位查看详情与状态流水</small>
          </div>
          <div class="wm-stage-tip">
            <span class="wm-layer-chip">HOSPITAL VISION 3D</span>
            <span>
              {{
                viewMode === 'building'
                  ? '整栋透明剖面'
                  : viewMode === 'focus'
                    ? '单层聚焦：' + activeFloorLabel
                    : '分层展开'
              }}
              · 模拟建筑坐标 · 拖拽平移 / 滚轮缩放
            </span>
          </div>
        </div>

        <div class="wm-stage-footer">
          <div class="wm-legend">
            <span v-for="s in stateOrder" :key="s">
              <i :style="{ background: statusMeta[s].hex }"></i>{{ statusMeta[s].label }}
            </span>
          </div>
          <span class="wm-update">更新于 {{ lastUpdated }}</span>
        </div>

        <details class="wm-keyboard">
          <summary>键盘访问床位列表（无障碍）</summary>
          <div class="wm-keyboard-grid">
            <button
              v-for="b in visibleBeds"
              :key="b.id"
              type="button"
              @click="selectBed(b)"
            >
              {{ b.code }} · {{ statusMeta[b.status].label }}
            </button>
          </div>
        </details>
      </section>
    </template>

    <Modal
      variant="drawer"
      :open="Boolean(selectedExists)"
      title="床位详情"
      @close="closeDrawer"
    >
      <div v-if="selectedExists" class="wm-drawer-body">
        <div class="wm-drawer-header">
          <span class="wm-eyebrow">BED DETAILS</span>
          <h2>{{ selectedExists.code }}</h2>
          <p>{{ selectedExists.department_name }} · {{ selectedExists.ward_name }}</p>
        </div>

        <div class="wm-detail-state">
          <span class="wm-bed-dot" :style="{ background: detailStatus?.hex }"></span>
          <strong>{{ detailStatus?.label }}</strong>
          <span>当前业务状态</span>
        </div>

        <div v-if="selectedExists.state_warning" class="wm-error" role="alert">
          {{ selectedExists.state_warning }}
        </div>

        <h3>床位信息</h3>
        <dl class="wm-fields">
          <div><dt>床位编号</dt><dd>{{ selectedExists.code }}</dd></div>
          <div><dt>床位类型</dt><dd>{{ labelOf('bedType', selectedExists.bed_type) }}</dd></div>
          <div><dt>所在病房</dt><dd>{{ selectedExists.ward_name }}</dd></div>
          <div>
            <dt>所在楼层</dt>
            <dd>{{ selectedExists.building }} · {{ selectedExists.floor }} 层</dd>
          </div>
          <div><dt>隔离标记</dt><dd>{{ selectedExists.is_isolation ? '是' : '否' }}</dd></div>
          <div><dt>空间坐标</dt><dd>模拟坐标（不代表真实位置）</dd></div>
        </dl>

        <h3>关联患者概况 <span>后端脱敏摘要</span></h3>
        <div v-if="selectedExists.patient" class="wm-patient">
          <div class="wm-avatar">人</div>
          <div>
            <strong>{{ selectedExists.patient.masked_name }}</strong>
            <p>优先级：{{ labelOf('priority', selectedExists.patient.priority) }}</p>
            <p>
              分配阶段：{{ selectedExists.patient.allocation_status === 'ADMITTED' ? '已入住' : '预占待入住' }}
            </p>
          </div>
        </div>
        <p v-else class="wm-none">
          当前没有有效活动分配。未读取诊断、体征或其他敏感医疗数据。
        </p>

        <h3>床位状态流水</h3>
        <p v-if="logsLoading" class="wm-none">读取流水中…</p>
        <p v-if="logsError" class="wm-error">{{ logsError }}</p>
        <div v-if="logs && !logs.length" class="wm-none">暂无状态流水</div>
        <ol v-if="logs?.length" class="wm-timeline">
          <li v-for="l in logs" :key="l.id">
            <span class="wm-time">{{ fmtTime(l.created_at) }}</span>
            <strong>
              {{ labelOf('bed', l.from_status) }} → {{ labelOf('bed', l.to_status) }}
            </strong>
            <small>操作人：{{ l.operator_name || '未记录（历史）' }}</small>
            <small v-if="l.reason">{{ l.reason }}</small>
          </li>
        </ol>
      </div>

      <template #footer>
        <RouterLink class="btn btn--primary" to="/beds">打开正式床位管理 ↗</RouterLink>
        <RouterLink v-if="selectedExists?.patient" class="btn" to="/allocations">
          查看分配记录
        </RouterLink>
      </template>
    </Modal>
  </div>
</template>