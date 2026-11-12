<script setup>
// 企业用户AI聊天页：会话管理 + 对话 + 知识库RAG
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { BookOpen, ChevronDown, Edit3, FileUp, Mic, MessageSquarePlus, RefreshCw, Search, Send, Star, Trash2, Volume2, X } from 'lucide-vue-next'
import { chatApi, knowledgeApi } from '../api/modules'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
// 知识库上传/删除属管理操作，后端仅对客服与管理员开放
const isStaff = computed(() => ['customer_service', 'admin'].includes(auth.role))

const welcomeMessage = { role: 'assistant', content: '您好，我是智企通 AI 商务助手。可以咨询产品、服务、知识库或业务流程。' }

// 聊天状态
const input = ref('平台是否支持私有化部署？')
const conversationId = ref(null)
const messages = ref([{ ...welcomeMessage }])
const loading = ref(false)
const conversationLoading = ref(false)
const conversations = ref([])
const favoriteOnly = ref(false)
const sidebarCollapsed = ref(false)
const kbOpen = ref(false)
const docsExpanded = ref(false)

// 知识库状态
const kbQuestion = ref('平台是否支持私有化部署？')
const kbAnswer = ref('')
const kbSources = ref([])
const kbLoading = ref(false)
const kbTopK = ref(4)
const uploadFile = ref(null)
const uploadRef = ref()
const documents = ref([])

const currentConversation = computed(() => conversations.value.find((item) => item.id === conversationId.value))

const statusType = (status) => {
  if (status === 'indexed') return 'success'
  if (status === 'processing') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}

const statusText = (status) => {
  const labels = { indexed: '已索引', processing: '解析中', failed: '失败', empty: '空文档' }
  return labels[status] || '未知'
}

const formatDate = (value) => {
  if (!value) return '暂无'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

// 加载会话列表
const loadConversations = async () => {
  conversationLoading.value = true
  try {
    const data = await chatApi.conversations(favoriteOnly.value ? { favorite: true } : undefined)
    conversations.value = data.items || []
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    conversationLoading.value = false
  }
}

// 创建新会话
const startNewConversation = () => {
  conversationId.value = null
  messages.value = [{ ...welcomeMessage }]
  input.value = ''
}

// 打开指定会话
const openConversation = async (item) => {
  conversationLoading.value = true
  try {
    const data = await chatApi.conversation(item.id)
    conversationId.value = data.id
    messages.value = data.messages.length
      ? data.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources || [] }))
      : [{ ...welcomeMessage }]
    await nextTick()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    conversationLoading.value = false
  }
}

// 重命名会话
const renameConversation = async (item) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名会话', {
      inputValue: item.title,
      inputPattern: /^.{1,200}$/,
      inputErrorMessage: '会话名称不能为空，且不超过 200 字',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    await chatApi.updateConversation(item.id, { title: value.trim() })
    ElMessage.success('会话名称已更新')
    await loadConversations()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '重命名失败')
  }
}

// 切换收藏
const toggleFavorite = async (item) => {
  try {
    await chatApi.updateConversation(item.id, { is_favorite: !item.is_favorite })
    ElMessage.success(item.is_favorite ? '已取消收藏' : '已收藏会话')
    await loadConversations()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 发送消息
const send = async () => {
  if (!input.value.trim()) return
  const question = input.value
  messages.value.push({ role: 'user', content: question })
  input.value = ''
  loading.value = true
  const replyIndex = messages.value.push({ role: 'assistant', content: '', sources: [] }) - 1
  try {
    await chatApi.stream(
      { message: question, conversation_id: conversationId.value },
      {
        onDelta: (content) => { messages.value[replyIndex].content += content },
        onDone: (data) => {
          conversationId.value = data.conversation_id
          messages.value[replyIndex].sources = data.sources || []
        },
      },
    )
    await loadConversations()
    await nextTick()
  } catch (error) {
    if (!messages.value[replyIndex].content) messages.value.splice(replyIndex, 1)
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

// 知识库RAG问答
const askKnowledge = async () => {
  if (!kbQuestion.value.trim()) { ElMessage.warning('请输入知识库问题'); return }
  kbLoading.value = true
  kbAnswer.value = ''
  kbSources.value = []
  try {
    const data = await knowledgeApi.query({ question: kbQuestion.value, top_k: kbTopK.value })
    kbAnswer.value = data.answer
    kbSources.value = data.sources || []
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    kbLoading.value = false
  }
}

// 加载文档列表
const loadDocuments = async () => {
  try { documents.value = (await knowledgeApi.documents()).items || [] } catch { documents.value = [] }
}

// 上传知识文档
const uploadKnowledge = async () => {
  if (!uploadFile.value) { ElMessage.warning('请先选择知识文档'); return }
  const formData = new FormData()
  formData.append('file', uploadFile.value.raw)
  try {
    const data = await knowledgeApi.upload(formData)
    ElMessage.success(data.message || `已上传 ${data.filename}，生成 ${data.chunk_count} 个知识片段`)
    uploadFile.value = null
    uploadRef.value?.clearFiles()
    await loadDocuments()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 语音播报
const speak = (text) => {
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = 'zh-CN'
  window.speechSynthesis.speak(utterance)
}

// 语音输入
const listen = () => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!Recognition) { ElMessage.warning('当前浏览器不支持语音识别'); return }
  const recognition = new Recognition()
  recognition.lang = 'zh-CN'
  recognition.onresult = (event) => { input.value = event.results[0][0].transcript }
  recognition.start()
}

// 删除会话
const deleteConversation = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除会话「${item.title}」？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await chatApi.removeConversation(item.id)
    ElMessage.success('会话已删除')
    if (conversationId.value === item.id) startNewConversation()
    await loadConversations()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

// 删除知识文档
const deleteKnowledgeDocument = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除文档「${item.filename}」？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await knowledgeApi.removeDocument(item.id)
    ElMessage.success('文档已删除')
    await loadDocuments()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

onMounted(async () => {
  await Promise.all([loadConversations(), loadDocuments()])
})
</script>

<template>
  <section class="chat-workbench">
    <aside v-loading="conversationLoading" :class="['panel', 'conversation-panel', { collapsed: sidebarCollapsed }]">
      <div class="conversation-header">
        <div v-if="!sidebarCollapsed">
          <p>会话历史</p>
          <h2>对话记录</h2>
        </div>
        <div class="conversation-header-actions">
          <el-tooltip v-if="!sidebarCollapsed" content="新建会话">
            <el-button circle @click="startNewConversation"><MessageSquarePlus :size="17" /></el-button>
          </el-tooltip>
          <el-button text circle class="collapse-toggle" @click="sidebarCollapsed = !sidebarCollapsed">
            <ChevronDown :size="17" />
          </el-button>
        </div>
      </div>
      <template v-if="!sidebarCollapsed">
        <div class="conversation-tools">
          <el-checkbox v-model="favoriteOnly" @change="loadConversations">只看收藏</el-checkbox>
          <el-button text @click="loadConversations"><RefreshCw :size="15" />刷新</el-button>
        </div>
        <div class="conversation-list">
          <article v-for="item in conversations" :key="item.id" :class="['conversation-item', { active: item.id === conversationId }]" @click="openConversation(item)">
            <div class="conversation-title">
              <strong>{{ item.title }}</strong>
              <el-button text circle @click.stop="toggleFavorite(item)">
                <Star :size="16" :fill="item.is_favorite ? 'currentColor' : 'none'" />
              </el-button>
            </div>
            <p>{{ item.last_message || '暂无消息' }}</p>
            <div class="conversation-meta">
              <span>{{ item.message_count }} 条消息</span>
              <span>{{ formatDate(item.updated_at || item.created_at) }}</span>
            </div>
            <div class="conversation-item-actions">
              <el-button class="rename-button" text @click.stop="renameConversation(item)"><Edit3 :size="14" />重命名</el-button>
              <el-button text type="danger" @click.stop="deleteConversation(item)"><Trash2 :size="14" />删除</el-button>
            </div>
          </article>
          <el-empty v-if="!conversations.length" description="暂无会话记录" />
        </div>
      </template>
    </aside>

    <div class="panel chat-panel">
      <div class="section-title">
        <div>
          <p>企业用户端</p>
          <h2>{{ currentConversation?.title || '新的 AI 智能对话' }}</h2>
        </div>
        <div class="section-title-actions">
          <el-tag>{{ currentConversation?.is_favorite ? '已收藏' : '上下文记忆 · 知识库检索' }}</el-tag>
          <el-button v-if="isStaff" @click="kbOpen = true"><BookOpen :size="16" />知识库问答</el-button>
        </div>
      </div>
      <div class="message-list">
        <article v-for="(item, index) in messages" :key="index" :class="['message', item.role]">
          <div>
            <p>{{ item.content }}</p>
            <div v-if="item.sources?.length" class="message-sources">
              <el-tag v-for="source in item.sources" :key="source.source + source.score" size="small" type="info">
                {{ source.source }} · {{ Number(source.score).toFixed(2) }}
              </el-tag>
            </div>
          </div>
          <button v-if="item.role === 'assistant'" type="button" @click="speak(item.content)"><Volume2 :size="16" /></button>
        </article>
      </div>
      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 8 }"
          placeholder="请输入商务问题"
        />
        <el-button circle @click="listen"><Mic :size="18" /></el-button>
        <el-button type="primary" :loading="loading" @click="send"><Send :size="18" />发送</el-button>
      </div>
    </div>

    <el-drawer v-model="kbOpen" direction="rtl" size="420px" :with-header="false" class="knowledge-drawer">
      <div class="panel knowledge-panel">
        <div class="section-title">
          <div>
            <p>知识库问答</p>
            <h2>RAG 检索增强</h2>
          </div>
          <div class="section-title-actions">
            <el-tag type="success">{{ documents.length }} 份文档</el-tag>
            <el-button text circle @click="kbOpen = false"><X :size="17" /></el-button>
          </div>
        </div>
        <div class="knowledge-tools">
          <el-input v-model="kbQuestion" type="textarea" :rows="3" placeholder="输入需要基于知识库回答的问题" />
          <div class="knowledge-actions">
            <el-input-number v-model="kbTopK" :min="1" :max="10" size="small" />
            <el-button type="primary" :loading="kbLoading" @click="askKnowledge"><Search :size="16" /> 开始问答</el-button>
          </div>
        </div>
        <div class="upload-strip">
          <BookOpen :size="18" />
          <span>文档上传后会显示解析状态、分块数和索引说明；未上传文档时会优先检索 FAQ。</span>
        </div>
        <div v-if="isStaff" class="upload-actions">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :show-file-list="true" @change="(file) => (uploadFile = file)">
            <el-button><FileUp :size="16" />选择文档</el-button>
          </el-upload>
          <el-button @click="uploadKnowledge">上传入库</el-button>
        </div>
        <el-collapse v-model="docsExpanded" class="docs-collapse">
          <el-collapse-item name="docs">
            <template #title>
              <div class="source-header docs-collapse-header">
                <h3>解析状态</h3>
                <span>{{ documents.length }} 份文档</span>
              </div>
            </template>
            <div class="document-status-list">
              <div class="source-header">
                <span />
                <el-button text @click="loadDocuments"><RefreshCw :size="14" />刷新</el-button>
              </div>
              <article v-for="item in documents.slice(0, 4)" :key="item.id" class="document-status-item">
                <div>
                  <strong>{{ item.filename }}</strong>
                  <p>{{ item.parse_message }}</p>
                </div>
                <div class="document-status-meta">
                  <el-tag :type="statusType(item.parse_status)" size="small">{{ statusText(item.parse_status) }}</el-tag>
                  <span>{{ item.chunk_count }} 块</span>
                  <el-button v-if="isStaff" text type="danger" size="small" @click="deleteKnowledgeDocument(item)"><Trash2 :size="12" />删除</el-button>
                </div>
              </article>
              <el-empty v-if="!documents.length" description="暂无文档状态" />
            </div>
          </el-collapse-item>
        </el-collapse>
        <section class="answer-box">
          <h3>回答</h3>
          <el-skeleton v-if="kbLoading" :rows="4" animated />
          <p v-else class="answer">{{ kbAnswer || '输入问题后点击"开始问答"，系统会召回知识片段并生成带来源的回答。' }}</p>
        </section>
        <section class="source-list">
          <div class="source-header">
            <h3>知识来源</h3>
            <span v-if="kbSources.length">共 {{ kbSources.length }} 条</span>
          </div>
          <el-empty v-if="!kbLoading && !kbSources.length" description="暂无来源。可先上传文档或维护 FAQ。" />
          <article v-for="(item, index) in kbSources" :key="item.source + index" class="source-item">
            <div class="source-title">
              <strong>{{ index + 1 }}. {{ item.source }}</strong>
              <span>相关度 {{ Number(item.score).toFixed(2) }}</span>
            </div>
            <p>{{ item.content }}</p>
          </article>
        </section>
      </div>
    </el-drawer>
  </section>
</template>
