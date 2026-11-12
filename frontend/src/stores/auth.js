// 认证状态管理（Pinia + localStorage 持久化）
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { setAuthToken } from '../api/request.js'
import { authApi } from '../api/modules.js'

export const useAuthStore = defineStore(
  'auth',
  () => {
    const user = ref(null)
    const token = ref('')

    const isLoggedIn = computed(() => Boolean(token.value))
    const role = computed(() => user.value?.role || 'guest')

    // 登录：保存 token 和用户信息，同步到 axios 请求头
    async function login(credentials) {
      const data = await authApi.login(credentials)
      token.value = data.access_token
      user.value = data.user
      setAuthToken(data.access_token)
      // 登录成功后清掉上一次 401 留下的提示，避免下次刷新又弹一遍
      sessionStorage.removeItem('authError')
    }

    // 退出登录：清除状态和 axios 请求头
    function logout() {
      user.value = null
      token.value = ''
      setAuthToken('')
    }

    return { user, token, isLoggedIn, role, login, logout }
  },
  {
    persist: {
      key: 'auth',
      pick: ['user', 'token'],
      afterHydrate: ({ store }) => {
        setAuthToken(store.token)
      },
    },
  },
)
