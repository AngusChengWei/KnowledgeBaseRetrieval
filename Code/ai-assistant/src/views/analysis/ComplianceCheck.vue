<template>
  <div class="analysis-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>文档合规检查</h3>
            <p class="sub-text">上传文档并与知识库中的制度规范进行合规性对比分析</p>
          </div>
        </div>
      </template>

      <!-- 上传区域 -->
      <div class="upload-area">
        <el-upload
          drag
          accept=".pdf,.docx,.doc,.txt,.md"
          :show-file-list="false"
          :before-upload="() => false"
          :on-change="handleFileSelect"
        >
          <el-icon class="upload-icon" :size="40"><UploadFilled /></el-icon>
          <div class="upload-text">
            <span>拖拽文件到此处，或 <em>点击选择文件</em></span>
          </div>
          <template #tip>
            <div class="upload-hint">支持 .pdf, .docx, .doc, .txt, .md 格式，文件大小不超过 10MB</div>
          </template>
        </el-upload>
      </div>

      <!-- 参数设置 -->
      <div class="params-area" v-if="selectedFile">
        <div class="selected-file-info">
          <el-icon><Document /></el-icon>
          <span>{{ selectedFile.name }}</span>
          <el-tag size="small">{{ formatSize(selectedFile.size) }}</el-tag>
          <el-button text type="danger" @click="clearFile">移除</el-button>
        </div>
        <div class="param-row">
          <span class="param-label">对照知识库：</span>
          <el-select v-model="selectedDepts" multiple collapse-tags style="width: 320px">
            <el-option
              v-for="d in departments"
              :key="d.name"
              :label="d.display_name"
              :value="d.name"
            />
          </el-select>
        </div>
        <div class="question-input">
          <el-input
            v-model="userNotes"
            placeholder="可选：补充检查要点，如「重点检查休假天数是否符合制度」"
            size="default"
            clearable
          />
        </div>
        <el-button type="primary" :loading="analyzing" :disabled="analyzing" size="large" @click="startAnalysis">
          <el-icon><MagicStick /></el-icon> 开始检查
        </el-button>
      </div>

      <!-- 加载状态 -->
      <div v-if="analyzing" class="analyzing-status">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在分析合规性，请稍候...</p>
      </div>

      <!-- 分析结果 -->
      <div v-if="result" class="result-area">
        <el-divider />
        <div class="result-header">
          <h4>合规检查报告</h4>
          <el-button size="small" @click="exportResultPdf" :disabled="exportingPdf">
            <el-icon><Download /></el-icon> 导出报告为 PDF
          </el-button>
        </div>

        <!-- 文档概览 -->
        <el-descriptions :column="3" border size="small" class="result-section">
          <el-descriptions-item label="文件名">{{ result.document_summary.filename }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">{{ formatSize(result.document_summary.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="知识库引用">
            <el-tag :type="result.document_summary.has_knowledge_base_reference ? 'success' : 'info'" size="small">
              {{ result.document_summary.has_knowledge_base_reference ? '已关联' : '未找到相关制度' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 引用的知识库来源 -->
        <div v-if="result.document_summary.knowledge_base_sources?.length" class="kb-sources">
          <span class="kb-sources-label">引用的知识库文档：</span>
          <el-tag
            v-for="src in result.document_summary.knowledge_base_sources"
            :key="src"
            size="small"
            type="primary"
            style="margin: 2px"
          >{{ src }}</el-tag>
        </div>

        <!-- 合规报告 -->
        <div class="compliance-report">
          <h4 class="section-title">AI 合规分析</h4>
          <div class="report-content" v-html="formatReport(result.compliance_report)"></div>
        </div>
      </div>

      <!-- 错误提示 -->
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        show-icon
        closable
        class="error-alert"
        @close="error = ''"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { uploadAnalysisFile, getAnalysisResult } from '../../api/analysis'
import { getDepartments, exportReportPdf } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document, MagicStick, Loading, Download } from '@element-plus/icons-vue'

const authStore = useAuthStore()

const selectedFile = ref(null)
const userNotes = ref('')
const analyzing = ref(false)
const result = ref(null)
const error = ref('')
const exportingPdf = ref(false)
const departments = ref([])
const selectedDepts = ref(['general'])

onMounted(async () => {
  await loadDepartments()
})

watch(() => authStore.currentOrgId, () => {
  loadDepartments()
})

async function loadDepartments() {
  try {
    const data = await getDepartments()
    departments.value = data.departments
  } catch (e) { /* silent */ }
}

function handleFileSelect(file) {
  const maxSize = 10 * 1024 * 1024
  if (file.raw.size > maxSize) {
    ElMessage.error('文件超过 10MB 限制')
    return
  }
  selectedFile.value = file.raw
  result.value = null
  error.value = ''
}

function clearFile() {
  selectedFile.value = null
  result.value = null
}

async function startAnalysis() {
  if (!selectedFile.value) return
  analyzing.value = true
  error.value = ''
  try {
    const data = await uploadAnalysisFile(selectedFile.value, 'compliance', selectedDepts.value.join(','), userNotes.value)
    const taskResult = await getAnalysisResult(data.task_id)
    if (taskResult.status === 'completed') {
      result.value = taskResult.result
      ElMessage.success('合规检查完成')
    } else {
      error.value = taskResult.error_message || '检查失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '检查请求失败，请检查网络连接'
  } finally {
    analyzing.value = false
  }
}

function formatReport(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

async function exportResultPdf() {
  if (!result.value) return
  exportingPdf.value = true
  try {
    const blob = await exportReportPdf({
      question: `文档合规检查 - ${result.value.document_summary.filename}`,
      answer: result.value.compliance_report || '无合规分析报告',
      sources: []
    })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `compliance_${result.value.document_summary.filename}_${new Date().toISOString().slice(0, 10)}.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    exportingPdf.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}
</script>

<style scoped>
.upload-area {
  margin-bottom: 16px;
}

.upload-icon {
  color: #c0c4cc;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}

.params-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
}

.selected-file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #ecf5ff;
  border-radius: 6px;
  font-size: 14px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-label {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}

.question-input {
  width: 100%;
}

.analyzing-status {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.analyzing-status p {
  margin-top: 12px;
}

.result-section {
  margin-bottom: 20px;
}

.section-title {
  margin: 20px 0 12px;
  font-size: 15px;
  color: #303133;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.result-header h4 {
  margin: 0;
  font-size: 16px;
}

.kb-sources {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.kb-sources-label {
  font-size: 13px;
  color: #606266;
}

.compliance-report {
  margin-top: 20px;
}

.report-content {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  line-height: 1.8;
  font-size: 14px;
  color: #303133;
}

.error-alert {
  margin-top: 16px;
}
</style>
