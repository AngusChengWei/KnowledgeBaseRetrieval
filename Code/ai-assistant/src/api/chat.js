import api from './index'

export async function createSession(department = 'general') {
  const res = await api.post(`/sessions?department=${department}`)
  return res.data
}

export async function listSessions() {
  const res = await api.get('/sessions')
  return res.data
}

export async function deleteSession(sessionId) {
  const res = await api.post(`/sessions/${sessionId}?action=delete`)
  return res.data
}

export async function renameSession(sessionId, title) {
  const res = await api.post(`/sessions/${sessionId}?action=rename`, { title })
  return res.data
}

export async function getSessionMessages(sessionId) {
  const res = await api.get(`/sessions/${sessionId}/messages`)
  return res.data
}

export async function askQuestion(sessionId, question, department) {
  const res = await api.post('/ask', {
    session_id: sessionId,
    question,
    department
  })
  return res.data
}

export async function getDepartments() {
  const res = await api.get('/departments')
  return res.data
}

export async function uploadDocuments(files, department) {
  const formData = new FormData()
  for (const file of files) {
    formData.append('files', file)
  }
  const res = await api.post(`/upload?department=${department}`, formData, {
    timeout: 300000 // 上传大文件给 5 分钟超时
  })
  return res.data
}

export async function listDocuments(department) {
  const res = await api.get(`/documents?department=${department}`)
  return res.data
}

export async function deleteDocument(filename, department) {
  const res = await api.post(`/documents/${encodeURIComponent(filename)}?action=delete&department=${department}`)
  return res.data
}

export async function rebuildKnowledgeBase(department) {
  const res = await api.post(`/rebuild?department=${department}`)
  return res.data
}

export async function rebuildFileVectors(filename, department) {
  const res = await api.post(
    `/rebuild-file?department=${department}&filename=${encodeURIComponent(filename)}`,
    null,
    { timeout: 300000 }
  )
  return res.data
}

export async function deleteFileVectors(filename, department) {
  const res = await api.post('/vectors', null, {
    params: { action: 'delete', filename, department }
  })
  return res.data
}

export async function importUrl(url, department) {
  const res = await api.post(
    `/import-url?department=${department}&url=${encodeURIComponent(url)}`,
    null,
    { timeout: 60000 } // URL 抓取最多 60s
  )
  return res.data
}

export async function getDocumentContent(filename, department) {
  const res = await api.get(
    `/document-content?department=${department}&filename=${encodeURIComponent(filename)}`
  )
  return res.data
}

export async function updateDocumentTitle(filename, title, department) {
  const res = await api.patch(
    `/document-title?department=${department}&filename=${encodeURIComponent(filename)}&title=${encodeURIComponent(title)}`
  )
  return res.data
}

// ============ 知识库导出 ============

export async function exportReportPdf(data) {
  const res = await api.post('/pdf/report', data, { responseType: 'blob' })
  return res.data
}

export async function exportDocsZip(data) {
  const res = await api.post('/export/download-zip', data, { responseType: 'blob' })
  return res.data
}
