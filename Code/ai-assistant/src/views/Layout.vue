<template>
  <el-container class="layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapsed ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <h1 v-show="!isCollapsed" class="logo-text">AI 知识助手</h1>
        <h1 v-show="isCollapsed" class="logo-text">AI</h1>
        <!-- 收缩按钮 -->
        <div class="collapse-btn" @click="isCollapsed = !isCollapsed">
          <el-icon :size="18">
            <Expand v-if="isCollapsed" />
            <Fold v-else />
          </el-icon>
        </div>
      </div>
      <el-menu
        :default-active="currentRoute"
        class="sidebar-menu"
        background-color="#1a1a2e"
        text-color="rgba(255,255,255,0.7)"
        active-text-color="#409EFF"
        :collapse="isCollapsed"
        router
      >
        <el-menu-item-group v-for="group in menuGroups" :key="group.title">
          <template #title>
            <span v-show="!isCollapsed">{{ group.title }}</span>
          </template>
          <el-menu-item
            v-for="item in group.items"
            :key="item.key"
            :index="'/' + item.key"
          >
            <el-icon><component :is="iconMap[item.icon]" /></el-icon>
            <template #title>{{ item.label }}</template>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <!-- 顶栏 -->
      <el-header class="topbar">
        <div class="topbar-left">
          <!-- 移动端菜单按钮 -->
          <el-button class="mobile-menu-btn" text @click="mobileDrawer = true">
            <el-icon :size="20"><Operation /></el-icon>
          </el-button>
          <span class="page-title">{{ currentPageTitle }}</span>
        </div>
        <div class="topbar-right">
          <!-- 超管组织切换器 -->
          <el-select
            v-if="authStore.isSuperAdmin && orgList.length > 0"
            v-model="selectedOrgId"
            placeholder="切换组织"
            size="small"
            style="width: 160px"
            @change="handleOrgSwitch"
          >
            <el-option
              v-for="org in orgList"
              :key="org.id"
              :label="org.display_name"
              :value="org.id"
            />
          </el-select>
          <el-tag :type="roleTagType" size="small" effect="dark">{{ roleLabel }}</el-tag>
          <span class="user-name">{{ authStore.user?.username }}</span>
          <el-button text @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <!-- 页面内容 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

    <!-- 移动端侧边栏抽屉 -->
    <el-drawer
      v-model="mobileDrawer"
      direction="ltr"
      size="240px"
      :show-close="false"
      class="mobile-drawer"
    >
      <div class="drawer-logo">AI 知识助手</div>
      <el-menu
        :default-active="currentRoute"
        background-color="#fff"
        text-color="#303133"
        active-text-color="#409EFF"
        router
        @select="mobileDrawer = false"
      >
        <el-menu-item-group v-for="group in menuGroups" :key="group.title">
          <template #title>{{ group.title }}</template>
          <el-menu-item
            v-for="item in group.items"
            :key="item.key"
            :index="'/' + item.key"
          >
            <el-icon><component :is="iconMap[item.icon]" /></el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-drawer>

    <!-- 悬浮机器人按钮（非 smart-qa 页面显示） -->
    <div
      v-if="route.meta.menuKey !== 'smart-qa'"
      class="float-robot"
      :style="{ left: floatPos.x + 'px', top: floatPos.y + 'px' }"
      @mousedown="startDrag"
      @touchstart.prevent="startDrag"
      @click="goSmartQA"
    >
      <el-icon :size="26"><ChatDotRound /></el-icon>
    </div>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { getOrganizations } from '../api/admin'
import { ElMessageBox } from 'element-plus'
import {
  ChatDotRound,
  Document,
  Reading,
  FolderOpened,
  User,
  OfficeBuilding,
  Lock,
  Fold,
  Expand,
  Operation,
  School,
  Upload,
  DataAnalysis,
  List
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCollapsed = ref(false)
const mobileDrawer = ref(false)
const orgList = ref([])
const selectedOrgId = ref(null)

// 超管加载组织列表
onMounted(async () => {
  if (authStore.isSuperAdmin) {
    try {
      const data = await getOrganizations()
      orgList.value = data.organizations || []
      selectedOrgId.value = authStore.currentOrgId
      // 页面刷新后补充 orgCode
      const matched = orgList.value.find(o => o.id === authStore.currentOrgId)
      if (matched && !authStore.currentOrgCode) {
        authStore.switchOrg(matched.id, matched.code)
      }
    } catch (e) { /* ignore */ }
  }
})

function handleOrgSwitch(orgId) {
  const org = orgList.value.find(o => o.id === orgId)
  if (org) {
    authStore.switchOrg(org.id, org.code)
  }
}

const iconMap = {
  chat: ChatDotRound,
  history: Document,
  book: Reading,
  folder: FolderOpened,
  users: User,
  building: OfficeBuilding,
  shield: Lock,
  office: School,
  upload: Upload,
  analysis: DataAnalysis,
  list: List,
}

const roleLabels = {
  super_admin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

const roleLabel = computed(() => roleLabels[authStore.user?.role] || '用户')
const roleTagType = computed(() => {
  const map = { super_admin: 'danger', admin: 'warning', user: '' }
  return map[authStore.user?.role] || 'info'
})

const currentRoute = computed(() => '/' + (route.meta.menuKey || 'smart-qa'))

const currentPageTitle = computed(() => {
  const menu = authStore.menus.find(m => m.key === route.meta.menuKey)
  return menu?.label || '企业AI知识助手'
})

const menuGroups = computed(() => {
  const menus = authStore.menus || []
  const groups = []

  const aiItems = menus.filter(m => ['smart-qa', 'my-sessions'].includes(m.key))
  if (aiItems.length) groups.push({ title: 'AI 助手', items: aiItems })

  const kbItems = menus.filter(m => ['company-kb', 'dept-kb', 'knowledge-export'].includes(m.key))
  if (kbItems.length) groups.push({ title: '知识库', items: kbItems })

  const analysisItems = menus.filter(m => ['analysis-data', 'analysis-compliance'].includes(m.key))
  if (analysisItems.length) groups.push({ title: '文件分析', items: analysisItems })

  const adminItems = menus.filter(m => ['user-manage', 'dept-manage', 'audit-log', 'user-sessions', 'company-settings'].includes(m.key))
  if (adminItems.length) groups.push({ title: '系统管理', items: adminItems })

  const orgItems = menus.filter(m => ['org-manage'].includes(m.key))
  if (orgItems.length) groups.push({ title: '组织管理', items: orgItems })

  return groups
})

async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  await authStore.logout()
  router.push('/login')
}

// 悬浮机器人拖拽逻辑
const floatPos = ref({ x: window.innerWidth - 80, y: window.innerHeight - 140 })
let isDragging = false
let hasMoved = false
let dragOffset = { x: 0, y: 0 }

function startDrag(e) {
  isDragging = true
  hasMoved = false
  const evt = e.touches ? e.touches[0] : e
  dragOffset.x = evt.clientX - floatPos.value.x
  dragOffset.y = evt.clientY - floatPos.value.y
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', endDrag)
  document.addEventListener('touchmove', onDrag)
  document.addEventListener('touchend', endDrag)
}

function onDrag(e) {
  const evt = e.touches ? e.touches[0] : e
  const newX = evt.clientX - dragOffset.x
  const newY = evt.clientY - dragOffset.y
  // 只要移动超过 5px 就认为是拖拽
  if (Math.abs(newX - floatPos.value.x) > 5 || Math.abs(newY - floatPos.value.y) > 5) {
    hasMoved = true
  }
  floatPos.value.x = Math.max(0, Math.min(window.innerWidth - 56, newX))
  floatPos.value.y = Math.max(0, Math.min(window.innerHeight - 56, newY))
}

function endDrag() {
  isDragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', endDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', endDrag)
}

function goSmartQA() {
  if (!hasMoved) {
    router.push('/smart-qa')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}

.sidebar {
  background: #1a1a2e;
  overflow-y: auto;
  overflow-x: hidden;
  border-right: none;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
}

.logo-area {
  padding: 16px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logo-text {
  color: #fff;
  font-size: 18px;
  font-weight: 700;
  margin: 0;
  text-align: center;
  white-space: nowrap;
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.sidebar-menu :deep(.el-menu-item-group__title) {
  padding: 12px 0 4px 20px;
  color: rgba(255,255,255,0.4);
  font-size: 12px;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin: 2px 8px;
  border-radius: 6px;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: rgba(64, 158, 255, 0.15) !important;
}

.sidebar-menu :deep(.el-menu--collapse .el-menu-item) {
  margin: 2px 4px;
  padding: 0 20px !important;
}

.collapse-btn {
  cursor: pointer;
  color: rgba(255,255,255,0.5);
  flex-shrink: 0;
  transition: color 0.2s;
  display: flex;
  align-items: center;
}

.collapse-btn:hover {
  color: #fff;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
  height: 56px;
  padding: 0 20px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  font-size: 14px;
  color: #606266;
}

.main-content {
  background: #f5f7fa;
  overflow-y: auto;
}

.mobile-menu-btn {
  display: none;
}

.drawer-logo {
  font-size: 18px;
  font-weight: 700;
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
  color: #303133;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .sidebar {
    display: none;
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .topbar {
    padding: 0 12px;
    height: 48px;
  }

  .page-title {
    font-size: 15px;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .topbar-right {
    gap: 8px;
  }

  .topbar-right .el-select {
    width: 110px !important;
  }

  .user-name {
    display: none;
  }

  .main-content {
    padding: 12px;
  }

  .main-content :deep(.el-card) {
    --el-card-padding: 12px;
  }

  .main-content :deep(.el-card__header) {
    padding: 12px;
  }
}

/* 悬浮机器人 */
.float-robot {
  position: fixed;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #66b1ff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.4);
  z-index: 9999;
  transition: box-shadow 0.2s;
  user-select: none;
  touch-action: none;
}

.float-robot:hover {
  box-shadow: 0 6px 20px rgba(64, 158, 255, 0.6);
}

.float-robot:active {
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
}
</style>
