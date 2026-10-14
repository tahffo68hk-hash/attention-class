<script setup lang="ts">
import { computed } from 'vue'

import { LABEL_MAPS, type LabelKind } from '@/lib/labels'

const props = defineProps<{
  kind: LabelKind
  value: string | null | undefined
  label?: string | null
}>()

const resolved = computed(() => {
  const key = props.value ?? ''
  const hit = LABEL_MAPS[props.kind]?.[key]
  return hit ?? [props.label || key || '—', 'muted']
})

const text = computed(() => props.label || resolved.value[0])
const tone = computed(() => resolved.value[1])
</script>

<template>
  <span class="badge" :class="`badge--${tone}`">{{ text }}</span>
</template>
