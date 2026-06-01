<template>
  <div class="my-sessions">
    <el-card shadow="never">
      <template #header>
        <div>
          <h3>我的会话</h3>
          <p class="sub-text">查看和管理历史对话记录</p>
        </div>
      </template>

      <el-empty v-if="sessions.length === 0" description="暂无对话记录" />

      <div v-else class="sessions-grid">
        <el-card
          v-for="s in sessions"
          :key="s.session_id"
          shadow="hover"
          class="session-card"
        >
          <div class="card-top">
            <div class="dept-tags">
              <el-tag
                v-for="d in (s.departments || [s.department])"
                :key="d"
                size="small"
                :type="d === s.department ? 'primary' : 'info'"
              >{{ getDeptName(d) }}</el-tag>
            </div>
            <span class="time-text">{{ formatTime(s.created_at) }}</span>
          </div>
          <div class="card-body">
            <p class="session-title">{{ s.title || '未命名会话' }}</p>
            <p class="updated">最后活跃: {{ formatTime(s.updated_at) }}</p>
          </div>
          <div class="card-actions">
            <el-button size="small" type="primary" @click="viewSession(s)">查看对话</el-button>
            <el-button size="small" @click="handleRename(s)">重命名</el-button>
            <el-popconfirm
              title="确认删除此会话？"
              confirm-button-text="确定"
              cancel-button-text="取消"
              @confirm="handleDelete(s.session_id)"
            >
              <template #reference>
                <el-button size="small" type="danger" plain>删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 对话详情弹窗 -->
    <el-dialog v-model="showDetail" title="对话详情" width="640px">
      <div class="detail-list">
        <div v-for="(msg, idx) in detailMessages" :key="idx" class="detail-msg" :class="msg.role">
          <el-tag :type="msg.role === 'user' ? '' : 'success'" size="small" class="role-tag">
            {{ msg.role === 'user' ? '我' : 'AI' }}
          </el-tag>
          <span class="msg-content">{{ msg.content }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { listSessions, deleteSession, getSessionMessages, getDepartments, renameSession } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const authStore = useAuthStore()

const sessions = ref([])
const departments = ref([])
const showDetail = ref(false)
const detailMessages = ref([])

onMounted(async () => {
  const deptData = await getDepartments()
  departments.value = deptData.departments
  await loadSessions()
})

// 监听组织切换，自动刷新会话列表
watch(() => authStore.currentOrgId, async () => {
  const deptData = await getDepartments()
  departments.value = deptData.departments
  await loadSessions()
})

async function loadSessions() {
  const data = await listSessions()
  sessions.value = data.sessions
}

async function viewSession(s) {
  const data = await getSessionMessages(s.session_id)
  detailMessages.value = data.messages || []
  showDetail.value = true
}

async function handleDelete(id) {
  try {
    await deleteSession(id)
    ElMessage.success('已删除')
    await loadSessions()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function handleRename(s) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: s.title || '',
      inputPlaceholder: '输入会话名称（最多50字）',
      inputValidator: (val) => {
        if (!val || !val.trim()) return '名称不能为空'
        if (val.trim().length > 50) return '名称不能超过50字'
        return true
      }
    })
    await renameSession(s.session_id, value.trim())
    ElMessage.success('重命名成功')
    await loadSessions()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('重命名失败')
  }
}

function getDeptName(name) {
  const d = departments.value.find(x => x.name === name)
  return d?.display_name || name
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.my-sessions {
  /* full width */
}

.my-sessions h3 {
  margin: 0;
  font-size: 18px;
}

.sub-text {
  margin: 4px 0 0;
  color: #909399;
  font-size: 13px;
}

.sessions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.session-card {
  border-radius: 8px;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.dept-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.time-text {
  font-size: 12px;
  color: #909399;
}

.card-body {
  margin-bottom: 12px;
}

.session-id {
  font-size: 12px;
  color: #606266;
  margin: 0 0 4px;
}

.updated {
  font-size: 12px;
  color: #909399;
  margin: 0;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.detail-list {
  max-height: 500px;
  overflow-y: auto;
}

.detail-msg {
  padding: 10px 0;
  border-bottom: 1px solid #f2f6fc;
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.role-tag {
  flex-shrink: 0;
}

.msg-content {
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
}
</style>
