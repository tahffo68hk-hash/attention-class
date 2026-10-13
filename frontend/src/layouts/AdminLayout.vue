<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { name: 'home', path: '/', label: '项目首页' },
  { name: 'system-status', path: '/system-status', label: '系统状态' },
]

const activePath = computed(() => route.path)

const envLabel = computed(() => (import.meta.env.DEV ? '开发环境' : '构建产物'))
const apiBase = computed(() => import.meta.env.VITE_API_BASE_URL || '（经 Vite 代理转发到后端）')
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar__brand">
        医院床位智能分配
        <small>与住院入院预办理系统</small>
      </div>

      <nav class="sidebar__nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.path"
          class="sidebar__link"
          :class="{ 'sidebar__link--active': activePath === item.path }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="sidebar__footer">
        <div>版本 v0.1.0 · M0</div>
        <div>{{ envLabel }}</div>
      </div>
    </aside>

    <main class="content">
      <RouterView />
      <p class="note" style="margin-top: 24px">
        接口基地址：{{ apiBase }} · 后端 API 文档：<a href="/docs" target="_blank" rel="noreferrer"
          >/docs</a
        >
      </p>
    </main>
  </div>
</template>
