import axios from 'axios'

// 自适应 baseURL：
// - 开发环境：走 vite dev server 的 /api 代理（vite.config.js 已 rewrite 去掉 /api 前缀转发到 localhost:8000）
// - 生产环境：走 nginx 的 /api 反向代理（需在 nginx 中将 /api 前缀剥离后转给后端，例如 proxy_pass http://127.0.0.1:8007/;）
// - 也允许通过 .env 中的 VITE_API_BASE_URL 显式覆盖（如对接独立域名后端）
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({
  baseURL,
  timeout: 60000
})

// Token 管理
const TOKEN_KEY = 'ai_assistant_token'

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAuthToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY)
}

// 请求拦截器
api.interceptors.request.use(config => {
  const token = getAuthToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // 超管切换组织时，自动附加当前组织ID
  const currentOrgId = localStorage.getItem('ai_assistant_current_org_id')
  if (currentOrgId) {
    config.headers['X-Current-Org-Id'] = currentOrgId
  }
  return config
})

// 响应拦截器：401 时清除 token 并跳转登录页
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      const detail = error.response?.data?.detail || '登录已过期，请重新登录'
      clearAuthToken()
      localStorage.removeItem('ai_assistant_current_org_id')
      // 避免在登录页重复跳转
      if (!window.location.pathname.includes('/login')) {
        alert(detail)
        window.location.href = '/'
      }
    }
    return Promise.reject(error)
  }
)

export default api
