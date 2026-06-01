<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <template #header>
        <div class="login-header">
          <h1>企业 AI 知识助手</h1>
          <p>{{ isRegister ? '注册新账号' : '请登录以访问系统' }}</p>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="0"
        size="large"
        @submit.prevent="handleSubmit"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            prefix-icon="User"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            prefix-icon="Lock"
            show-password
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item v-if="isRegister" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="再次输入密码"
            prefix-icon="Lock"
            show-password
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item v-if="isRegister" prop="inviteCode">
          <el-input
            v-model="form.inviteCode"
            placeholder="请输入邀请码"
            prefix-icon="Ticket"
            :disabled="loading"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            native-type="submit"
            :loading="loading"
            class="submit-btn"
          >
            {{ isRegister ? '注册' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <span v-if="!isRegister">
          没有账号？<el-link type="primary" @click="isRegister = true">去注册</el-link>
        </span>
        <span v-else>
          已有账号？<el-link type="primary" @click="isRegister = false">去登录</el-link>
        </span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { login, register, getMe } from '../api/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const isRegister = ref(false)

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  inviteCode: '',
})

const validateConfirm = (rule, value, callback) => {
  if (isRegister.value && value !== form.password) {
    callback(new Error('两次密码不一致'))
  } else {
    callback()
  }
}

const rules = computed(() => ({
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名需 3-32 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirmPassword: isRegister.value
    ? [
        { required: true, message: '请确认密码', trigger: 'blur' },
        { validator: validateConfirm, trigger: 'blur' },
      ]
    : [],
  inviteCode: isRegister.value
    ? [{ required: true, message: '请输入邀请码', trigger: 'blur' }]
    : [],
}))

async function handleSubmit() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      if (isRegister.value) {
        await register(form.username.trim(), form.password, form.inviteCode.trim())
        ElMessage.success('注册成功')
      } else {
        await login(form.username.trim(), form.password)
      }
      const me = await getMe()
      authStore.setUser(me)
      router.push('/')
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || (isRegister.value ? '注册失败' : '登录失败'))
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

.login-card {
  width: 420px;
  border-radius: 12px;
}

.login-header {
  text-align: center;
}

.login-header h1 {
  margin: 0 0 8px;
  font-size: 22px;
  color: #303133;
}

.login-header p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.submit-btn {
  width: 100%;
}

.login-footer {
  text-align: center;
  color: #909399;
  font-size: 14px;
}
</style>
