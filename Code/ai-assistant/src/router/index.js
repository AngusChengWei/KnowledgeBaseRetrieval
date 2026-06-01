import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { guest: true }
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/smart-qa'
      },
      {
        path: 'smart-qa',
        name: 'SmartQA',
        component: () => import('../views/chat/SmartQA.vue'),
        meta: { menuKey: 'smart-qa' }
      },
      {
        path: 'my-sessions',
        name: 'MySessions',
        component: () => import('../views/chat/MySessions.vue'),
        meta: { menuKey: 'my-sessions' }
      },
      {
        path: 'company-kb',
        name: 'CompanyKB',
        component: () => import('../views/knowledge/CompanyKB.vue'),
        meta: { menuKey: 'company-kb', requiresAdmin: true }
      },
      {
        path: 'dept-kb',
        name: 'DeptKB',
        component: () => import('../views/knowledge/DeptKB.vue'),
        meta: { menuKey: 'dept-kb', requiresAdmin: true }
      },
      {
        path: 'user-manage',
        name: 'UserManage',
        component: () => import('../views/admin/Users.vue'),
        meta: { menuKey: 'user-manage', requiresAdmin: true }
      },
      {
        path: 'dept-manage',
        name: 'DeptManage',
        component: () => import('../views/admin/Departments.vue'),
        meta: { menuKey: 'dept-manage', requiresAdmin: true }
      },
      {
        path: 'audit-log',
        name: 'AuditLog',
        component: () => import('../views/admin/AuditLog.vue'),
        meta: { menuKey: 'audit-log', requiresAdmin: true }
      },
      {
        path: 'user-sessions',
        name: 'UserSessions',
        component: () => import('../views/admin/UserSessions.vue'),
        meta: { menuKey: 'user-sessions', requiresAdmin: true }
      },
      {
        path: 'org-manage',
        name: 'OrgManage',
        component: () => import('../views/admin/Organizations.vue'),
        meta: { menuKey: 'org-manage', requiresSuperAdmin: true }
      },
      {
        path: 'company-settings',
        name: 'CompanySettings',
        component: () => import('../views/admin/CompanySettings.vue'),
        meta: { menuKey: 'company-settings', requiresAdmin: true }
      },
      // ============ 知识库导出 ============
      {
        path: 'knowledge-export',
        name: 'KnowledgeExport',
        component: () => import('../views/knowledge/KnowledgeExport.vue'),
        meta: { menuKey: 'knowledge-export', requiresAdmin: true }
      },
      // ============ 文件分析 ============
      {
        path: 'analysis-data',
        name: 'DataAnalysis',
        component: () => import('../views/analysis/DataAnalysis.vue'),
        meta: { menuKey: 'analysis-data', requiresAuth: true }
      },
      {
        path: 'analysis-compliance',
        name: 'ComplianceCheck',
        component: () => import('../views/analysis/ComplianceCheck.vue'),
        meta: { menuKey: 'analysis-compliance', requiresAuth: true }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 如果未检查过认证状态，先检查
  if (!authStore.isLoggedIn) {
    await authStore.checkAuth()
  }

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
  } else if (to.meta.guest && authStore.isLoggedIn) {
    next('/')
  } else if (to.meta.requiresSuperAdmin && !authStore.isSuperAdmin) {
    next('/')
  } else if (to.meta.requiresAdmin && !authStore.isAdmin) {
    next('/')
  } else {
    next()
  }
})

export default router
