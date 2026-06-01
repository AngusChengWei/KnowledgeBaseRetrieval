<template>
  <div class="smart-qa">
    <!-- 左侧会话列表 -->
    <aside class="session-panel">
      <div class="session-header">
        <span class="session-title">对话列表</span>
        <el-button type="primary" size="small" @click="handleNewChat">
          <el-icon><Plus /></el-icon> 新对话
        </el-button>
      </div>
      <div class="session-list">
        <el-empty v-if="sessions.length === 0" description="暂无对话" :image-size="60" />
        <div
          v-for="s in sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: s.session_id === currentSessionId }"
          @click="switchSession(s)"
          @dblclick.stop="startRename(s)"
        >
          <div class="session-top-row">
            <span class="session-name" v-if="renamingId !== s.session_id">
              {{ s.title || '新对话' }}
            </span>
            <input
              v-else
              v-model="renameText"
              class="rename-input"
              @blur="confirmRename(s)"
              @keyup.enter="confirmRename(s)"
              @keyup.escape="cancelRename"
              @click.stop
            />
            <el-button
              :icon="Close"
              size="small"
              text
              class="del-btn"
              @click.stop="handleDeleteSession(s.session_id)"
            />
          </div>
          <div class="session-tags">
            <el-tag
              v-for="d in (s.departments || [s.department])"
              :key="d"
              size="small"
              :type="d === s.department ? '' : 'info'"
              class="dept-tag"
            >{{ getDeptName(d) }}</el-tag>
          </div>
          <div class="session-time">{{ formatTime(s.updated_at) }}</div>
        </div>
      </div>
    </aside>

    <!-- 右侧对话区 -->
    <div class="chat-area">
      <!-- 部门选择 -->
      <div class="chat-toolbar">
        <el-button class="mobile-session-btn" text @click="mobileSessionDrawer = true">
          <el-icon><ChatDotRound /></el-icon>
        </el-button>
        <el-button class="mobile-new-btn" type="primary" size="small" @click="handleNewChat">
          <el-icon><Plus /></el-icon> 新对话
        </el-button>
        <span class="toolbar-label">知识库：</span>
        <el-select v-model="currentDepartment" size="default" style="width: 180px">
          <el-option
            v-for="d in departments"
            :key="d.name"
            :label="d.display_name"
            :value="d.name"
          />
        </el-select>
      </div>

      <!-- 消息列表 -->
      <div class="messages" ref="messagesRef">
        <div v-if="messages.length === 0" class="welcome">
          <el-icon :size="48" color="#909399"><ChatDotRound /></el-icon>
          <h2>欢迎使用 AI 知识助手</h2>
          <p>选择知识库并输入问题开始对话</p>
        </div>
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
              <div class="sources-toggle" @click="msg._expanded = !msg._expanded">
                <el-icon><ArrowRight v-if="!msg._expanded" /><ArrowDown v-else /></el-icon>
                参考来源 ({{ msg.sources.length }})
              </div>
              <el-collapse-transition>
                <div v-show="msg._expanded" class="sources-body">
                  <div v-for="(src, i) in msg.sources" :key="i" class="source-item">
                    <strong>{{ src.filename }}</strong>
                    <p>{{ src.chunk }}</p>
                  </div>
                </div>
              </el-collapse-transition>
            </div>
            <div v-if="msg.role === 'assistant' && msg.content" class="msg-actions">
              <el-button
                size="small"
                text
                type="primary"
                :icon="Document"
                @click="exportMsgAsPdf(msg)"
              >
                导出PDF
              </el-button>
            </div>
          </div>
        </div>
        <div v-if="loading" class="msg-row assistant">
          <div class="msg-avatar">🤖</div>
          <div class="msg-bubble typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

      <!-- 输入框 -->
      <div class="input-bar">
        <el-input
          v-model="inputText"
          placeholder="输入您的问题..."
          :disabled="loading"
          size="large"
          @keyup.enter="handleSend"
        />
        <el-button
          type="primary"
          size="large"
          :disabled="loading || !inputText.trim()"
          :loading="loading"
          @click="handleSend"
        >
          发送
        </el-button>
      </div>
    </div>

    <!-- 移动端会话抽屉 -->
    <el-drawer
      v-model="mobileSessionDrawer"
      direction="ltr"
      size="280px"
      :show-close="false"
      class="mobile-session-drawer"
    >
      <div class="session-header">
        <span class="session-title">对话列表</span>
        <el-button type="primary" size="small" @click="handleNewChat(); mobileSessionDrawer = false">
          <el-icon><Plus /></el-icon> 新对话
        </el-button>
      </div>
      <div class="session-list">
        <el-empty v-if="sessions.length === 0" description="暂无对话" :image-size="60" />
        <div
          v-for="s in sessions"
          :key="'m_' + s.session_id"
          class="session-item"
          :class="{ active: s.session_id === currentSessionId }"
          @click="switchSession(s); mobileSessionDrawer = false"
        >
          <div class="session-top-row">
            <span class="session-name">{{ s.title || '新对话' }}</span>
            <el-button
              :icon="Close"
              size="small"
              text
              class="del-btn"
              @click.stop="handleDeleteSession(s.session_id)"
            />
          </div>
          <div class="session-tags">
            <el-tag
              v-for="d in (s.departments || [s.department])"
              :key="d"
              size="small"
              :type="d === s.department ? '' : 'info'"
              class="dept-tag"
            >{{ getDeptName(d) }}</el-tag>
          </div>
          <div class="session-time">{{ formatTime(s.updated_at) }}</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { createSession, listSessions, deleteSession, getSessionMessages, askQuestion, getDepartments, renameSession, exportReportPdf } from '../../api/chat'
import { useAuthStore } from '../../stores/auth'
import { ElMessage } from 'element-plus'
import { Plus, Close, ChatDotRound, ArrowRight, ArrowDown, Document } from '@element-plus/icons-vue'

const authStore = useAuthStore()

const sessions = ref([])
const messages = ref([])
const departments = ref([])
const currentSessionId = ref('')
const currentDepartment = ref('general')
const inputText = ref('')
const loading = ref(false)
const messagesRef = ref(null)
const renamingId = ref('')
const renameText = ref('')
const mobileSessionDrawer = ref(false)

onMounted(async () => {
  await loadDepartments()
  await loadSessions()
})

// 监听组织切换，自动刷新部门列表和会话
watch(() => authStore.currentOrgId, async () => {
  await loadDepartments()
  await loadSessions()
  // 清空当前会话内容
  currentSessionId.value = ''
  messages.value = []
})

async function loadDepartments() {
  try {
    const data = await getDepartments()
    departments.value = data.departments
    if (data.departments.length > 0) {
      currentDepartment.value = data.departments[0].name
    }
  } catch (e) { /* silent */ }
}

async function loadSessions() {
  try {
    const data = await listSessions()
    sessions.value = data.sessions
  } catch (e) { /* silent */ }
}

async function handleNewChat() {
  try {
    const data = await createSession(currentDepartment.value)
    currentSessionId.value = data.session_id
    messages.value = []
    await loadSessions()
  } catch (e) { /* silent */ }
}

async function switchSession(s) {
  currentSessionId.value = s.session_id
  currentDepartment.value = s.department
  try {
    const data = await getSessionMessages(s.session_id)
    messages.value = (data.messages || []).map(m => ({ ...m, _expanded: false }))
    scrollBottom()
  } catch (e) { /* silent */ }
}

async function handleDeleteSession(id) {
  try {
    await deleteSession(id)
    if (currentSessionId.value === id) {
      currentSessionId.value = ''
      messages.value = []
    }
    await loadSessions()
  } catch (e) { /* silent */ }
}

function startRename(s) {
  renamingId.value = s.session_id
  renameText.value = s.title || getDeptName(s.department)
  nextTick(() => {
    const inputs = document.querySelectorAll('.rename-input')
    if (inputs.length > 0) inputs[inputs.length - 1].focus()
  })
}

async function confirmRename(s) {
  const title = renameText.value.trim()
  if (title && title !== (s.title || getDeptName(s.department))) {
    try {
      await renameSession(s.session_id, title)
      s.title = title
    } catch (e) { /* silent */ }
  }
  renamingId.value = ''
}

function cancelRename() {
  renamingId.value = ''
}

async function handleSend() {
  const q = inputText.value.trim()
  if (!q || loading.value) return

  if (!currentSessionId.value) {
    await handleNewChat()
  }

  messages.value.push({ role: 'user', content: q, sources: [] })
  inputText.value = ''
  loading.value = true
  scrollBottom()

  try {
    const data = await askQuestion(currentSessionId.value, q, currentDepartment.value)
    messages.value.push({
      role: 'assistant',
      content: data.answer,
      sources: data.sources || [],
      _expanded: false
    })
    await loadSessions()
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `抱歉，出现错误：${e.response?.data?.detail || '请求失败'}`,
      sources: []
    })
  } finally {
    loading.value = false
    scrollBottom()
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

function formatMsg(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

async function scrollBottom() {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

async function exportMsgAsPdf(msg) {
  try {
    const blob = await exportReportPdf({
      session_id: currentSessionId.value,
      question: findUserQuestion(msg),
      answer: msg.content,
      sources: msg.sources || []
    })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `report_${new Date().toISOString().slice(0, 10)}.pdf`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出PDF失败')
  }
}

function findUserQuestion(assistantMsg) {
  const idx = messages.value.indexOf(assistantMsg)
  // 查找该 AI 回答前的最近一条用户消息
  for (let i = idx - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      return messages.value[i].content
    }
  }
  return ''
}
</script>

<style scoped>
.smart-qa {
  display: flex;
  height: calc(100vh - 104px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}

.session-panel {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.session-header {
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e4e7ed;
}

.session-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.session-item:hover { background: #e4e7ed; }
.session-item.active { background: #ecf5ff; }

.session-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.session-name {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.session-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.dept-tag {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rename-input {
  font-size: 13px;
  border: 1px solid #409eff;
  border-radius: 4px;
  padding: 2px 6px;
  outline: none;
  flex: 1;
  min-width: 0;
  box-sizing: border-box;
}

.session-time {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.del-btn {
  color: #909399 !important;
  flex-shrink: 0;
}
.del-btn:hover {
  color: #f56c6c !important;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-toolbar {
  padding: 12px 20px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.toolbar-label {
  font-size: 13px;
  color: #606266;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome {
  text-align: center;
  padding: 80px 20px;
  color: #909399;
}

.welcome h2 {
  font-size: 20px;
  color: #303133;
  margin: 16px 0 8px;
}

.welcome p {
  margin: 0;
  font-size: 14px;
}

.msg-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  font-size: 24px;
  flex-shrink: 0;
}

.msg-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 12px;
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
  margin-top: 10px;
  border-top: 1px solid #dcdfe6;
  padding-top: 8px;
}

.sources-toggle {
  font-size: 12px;
  color: #909399;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}

.sources-toggle:hover { color: #409eff; }

.sources-body {
  margin-top: 8px;
}

.source-item {
  font-size: 12px;
  padding: 6px 8px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 4px;
  border: 1px solid #ebeef5;
}

.source-item strong {
  color: #409eff;
}

.source-item p {
  margin: 4px 0 0;
  color: #909399;
}

.msg-actions {
  margin-top: 8px;
  border-top: 1px dashed #dcdfe6;
  padding-top: 6px;
  display: flex;
  justify-content: flex-end;
}

.typing span {
  display: inline-block;
  width: 8px;
  height: 8px;
  background: #c0c4cc;
  border-radius: 50%;
  margin: 0 2px;
  animation: bounce 1.2s infinite;
}

.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.input-bar {
  padding: 16px 20px;
  border-top: 1px solid #e4e7ed;
  display: flex;
  gap: 10px;
}

/* 移动端按钮默认隐藏 */
.mobile-session-btn,
.mobile-new-btn {
  display: none;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .smart-qa {
    height: calc(100vh - 60px);
    border-radius: 0;
    box-shadow: none;
  }

  .session-panel {
    display: none;
  }

  .mobile-session-btn,
  .mobile-new-btn {
    display: inline-flex;
  }

  .chat-toolbar {
    padding: 10px 12px;
  }

  .messages {
    padding: 12px;
  }

  .welcome {
    padding: 40px 16px;
  }

  .welcome h2 {
    font-size: 18px;
  }

  .msg-bubble {
    max-width: 85%;
    padding: 10px 12px;
    font-size: 14px;
  }

  .msg-avatar {
    font-size: 20px;
  }

  .msg-row {
    gap: 8px;
    margin-bottom: 14px;
  }

  .input-bar {
    padding: 10px 12px;
    gap: 8px;
  }

  .source-item p {
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }
}
</style>
