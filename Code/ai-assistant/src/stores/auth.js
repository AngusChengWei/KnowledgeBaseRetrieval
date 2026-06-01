import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, logout as apiLogout } from '../api/auth'
import { getAuthToken, clearAuthToken } from '../api/index'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const menus = ref([])
  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin' || user.value?.role === 'super_admin')
  const isSuperAdmin = computed(() => user.value?.role === 'super_admin')

  // 当前操作的组织（超管可切换）
  const ORG_STORAGE_KEY = 'ai_assistant_current_org_id'
  const currentOrgId = ref(localStorage.getItem(ORG_STORAGE_KEY) ? Number(localStorage.getItem(ORG_STORAGE_KEY)) : null)
  const currentOrgCode = ref(null)

  async function checkAuth() {
    const token = getAuthToken()
    if (!token) return false
    try {
      const data = await getMe()
      user.value = data
      menus.value = data.menus || []
      // 保留 localStorage 中已切换的组织，仅在未切换过时用默认值
      const savedOrgId = localStorage.getItem(ORG_STORAGE_KEY)
      if (savedOrgId) {
        currentOrgId.value = Number(savedOrgId)
        // currentOrgCode 会在 Layout 加载组织列表后补充
      } else {
        currentOrgId.value = data.org_id
        currentOrgCode.value = data.org_code
      }
      return true
    } catch (e) {
      clearAuthToken()
      return false
    }
  }

  function setUser(data) {
    user.value = {
      user_id: data.user_id,
      username: data.username,
      role: data.role,
      org_id: data.org_id,
      org_code: data.org_code,
      departments: data.departments || [],
    }
    menus.value = data.menus || []
    currentOrgId.value = data.org_id
    currentOrgCode.value = data.org_code
  }

  function switchOrg(orgId, orgCode) {
    currentOrgId.value = orgId
    currentOrgCode.value = orgCode
    // 同步到 localStorage 供 axios 拦截器读取
    if (orgId) {
      localStorage.setItem(ORG_STORAGE_KEY, String(orgId))
    } else {
      localStorage.removeItem(ORG_STORAGE_KEY)
    }
  }

  async function logout() {
    try {
      await apiLogout()
    } catch (e) { /* ignore */ }
    clearAuthToken()
    localStorage.removeItem(ORG_STORAGE_KEY)
    user.value = null
    menus.value = []
    currentOrgId.value = null
    currentOrgCode.value = null
  }

  return { user, menus, isLoggedIn, isAdmin, isSuperAdmin, currentOrgId, currentOrgCode, checkAuth, setUser, switchOrg, logout }
})
