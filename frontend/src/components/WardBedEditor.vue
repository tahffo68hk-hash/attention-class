<script setup lang="ts">
/**
 * 三维模拟空间编辑器面板（**只读草稿** + 场景拖放落点）。
 *
 * 边界（与交付包声明一致，务必保持）：
 * - 只改**本地草稿状态**：不调用任何创建/归档/恢复接口，不写数据库、不写审计；
 * - 合成床位 id 为负数，**不允许**当作正式床位 id 传给后端；
 * - 槽位是「屏幕网格吸附位置」，不是医疗评分坐标，也不参与推荐评分；
 * - 编辑态下点击床位走 `edit-select`，绝不打开真实床位详情或读取患者状态流水。
 *
 * 与 3D 场景的分工：场景负责「射线求交 → 槽位吸附 → Ghost 预览」，
 * 通过 `edit-place` 把落点交回本面板执行 —— 本面板是唯一修改草稿状态的地方。
 */
import { computed, ref, watch } from 'vue'

import type { WardBed, WardRoom } from '@/modules/ward-map/types'
import {
  addDraft,
  initialEditor,
  moveDraft,
  removeDraft,
  redo,
  roomSlots,
  undo,
  validatePose,
  type EditorState,
  type EditPose,
  type Rotation,
} from '@/modules/ward-map/editor'

/** 三维编辑工具：选择 / 预览添加 / 拖动已选床 */
type EditTool = 'select' | 'add' | 'move'

const props = defineProps<{
  /** 真实快照床位：编辑器**总是**从真实数据起稿，不用上一次的草稿 */
  beds: WardBed[]
  rooms: WardRoom[]
  active: boolean
  selectedId: number | null
}>()

const emit = defineEmits<{
  (e: 'change', state: EditorState | null): void
  (e: 'close'): void
  /** 把当前工具/病房/朝向同步给 3D 场景，供 Ghost 预览使用 */
  (e: 'intent', tool: EditTool, roomId: number, rotation: Rotation): void
}>()

const state = ref<EditorState>(initialEditor(props.rooms, props.beds))
const roomId = ref(props.rooms[0]?.ward_id ?? 0)
const slot = ref(0)
const rotation = ref<Rotation>(0)
const code = ref('SIM-001')
const tool = ref<EditTool>('select')
const error = ref('')
const message = ref('')

/** 当前被选中的床位（来自三维拾取或二维列表） */
const chosen = computed(() => state.value.items.find((x) => x.bed.id === props.selectedId) || null)

const room = computed(() => props.rooms.find((r) => r.ward_id === roomId.value))
/** 本病房可用槽位数：真实床与草稿床**共用同一套槽位** */
const roomSize = computed(() =>
  room.value
    ? roomSlots(room.value, state.value.items.filter((i) => i.pose.wardId === roomId.value).length)
    : 0,
)
/** 本病房已占用槽位（编辑自身时排除自己，否则「原地保存」会被误判冲突） */
const occupied = computed(
  () =>
    new Set(
      state.value.items
        .filter((i) => i.pose.wardId === roomId.value && i.key !== chosen.value?.key)
        .map((i) => i.pose.slot),
    ),
)
/** 当前表单落点的合法性：与场景 Ghost 的绿/红**共用同一个 validatePose 判据** */
const placementReason = computed(() =>
  validatePose(
    state.value,
    props.rooms,
    tool.value === 'add' ? 'preview:new' : (chosen.value?.key ?? 'preview:move'),
    { wardId: roomId.value, slot: slot.value, rotation: rotation.value },
  ),
)

// 进入编辑态时重置为「真实快照」草稿，并把初始状态交给外层渲染
watch(
  () => props.active,
  (active) => {
    if (!active) return
    state.value = initialEditor(props.rooms, props.beds)
    tool.value = 'select'
    roomId.value = props.rooms[0]?.ward_id ?? 0
    slot.value = 0
    while (occupied.value.has(slot.value) && slot.value < roomSize.value - 1) slot.value++
    code.value = nextCode()
    emit('change', state.value)
    emitIntent()
  },
)
// 真实快照刷新（例如切到演示模式）时同步草稿 —— 但用户已有编辑历史时不打扰
watch(
  () => props.beds,
  (beds) => {
    if (props.active && state.value.history.length === 0) {
      state.value = initialEditor(props.rooms, beds)
      emit('change', state.value)
    }
  },
)
// 工具/病房/朝向一变就同步给场景，Ghost 预览立刻跟着换
watch([roomId, rotation, tool], () => emitIntent())

function emitIntent() {
  emit('intent', tool.value, roomId.value, rotation.value)
}

function apply(fn: () => EditorState) {
  error.value = ''
  message.value = ''
  try {
    state.value = fn()
    emit('change', state.value)
    message.value = '模拟草稿已更新，真实床位没有变化'
  } catch (e) {
    error.value = (e as Error).message
  }
}

function rotateSelection() {
  rotation.value = ((rotation.value + 90) % 360) as Rotation
}

/** 取下一个空闲的 SIM-xxx（避开已有草稿床号） */
function nextCode() {
  let n = 1
  while (state.value.items.some((i) => i.bed.code === `SIM-${String(n).padStart(3, '0')}`)) n++
  return `SIM-${String(n).padStart(3, '0')}`
}

function add(at: EditPose = { wardId: roomId.value, slot: slot.value, rotation: rotation.value }) {
  apply(() => addDraft(state.value, props.rooms, at.wardId, at.slot, code.value, at.rotation))
  if (!error.value) code.value = nextCode()
}

function move(
  at: EditPose = { wardId: roomId.value, slot: slot.value, rotation: rotation.value },
  bedId: number | null = props.selectedId,
) {
  const target = state.value.items.find((i) => i.bed.id === bedId)
  if (!target) {
    error.value = '先在三维画面或二维列表中选择床位'
    return
  }
  apply(() => moveDraft(state.value, props.rooms, target.key, at))
}

/** 三维场景落点入口：由 `edit-place` 事件驱动（拖放或点击确认） */
function placeFromScene(at: EditPose, bedId: number | null) {
  roomId.value = at.wardId
  slot.value = at.slot
  rotation.value = at.rotation
  if (tool.value === 'add') add(at)
  else if (tool.value === 'move') move(at, bedId)
}

defineExpose({ placeFromScene })

function remove() {
  if (chosen.value) apply(() => removeDraft(state.value, chosen.value!.key))
}

function reset() {
  state.value = initialEditor(props.rooms, props.beds)
  emit('change', state.value)
  error.value = ''
  message.value = '已恢复模拟快照'
}

function changeHistory(direction: 'undo' | 'redo') {
  state.value = direction === 'undo' ? undo(state.value) : redo(state.value)
  emit('change', state.value)
}

// 选中床位后把表单同步到它的病房/槽位/旋转；「添加」工具下不抢当前落点
watch(chosen, (item) => {
  if (item && tool.value !== 'add') {
    roomId.value = item.pose.wardId
    slot.value = item.pose.slot
    rotation.value = item.pose.rotation
  }
})
</script>

<template>
  <section
    v-if="active"
    class="wm-editor"
    aria-label="三维模拟床位编辑工具"
    @keydown.r.prevent="rotateSelection"
  >
    <div class="wm-editor-head">
      <div>
        <strong>空间模拟编辑</strong>
        <small>仅本次页面草稿 · 不执行真实床位写入</small>
      </div>
      <button class="btn btn--sm" type="button" @click="emit('close')">退出</button>
    </div>

    <div class="wm-editor-tools" role="group" aria-label="三维编辑工具">
      <button
        class="btn btn--sm"
        type="button"
        :class="{ 'is-active': tool === 'select' }"
        :aria-pressed="tool === 'select'"
        @click="tool = 'select'"
      >
        选择
      </button>
      <button
        class="btn btn--sm"
        type="button"
        :class="{ 'is-active': tool === 'add' }"
        :aria-pressed="tool === 'add'"
        @click="tool = 'add'"
      >
        ＋ 添加 / 预览
      </button>
      <button
        class="btn btn--sm"
        type="button"
        :class="{ 'is-active': tool === 'move' }"
        :aria-pressed="tool === 'move'"
        @click="tool = 'move'"
      >
        拖动已选床
      </button>
    </div>

    <p class="wm-editor-hint">
      {{
        tool === 'add'
          ? '把鼠标移入病房：绿色半透明床代表合法槽位，单击确认添加。'
          : tool === 'move'
            ? '按住现有床并拖动到绿色网格槽位，松开确认；也可以直接改下面的病房/槽位/朝向。'
            : '点击床位查看属性；切换到「添加 / 预览」或「拖动已选床」开始编辑。'
      }}
    </p>

    <div class="wm-editor-controls">
      <label>
        病房
        <select v-model.number="roomId">
          <option v-for="r in rooms" :key="r.ward_id" :value="r.ward_id">
            {{ r.code }} · {{ r.name }}
          </option>
        </select>
      </label>
      <label>
        槽位
        <select v-model.number="slot">
          <option v-for="i in roomSize" :key="i" :value="i - 1" :disabled="occupied.has(i - 1)">
            {{ i }}{{ occupied.has(i - 1) ? ' · 已占用' : '' }}
          </option>
        </select>
      </label>
      <label>
        朝向
        <select v-model.number="rotation">
          <option v-for="degree in [0, 90, 180, 270]" :key="degree" :value="degree">
            {{ degree }}°
          </option>
        </select>
      </label>
      <label>
        虚构床号
        <input v-model="code" maxlength="32" placeholder="SIM-001" />
      </label>
      <button class="btn btn--sm" type="button" @click="rotateSelection">R · 旋转 90°</button>
    </div>

    <div class="wm-editor-actions">
      <button class="btn btn--primary btn--sm" type="button" :disabled="!!placementReason" @click="add()">
        按选定槽位添加
      </button>
      <button
        class="btn btn--sm"
        type="button"
        :disabled="!chosen || !!placementReason"
        @click="move()"
      >
        移动 / 旋转选中床
      </button>
      <button class="btn btn--sm" type="button" :disabled="!chosen" @click="remove">
        从模拟场景移除
      </button>
      <button
        class="btn btn--sm"
        type="button"
        :disabled="!state.history.length"
        @click="changeHistory('undo')"
      >
        撤销
      </button>
      <button
        class="btn btn--sm"
        type="button"
        :disabled="!state.future.length"
        @click="changeHistory('redo')"
      >
        重做
      </button>
      <button class="btn btn--sm" type="button" @click="reset">重置草稿</button>
    </div>

    <p v-if="placementReason" class="wm-editor-error">当前槽位不可用：{{ placementReason }}</p>
    <p v-if="error" role="alert" class="wm-editor-error">{{ error }}</p>
    <p v-else-if="message" role="status" class="wm-editor-message">{{ message }}</p>

    <small class="wm-editor-note">
      真实床位与草稿床统一占用槽位。绿色=合法预览，红色=不可放置；均不改变床位五态。虚构负 ID
      不能用于正式分配；正式管理功能未在此页开放。
    </small>
  </section>
</template>
