<template>
  <div class="company-settings">
    <h2>公司设置</h2>
    <el-card v-loading="loading" class="settings-card">
      <el-form :model="form" label-width="120px" @submit.prevent>
        <el-form-item label="公司名称">
          <el-input v-model="form.display_name" placeholder="请输入公司名称" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSaveName" :loading="saving">保存名称</el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <el-form label-width="120px">
        <el-form-item label="用户邀请码">
          <div class="invite-code-row">
            <el-input :model-value="userInviteCode" disabled class="code-input" />
            <el-button @click="handleCopy" :icon="DocumentCopy" title="复制" />
            <el-button type="warning" @click="handleRegenerate" :loading="regenerating">重新生成</el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-text type="info" size="small">用户邀请码用于邀请普通用户注册到本公司，重新生成后旧邀请码将失效。</el-text>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getMyOrg, updateMyOrg, regenerateMyUserInviteCode } from '../../api/admin'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

const loading = ref(false)
const saving = ref(false)
const regenerating = ref(false)
const orgInfo = ref({})
const form = ref({ display_name: '' })
const userInviteCode = ref('')

async function loadData() {
  loading.value = true
  try {
    const data = await getMyOrg()
    orgInfo.value = data
    form.value.display_name = data.display_name || ''
    userInviteCode.value = data.user_invite_code || ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function handleSaveName() {
  if (!form.value.display_name || !form.value.display_name.trim()) {
    ElMessage.warning('请输入公司名称')
    return
  }
  saving.value = true
  try {
    await updateMyOrg({ display_name: form.value.display_name.trim() })
    ElMessage.success('保存成功')
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function handleCopy() {
  if (!userInviteCode.value) return
  navigator.clipboard.writeText(userInviteCode.value)
  ElMessage.success('已复制到剪贴板')
}

async function handleRegenerate() {
  try {
    await ElMessageBox.confirm('重新生成后，旧的用户邀请码将失效，确定继续？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  regenerating.value = true
  try {
    const res = await regenerateMyUserInviteCode()
    userInviteCode.value = res.user_invite_code
    ElMessage.success('用户邀请码已重新生成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    regenerating.value = false
  }
}

onMounted(loadData)

watch(() => authStore.currentOrgId, () => {
  loadData()
})
</script>

<style scoped>
.company-settings {
  padding: 20px;
}
.settings-card {
  max-width: 600px;
}
.invite-code-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.code-input {
  flex: 1;
}
</style>
