<script setup>
// 知识库管理中心：文档上传/解析/分块/FAQ
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FileUp, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import { knowledgeApi } from '../api/modules'

const loading = ref(false)
const uploadFile = ref(null)
const uploadRef = ref()
const activeTab = ref('documents')
// 搜索框输入值与已生效的关键词分离：点「搜索」或按回车才过滤
const searchInput = ref('')
const keyword = ref('')
const overview = ref({ documents: [], chunks: [], faqs: [], stats: { document_count: 0, chunk_count: 0, faq_count: 0 } })

const doSearch = () => {
  keyword.value = searchInput.value.trim()
}

// 按关键词过滤文档（文件名/类型）
const filteredDocuments = computed(() => {
  const k = keyword.value
  if (!k) return overview.value.documents
  return overview.value.documents.filter((item) => item.filename.includes(k) || (item.content_type || '').includes(k))
})

// 按关键词过滤分块
const filteredChunks = computed(() => {
  const k = keyword.value
  if (!k) return overview.value.chunks
  return overview.value.chunks.filter((item) => item.content.includes(k) || item.source.includes(k))
})

// 按关键词过滤FAQ
const filteredFaqs = computed(() => {
  const k = keyword.value
  if (!k) return overview.value.faqs
  return overview.value.faqs.filter((item) => item.question.includes(k) || item.answer.includes(k) || item.category.includes(k))
})

const formatTime = (value) => {
  if (!value) return '\u2014'
  return value.replace('T', ' ').slice(0, 16)
}

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

// 加载概览
const loadOverview = async () => {
  loading.value = true
  try {
    overview.value = await knowledgeApi.overview()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

// 上传文档
const uploadKnowledge = async () => {
  if (!uploadFile.value) { ElMessage.warning('请先选择文档'); return }
  const formData = new FormData()
  formData.append('file', uploadFile.value.raw)
  try {
    const data = await knowledgeApi.upload(formData)
    ElMessage.success(data.message || `${data.filename} 已持久化保存，生成 ${data.chunk_count} 个分块`)
    uploadFile.value = null
    uploadRef.value?.clearFiles()
    await loadOverview()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 删除文档
const deleteDocument = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除文档「${row.filename}」？该文档的所有知识分块也将被删除。`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await knowledgeApi.removeDocument(row.id)
    ElMessage.success('文档已删除')
    await loadOverview()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

// FAQ 编辑/删除
const faqDialog = ref(false)
const faqForm = reactive({ id: 0, question: '', answer: '', category: '', is_active: true })

const openFaqEdit = (item) => {
  Object.assign(faqForm, { id: item.id, question: item.question, answer: item.answer, category: item.category, is_active: item.is_active })
  faqDialog.value = true
}

const saveFaq = async () => {
  if (!faqForm.question.trim() || !faqForm.answer.trim()) { ElMessage.warning('问题和答案不能为空'); return }
  try {
    await knowledgeApi.updateFaq(faqForm.id, {
      question: faqForm.question.trim(),
      answer: faqForm.answer.trim(),
      category: faqForm.category.trim() || 'general',
      is_active: faqForm.is_active,
    })
    faqDialog.value = false
    ElMessage.success('FAQ 已更新')
    await loadOverview()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const deleteFaq = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除 FAQ「${item.question}」？`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await knowledgeApi.removeFaq(item.id)
    ElMessage.success('FAQ 已删除')
    await loadOverview()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

onMounted(loadOverview)
</script>

<template>
  <section v-loading="loading" class="knowledge-page">
    <div class="section-title">
      <div>
        <p>知识库中心</p>
        <h2>全部知识内容</h2>
      </div>
      <el-button @click="loadOverview"><RefreshCw :size="16" />刷新</el-button>
    </div>
    <div class="metric-row">
      <div class="metric-card"><span>文档</span><strong>{{ overview.stats.document_count }}</strong></div>
      <div class="metric-card"><span>知识分块</span><strong>{{ overview.stats.chunk_count }}</strong></div>
      <div class="metric-card"><span>FAQ</span><strong>{{ overview.stats.faq_count }}</strong></div>
    </div>
    <div class="panel knowledge-manager">
      <div class="knowledge-topbar">
        <div class="upload-actions">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" @change="(file) => (uploadFile = file)">
            <el-button><FileUp :size="16" />选择文档</el-button>
          </el-upload>
          <el-button type="primary" @click="uploadKnowledge">上传并永久入库</el-button>
        </div>
        <el-input
          v-model="searchInput"
          class="knowledge-search"
          placeholder="搜索文档、分块、来源或 FAQ"
          clearable
          @keyup.enter="doSearch"
          @clear="doSearch"
        >
          <template #prefix><Search :size="16" /></template>
          <template #append>
            <el-button @click="doSearch">搜索</el-button>
          </template>
        </el-input>
      </div>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="上传文档" name="documents">
          <el-table :data="filteredDocuments" height="430">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="filename" label="文件名" min-width="150" show-overflow-tooltip />
            <el-table-column prop="content_type" label="类型" width="100" show-overflow-tooltip />
            <el-table-column label="解析状态" width="90">
              <template #default="{ row }">
                <el-tag :type="statusType(row.parse_status)" size="small">{{ statusText(row.parse_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="chunk_count" label="分块数" width="80" />
            <el-table-column prop="parse_message" label="解析说明" min-width="180" show-overflow-tooltip />
            <el-table-column prop="segment_rule" label="切分方式" width="170" show-overflow-tooltip />
            <el-table-column label="上传时间" width="150">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button text type="danger" @click="deleteDocument(row)"><Trash2 :size="14" />删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!filteredDocuments.length" :description="keyword ? '没有匹配的文档' : '暂无上传文档'" />
        </el-tab-pane>
        <el-tab-pane label="知识分块" name="chunks">
          <div class="chunk-list">
            <article v-for="item in filteredChunks" :key="item.id" class="source-item">
              <div class="source-title">
                <strong>#{{ item.id }} · {{ item.source }}</strong>
                <span>文档 {{ item.document_id }}</span>
              </div>
              <p>{{ item.content }}</p>
            </article>
            <el-empty v-if="!filteredChunks.length" description="暂无知识分块" />
          </div>
        </el-tab-pane>
        <el-tab-pane label="FAQ" name="faqs">
          <div class="chunk-list">
            <article v-for="item in filteredFaqs" :key="item.id" class="source-item">
              <div class="source-title">
                <strong>#{{ item.id }} · {{ item.category }}</strong>
                <div class="faq-actions">
                  <el-tag :type="item.is_active ? 'success' : 'info'">{{ item.is_active ? '启用' : '停用' }}</el-tag>
                  <el-button text size="small" @click="openFaqEdit(item)">编辑</el-button>
                  <el-button text type="danger" size="small" @click="deleteFaq(item)"><Trash2 :size="14" />删除</el-button>
                </div>
              </div>
              <p>问：{{ item.question }}</p>
              <p>答：{{ item.answer }}</p>
            </article>
            <el-empty v-if="!filteredFaqs.length" description="暂无 FAQ" />
          </div>
        </el-tab-pane>
      </el-tabs>

      <el-dialog v-model="faqDialog" :title="`编辑 FAQ #${faqForm.id}`" width="520">
        <el-form label-position="top">
          <el-form-item label="问题"><el-input v-model="faqForm.question" maxlength="200" /></el-form-item>
          <el-form-item label="答案"><el-input v-model="faqForm.answer" type="textarea" :rows="5" /></el-form-item>
          <el-form-item label="分类"><el-input v-model="faqForm.category" maxlength="30" placeholder="如 billing / refund / product" /></el-form-item>
          <el-form-item label="状态">
            <el-switch v-model="faqForm.is_active" active-text="启用" inactive-text="停用" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="faqDialog = false">取消</el-button>
          <el-button type="primary" @click="saveFaq">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </section>
</template>
