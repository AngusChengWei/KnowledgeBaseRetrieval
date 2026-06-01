<template>
  <div class="admin-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>部门管理</h3>
            <p class="sub-text">管理系统部门，控制知识库访问范围</p>
          </div>
          <el-button type="primary" @click="openDialog(null)">
            <el-icon><Plus /></el-icon> 新增部门
          </el-button>
        </div>
      </template>

      <el-table :data="departments" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="标识名" width="140" />
        <el-table-column prop="display_name" label="显示名称" width="160" />
        <el-table-column prop="description" label="描述" min-width="200" />
        <el-table-column v-if="isSuperAdmin" label="所属组织" width="140">
          <template #default="{ row }">
            <span>{{ row.org_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm
              title="确定要删除该部门吗？"
              confirm-button-text="确定"
              cancel-button-text="取消"
              @confirm="handleDelete(row.id)"
            >
              <template #reference>
                <el-button size="small" text type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑部门' : '新增部门'"
      width="460px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="标识名" prop="name">
          <el-input v-model="form.name" placeholder="英文标识，如 tech" :disabled="!!editing" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="form.display_name" placeholder="如：技术部" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="部门描述（选填）" />
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
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { getDepartments, createDepartment, updateDepartment, deleteDepartment } from '../../api/admin'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const authStore = useAuthStore()
const isSuperAdmin = computed(() => authStore.user?.role === 'super_admin')

// 监听组织切换，自动刷新数据
watch(() => authStore.currentOrgId, () => {
  loadData()
})

const departments = ref([])
const dialogVisible = ref(false)
const editing = ref(null)
const formRef = ref()

const form = reactive({
  name: '',
  display_name: '',
  description: '',
})

const rules = {
  name: [{ required: true, message: '请输入标识名', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
}

onMounted(loadData)

async function loadData() {
  const data = await getDepartments()
  departments.value = data.departments
}

function openDialog(row) {
  editing.value = row
  if (row) {
    form.name = row.name
    form.display_name = row.display_name
    form.description = row.description || ''
  } else {
    form.name = ''
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
        await updateDepartment(editing.value.id, {
          display_name: form.display_name,
          description: form.description,
        })
        ElMessage.success('更新成功')
      } else {
        await createDepartment(form)
        ElMessage.success('创建成功')
      }
      dialogVisible.value = false
      await loadData()
    } catch (e) {
      ElMessage.error(e.response?.data?.detail || '操作失败')
    }
  })
}

async function handleDelete(id) {
  try {
    await deleteDepartment(id)
    ElMessage.success('删除成功')
    await loadData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
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
</style>
