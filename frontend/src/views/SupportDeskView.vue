<script setup>
// 客服工作台：AI智能辅助 + 咨询记录 + FAQ管理
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Trash2 } from 'lucide-vue-next'
import { supportApi, knowledgeApi } from '../api/modules'
import { categoryLabel, statusLabel } from '../constants'

const assistForm = reactive({ customer_name: '张三', question: '客户想了解私有化部署和报价流程' })
const agentResult = ref(null)
const consultations = ref([])
const faqs = ref([])
const faqForm = reactive({ question: '', answer: '', category: 'general' })
const loading = ref(false)
const saving = ref(false)
// 当前草稿已落库的记录 ID，后端生成时自动创建
const savedId = ref(null)
// 命中风险的记录是否已被客服确认处理
const handled = ref(false)

// 加载咨询记录和FAQ
const load = async () => {
  consultations.value = (await supportApi.consultations()).items
  faqs.value = (await knowledgeApi.faqs()).items
}

// 待复核工单：风控命中后落库、仍为 pending 状态的记录数
const pendingCount = () => consultations.value.filter((item) => item.status === 'pending').length

// AI智能辅助生成回复
const assist = async () => {
  loading.value = true
  try {
    agentResult.value = await supportApi.assist(assistForm)
    savedId.value = agentResult.value.consultation_id ?? null
    handled.value = false
    await load()
    ElMessage.success('智能客服建议已生成并保存')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

// 客服修改推荐回复后失焦：静默同步回已落库的记录
const syncReply = async () => {
  if (!savedId.value || !agentResult.value) return
  try {
    await supportApi.updateConsultation(savedId.value, { ai_reply: agentResult.value.reply })
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 命中风险的记录经人工确认后闭环
const confirmHandled = async () => {
  saving.value = true
  try {
    await supportApi.updateConsultation(savedId.value, { status: 'resolved' })
    handled.value = true
    ElMessage.success(`记录 #${savedId.value} 已确认处理`)
    await load()
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    saving.value = false
  }
}

// 删除记录
const deleteConsultation = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除记录 #${row.id}？删除后不可恢复。`, '删除确认', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await supportApi.removeConsultation(row.id)
    ElMessage.success('记录已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '删除失败')
  }
}

// 保存FAQ
const saveFaq = async () => {
  await knowledgeApi.createFaq(faqForm)
  faqForm.question = ''
  faqForm.answer = ''
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page-grid two">
    <div class="panel">
      <div class="section-title">
        <div>
          <p>客服人员端</p>
          <h2>智能客服辅助</h2>
        </div>
        <el-button type="primary" :loading="loading" @click="assist">生成建议</el-button>
      </div>
      <el-form label-position="top">
        <el-form-item label="客户名称"><el-input v-model="assistForm.customer_name" /></el-form-item>
        <el-form-item label="客户问题"><el-input v-model="assistForm.question" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <div v-if="agentResult" class="agent-result">
        <el-tag>{{ categoryLabel(agentResult.category) }}</el-tag>
        <el-tag v-if="agentResult.urgency === 'high'" type="danger">高紧急</el-tag>
        <el-tag v-if="agentResult.needs_human" type="warning">建议人工介入</el-tag>
        <el-tag v-if="agentResult.action === 'escalate'" type="danger">需人工复核</el-tag>
        <el-tag type="info" effect="plain" class="source-tag">
          {{ agentResult.classification_source === 'llm' ? '模型结构化分类' : '规则分类' }}
        </el-tag>
        <p v-if="agentResult.intent" class="meta-line">意图：{{ agentResult.intent }}</p>
        <el-alert
          v-if="agentResult.missing_information?.length"
          type="info"
          :closable="false"
          show-icon
          :title="`回答前还缺：${agentResult.missing_information.join('、')}`"
        />
        <h3>推荐回复</h3>
        <el-input v-model="agentResult.reply" type="textarea" :rows="6" @blur="syncReply" />
        <el-alert
          v-if="agentResult.risk_flags?.length"
          type="warning"
          :closable="false"
          show-icon
          :title="`风险提示：命中 ${agentResult.risk_flags.join('、')}，${
            agentResult.consultation_id ? `已创建待复核记录 #${agentResult.consultation_id}` : '请人工确认后再发送'
          }`"
        />
        <p v-else>风险检查：未发现高风险表述</p>
        <div class="result-actions">
          <el-button v-if="agentResult.action === 'escalate' && !handled" type="primary" :loading="saving" @click="confirmHandled">确认已处理</el-button>
          <span v-if="savedId" class="saved-hint">已存入记录 #{{ savedId }}，修改回复会自动同步</span>
        </div>
        <el-timeline>
          <el-timeline-item v-for="item in agentResult.trace" :key="item">{{ item }}</el-timeline-item>
        </el-timeline>
      </div>
    </div>

    <div class="panel">
      <div class="section-title">
        <div>
          <p>记录管理</p>
          <h2>客服对话与 FAQ</h2>
        </div>
        <div class="title-actions">
          <span v-if="pendingCount()" class="pending-badge">待复核 {{ pendingCount() }} 单</span>
          <el-button @click="load">刷新</el-button>
        </div>
      </div>
      <el-table :data="consultations" height="240">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="customer_name" label="客户" width="90" />
        <el-table-column label="分类" width="100">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">{{ statusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column prop="question" label="问题" min-width="140" show-overflow-tooltip />
        <el-table-column prop="ai_reply" label="AI 回复" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button text type="danger" size="small" @click="deleteConsultation(row)"><Trash2 :size="14" />删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-divider />
      <el-form label-position="top" class="faq-form">
        <el-form-item label="常见问题"><el-input v-model="faqForm.question" /></el-form-item>
        <el-form-item label="标准答案"><el-input v-model="faqForm.answer" type="textarea" :rows="3" /></el-form-item>
        <el-button @click="saveFaq">新增 FAQ</el-button>
      </el-form>
      <div class="chunk-list faq-scroll">
        <article v-for="item in faqs" :key="item.id" class="source-item">
          <strong>{{ item.question }}</strong>
          <p>{{ item.answer }}</p>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* FAQ 列表收进固定高度滚动区，避免条目多时把页面撑长 */
.faq-scroll {
  margin-top: 12px;
  max-height: 420px;
}

.result-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
}

.saved-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.title-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 待复核工单角标：风控命中且仍为 pending 的记录数，提醒客服处理 */
.pending-badge {
  padding: 5px 12px;
  border: 1px solid var(--el-color-warning);
  border-radius: 999px;
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
</style>
