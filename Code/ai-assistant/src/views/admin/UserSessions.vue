<template>
  <div class="admin-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <h3>用户会话</h3>
            <p class="sub-text">查看所有用户的历史对话记录</p>
          </div>
          <el-select
            v-model="filterUserId"
            placeholder="按用户筛选"
            clearable
            style="width: 180px"
            @change="loadSessions"
          >
            <el-option
              v-for="u in allUsers"
              :key="u.id"
              :label="u.username"
              :value="u.id"
            />
          </el-select>
        </div>
      </template>

      <el-table :data="sessions" stripe style="width: 100%">
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column prop="department" label="知识库" min-width="180">
          <template #default="{ row }">
            <div class="dept-tags">
              <el-tag
                v-for="d in (row.departments || [row.department])"
                :key="d"
                size="small"
                :type="d === row.department ? '' : 'info'"
              >{{ getDeptName(d) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_deleted" type="info" size="small">已删除</el-tag>
            <el-tag v-else type="success" size="small">正常</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最后活跃" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作">
          <template #default="{ row }">
            <el-button type="primary" text size="small" @click="viewMessages(row)">
              查看对话
            </el-button>
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

    <!-- 会话消息弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="700px"
      top="5vh"
    >
      <div class="messages-container">
        <el-empty v-if="messages.length === 0" description="暂无消息记录" />
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="msg-row"
          :class="msg.role"
        >
          <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="msg-bubble">
            <div class="msg-text" v-html="formatMsg(msg.content)"></div>
            <div v-if="msg.sources && msg.sources.length" class="msg-sources">
              <span class="source-label">参考来源：</span>
              <span v-for="(src, i) in msg.sources" :key="i" class="source-tag">
                {{ src.filename }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { getUsers, getAdminSessions, getAdminSessionMessages } from '../../api/admin'
import { getDepartments } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()

// 监听组织切换，自动刷新数据
watch(() => authStore.currentOrgId, () => {
  filterUserId.value = ''
  loadUsers()
  loadSessions()
})

const sessions = ref([])
const allUsers = ref([])
const departments = ref([])
const filterUserId = ref('')
const dialogVisible = ref(false)
const dialogTitle = ref('')
const messages = ref([])
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

onMounted(async () => {
  await loadDepartments()
  await loadUsers()
  await loadSessions()
})

async function loadDepartments() {
  try {
    const data = await getDepartments()
    departments.value = data.departments
  } catch (e) { /* silent */ }
}

async function loadUsers() {
  try {
    const data = await getUsers()
    allUsers.value = data.users
  } catch (e) {
    ElMessage.error('加载用户列表失败')
  }
}

async function loadSessions() {
  try {
    const data = await getAdminSessions(filterUserId.value, page.value, pageSize.value)
    sessions.value = data.sessions
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载会话列表失败')
  }
}

function handleSizeChange(size) {
  pageSize.value = size
  page.value = 1
  loadSessions()
}

function handlePageChange(p) {
  page.value = p
  loadSessions()
}

async function viewMessages(session) {
  try {
    const data = await getAdminSessionMessages(session.session_id)
    messages.value = data.messages
    dialogTitle.value = `${session.username} 的对话 (${getDeptName(session.department)})`
    dialogVisible.value = true
  } catch (e) {
    ElMessage.error('加载消息失败')
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

function formatMsg(content) {
  if (!content) return ''
  return content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
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

.time-text {
  font-size: 13px;
  color: #909399;
}

.dept-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.messages-container {
  max-height: 60vh;
  overflow-y: auto;
  padding: 12px 0;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  font-size: 22px;
  flex-shrink: 0;
}

.msg-bubble {
  max-width: 75%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.msg-row.user .msg-bubble {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg-row.assistant .msg-bubble {
  background: #f4f4f5;
  color: #303133;
  border-bottom-left-radius: 4px;
}

.msg-sources {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.source-tag {
  background: rgba(255,255,255,0.2);
  padding: 2px 6px;
  border-radius: 3px;
  margin-left: 4px;
}

.msg-row.assistant .source-tag {
  background: #e4e7ed;
}
</style>
