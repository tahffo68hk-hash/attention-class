<script setup lang="ts">
/**
 * 正式床位管理面板 —— **唯一会写库**的三维入口（仅 ADMIN）。
 *
 * 与「模拟编辑」完全隔离：模拟编辑只改内存草稿，本面板才会调用
 * `/api/v1/ward-map/managed-beds*`。每次提交都必须人工确认，服务端还会再做一次
 * ADMIN 校验、单事务提交与审计留痕。
 *
 * 边界：
 * - `scene_slot` / `rotation` 是**展示槽位**，不等于五维评分用的 `position_x/position_y`；
 * - 新床的评分坐标复用同病房模板床（由服务端生成），不是真实测绘结果；
 * - 停用是**软停用**（`retired_at`）：历史分配、流水与审计一律保留，不物理删除。
 */
import { computed, ref, watch } from 'vue'

import http from '@/api/http'
import { initialEditor, roomSlots, type Rotation } from '@/modules/ward-map/editor'
import type { WardBed, WardRoom } from '@/modules/ward-map/types'
import { useAuth } from '@/stores/auth'

/** 正式管理接口的返回结构（见 backend/app/schemas/ward_editor.py:ManagedBedOut） */
interface ManagedBed {
  id: number
  code: string
  ward_id: number
  scene_slot: number
  rotation: number
  retired: boolean
  status: string
}

type Operation = 'create' | 'pose' | 'archive' | 'restore'

const props = defineProps<{
  active: boolean
  /** 真实快照床位（草稿床不参与正式管理） */
  beds: WardBed[]
  rooms: WardRoom[]
  selectedId: number | null
}>()

const emit = defineEmits<{
  (e: 'saved'): void
  (e: 'close'): void
}>()

const { isAdmin } = useAuth()

const operation = ref<Operation>('create')
const code = ref('')
const roomId = ref(0)
const slot = ref(0)
const rotation = ref<Rotation>(0)
const bedType = ref<'NORMAL' | 'ISOLATION' | 'MONITOR'>('NORMAL')
const genderLimit = ref<'ANY' | 'MALE' | 'FEMALE'>('ANY')
const dailyRate = ref('0.00')
const reason = ref('床位资源调整')
const templateId = ref(0)
const archived = ref<ManagedBed[]>([])
const chosenArchive = ref(0)
const busy = ref(false)
const message = ref('')
const error = ref('')

const room = computed(() => props.rooms.find((r) => r.ward_id === roomId.value))
/** 同病房真实床位：既是「评分坐标模板」的来源，也是槽位占用的真实基线 */
const templates = computed(() => props.beds.filter((b) => b.ward_id === roomId.value))
const selected = computed(() => props.beds.find((b) => b.id === props.selectedId) || null)
/**
 * 真实床位的槽位占用。直接用编辑器同一套 `initialEditor` 推导 ——
 * 管理端的槽位口径必须和模拟编辑、场景布局完全一致。
 */
const realSlotState = computed(() => initialEditor(props.rooms, props.beds))
const occupied = computed(
  () =>
    new Set(
      realSlotState.value.items
        .filter(
          (i) =>
            i.pose.wardId === roomId.value &&
            // 改自己的位置时要把自己排除，否则「原地保存」会被判冲突
            (operation.value !== 'pose' || i.bed.id !== selected.value?.id),
        )
        .map((i) => i.pose.slot),
    ),
)
const roomSize = computed(() => (room.value ? roomSlots(room.value, templates.value.length) : 0))

watch(
  () => props.active,
  (active) => {
    if (!active) return
    roomId.value = props.rooms[0]?.ward_id ?? 0
    message.value = ''
    error.value = ''
    void refreshArchived()
  },
)

// 换病房：重选模板床，并默认挑一个空闲槽位
watch(roomId, () => {
  templateId.value = templates.value[0]?.id ?? 0
  slot.value = realSlotState.value.items.find((i) => i.pose.wardId === roomId.value)?.pose.slot ?? 0
  while (occupied.value.has(slot.value) && slot.value < roomSize.value - 1) slot.value++
})

// 选中某张正式床后，把表单对齐到它当前的病房 / 槽位 / 朝向
watch(selected, (b) => {
  if (!b) return
  roomId.value = b.ward_id
  slot.value =
    b.scene_slot ?? realSlotState.value.items.find((i) => i.bed.id === b.id)?.pose.slot ?? 0
  rotation.value = (b.scene_rotation ?? 0) as Rotation
})

async function refreshArchived() {
  try {
    const { data } = await http.get<ManagedBed[]>('/api/v1/ward-map/managed-beds/archived')
    archived.value = data
  } catch {
    // 历史列表拿不到不该阻断整个面板：按钮侧会因「未选择」而禁用。
    archived.value = []
  }
}

/** 提交正式操作：先人工确认，再由服务端复核 ADMIN、事务与审计。 */
async function execute() {
  if (!props.active || !isAdmin.value || busy.value) return
  if ((operation.value === 'archive' || operation.value === 'pose') && !selected.value) {
    error.value = '先选中一张正式床位'
    return
  }
  if (operation.value === 'create' && (!templateId.value || !code.value.trim())) {
    error.value = '填写床位号并选择同病房的模板床'
    return
  }
  if (operation.value === 'restore' && !chosenArchive.value) {
    error.value = '请选择要恢复的正式床位'
    return
  }
  const noun = {
    create: '新增正式床位',
    archive: '正式停用床位',
    restore: '恢复停用床位',
    pose: '保存空间位置',
  }[operation.value]
  if (!window.confirm(`确定${noun}吗？这将写入真实数据库并产生审计记录。`)) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    let url = '/api/v1/ward-map/managed-beds'
    let method: 'post' | 'put' = 'post'
    const payload: Record<string, unknown> = { confirm: true }
    if (operation.value === 'create') {
      Object.assign(payload, {
        code: code.value.trim(),
        ward_id: roomId.value,
        scene_slot: slot.value,
        rotation: rotation.value,
        template_bed_id: templateId.value,
        bed_type: bedType.value,
        gender_limit: genderLimit.value,
        daily_rate: dailyRate.value,
      })
    } else if (operation.value === 'archive') {
      url += `/${selected.value!.id}/archive`
      Object.assign(payload, { reason: reason.value })
    } else if (operation.value === 'restore') {
      url += `/${chosenArchive.value}/restore`
      Object.assign(payload, { reason: reason.value })
    } else {
      url += `/${selected.value!.id}/pose`
      method = 'put'
      Object.assign(payload, {
        ward_id: roomId.value,
        scene_slot: slot.value,
        rotation: rotation.value,
      })
    }
    const { data } = await http[method]<ManagedBed>(url, payload)
    message.value = `${noun}成功：${data.code}。正在刷新业务床位快照。`
    await refreshArchived()
    emit('saved')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section v-if="active && isAdmin" class="wm-manager" aria-label="管理员床位管理">
    <div class="wm-manager-head">
      <div>
        <strong>正式床位管理</strong>
        <small>仅管理员 · 与模拟编辑相互隔离 · 操作将持久化并写入审计</small>
      </div>
      <button class="btn btn--sm" type="button" @click="emit('close')">关闭</button>
    </div>

    <div class="wm-manager-controls">
      <label>
        操作
        <select v-model="operation">
          <option value="create">新增床位</option>
          <option value="pose">保存空间位置</option>
          <option value="archive">正式停用</option>
          <option value="restore">恢复床位</option>
        </select>
      </label>

      <template v-if="operation === 'create' || operation === 'pose'">
        <label>
          病房
          <select v-model.number="roomId" :disabled="operation === 'pose'">
            <option v-for="r in rooms" :key="r.ward_id" :value="r.ward_id">
              {{ r.code }} · {{ r.name }}
            </option>
          </select>
        </label>
        <label>
          槽位
          <select v-model.number="slot">
            <option v-for="i in roomSize" :key="i" :value="i - 1" :disabled="occupied.has(i - 1)">
              {{ i }}{{ occupied.has(i - 1) ? ' · 占用' : '' }}
            </option>
          </select>
        </label>
        <label>
          朝向
          <select v-model.number="rotation">
            <option v-for="n in [0, 90, 180, 270]" :key="n" :value="n">{{ n }}°</option>
          </select>
        </label>
      </template>

      <template v-if="operation === 'create'">
        <label>
          床位编号
          <input v-model="code" maxlength="32" placeholder="例：C-101-09" />
        </label>
        <label>
          评分坐标模板
          <select v-model.number="templateId">
            <option v-for="b in templates" :key="b.id" :value="b.id">{{ b.code }}</option>
          </select>
        </label>
        <label>
          床型
          <select v-model="bedType">
            <option value="NORMAL">普通床</option>
            <option value="ISOLATION">隔离床</option>
            <option value="MONITOR">监护床</option>
          </select>
        </label>
        <label>
          性别限制
          <select v-model="genderLimit">
            <option value="ANY">不限</option>
            <option value="MALE">男性</option>
            <option value="FEMALE">女性</option>
          </select>
        </label>
        <label>
          日费用（元）
          <input v-model="dailyRate" type="number" min="0" step="0.01" />
        </label>
      </template>

      <template v-if="operation === 'archive'">
        <label>
          停用原因
          <input v-model="reason" maxlength="255" />
        </label>
        <p class="wm-sandbox-note">
          仅可停用「空闲 / 维护」且无有效分配（预占 / 已入住）的床位，历史记录不会删除。
        </p>
      </template>

      <template v-if="operation === 'restore'">
        <label>
          已停用床
          <select v-model.number="chosenArchive">
            <option :value="0">选择床位</option>
            <option v-for="b in archived" :key="b.id" :value="b.id">{{ b.code }}</option>
          </select>
        </label>
        <label>
          恢复原因
          <input v-model="reason" maxlength="255" />
        </label>
      </template>
    </div>

    <p v-if="operation === 'pose' || operation === 'archive'" class="wm-sandbox-note">
      当前选择：{{ selected?.code ?? '尚未选择正式床位' }}。空间位置不等于五维评分的距离坐标。
    </p>

    <button
      class="btn btn--primary btn--sm"
      type="button"
      :disabled="busy || ((operation === 'create' || operation === 'pose') && occupied.has(slot))"
      @click="execute"
    >
      {{ busy ? '提交中…' : '确认正式操作' }}
    </button>

    <p v-if="error" class="wm-error" role="alert">{{ error }}</p>
    <p v-if="message" class="wm-sandbox-note" role="status">{{ message }}</p>
  </section>
</template>
