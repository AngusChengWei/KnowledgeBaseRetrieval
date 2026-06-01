<template>
  <div class="admin-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>用户管理</h3>
            <p class="sub-text">管理系统用户、角色和部门权限</p>
          </div>
          <el-button type="primary" @click="openCreateDialog">
            <el-icon><Plus /></el-icon> 新增用户
          </el-button>
        </div>
      </template>

      <el-table :data="users" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column label="角色" width="160">
          <template #default="{ row }">
            <el-select
              :model-value="row.role"
              size="small"
              :disabled="row.role === 'super_admin' && !isSuperAdmin"
              @change="(val) => handleRoleChange(row.id, val)"
            >
              <el-option label="普通用户" value="user" />
              <el-option label="管理员" value="admin" />
              <el-option v-if="isSuperAdmin" label="超级管理员" value="super_admin" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="isSuperAdmin" label="所属组织" width="150">
          <template #default="{ row }">
            <el-select
              :model-value="row.org_id"
              size="small"
              placeholder="未分配"
              @change="(val) => handleOrgChange(row.id, val)"
            >
              <el-option
                v-for="org in orgList"
                :key="org.id"
                :label="org.display_name"
                :value="org.id"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'danger'" size="small">
              {{ row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="部门" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="d in row.departments"
              :key="d.id"
              size="small"
              type="info"
              class="dept-tag"
            >
              {{ d.display_name }}
            </el-tag>
            <el-button size="small" text type="primary" @click="openDeptEditor(row)">
              编辑
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="160">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              size="small"
              :type="row.status === 'active' ? 'danger' : 'success'"
              text
              :disabled="row.role === 'super_admin' && !isSuperAdmin"
              @click="handleToggleStatus(row.id)"
            >
              {{ row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 部门编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="'编辑部门 - ' + (editingUser?.username || '')"
      width="420px"
    >
      <el-checkbox-group v-model="selectedDeptIds">
        <el-checkbox
          v-for="d in allDepartments"
          :key="d.id"
          :value="d.id"
          :label="d.display_name"
          style="display: block; margin-bottom: 12px;"
        />
      </el-checkbox-group>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDepts">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增用户弹窗 -->
    <el-dialog v-model="createDialogVisible" title="新增用户" width="440px">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="3-32位，字母/数字/下划线/中文" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" placeholder="至少6位" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
            <el-option v-if="isSuperAdmin" label="超级管理员" value="super_admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateUser">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { getUsers, createUser, updateUserRole, updateUserOrg, toggleUserStatus, updateUserDepartments, getDepartments, getOrganizations } from '../../api/admin'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const isSuperAdmin = computed(() => authStore.user?.role === 'super_admin')

// 监听组织切换，自动刷新数据
watch(() => authStore.currentOrgId, () => {
  loadData()
})

const users = ref([])
const allDepartments = ref([])
const orgList = ref([])
const editingUser = ref(null)
const selectedDeptIds = ref([])
const dialogVisible = ref(false)

// 新增用户
const createDialogVisible = ref(false)
const createFormRef = ref()
const createForm = reactive({
  username: '',
  password: '',
  role: 'user',
})
const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名需 3-32 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

onMounted(async () => {
  await loadData()
})

async function loadData() {
  const promises = [getUsers(), getDepartments()]
  if (isSuperAdmin.value) promises.push(getOrganizations())
  const results = await Promise.all(promises)
  users.value = results[0].users
  allDepartments.value = results[1].departments
  if (results[2]) orgList.value = results[2].organizations || []
}

async function handleRoleChange(userId, newRole) {
  try {
    await updateUserRole(userId, newRole)
    ElMessage.success('角色更新成功')
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  }
}

async function handleOrgChange(userId, newOrgId) {
  try {
    await updateUserOrg(userId, newOrgId)
    ElMessage.success('组织更新成功')
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  }
}

async function handleToggleStatus(userId) {
  try {
    await toggleUserStatus(userId)
    ElMessage.success('状态更新成功')
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

function openDeptEditor(u) {
  editingUser.value = u
  selectedDeptIds.value = u.departments.map(d => d.id)
  dialogVisible.value = true
}

async function saveDepts() {
  try {
    await updateUserDepartments(editingUser.value.id, selectedDeptIds.value)
    ElMessage.success('部门更新成功')
    dialogVisible.value = false
    await loadData()
  } catch (e) {
    ElMessage.error('更新失败')
  }
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 16)
}

function openCreateDialog() {
  createForm.username = ''
  createForm.password = ''
  createForm.role = 'user'
  createDialogVisible.value = true
}

async function handleCreateUser() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    try {
      await createUser({
        username: createForm.username.trim(),
        password: createForm.password,
        role: createForm.role,
      })
      ElMessage.success('用户创建成功')
      createDialogVisible.value = false
      await loadData()
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '创建失败')
    }
  })
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

.dept-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.time-text {
  font-size: 13px;
  color: #909399;
}
</style>
