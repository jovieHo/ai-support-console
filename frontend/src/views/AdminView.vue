<script setup>
// 系统管理：用户管理（增删改查）
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { userApi } from '../api/modules'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const users = ref([])
const roles = ref([])
const dialogVisible = ref(false)
// null 表示新增，否则为正在编辑的用户行
const editing = ref(null)
const form = reactive({ username: '', email: '', password: '', role: 'enterprise_user' })

const ROLE_LABELS = {
  enterprise_user: '企业用户',
  customer_service: '客服',
  admin: '管理员',
}
const ROLE_TAGS = { admin: 'danger', customer_service: 'warning', enterprise_user: 'info' }

const load = async () => {
  users.value = (await userApi.list()).items
}

// 唯一一个启用状态的管理员：不能停用，也不能降级（否则系统再没人能进管理端）
const isSoleAdmin = (row) =>
  !!row && row.role === 'admin' && row.is_active &&
  users.value.filter((item) => item.role === 'admin' && item.is_active).length === 1

const openCreate = () => {
  editing.value = null
  Object.assign(form, { username: '', email: '', password: '', role: 'enterprise_user' })
  dialogVisible.value = true
}

const openEdit = (row) => {
  editing.value = row
  Object.assign(form, { username: row.username, email: row.email, password: '', role: row.role })
  dialogVisible.value = true
}

const submit = async () => {
  if (!form.email.trim()) { ElMessage.warning('请填写邮箱'); return }
  try {
    if (editing.value) {
      // 编辑时用户名不可改，密码留空表示不重置
      const data = { email: form.email.trim(), role: form.role }
      if (form.password) data.password = form.password
      await userApi.update(editing.value.id, data)
      ElMessage.success('用户已更新')
    } else {
      if (form.username.trim().length < 3 || form.password.length < 6) {
        ElMessage.warning('用户名至少 3 个字符，密码至少 6 位'); return
      }
      await userApi.create({ username: form.username.trim(), email: form.email.trim(), password: form.password, role: form.role })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message)
  }
}

const toggleActive = async (row) => {
  const enabling = !row.is_active
  const self = row.id === auth.user?.id
  try {
    if (!enabling) {
      await ElMessageBox.confirm(
        self
          ? `确定停用你自己的账号「${row.username}」？停用后你会立即被登出。`
          : `确定停用账号「${row.username}」？停用后该账号无法登录。`,
        '停用确认',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    }
    await userApi.update(row.id, { is_active: enabling })
    // 停用的是自己：token 立刻失效，主动退出比等下一个请求报 403 干净
    if (self && !enabling) {
      auth.logout()
      router.push('/login')
      return
    }
    ElMessage.success(enabling ? '账号已启用' : '账号已停用')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '操作失败')
  }
}

onMounted(async () => {
  await Promise.all([load(), userApi.roles().then((data) => (roles.value = data))])
})
</script>

<template>
  <section class="page-grid">
    <div class="panel">
      <div class="section-title">
        <div>
          <p>系统管理员端</p>
          <h2>用户管理</h2>
        </div>
        <div class="section-actions">
          <el-button @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新增用户</el-button>
        </div>
      </div>
      <el-table :data="users" height="480">
        <el-table-column prop="username" label="账号" min-width="120" />
        <el-table-column prop="email" label="邮箱" min-width="160" />
        <el-table-column prop="role" label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="ROLE_TAGS[row.role] || 'info'">{{ ROLE_LABELS[row.role] || row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'danger' : 'success'"
              plain
              :disabled="isSoleAdmin(row)"
              :title="isSoleAdmin(row) ? '系统至少需要保留一名启用的管理员' : ''"
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? `编辑用户：${editing.username}` : '新增用户'" width="440">
      <el-form label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="!!editing" maxlength="50" placeholder="至少 3 个字符" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" maxlength="100" />
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '密码'">
          <el-input v-model="form.password" type="password" show-password maxlength="100" :placeholder="editing ? '留空表示不修改' : '至少 6 位'" />
        </el-form-item>
        <el-form-item label="角色">
          <div style="width: 100%">
            <el-select v-model="form.role" style="width: 100%">
              <el-option
                v-for="role in roles"
                :key="role"
                :value="role"
                :label="ROLE_LABELS[role] || role"
                :disabled="isSoleAdmin(editing) && role !== 'admin'"
              />
            </el-select>
            <div v-if="isSoleAdmin(editing)" style="font-size: 12px; color: #909399; line-height: 1.6">
              当前是唯一启用的管理员，不能改为其他角色
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>
