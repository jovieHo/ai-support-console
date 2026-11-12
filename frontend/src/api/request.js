// Axios 封装：统一 baseURL、token 注入、错误处理
import axios from 'axios'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 手动设置/清除 token（登录后调用，退出时清空）
export function setAuthToken(token) {
  if (token) {
    localStorage.setItem('token', token)
    request.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    localStorage.removeItem('token')
    delete request.defaults.headers.common.Authorization
  }
}

// 请求拦截器：自动附加 token
request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：自动提取 response.data，统一错误格式化
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 401 未认证：清除所有 token 并强制跳转到登录页
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('auth') // 清除 Pinia persist 持久化数据
      delete request.defaults.headers.common.Authorization
      // 下面是整页跳转，会丢掉当前页面的提示；原因先存起来，登录页读取后展示
      const detail = error.response?.data?.detail
      sessionStorage.setItem('authError', typeof detail === 'string' ? detail : '登录状态已失效，请重新登录')
      // 避免死循环：仅当不在登录页时才跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }
    const detail = error.response?.data?.detail
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join('; ')
      : detail || error.message || 'Request failed'
    console.error('API error:', message)
    error.message = message
    return Promise.reject(error)
  },
)

// 页面刷新时恢复 token
const savedToken = localStorage.getItem('token')
if (savedToken) {
  request.defaults.headers.common.Authorization = `Bearer ${savedToken}`
}

export default request
