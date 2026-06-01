import api, { setAuthToken } from './index'

export async function login(username, password) {
  const res = await api.post('/auth/login', { username, password })
  setAuthToken(res.data.token)
  return res.data
}

export async function register(username, password, inviteCode = '') {
  const data = { username, password }
  if (inviteCode) data.invite_code = inviteCode
  const res = await api.post('/auth/register', data)
  setAuthToken(res.data.token)
  return res.data
}

export async function getMe() {
  const res = await api.get('/auth/me')
  return res.data
}

export async function logout() {
  await api.post('/auth/logout')
}
