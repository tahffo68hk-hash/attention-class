import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { title: '项目首页' },
  },
  {
    path: '/system-status',
    name: 'system-status',
    component: () => import('@/views/SystemStatusView.vue'),
    meta: { title: '系统状态' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const title = (to.meta?.title as string) ?? ''
  document.title = title
    ? `${title} · 医院床位智能分配与住院入院预办理系统`
    : '医院床位智能分配与住院入院预办理系统'
})

export default router
