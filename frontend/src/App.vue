<script setup>
// 根组件：登录页全屏，其他页面展示侧边栏布局
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, Bot, Database, Headphones, LayoutDashboard, LogOut, Settings, Table2 } from 'lucide-vue-next'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 登录页不显示侧边栏外壳
const showShell = computed(() => route.path !== '/login')

// 导航菜单配置（roles 为空表示所有登录角色可见）
const navItems = [
  { path: '/chat', label: '企业用户端', icon: Bot },
  { path: '/support', label: '客服工作台', icon: Headphones, roles: ['customer_service', 'admin'] },
  { path: '/business', label: '商务数据', icon: Table2, roles: ['admin'] },
  { path: '/knowledge', label: '知识库', icon: BookOpen, roles: ['admin', 'customer_service'] },
  { path: '/admin', label: '系统管理', icon: Settings, roles: ['admin'] },
  { path: '/dashboard', label: '决策大屏', icon: LayoutDashboard, roles: ['admin'] },
]

// 只显示当前角色有权访问的菜单项
const visibleNavs = computed(() => navItems.filter((item) => !item.roles || item.roles.includes(auth.role)))

// 退出登录
const logout = () => {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <router-view v-if="!showShell" />
  <div v-else class="app-shell">
    <!-- 侧边栏导航 -->
    <aside class="sidebar">
      <div class="brand">
        <Database :size="24" />
        <div>
          <strong>智企通 AI</strong>
          <span>{{ auth.user?.username }} · {{ auth.role }}</span>
        </div>
      </div>
      <nav>
        <router-link v-for="item in visibleNavs" :key="item.path" :to="item.path">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <button class="logout" type="button" @click="logout">
        <LogOut :size="18" />
        退出登录
      </button>
    </aside>
    <main class="workspace">
      <router-view />
    </main>
  </div>
</template>
