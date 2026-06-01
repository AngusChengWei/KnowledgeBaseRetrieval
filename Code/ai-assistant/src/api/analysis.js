import api from './index'

export async function uploadAnalysisFile(file, analysisType, departments = 'general', question = '') {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post(`/analyze/upload?analysis_type=${analysisType}&departments=${encodeURIComponent(departments)}&user_question=${encodeURIComponent(question)}`, formData, {
    timeout: 300000,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
  return res.data
}

export async function getAnalysisResult(taskId) {
  const res = await api.get(`/analyze/result/${taskId}`)
  return res.data
}

export async function getAnalysisHistory() {
  const res = await api.get('/analyze/history')
  return res.data
}
