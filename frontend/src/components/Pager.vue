<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pageSize: number
  total: number
}>()

const emit = defineEmits<{ (e: 'update:page', page: number): void }>()

const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const canPrev = computed(() => props.page > 1)
const canNext = computed(() => props.page < pageCount.value)

function go(target: number) {
  emit('update:page', Math.min(Math.max(1, target), pageCount.value))
}
</script>

<template>
  <div class="pager">
    <span class="note">共 {{ total }} 条 · 第 {{ page }} / {{ pageCount }} 页</span>
    <span>
      <button class="btn btn--sm" :disabled="!canPrev" @click="go(page - 1)">上一页</button>
      <button class="btn btn--sm" :disabled="!canNext" @click="go(page + 1)">下一页</button>
    </span>
  </div>
</template>
