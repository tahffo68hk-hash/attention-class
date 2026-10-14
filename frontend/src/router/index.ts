import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { TOKEN_STORAGE_KEY } from '@/api/http'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '管理看板', requiresAuth: true },
  },
  {
    path: '/admissions',
    name: 'admissions',
    component: () => import('@/views/AdmissionsView.vue'),
    meta: { title: '住院证与预登记', requiresAuth: true },
  },
  {
    path: '/recommendations',
    name: 'recommendations',
    component: () => import('@/views/RecommendationView.vue'),
    meta: { title: '床位推荐', requiresAuth: true },
  },
  {
    path: '/beds',
    name: 'beds',
    component: () => import('@/views/BedsView.vue'),
    meta: { title: '床位管理', requiresAuth: true },
  },
  {
    path: '/ward-map',
    name: 'ward-map',
    component: () => import('@/views/WardMapView.vue'),
    meta: { title: '病区床位态势图', requiresAuth: true },
  },
  {
    path: '/allocations',
    name: 'allocations',
    component: () => import('@/views/AllocationsView.vue'),
    meta: { title: '分配与住院办理', requiresAuth: true },
  },
  {
    path: '/optimization',
    name: 'optimization',
    component: () => import('@/views/OptimizationView.vue'),
    meta: { title: '多患者联合排床', requiresAuth: true },
  },
  {
    path: '/assistant',
    name: 'assistant',
    component: () => import('@/views/AssistantView.vue'),
    meta: { title: '辅助决策解释', requiresAuth: true },
  },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('@/views/AuditView.vue'),
    meta: { title: '操作审计', requiresAuth: true },
  },
  {
    path: '/system-status',
    name: 'system-status',
    component: () => import('@/views/SystemStatusView.vue'),
    meta: { title: '系统状态', requiresAuth: true },
  },
  {
    path: '/about',
    name: 'about',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '项目说明', requiresAuth: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const hasToken = Boolean(localStorage.getItem(TOKEN_STORAGE_KEY))

  if (to.meta.requiresAuth && !hasToken) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && hasToken) {
    return { name: 'dashboard' }
  }
  return true
})

router.afterEach((to) => {
  const title = (to.meta?.title as string) ?? ''
  document.title = title
    ? `${title} · 医院床位智能分配与住院入院预办理系统`
    : '医院床位智能分配与住院入院预办理系统'
})

export default router
