<template>
  <div class="kb-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>公司知识库</h3>
            <p class="sub-text">管理公司级公共知识库文档</p>
          </div>
          <div class="header-actions">
            <el-upload
              :show-file-list="false"
              :before-upload="() => false"
              :on-change="handleUpload"
              multiple
              accept=".pdf,.docx,.doc,.txt,.md,.xlsx,.xls"
            >
              <el-button type="primary" :loading="uploading">
                <el-icon><Upload /></el-icon> 上传文档
              </el-button>
            </el-upload>
            <el-button type="success" :loading="rebuilding" @click="handleRebuild">
              <el-icon><Refresh /></el-icon> 更新知识库
            </el-button>
            <el-button type="warning" plain @click="urlDialogVisible = true">
              <el-icon><Link /></el-icon> URL 导入
            </el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="documents.length === 0" description="暂无文档，请上传文件" />

      <template v-else>
        <el-table :data="pagedDocuments" stripe style="width: 100%">
          <el-table-column label="名称" min-width="300">
            <template #default="{ row }">
              <span v-if="row.source_type === 'url'" style="display:inline-flex;align-items:center;gap:4px">
                <el-tag size="small" type="warning">网页</el-tag>
                <el-tooltip :content="row.source_ref" placement="top">
                  <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:200px;display:inline-block">{{ row.display_title || row.filename }}</span>
                </el-tooltip>
                <el-button size="small" :icon="Edit" circle text @click="handleEditTitle(row)" />
                <el-button size="small" :icon="CopyDocument" circle text @click="handleCopyUrl(row.source_ref)" />
              </span>
              <span v-else>{{ row.filename }}</span>
            </template>
          </el-table-column>
          <el-table-column label="大小/块数" width="120">
            <template #default="{ row }">
              <span v-if="row.source_type === 'url'">{{ row.size }} 块</span>
              <span v-else>{{ formatSize(row.size) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="260">
            <template #default="{ row }">
              <div style="display:flex;align-items:center;flex-wrap:nowrap;gap:2px">
                <el-button v-if="row.source_type === 'url'" size="small" type="info" text
                  @click="handleViewContent(row)">
                  查看
                </el-button>
                <el-popconfirm
                  :title="row.source_type === 'url' ? '确认重新抓取并更新向量？' : '确认更新该文档的向量？'"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleRebuildFile(row)"
                >
                  <template #reference>
                    <el-button size="small" type="primary" text
                      :loading="updatingFiles.has(row.filename)">
                      更新向量
                    </el-button>
                  </template>
                </el-popconfirm>
                <el-popconfirm v-if="row.source_type !== 'url'"
                  :title="'确认删除 ' + row.filename + '？'"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleDelete(row.filename)"
                >
                  <template #reference>
                    <el-button size="small" type="danger" text>删除</el-button>
                  </template>
                </el-popconfirm>
                <el-popconfirm v-if="row.source_type === 'url'"
                  :title="'确认删除该网页知识？'"
                  confirm-button-text="确定"
                  cancel-button-text="取消"
                  @confirm="handleDeleteVectors(row.filename)"
                >
                  <template #reference>
                    <el-button size="small" type="danger" text>删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrap" v-if="documents.length > pageSize">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="documents.length"
            :page-size="pageSize"
            :current-page="currentPage"
            @current-change="currentPage = $event"
          />
        </div>
      </template>
    </el-card>
    <!-- URL 导入对话框 -->
    <el-dialog v-model="urlDialogVisible" title="URL 导入知识库" width="500px" class="responsive-dialog" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="URL">
          <el-input
            v-model="importUrlInput"
            placeholder="https://example.com/page"
            clearable
            @keyup.enter="handleImportUrl"
          />
        </el-form-item>
        <el-form-item>
          <el-alert type="info" :closable="false" style="width:100%">
            <template #default>
              支持 http/https 页面（含动态渲染页面），禁止内网地址。<br/>
              页面正文将自动抽取并写入知识库。
            </template>
          </el-alert>
        </el-form-item>
        <el-form-item>
          <el-alert type="warning" :closable="false" style="width:100%">
            <template #default>
              ⚠️ 请确保您有权使用该页面内容，导入内容仅限内部参考使用。
            </template>
          </el-alert>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="urlDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="handleImportUrl">
          导入
        </el-button>
      </template>
    </el-dialog>
    <!-- 查看内容对话框 -->
    <el-dialog v-model="contentDialogVisible" :title="contentDialogTitle" width="700px" class="responsive-dialog" :close-on-click-modal="true">
      <div v-if="contentLoading" style="text-align:center;padding:40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else style="max-height:60vh;overflow-y:auto;white-space:pre-wrap;font-size:13px;line-height:1.7;padding:8px;background:#f9f9f9;border-radius:6px">
        {{ contentDialogText }}
      </div>
      <template #footer>
        <el-tag>{{ contentDialogChunks }} 个文本块</el-tag>
        <el-button @click="contentDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
    <!-- 编辑标题对话框 -->
    <el-dialog v-model="titleDialogVisible" title="修改标题" width="450px" class="responsive-dialog" :close-on-click-modal="false">
      <el-input v-model="titleEditInput" placeholder="请输入新标题" clearable @keyup.enter="handleSaveTitle" />
      <template #footer>
        <el-button @click="titleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="titleSaving" @click="handleSaveTitle">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { uploadDocuments, listDocuments, deleteDocument, rebuildKnowledgeBase, rebuildFileVectors, deleteFileVectors, importUrl, getDocumentContent, updateDocumentTitle } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { Upload, Refresh, Link, CopyDocument, Loading, Edit } from '@element-plus/icons-vue'

const authStore = useAuthStore()

// 监听组织切换，自动刷新文档列表
watch(() => authStore.currentOrgId, () => {
  loadDocs()
})

const department = 'general'
const documents = ref([])
const uploading = ref(false)
const rebuilding = ref(false)
const currentPage = ref(1)
const pageSize = 15
const updatingFiles = ref(new Set())
const removingFiles = ref(new Set())
const urlDialogVisible = ref(false)
const importUrlInput = ref('')
const importing = ref(false)
const contentDialogVisible = ref(false)
const contentDialogTitle = ref('')
const contentDialogText = ref('')
const contentDialogChunks = ref(0)
const contentLoading = ref(false)
const titleDialogVisible = ref(false)
const titleEditInput = ref('')
const titleEditFilename = ref('')
const titleSaving = ref(false)

const pagedDocuments = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return documents.value.slice(start, start + pageSize)
})

onMounted(() => loadDocs())

async function loadDocs() {
  currentPage.value = 1
  documents.value = []
  try {
    const data = await listDocuments(department)
    documents.value = data.documents
  } catch (e) { /* silent */ }
}

async function handleUpload(file) {
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.raw.size > maxSize) {
    ElMessage.error(`文件 ${file.name} 超过 10MB 限制，请压缩后重试`)
    return
  }
  uploading.value = true
  try {
    const data = await uploadDocuments([file.raw], department)
    if (data.uploaded_files.length) ElMessage.success(`成功上传 ${data.uploaded_files.length} 个文件`)
    if (data.failed_files.length) ElMessage.warning(`失败: ${data.failed_files.join(', ')}`)
    await loadDocs()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败，请检查网络或文件格式')
  } finally {
    uploading.value = false
  }
}

async function handleRebuild() {
  rebuilding.value = true
  try {
    const data = await rebuildKnowledgeBase(department)
    ElMessage.success(`知识库更新成功！${data.doc_count} 个文档，${data.chunk_count} 个文本块`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    rebuilding.value = false
  }
}

async function handleDelete(filename) {
  try {
    await deleteDocument(filename, department)
    ElMessage.success(`已删除 ${filename}`)
    await loadDocs()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function handleImportUrl() {
  if (!importUrlInput.value.trim()) {
    ElMessage.warning('请输入 URL')
    return
  }
  importing.value = true
  try {
    const data = await importUrl(importUrlInput.value.trim(), department)
    ElMessage.success(`导入成功！「${data.title}」共 ${data.chunk_count} 个文本块`)
    importUrlInput.value = ''
    urlDialogVisible.value = false
    await loadDocs()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'URL 导入失败')
  } finally {
    importing.value = false
  }
}

async function handleRebuildFile(row) {
  const filename = row.filename
  updatingFiles.value.add(filename)
  updatingFiles.value = new Set(updatingFiles.value)
  try {
    let data
    if (row.source_type === 'url') {
      data = await importUrl(row.source_ref || filename, department)
    } else {
      data = await rebuildFileVectors(filename, department)
    }
    ElMessage.success(`向量更新成功，共 ${data.chunk_count} 个文本块`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '向量更新失败')
  } finally {
    updatingFiles.value.delete(filename)
    updatingFiles.value = new Set(updatingFiles.value)
  }
}

async function handleDeleteVectors(filename) {
  removingFiles.value.add(filename)
  removingFiles.value = new Set(removingFiles.value)
  try {
    await deleteFileVectors(filename, department)
    ElMessage.success('已删除')
    await loadDocs()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  } finally {
    removingFiles.value.delete(filename)
    removingFiles.value = new Set(removingFiles.value)
  }
}

function handleCopyUrl(url) {
  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('链接已复制')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

async function handleViewContent(row) {
  contentDialogTitle.value = row.display_title || row.filename
  contentDialogVisible.value = true
  contentLoading.value = true
  contentDialogText.value = ''
  contentDialogChunks.value = 0
  try {
    const data = await getDocumentContent(row.filename, department)
    contentDialogText.value = data.content
    contentDialogChunks.value = data.chunk_count
  } catch (e) {
    contentDialogText.value = '加载失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    contentLoading.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}

function handleEditTitle(row) {
  titleEditFilename.value = row.filename
  titleEditInput.value = row.display_title || ''
  titleDialogVisible.value = true
}

async function handleSaveTitle() {
  if (!titleEditInput.value.trim()) {
    ElMessage.warning('标题不能为空')
    return
  }
  titleSaving.value = true
  try {
    await updateDocumentTitle(titleEditFilename.value, titleEditInput.value.trim(), department)
    ElMessage.success('标题已更新')
    titleDialogVisible.value = false
    await loadDocs()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  } finally {
    titleSaving.value = false
  }
}
</script>

<style scoped>
.kb-page {
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

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .header-actions {
    width: 100%;
    gap: 8px;
  }

  :deep(.el-table) {
    font-size: 13px;
  }

  :deep(.el-table .el-table__cell) {
    padding: 8px 4px;
  }

  :deep(.responsive-dialog) {
    --el-dialog-width: 92vw !important;
    width: 92vw !important;
    margin: 0 auto;
  }
}
</style>
