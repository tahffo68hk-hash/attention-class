<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import AdminLayout from '@/layouts/AdminLayout.vue'

const route = useRoute()
const usePlainLayout = computed(() => route.meta.public === true)
</script>

<template>
  <RouterView v-if="usePlainLayout" />
  <AdminLayout v-else />
</template>
