<template>
  <div class="admin-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>组织管理</h3>
            <p class="sub-text">管理销售组织（公司），控制数据隔离范围</p>
          </div>
          <el-button type="primary" @click="openDialog(null)">
            <el-icon><Plus /></el-icon> 新增组织
          </el-button>
        </div>
      </template>

      <el-table :data="organizations" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="code" label="编码" width="140" />
        <el-table-column prop="display_name" label="名称" width="160" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column prop="user_count" label="用户数" width="80" align="center" />
        <el-table-column label="管理员邀请码" width="160">
          <template #default="{ row }">
            <div class="code-cell">
              <code>{{ row.admin_invite_code || '-' }}</code>
              <el-button
                v-if="row.admin_invite_code"
                size="small" text type="primary"
                @click="copyCode(row.admin_invite_code)"
              >复制</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="用户邀请码" width="160">
          <template #default="{ row }">
            <div class="code-cell">
              <code>{{ row.user_invite_code || '-' }}</code>
              <el-button
                v-if="row.user_invite_code"
                size="small" text type="primary"
                @click="copyCode(row.user_invite_code)"
              >复制</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
              {{ row.status === 'active' ? '正常' : '已禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div style="white-space: nowrap;">
              <el-button size="small" text type="primary" @click="openDialog(row)">编辑</el-button>
              <el-button size="small" text type="warning" @click="handleRegenCodes(row)">重生邀请码</el-button>
              <el-button
                v-if="row.code !== 'default'"
                size="small" text
                :type="row.status === 'active' ? 'danger' : 'success'"
                @click="handleToggleStatus(row)"
              >
                {{ row.status === 'active' ? '禁用' : '启用' }}
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑组织' : '新增组织'"
      width="460px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="编码" prop="code">
          <el-input v-model="form.code" placeholder="英文编码，如 company_a" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="如：A公司" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="组织描述（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getOrganizations, createOrganization, updateOrganization, deleteOrganization, regenerateInviteCodes } from '../../api/admin'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const organizations = ref([])
const dialogVisible = ref(false)
const editing = ref(null)
const formRef = ref()

const form = reactive({
  code: '',
  display_name: '',
  description: '',
})

const rules = {
  code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

onMounted(loadData)

async function loadData() {
  const data = await getOrganizations()
  organizations.value = data.organizations
}

function openDialog(row) {
  editing.value = row
  if (row) {
    form.code = row.code
    form.display_name = row.display_name
    form.description = row.description || ''
  } else {
    form.code = ''
    form.display_name = ''
    form.description = ''
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      if (editing.value) {
        await updateOrganization(editing.value.id, {
          display_name: form.display_name,
          description: form.description,
        })
        ElMessage.success('更新成功')
      } else {
        await createOrganization(form)
        ElMessage.success('创建成功')
      }
      dialogVisible.value = false
      await loadData()
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '操作失败')
    }
  })
}

async function handleToggleStatus(row) {
  try {
    if (row.status === 'active') {
      await deleteOrganization(row.id)
      ElMessage.success('已禁用')
    } else {
      await updateOrganization(row.id, { status: 'active' })
      ElMessage.success('已启用')
    }
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleRegenCodes(row) {
  try {
    await ElMessageBox.confirm(
      `确定重新生成「${row.display_name}」的邀请码？\n旧邀请码将立即失效。`,
      '重新生成邀请码',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await regenerateInviteCodes(row.id)
    ElMessage.success('邀请码已重新生成')
    await loadData()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '操作失败')
    }
  }
}

function copyCode(code) {
  navigator.clipboard.writeText(code)
  ElMessage.success('已复制到剪贴板')
}
</script>

<style scoped>
.admin-page {
  /* full width */
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  font-size: 18px;
}

.sub-text {
  margin: 4px 0 0;
  color: #909399;
  font-size: 13px;
}

.code-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.code-cell code {
  font-family: monospace;
  font-size: 13px;
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 3px;
}
</style>
