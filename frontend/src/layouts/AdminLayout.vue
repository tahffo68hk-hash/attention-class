<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useAuth } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const { currentUser, signOut } = useAuth()

const navItems = [
  { name: 'dashboard', path: '/dashboard', label: '管理看板' },
  { name: 'admissions', path: '/admissions', label: '住院证与预登记' },
  { name: 'recommendations', path: '/recommendations', label: '床位推荐' },
  { name: 'beds', path: '/beds', label: '床位管理' },
  { name: 'allocations', path: '/allocations', label: '分配与住院办理' },
  { name: 'optimization', path: '/optimization', label: '多患者联合排床' },
  { name: 'assistant', path: '/assistant', label: '辅助决策解释' },
  { name: 'audit', path: '/audit', label: '操作审计' },
  { name: 'system-status', path: '/system-status', label: '系统状态' },
]

const activePath = computed(() => route.path)
const envLabel = computed(() => (import.meta.env.DEV ? '开发环境' : '构建产物'))
const apiBase = computed(() => import.meta.env.VITE_API_BASE_URL || '（经 Vite 代理转发到后端）')

const signingOut = ref(false)

async function onSignOut() {
  signingOut.value = true
  try {
    await signOut()
    await router.replace({ name: 'login' })
  } finally {
    signingOut.value = false
  }
}
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
      <div class="topbar">
        <span class="topbar__user">
          <template v-if="currentUser">
            {{ currentUser.full_name }}
            <span class="badge badge--info">{{ currentUser.role_label || currentUser.role }}</span>
          </template>
          <template v-else>未登录</template>
        </span>
        <button class="btn btn--sm" :disabled="signingOut" @click="onSignOut">
          退出登录
        </button>
      </div>

      <RouterView />
      <p class="note" style="margin-top: 24px">
        接口基地址：{{ apiBase }} · 后端 API 文档：<a href="/docs" target="_blank" rel="noreferrer"
          >/docs</a
        >
      </p>
    </main>
  </div>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 14px;
}

.topbar__user {
  font-size: 13px;
  color: var(--color-text-dim);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
