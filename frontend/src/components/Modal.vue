<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  width?: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

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
    <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
      <div class="modal" :style="{ maxWidth: width || '560px' }">
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
