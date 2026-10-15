<script setup lang="ts">
/**
 * 三维模拟空间编辑器（**只读草稿**）。
 *
 * 边界（与交付包声明一致，务必保持）：
 * - 只改**本地草稿状态**：不调用任何创建/归档/恢复接口，不写数据库、不写审计；
 * - 合成床位 id 为负数，**不允许**当作正式床位 id 传给后端；
 * - 槽位是「屏幕网格吸附位置」，不是医疗评分坐标，也不参与推荐评分；
 * - 编辑态下点击床位走 `edit-select`，绝不打开真实床位详情或读取患者状态流水。
 */
import { computed, ref, watch } from 'vue'
import type { WardBed, WardRoom } from '@/modules/ward-map/types'
import {
  initialEditor,
  addDraft,
  moveDraft,
  removeDraft,
  undo,
  redo,
  roomSlots,
  type EditorState,
} from '@/modules/ward-map/editor'

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
}>()

const state = ref<EditorState>(initialEditor(props.rooms, props.beds))
const roomId = ref(props.rooms[0]?.ward_id ?? 0)
const slot = ref(0)
const rotation = ref<0 | 90 | 180 | 270>(0)
const code = ref('SIM-001')
const error = ref('')
const message = ref('')

/** 当前被选中的床位（来自三维拾取或二维列表） */
const chosen = computed(() => state.value.items.find((x) => x.bed.id === props.selectedId) || null)

// 进入编辑态时重置为「真实快照」草稿，并把初始状态交给外层渲染
watch(
  () => props.active,
  (active) => {
    if (active) {
      state.value = initialEditor(props.rooms, props.beds)
      emit('change', state.value)
    }
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

/** 该病房当前占用的槽位数。**只算本病房**，与 `validatePose` 的判据保持一致。 */
const roomBedCount = computed(
  () => state.value.items.filter((i) => i.pose.wardId === roomId.value).length,
)
/** 可选槽位序号（0 基，展示为 1 基），随病房床位数自适应 */
const slotOptions = computed(() => {
  const room = props.rooms.find((r) => r.ward_id === roomId.value)!
  return Array.from({ length: roomSlots(room, roomBedCount.value) }, (_, i) => i)
})

function apply(fn: () => EditorState) {
  error.value = ''
  message.value = ''
  try {
    state.value = fn()
    emit('change', state.value)
    message.value = '仅修改模拟草稿，真实数据库没有变化'
  } catch (e) {
    error.value = (e as Error).message
  }
}

function rotateSelection() {
  rotation.value = ((rotation.value + 90) % 360) as 0 | 90 | 180 | 270
}

function add() {
  apply(() => addDraft(state.value, props.rooms, roomId.value, slot.value, code.value))
  code.value = `SIM-${String(Math.abs(Date.now()) % 100000).padStart(5, '0')}`
}

function move() {
  if (!chosen.value) {
    error.value = '先在三维画面或二维列表中选择床位'
    return
  }
  apply(() =>
    moveDraft(state.value, props.rooms, chosen.value!.key, {
      wardId: roomId.value,
      slot: slot.value,
      rotation: rotation.value,
    }),
  )
}

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

// 选中床位后，把表单同步到该床位当前的病房/槽位/旋转，便于连续调整
watch(chosen, (item) => {
  if (item) {
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
        <strong>模拟空间编辑器</strong>
        <small>本地草稿 · 不会保存到真实床位数据库</small>
      </div>
      <button class="btn btn--sm" type="button" @click="emit('close')">退出</button>
    </div>

    <div class="wm-editor-controls">
      <label>
        病房
        <select v-model.number="roomId">
          <option v-for="room in rooms" :key="room.ward_id" :value="room.ward_id">
            {{ room.code }} · {{ room.name }}
          </option>
        </select>
      </label>
      <label>
        槽位（网格吸附）
        <select v-model.number="slot">
          <option v-for="i in slotOptions" :key="i" :value="i">{{ i + 1 }}</option>
        </select>
      </label>
      <label>
        旋转
        <select v-model.number="rotation">
          <option v-for="degree in [0, 90, 180, 270]" :key="degree" :value="degree">
            {{ degree }}°
          </option>
        </select>
      </label>
      <label>
        新增模拟床号
        <input v-model="code" maxlength="32" placeholder="SIM-001" />
      </label>
    </div>

    <div class="wm-editor-actions">
      <button class="btn btn--primary btn--sm" type="button" @click="add">＋ 添加模拟床位</button>
      <button class="btn btn--sm" type="button" :disabled="!chosen" @click="move">
        移动 / 旋转选中床
      </button>
      <button class="btn btn--sm" type="button" :disabled="!chosen" @click="remove">
        移除模拟床位
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

    <p v-if="error" role="alert" class="wm-editor-error">{{ error }}</p>
    <p v-else-if="message" role="status" class="wm-editor-message">{{ message }}</p>

    <small class="wm-editor-note">
      选中床位后可调整病房、槽位和旋转角度。槽位仅为屏幕网格吸附，不代表业务床位位置；正式管理功能未在此页开放。
    </small>
  </section>
</template>
