<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { useAuth } from '@/stores/auth'
import { applyTheme, readStoredTheme, toggleTheme } from '@/lib/theme'

/**
 * AppShell —— Clinical SaaS Visual Redesign V1 外壳。
 * 导航项与本地 router 命名路由一一对应，不新增/删除业务入口；
 * 退出登录沿用 useAuth().signOut()，与 P3/P4 会话清理逻辑保持一致。
 */

interface NavItem {
  name: string
  path: string
  label: string
  symbol: string
  ai?: boolean
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    title: '工作空间',
    items: [{ name: 'dashboard', path: '/dashboard', label: '管理看板', symbol: '▦' }],
  },
  {
    title: '住院业务',
    items: [
      { name: 'admissions', path: '/admissions', label: '住院证与预登记', symbol: '▤' },
      { name: 'recommendations', path: '/recommendations', label: '床位推荐', symbol: '✦' },
      { name: 'beds', path: '/beds', label: '床位管理', symbol: '▥' },
      { name: 'allocations', path: '/allocations', label: '分配与住院办理', symbol: '⇄' },
    ],
  },
  {
    title: '决策分析',
    items: [
      { name: 'optimization', path: '/optimization', label: '多患者联合排床', symbol: '◈' },
      { name: 'assistant', path: '/assistant', label: '辅助决策解释', symbol: '✧', ai: true },
    ],
  },
  {
    title: '系统管理',
    items: [
      { name: 'audit', path: '/audit', label: '操作审计', symbol: '◷' },
      { name: 'system-status', path: '/system-status', label: '系统状态', symbol: '⚙' },
      { name: 'about', path: '/about', label: '项目说明', symbol: '◇' },
    ],
  },
]

const allItems = navGroups.flatMap((g) => g.items)

const route = useRoute()
const router = useRouter()
const { currentUser, signOut } = useAuth()

const collapsed = ref(false)
const mobileOpen = ref(false)
const searchOpen = ref(false)
const search = ref('')
const dark = ref(false)
const signingOut = ref(false)

const activeItem = computed(() => allItems.find((i) => i.path === route.path))
const activeLabel = computed(() => activeItem.value?.label ?? '控制台')

const matches = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return allItems
  return allItems.filter(
    (i) => i.label.toLowerCase().includes(q) || i.path.toLowerCase().includes(q),
  )
})

const userLabel = computed(
  () => currentUser.value?.full_name || currentUser.value?.username || '演示用户',
)
const roleLabel = computed(
  () => currentUser.value?.role_label || currentUser.value?.role || '未登录',
)

function onThemeToggle() {
  dark.value = toggleTheme()
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    searchOpen.value = !searchOpen.value
  }
  if (e.key === 'Escape') {
    searchOpen.value = false
    mobileOpen.value = false
  }
}

function navigate(path: string) {
  searchOpen.value = false
  mobileOpen.value = false
  search.value = ''
  router.push(path)
}

async function onSignOut() {
  signingOut.value = true
  try {
    await signOut()
    await router.replace({ name: 'login' })
  } finally {
    signingOut.value = false
  }
}

watch(
  () => route.fullPath,
  () => {
    mobileOpen.value = false
    searchOpen.value = false
  },
)

onMounted(() => {
  dark.value = applyTheme(readStoredTheme()) === 'dark'
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div
    class="workspace"
    :class="{ 'theme-dark': dark, 'sidebar-collapsed': collapsed, 'nav-open': mobileOpen }"
  >
    <div v-if="mobileOpen" class="mobile-overlay" @click="mobileOpen = false"></div>

    <aside class="sidebar">
      <div class="brand">
        <div class="brand-icon">✚</div>
        <div class="brand-copy">
          <strong>ATTENTION</strong>
          <small>床位智能分配</small>
        </div>
        <button
          class="icon-button collapse"
          type="button"
          aria-label="折叠侧边栏"
          @click="collapsed = !collapsed"
        >
          {{ collapsed ? '›' : '‹' }}
        </button>
      </div>

      <div class="org-switch">
        <span class="org-avatar">H</span>
        <div class="org-text">
          <strong>医院床位智能分配</strong>
          <small>教学演示工作空间</small>
        </div>
        <span class="org-chevron">⌄</span>
      </div>

      <nav class="navigation" aria-label="主导航">
        <section v-for="group in navGroups" :key="group.title">
          <div class="nav-heading">{{ group.title }}</div>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="item.path"
            class="nav-item"
            :class="{ selected: route.path === item.path }"
            :title="item.label"
            @click="mobileOpen = false"
          >
            <span class="nav-icon">{{ item.symbol }}</span>
            <span class="nav-text">{{ item.label }}</span>
            <span v-if="item.ai" class="ai-dot"></span>
          </RouterLink>
        </section>
      </nav>

      <div class="sidebar-bottom">
        <div class="demo-notice">
          <span class="demo-dot"></span>
          <span class="demo-text">
            教学模拟环境
            <br />
            <small>非真实临床决策系统</small>
          </span>
        </div>
        <div class="sidebar-profile">
          <span class="avatar">{{ userLabel.slice(0, 1) }}</span>
          <div class="profile-copy">
            <strong>{{ userLabel }}</strong>
            <small>{{ roleLabel }}</small>
          </div>
        </div>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="top-left">
          <button class="icon-button mobile-toggle" aria-label="打开导航" @click="mobileOpen = true">
            ☰
          </button>
          <div class="breadcrumb">
            <span>工作空间</span>
            <span class="crumb-sep">/</span>
            <strong>{{ activeLabel }}</strong>
          </div>
        </div>
        <div class="top-actions">
          <button class="search-trigger" type="button" @click="searchOpen = true">
            <span>⌕</span>
            <span>搜索功能或页面...</span>
            <kbd>Ctrl K</kbd>
          </button>
          <span class="top-divider"></span>
          <span class="environment-status"><i></i> 演示环境</span>
          <button
            class="icon-button"
            :aria-label="dark ? '切换浅色主题' : '切换深色主题'"
            :title="dark ? '切换浅色主题' : '切换深色主题'"
            @click="onThemeToggle"
          >
            {{ dark ? '☀' : '☾' }}
          </button>
          <button
            class="icon-button logout-button"
            title="退出登录"
            aria-label="退出登录"
            :disabled="signingOut"
            @click="onSignOut"
          >
            ↪
          </button>
        </div>
      </header>

      <main class="content">
        <div class="page-context">
          <span class="context-badge">WORKSPACE</span>
          <span>/</span>
          <span>{{ activeLabel }}</span>
        </div>
        <RouterView />
      </main>

      <footer class="footer">
        <span>© Attention is all you need · Clinical Workspace</span>
        <span>
          课程设计原型 · 仅使用模拟数据 ·
          <a href="/docs" target="_blank" rel="noreferrer">接口文档 /docs</a>
        </span>
      </footer>
    </div>

    <div v-if="searchOpen" class="command-overlay" @click.self="searchOpen = false">
      <div class="command-dialog" role="dialog" aria-modal="true" aria-label="搜索功能">
        <div class="command-input">
          <span>⌕</span>
          <input
            v-model="search"
            autofocus
            placeholder="搜索页面、床位、功能…"
            @keydown.enter="matches.length && navigate(matches[0].path)"
          />
          <kbd>ESC</kbd>
        </div>
        <div class="command-list">
          <p>快速导航</p>
          <button v-for="item in matches" :key="item.name" @click="navigate(item.path)">
            <span>{{ item.symbol }}</span>
            {{ item.label }}
            <small>{{ item.path }}</small>
          </button>
          <p v-if="!matches.length" class="empty">没有匹配的功能</p>
        </div>
      </div>
    </div>
  </div>
</template>
