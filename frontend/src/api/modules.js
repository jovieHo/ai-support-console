// API 模块：按业务域组织所有后端接口
import request from './request'

// 认证
export const authApi = {
  login: (data) => request.post('/auth/login', data),
  register: (data) => request.post('/auth/register', data),
}

// 用户管理
export const userApi = {
  list: (params) => request.get('/users', { params }),
  roles: () => request.get('/users/roles'),
  create: (data) => request.post('/users', data),
  update: (id, data) => request.put(`/users/${id}`, data),
  remove: (id) => request.delete(`/users/${id}`),
}

// 商务数据
export const businessApi = {
  list: (params) => request.get('/business', { params }),
  create: (data) => request.post('/business', data),
  update: (id, data) => request.put(`/business/${id}`, data),
  remove: (id) => request.delete(`/business/${id}`),
}

// AI 聊天 + 会话管理
export const chatApi = {
  stream: async (data, { onDelta, onDone, signal } = {}) => {
    const baseURL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
    const token = localStorage.getItem('token')
    const response = await fetch(`${baseURL}/chat/stream`, {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    })
    if (response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('auth')
      if (window.location.pathname !== '/login') window.location.href = '/login'
      throw new Error('登录状态无效')
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || `请求失败 (${response.status})`)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const consume = () => {
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() || ''
      for (const event of events) {
        const raw = event.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
        if (!raw) continue
        const payload = JSON.parse(raw)
        if (payload.type === 'delta') onDelta?.(payload.content)
        if (payload.type === 'done') onDone?.(payload)
      }
    }
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      consume()
      if (done) break
    }
  },
  conversations: (params) => request.get('/chat/conversations', { params }),
  conversation: (id) => request.get(`/chat/conversations/${id}`),
  updateConversation: (id, data) => request.patch(`/chat/conversations/${id}`, data),
  removeConversation: (id) => request.delete(`/chat/conversations/${id}`),
}

// 知识库：RAG 检索、文档管理、FAQ
export const knowledgeApi = {
  query: (data) => request.post('/knowledge/query', data),
  upload: (formData) =>
    request.post('/knowledge/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  overview: () => request.get('/knowledge/overview'),
  documents: () => request.get('/knowledge/documents'),
  removeDocument: (id) => request.delete(`/knowledge/documents/${id}`),
  faqs: (params) => request.get('/knowledge/faqs', { params }),
  createFaq: (data) => request.post('/knowledge/faqs', data),
  updateFaq: (id, data) => request.put(`/knowledge/faqs/${id}`, data),
  removeFaq: (id) => request.delete(`/knowledge/faqs/${id}`),
}

// 客服支持
export const supportApi = {
  assist: (data) => request.post('/support/assist', data),
  consultations: (params) => request.get('/support/consultations', { params }),
  createConsultation: (data) => request.post('/support/consultations', data),
  updateConsultation: (id, data) => request.put(`/support/consultations/${id}`, data),
  removeConsultation: (id) => request.delete(`/support/consultations/${id}`),
}

// 数据分析
export const analyticsApi = {
  report: () => request.get('/analytics/report'),
}
