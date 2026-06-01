<template>
  <div class="admin-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>审计日志</h3>
            <p class="sub-text">查看系统操作记录</p>
          </div>
        </div>
      </template>

      <!-- 筛选器 -->
      <div class="filter-bar">
        <el-select v-model="filters.action" placeholder="操作类型" clearable size="default" style="width: 170px">
          <el-option v-for="a in allActions" :key="a.value" :label="a.label" :value="a.value" />
        </el-select>
        <el-input
          v-model="filters.username"
          placeholder="按用户名筛选"
          clearable
          style="width: 160px"
        />
        <el-button type="primary" @click="loadData">查询</el-button>
      </div>

      <el-table :data="logs" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="actionTagType(row.action)">{{ row.action_label || row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource" label="资源" width="100" />
        <el-table-column prop="detail" label="详情" min-width="250" show-overflow-tooltip />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-area">
        <el-pagination
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { getAuditLogs } from '../../api/admin'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

// 监听组织切换，自动刷新数据
watch(() => authStore.currentOrgId, () => {
  page.value = 1
  loadData()
})

const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const filters = reactive({
  action: '',
  username: '',
})

onMounted(loadData)

async function loadData() {
  const data = await getAuditLogs(page.value, pageSize.value, filters.action || '')
  logs.value = data.logs
  if (filters.username) {
    logs.value = logs.value.filter(l => l.username?.includes(filters.username))
  }
  total.value = data.total
}

function handlePageChange(p) {
  page.value = p
  loadData()
}

function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  loadData()
}

// 所有操作类型（供筛选下拉使用）
const allActions = [
  { label: '用户登录', value: 'login' },
  { label: '智能问答', value: 'ask_question' },
  { label: '上传文档', value: 'upload_document' },
  { label: '删除文档', value: 'delete_document' },
  { label: '重建知识库', value: 'rebuild_knowledge_base' },
  { label: '重建文件向量', value: 'rebuild_file_vectors' },
  { label: '删除文件向量', value: 'delete_file_vectors' },
  { label: '导入URL', value: 'import_url' },
  { label: '导出PDF报告', value: 'export_report_pdf' },
  { label: '导出文档ZIP', value: 'export_docs_zip' },
  { label: '数据分析', value: 'analyze_data' },
  { label: '合规检查', value: 'analyze_compliance' },
  { label: '创建用户', value: 'create_user' },
  { label: '修改用户角色', value: 'update_user_role' },
  { label: '修改用户组织', value: 'update_user_org' },
  { label: '变更用户状态', value: 'toggle_user_status' },
  { label: '修改用户部门', value: 'update_user_departments' },
  { label: '创建部门', value: 'create_department' },
  { label: '更新部门', value: 'update_department' },
  { label: '删除部门', value: 'delete_department' },
  { label: '创建组织', value: 'create_organization' },
  { label: '更新组织', value: 'update_organization' },
  { label: '禁用组织', value: 'delete_organization' },
  { label: '重生成邀请码', value: 'regenerate_invite_codes' },
  { label: '修改公司信息', value: 'update_my_org' },
  { label: '重生成用户邀请码', value: 'regenerate_user_invite_code' },
]

function actionTagType(action) {
  const map = {
    login: '',
    ask_question: 'success',
    upload_document: 'warning',
    delete_document: 'danger',
    rebuild_knowledge_base: 'info',
    rebuild_file_vectors: 'info',
    delete_file_vectors: 'danger',
    import_url: 'warning',
    export_report_pdf: '',
    export_docs_zip: '',
    analyze_data: 'success',
    analyze_compliance: 'warning',
    create_user: 'success',
    update_user_role: 'warning',
    update_user_org: 'warning',
    toggle_user_status: 'warning',
    update_user_departments: 'info',
    create_department: 'success',
    update_department: 'warning',
    delete_department: 'danger',
    create_organization: 'success',
    update_organization: 'warning',
    delete_organization: 'danger',
    regenerate_invite_codes: 'info',
    update_my_org: 'warning',
    regenerate_user_invite_code: 'info',
  }
  return map[action] || 'info'
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 19)
}
</script>

<style scoped>
.admin-page {
  /* full width */
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

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.pagination-area {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.time-text {
  font-size: 13px;
  color: #909399;
}
</style>
