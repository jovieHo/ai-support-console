// 路由配置：懒加载 + JWT 鉴权守卫 + 按角色隔离
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// 懒加载各页面组件
const LoginView = () => import('../views/LoginView.vue')
const EnterpriseChatView = () => import('../views/EnterpriseChatView.vue')
const SupportDeskView = () => import('../views/SupportDeskView.vue')
const BusinessDataView = () => import('../views/BusinessDataView.vue')
const KnowledgeBaseView = () => import('../views/KnowledgeBaseView.vue')
const AdminView = () => import('../views/AdminView.vue')
const DashboardView = () => import('../views/DashboardView.vue')

const routes = [
  { path: '/login', component: LoginView },
  { path: '/', redirect: '/chat' },
  // 对话页面向所有登录角色开放
  { path: '/chat', component: EnterpriseChatView },
  // 以下页面按角色开放，未授权角色会被守卫重定向回对话页
  { path: '/support', component: SupportDeskView, meta: { roles: ['customer_service', 'admin'] } },
  { path: '/business', component: BusinessDataView, meta: { roles: ['admin'] } },
  { path: '/knowledge', component: KnowledgeBaseView, meta: { roles: ['admin', 'customer_service'] } },
  { path: '/admin', component: AdminView, meta: { roles: ['admin'] } },
  { path: '/dashboard', component: DashboardView, meta: { roles: ['admin'] } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 前置守卫：未登录去登录页；已登录但角色无权访问的页面重定向回对话页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.isLoggedIn) {
    return '/login'
  }
  const allowed = to.meta.roles
  if (allowed && !allowed.includes(auth.role)) {
    return '/chat'
  }
  return true
})

export default router
