<script setup>
// 商务数据管理：全宽列表 + 新增/编辑对话框
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { businessApi } from '../api/modules'

const rows = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const statusFilter = ref('active')
const form = reactive({ title: '', content: '', amount: 0, status: 'draft' })

const statusMeta = {
  draft: { label: '草稿', type: 'info' },
  published: { label: '发布', type: 'success' },
  archived: { label: '已归档', type: 'info' },
}

// 加载列表：「进行中」由前端排除已归档，其余状态走后端筛选
const load = async () => {
  loading.value = true
  try {
    const params = statusFilter.value === 'active' ? {} : { status: statusFilter.value }
    let items = (await businessApi.list(params)).items
    if (statusFilter.value === 'active') items = items.filter((row) => row.status !== 'archived')
    rows.value = items
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

const formatTime = (value) => (value ? value.replace('T', ' ').slice(0, 16) : '—')

const formatAmount = (value) => `¥ ${Number(value || 0).toLocaleString('zh-CN')}`

// 新增与编辑共用同一个对话框，靠 editingId 区分
const openCreate = () => {
  editingId.value = null
  Object.assign(form, { title: '', content: '', amount: 0, status: 'draft' })
  dialogVisible.value = true
}

const openEdit = (row) => {
  editingId.value = row.id
  Object.assign(form, {
    title: row.title,
    content: row.content ?? '',
    amount: row.amount ?? 0,
    status: row.status ?? 'draft',
  })
  dialogVisible.value = true
}

const save = async () => {
  if (!form.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  try {
    if (editingId.value) {
      await businessApi.update(editingId.value, { ...form })
      ElMessage.success('已更新')
    } else {
      await businessApi.create({ ...form })
      ElMessage.success('商务数据已保存')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

// 归档（软删除）：后端把状态改为 archived，数据保留可回溯
const archiveRow = async (row) => {
  try {
    await ElMessageBox.confirm(`确定归档「${row.title}」？归档后可在状态筛选中选择「已归档」查看。`, '归档确认', { type: 'warning', confirmButtonText: '归档', cancelButtonText: '取消' })
    await businessApi.remove(row.id)
    ElMessage.success('已归档')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '归档失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="section-title">
      <div>
        <p>基础业务功能</p>
        <h2>商务数据</h2>
      </div>
      <div class="toolbar">
        <el-select v-model="statusFilter" style="width: 110px" @change="load">
          <el-option label="进行中" value="active" />
          <el-option label="草稿" value="draft" />
          <el-option label="发布" value="published" />
          <el-option label="已归档" value="archived" />
        </el-select>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增数据</el-button>
      </div>
    </div>
    <el-table v-loading="loading" :data="rows" height="480">
      <el-table-column prop="title" label="标题" width="320" show-overflow-tooltip />
      <el-table-column label="金额" width="150" align="right">
        <template #default="{ row }">{{ formatAmount(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
            {{ statusMeta[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button text type="danger" size="small" @click="archiveRow(row)">归档</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑商务数据' : '新增商务数据'" width="520">
      <el-form label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="5" /></el-form-item>
        <el-form-item label="金额"><el-input-number v-model="form.amount" :min="0" :step="10000" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option label="草稿" value="draft" />
            <el-option label="发布" value="published" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
}

/* 表格内相邻按钮去掉默认间距，保证编辑/归档并排 */
.toolbar :deep(.el-button + .el-button),
:deep(.el-table .el-button + .el-button) {
  margin-left: 8px;
}
</style>
