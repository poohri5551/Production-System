let authFailureHandler = null

export function setAuthFailureHandler(handler) {
  authFailureHandler = handler
}

function notifyAuthFailure(data) {
  if (authFailureHandler) {
    authFailureHandler(data?.message || 'Session expired or account was removed. Please login again.')
  }
}

async function readJson(response) {
  const data = await response.json().catch(() => ({}))
  if (data.logged_out || data.auth_required) {
    notifyAuthFailure(data)
  }
  if (!response.ok) {
    if (response.status === 401 || data.auth_required) {
      notifyAuthFailure(data)
    }
    return {
      success: false,
      message: data.message || `Request failed with status ${response.status}`,
      ...data,
    }
  }
  return data
}

export async function getJson(url) {
  const response = await fetch(url, {
    credentials: 'same-origin',
  })
  return readJson(response)
}

export async function postForm(url, formData) {
  const response = await fetch(url, {
    method: 'POST',
    body: formData,
    credentials: 'same-origin',
  })
  return readJson(response)
}

export async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload || {}),
    credentials: 'same-origin',
  })
  return readJson(response)
}

export async function login(username, password) {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return postForm('/api/login', formData)
}

export function logoutSession() {
  return postForm('/api/logout', new FormData())
}

export function getCurrentSession() {
  return getJson('/api/me')
}

export function getDashboardPartsStatus() {
  return getJson('/api/dashboard/parts-status')
}

export function getDashboardPartStatusDetail(planId) {
  return getJson(`/api/dashboard/parts-status/${planId}`)
}

export function getProductionJobs(filters = {}) {
  const params = new URLSearchParams()
  if (filters.zone) params.set('zone', filters.zone)
  if (filters.partNo) params.set('part_no', filters.partNo)
  if (filters.dieNo) params.set('die_no', filters.dieNo)

  const query = params.toString()
  return getJson(`/api/jobs${query ? `?${query}` : ''}`)
}

export function getProductionJobDetail(jobId) {
  return getJson(`/api/jobs/${jobId}`)
}

export function createProductionJob(formData) {
  return postForm('/api/production', formData)
}

export function acceptProductionJob(jobId) {
  return postForm(`/api/jobs/${jobId}/accept`, new FormData())
}

export function saveSettingDie(formData) {
  return postForm('/api/setting_die', formData)
}

export function bulkDeleteProductionJobs(ids, adminPassword) {
  const formData = new FormData()
  ids.forEach((id) => formData.append('ids[]', id))
  formData.append('admin_password', adminPassword)
  return postForm('/api/jobs/bulk_delete', formData)
}

export function getQCInspections(filters = {}) {
  const params = new URLSearchParams()
  if (filters.partNo) params.set('part_no', filters.partNo)
  if (filters.lotNo) params.set('lot_no', filters.lotNo)

  const query = params.toString()
  return getJson(`/api/qc_list${query ? `?${query}` : ''}`)
}

export function getQCInspectionDetail(qcId) {
  return getJson(`/api/qc/${qcId}`)
}

export function saveQCInspection(formData, qcId = '') {
  return postForm(qcId ? `/api/qc/${qcId}/update` : '/api/qc', formData)
}

export function getQCPlanOptions() {
  return getJson('/api/qc/plans')
}

export function getQCPlanDetail(planNo) {
  return getJson(`/api/qc/plan?plan_no=${encodeURIComponent(planNo)}`)
}

export function sendSettingDieToQCLine(planNo) {
  const formData = new FormData()
  formData.append('plan_no', planNo)
  return postForm('/api/qc/from_setting_die', formData)
}

export function bulkDeleteQCInspections(ids, adminPassword) {
  const formData = new FormData()
  ids.forEach((id) => formData.append('ids[]', id))
  formData.append('admin_password', adminPassword)
  return postForm('/api/qc/bulk_delete', formData)
}

export function createProductionStartFromQC(qc) {
  const formData = new FormData()
  formData.append('plan_no', qc.plan_no || '')
  formData.append('lot_no', qc.lot_no || '')
  formData.append('part_no', qc.part_no || '')
  return postForm('/api/production_start/from_qc', formData)
}

export function getProductionStarts() {
  return getJson('/api/production_starts')
}

export function getProductionStartDetail(startId) {
  return getJson(`/api/production_start/${startId}`)
}

export function saveProductionStart(formData) {
  return postForm('/api/production_start', formData)
}

export function getProductionStartPlanOptions() {
  return getJson('/api/production_start/plans')
}

export function getProductionStartPlanDetail(planNo) {
  return getJson(`/api/production_start/plan?plan_no=${encodeURIComponent(planNo)}`)
}

export function confirmProductionStart(startId) {
  return postForm(`/api/production_start/${startId}/confirm`, new FormData())
}

export function bulkDeleteProductionStarts(ids, adminPassword) {
  const formData = new FormData()
  ids.forEach((id) => formData.append('ids[]', id))
  formData.append('admin_password', adminPassword)
  return postForm('/api/production_start/bulk_delete', formData)
}

export function getProductionFinishes() {
  return getJson('/api/production_finishes')
}

export function saveProductionFinish(formData) {
  return postForm('/api/production_finish', formData)
}

export function getProductionFinishPlanOptions() {
  return getJson('/api/production_finish/plans')
}

export function getProductionFinishPlanDetail(planNo) {
  return getJson(`/api/production_finish/plan?plan_no=${encodeURIComponent(planNo)}`)
}

export function confirmProductionFinish(finishId) {
  return postForm(`/api/production_finish/${finishId}/confirm`, new FormData())
}

export function bulkDeleteProductionFinishes(ids, adminPassword) {
  const formData = new FormData()
  ids.forEach((id) => formData.append('ids[]', id))
  formData.append('admin_password', adminPassword)
  return postForm('/api/production_finish/bulk_delete', formData)
}

export function getUsers() {
  return getJson('/api/users')
}

export function createUser(formData) {
  return postForm('/api/users', formData)
}

export function updateUserRole(userId, role, adminPassword) {
  const formData = new FormData()
  formData.append('role', role)
  formData.append('admin_password', adminPassword)
  return postForm(`/api/users/${userId}/role`, formData)
}

export function deleteUser(userId, adminPassword) {
  const formData = new FormData()
  formData.append('admin_password', adminPassword)
  return postForm(`/api/users/${userId}/delete`, formData)
}

export function resetUserPassword(userId, payload) {
  return postJson(`/api/users/${userId}/reset-password`, payload)
}
