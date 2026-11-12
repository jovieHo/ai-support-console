<script setup>
// 登录页面
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

// 401 跳回登录页是整页刷新，原因由 request.js 暂存在 sessionStorage，这里取出来提示
onMounted(() => {
  const reason = sessionStorage.getItem('authError')
  if (reason) {
    ElMessage.error({ message: reason, duration: 4000 })
    sessionStorage.removeItem('authError')
  }
})

// 提交登录
const submit = async () => {
  loading.value = true
  try {
    await auth.login(form)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="login-panel">
      <p class="eyebrow">ZhiQiTong Business AI</p>
      <h1>智企通 AI 商务助手平台</h1>
      <el-form label-position="top" @keyup.enter="submit">
        <el-form-item label="账号">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">进入平台</el-button>
      </el-form>
    </section>
  </div>
</template>
