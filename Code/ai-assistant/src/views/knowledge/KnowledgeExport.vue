<template>
  <div class="kb-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>知识库文档导出</h3>
            <p class="sub-text">将知识库中的文档打包为压缩包 (ZIP) 下载</p>
          </div>
        </div>
      </template>

      <!-- 部门选择 -->
      <div class="dept-selector">
        <span style="font-size: 14px; color: #606266; margin-right: 10px;">选择知识库：</span>
        <el-select v-model="selectedDept" style="width: 200px" @change="loadDocs">
          <el-option
            v-for="d in departments"
            :key="d.name"
            :label="d.display_name"
            :value="d.name"
          />
        </el-select>
      </div>

     <el-empty v-if="documents.length === 0" description="该知识库暂无可导出的文档" />
      <p v-if="hasUrlEntries" class="url-hint">
        <el-icon><WarningFilled /></el-icon> 网页条目不支持导出为文件，已自动过滤
      </p>

      <template v-else>
        <div class="select-all-bar">
          <el-checkbox v-model="selectAll" :indeterminate="isIndeterminate" @change="handleSelectAll">
            全选
          </el-checkbox>
          <span class="selected-count">已选 {{ selectedFiles.length }} / {{ documents.length }} 个文档</span>
          <el-button type="primary" :disabled="selectedFiles.length === 0" :loading="exporting" @click="handleExport">
            <el-icon><Download /></el-icon> 导出选中（ZIP）
          </el-button>
          <el-button :disabled="exporting" @click="handleExportAll">
            <el-icon><Download /></el-icon> 导出全部（ZIP）
          </el-button>
        </div>

        <el-table :data="documents" stripe style="width: 100%" @selection-change="onSelectionChange">
          <el-table-column type="selection" width="50" />
          <el-table-column prop="filename" label="文件名" min-width="250" />
          <el-table-column label="大小" width="120">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { listDocuments, getDepartments, exportDocsZip } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { Download, WarningFilled } from '@element-plus/icons-vue'

const authStore = useAuthStore()

const departments = ref([])
const selectedDept = ref('general')
const documents = ref([])
const selectedFiles = ref([])
const exporting = ref(false)
const hasUrlEntries = ref(false)

const selectAll = ref(false)
const isIndeterminate = ref(false)

onMounted(async () => {
  await loadDepartments()
  await loadDocs()
})

watch(() => authStore.currentOrgId, () => {
  loadDepartments()
  loadDocs()
})

async function loadDepartments() {
  try {
    const data = await getDepartments()
    departments.value = data.departments
    if (data.departments.length > 0 && !data.departments.find(d => d.name === selectedDept.value)) {
      selectedDept.value = data.departments[0].name
    }
  } catch (e) { /* silent */ }
}

async function loadDocs() {
  selectedFiles.value = []
  selectAll.value = false
  isIndeterminate.value = false
  try {
    const data = await listDocuments(selectedDept.value)
    const totalBefore = data.documents.length
    documents.value = data.documents.filter(d => d.source_type !== 'url')
    hasUrlEntries.value = documents.value.length < totalBefore
  } catch (e) { /* silent */ }
}

function onSelectionChange(rows) {
  selectedFiles.value = rows.map(r => r.filename)
  const total = documents.value.length
  const selected = selectedFiles.value.length
  selectAll.value = total > 0 && selected === total
  isIndeterminate.value = selected > 0 && selected < total
}

function handleSelectAll(val) {
  if (val) {
    selectedFiles.value = documents.value.map(d => d.filename)
  } else {
    selectedFiles.value = []
  }
}

function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

async function handleExport() {
  if (selectedFiles.value.length === 0) return
  exporting.value = true
  try {
    const blob = await exportDocsZip({
      department: selectedDept.value,
      filenames: selectedFiles.value
    })
    downloadBlob(blob, `knowledge_${selectedDept.value}_${new Date().toISOString().slice(0, 10)}.zip`)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function handleExportAll() {
  exporting.value = true
  try {
    const blob = await exportDocsZip({
      department: selectedDept.value,
      filenames: []
    })
    downloadBlob(blob, `knowledge_${selectedDept.value}_${new Date().toISOString().slice(0, 10)}.zip`)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}
</script>

<style scoped>
.dept-selector {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.select-all-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  flex-wrap: wrap;
}

.selected-count {
  font-size: 13px;
  color: #909399;
  flex: 1;
  white-space: nowrap;
}

.url-hint {
  font-size: 13px;
  color: #e6a23c;
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .dept-selector {
    flex-direction: column;
    align-items: flex-start;
  }

  .dept-selector .el-select {
    width: 100% !important;
  }

  .select-all-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 12px;
  }

  .selected-count {
    width: 100%;
  }

  .select-all-bar .el-button {
    width: 100%;
  }

  :deep(.el-table) {
    font-size: 13px;
  }

  :deep(.el-table .el-table__cell) {
    padding: 8px 4px;
  }
}
</style>
