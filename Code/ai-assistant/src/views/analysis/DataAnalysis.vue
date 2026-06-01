<template>
  <div class="analysis-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>数据文件校验</h3>
            <p class="sub-text">上传 Excel 或 CSV 文件，AI 自动分析数据质量、缺失值、异常值等</p>
          </div>
        </div>
      </template>

      <!-- 上传区域 -->
      <div class="upload-area">
        <el-upload
          drag
          accept=".xlsx,.xls,.csv"
          :show-file-list="false"
          :before-upload="() => false"
          :on-change="handleFileSelect"
        >
          <el-icon class="upload-icon" :size="40"><UploadFilled /></el-icon>
          <div class="upload-text">
            <span>拖拽文件到此处，或 <em>点击选择文件</em></span>
          </div>
          <template #tip>
            <div class="upload-hint">支持 .xlsx, .xls, .csv 格式，文件大小不超过 10MB</div>
          </template>
        </el-upload>
      </div>

      <!-- 分析参数 -->
      <div class="params-area" v-if="selectedFile">
        <div class="selected-file-info">
          <el-icon><Document /></el-icon>
          <span>{{ selectedFile.name }}</span>
          <el-tag size="small">{{ formatSize(selectedFile.size) }}</el-tag>
          <el-button text type="danger" @click="clearFile">移除</el-button>
        </div>
        <div class="param-row">
          <span class="param-label">关联知识库：</span>
          <el-select v-model="selectedDepts" multiple collapse-tags style="width: 320px" placeholder="选填，用于 AI 分析的业务上下文">
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
            v-model="userQuestion"
            placeholder="可选：输入分析重点，如「检查金额列是否有负数」「确认日期格式是否正确」"
            size="default"
            clearable
          />
        </div>
        <el-button type="primary" :loading="analyzing" :disabled="analyzing" size="large" @click="startAnalysis">
          <el-icon><MagicStick /></el-icon> 开始分析
        </el-button>
      </div>

      <!-- 加载状态 -->
      <div v-if="analyzing" class="analyzing-status">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p>正在分析文件，请稍候...</p>
      </div>

      <!-- 分析结果 -->
      <div v-if="result" class="result-area">
        <el-divider />
        <div class="result-header">
          <h4>分析结果</h4>
          <el-button size="small" @click="exportResultPdf" :disabled="exportingPdf">
            <el-icon><Download /></el-icon> 导出报告为 PDF
          </el-button>
        </div>

        <!-- 概览 -->
        <el-descriptions :column="3" border size="small" class="result-section">
          <el-descriptions-item label="文件名">{{ result.summary.filename }}</el-descriptions-item>
          <el-descriptions-item label="行数">{{ result.summary.rows }}</el-descriptions-item>
          <el-descriptions-item label="列数">{{ result.summary.columns }}</el-descriptions-item>
          <el-descriptions-item label="缺失值">
            <el-tag :type="result.missing_values.has_missing ? 'warning' : 'success'" size="small">
              {{ result.missing_values.total_missing_cells || 0 }} 个
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="重复行">
            <el-tag :type="result.duplicates.has_duplicates ? 'warning' : 'success'" size="small">
              {{ result.duplicates.duplicate_rows || 0 }} 行
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="异常值">
            <el-tag :type="result.outliers.has_outliers ? 'danger' : 'success'" size="small">
              {{ result.outliers.columns_with_outliers?.length || 0 }} 列
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 列分析 -->
        <h4 class="section-title">列详情</h4>
        <el-table :data="result.columns" stripe size="small" max-height="400">
          <el-table-column prop="name" label="列名" min-width="120" fixed />
          <el-table-column prop="dtype" label="类型" width="100" />
          <el-table-column label="非空" width="80">
            <template #default="{ row }">{{ row.non_null_count }}</template>
          </el-table-column>
          <el-table-column label="缺失" width="80">
            <template #default="{ row }">
              <span v-if="row.null_count > 0" style="color: #e6a23c">{{ row.null_count }}</span>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="最小值" width="100">
            <template #default="{ row }">{{ row.min ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="最大值" width="100">
            <template #default="{ row }">{{ row.max ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="均值" width="100">
            <template #default="{ row }">{{ row.mean ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="异常值" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.outlier_count > 0" type="danger" size="small">{{ row.outlier_count }}</el-tag>
              <span v-else>0</span>
            </template>
          </el-table-column>
          <el-table-column label="唯一值" width="80">
            <template #default="{ row }">{{ row.unique_count ?? '-' }}</template>
          </el-table-column>
        </el-table>

        <!-- AI 分析报告 -->
        <div v-if="result.ai_report" class="ai-report">
          <h4 class="section-title">AI 分析报告</h4>
          <div class="report-content" v-html="formatReport(result.ai_report)"></div>
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
import { ref, onMounted } from 'vue'
import { uploadAnalysisFile, getAnalysisResult } from '../../api/analysis'
import { getDepartments, exportReportPdf } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document, MagicStick, Loading, Download } from '@element-plus/icons-vue'

const authStore = useAuthStore()

const selectedFile = ref(null)
const userQuestion = ref('')
const analyzing = ref(false)
const result = ref(null)
const error = ref('')
const exportingPdf = ref(false)
const departments = ref([])
const selectedDepts = ref([])

onMounted(async () => {
  try {
    const data = await getDepartments()
    departments.value = data.departments
  } catch (e) { /* silent */ }
})

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
    const depts = selectedDepts.value.length ? selectedDepts.value.join(',') : ''
    const data = await uploadAnalysisFile(selectedFile.value, 'data', depts, userQuestion.value)
    // 获取结果
    const taskResult = await getAnalysisResult(data.task_id)
    if (taskResult.status === 'completed') {
      result.value = taskResult.result
      ElMessage.success('分析完成')
    } else {
      error.value = taskResult.error_message || '分析失败'
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '分析请求失败，请检查网络连接'
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
    const reportContent = result.value.ai_report || '无 AI 分析报告'
    const blob = await exportReportPdf({
      question: userQuestion.value || result.value.summary.filename,
      answer: reportContent,
      sources: []
    })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `analysis_${result.value.summary.filename}_${new Date().toISOString().slice(0, 10)}.pdf`
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

.ai-report {
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
