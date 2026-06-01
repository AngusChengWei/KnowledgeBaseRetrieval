import api from './index'

// ============ 用户管理 ============

export async function getUsers() {
  const res = await api.get('/admin/users')
  return res.data
}

export async function createUser(data) {
  const res = await api.post('/admin/users', data)
  return res.data
}

export async function updateUserRole(userId, role) {
  const res = await api.post(`/admin/users/${userId}?action=update_role`, { role })
  return res.data
}

export async function updateUserOrg(userId, orgId) {
  const res = await api.post(`/admin/users/${userId}?action=update_org`, { org_id: orgId })
  return res.data
}

export async function toggleUserStatus(userId) {
  const res = await api.post(`/admin/users/${userId}?action=toggle_status`)
  return res.data
}

export async function updateUserDepartments(userId, departmentIds) {
  const res = await api.post(`/admin/users/${userId}?action=update_departments`, { department_ids: departmentIds })
  return res.data
}

// ============ 部门管理 ============

export async function getDepartments() {
  const res = await api.get('/admin/departments')
  return res.data
}

export async function createDepartment(data) {
  const res = await api.post('/admin/departments', data)
  return res.data
}

export async function updateDepartment(deptId, data) {
  const res = await api.post(`/admin/departments/${deptId}?action=update`, data)
  return res.data
}

export async function deleteDepartment(deptId) {
  const res = await api.post(`/admin/departments/${deptId}?action=delete`)
  return res.data
}

// ============ 审计日志 ============

export async function getAuditLogs(page = 1, pageSize = 20, action = '') {
  let url = `/audit/logs?page=${page}&page_size=${pageSize}`
  if (action) url += `&action=${action}`
  const res = await api.get(url)
  return res.data
}

// ============ 组织管理 ============

export async function getOrganizations() {
  const res = await api.get('/admin/organizations')
  return res.data
}

export async function createOrganization(data) {
  const res = await api.post('/admin/organizations', data)
  return res.data
}

export async function updateOrganization(orgId, data) {
  const res = await api.post(`/admin/organizations/${orgId}?action=update`, data)
  return res.data
}

export async function deleteOrganization(orgId) {
  const res = await api.post(`/admin/organizations/${orgId}?action=delete`)
  return res.data
}

export async function regenerateInviteCodes(orgId) {
  const res = await api.post(`/admin/organizations/${orgId}?action=regenerate_invite_codes`)
  return res.data
}

// ============ 管理员本公司设置 ============

export async function getMyOrg() {
  const res = await api.get('/admin/my-org')
  return res.data
}

export async function updateMyOrg(data) {
  const res = await api.post('/admin/my-org?action=update', data)
  return res.data
}

export async function regenerateMyUserInviteCode() {
  const res = await api.post('/admin/my-org?action=regenerate_user_invite_code')
  return res.data
}

// ============ 用户会话管理 ============

export async function getAdminSessions(userId = '', page = 1, pageSize = 10) {
  let url = `/admin/sessions?page=${page}&page_size=${pageSize}`
  if (userId) url += `&user_id=${userId}`
  const res = await api.get(url)
  return res.data
}

export async function getAdminSessionMessages(sessionId) {
  const res = await api.get(`/admin/sessions/${sessionId}/messages`)
  return res.data
}
