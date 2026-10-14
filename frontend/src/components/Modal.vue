<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    width?: string
    /** default = 居中模态框；drawer = 右侧抽屉（如床位状态流水） */
    variant?: 'default' | 'drawer'
  }>(),
  { width: undefined, variant: 'default' },
)

const emit = defineEmits<{ (e: 'close'): void }>()

const isDrawer = computed(() => props.variant === 'drawer')

const bodyStyle = computed(() =>
  isDrawer.value ? undefined : { maxWidth: props.width || '560px' },
)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      window.addEventListener('keydown', onKey)
    } else {
      window.removeEventListener('keydown', onKey)
    }
  },
)

onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-backdrop"
      :class="{ 'drawer-backdrop': isDrawer }"
      @click.self="emit('close')"
    >
      <div class="modal" :class="{ drawer: isDrawer }" :style="bodyStyle">
        <div class="modal__head">
          <h3>{{ title }}</h3>
          <button class="modal__close" aria-label="关闭" @click="emit('close')">×</button>
        </div>
        <div class="modal__body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="modal__foot">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
