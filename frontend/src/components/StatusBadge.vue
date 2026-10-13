<script setup lang="ts">
import { computed } from 'vue'

type Kind = 'bed' | 'priority' | 'admission' | 'allocation' | 'deposit' | 'bedType' | 'gender'

const props = defineProps<{
  kind: Kind
  value: string | null | undefined
  label?: string | null
}>()

const MAPS: Record<Kind, Record<string, [string, string]>> = {
  bed: {
    AVAILABLE: ['空闲', 'ok'],
    RESERVED: ['预占用', 'warn'],
    OCCUPIED: ['已入住', 'info'],
    CLEANING: ['清洁中', 'muted'],
    MAINTENANCE: ['维护中', 'danger'],
  },
  priority: {
    CRITICAL: ['危重', 'danger'],
    SEVERE: ['重症', 'warn'],
    URGENT: ['急症', 'info'],
    NORMAL: ['普通', 'muted'],
    MILD: ['轻症', 'muted'],
  },
  admission: {
    DRAFT: ['草稿', 'muted'],
    ISSUED: ['已开具', 'info'],
    PRE_ADMITTED: ['待入院', 'warn'],
    ADMITTED: ['已入住', 'ok'],
    COMPLETED: ['已出院', 'muted'],
    CANCELLED: ['已取消', 'danger'],
  },
  allocation: {
    RESERVED: ['预占用', 'warn'],
    ADMITTED: ['已入住', 'ok'],
    DISCHARGED: ['已出院', 'muted'],
    CANCELLED: ['已取消', 'danger'],
  },
  deposit: {
    PENDING: ['待缴纳（模拟）', 'warn'],
    PAID: ['已缴纳（模拟）', 'ok'],
    REFUNDED: ['已退还（模拟）', 'muted'],
  },
  bedType: {
    NORMAL: ['普通床', 'muted'],
    ISOLATION: ['隔离床', 'danger'],
    MONITOR: ['监护床', 'info'],
  },
  gender: {
    MALE: ['男', 'info'],
    FEMALE: ['女', 'warn'],
    ANY: ['不限', 'muted'],
  },
}

const resolved = computed(() => {
  const key = props.value ?? ''
  const hit = MAPS[props.kind]?.[key]
  return hit ?? [props.label || key || '—', 'muted']
})

const text = computed(() => props.label || resolved.value[0])
const tone = computed(() => resolved.value[1])
</script>

<template>
  <span class="badge" :class="`badge--${tone}`">{{ text }}</span>
</template>
