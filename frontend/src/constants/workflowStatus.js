export const DASHBOARD_BUCKETS = [
  { key: 'total', label: 'Total', description: 'แผนการผลิตทั้งหมด', tone: 'text-slate-950' },
  { key: 'waiting', label: 'Waiting', description: 'ยังไม่เริ่มดำเนินการ', tone: 'text-amber-700' },
  { key: 'in_progress', label: 'In Progress', description: 'กำลังดำเนินการ', tone: 'text-blue-700' },
  { key: 'qc', label: 'QC', description: 'อยู่ในขั้นตอนตรวจสอบคุณภาพ', tone: 'text-sky-700' },
  { key: 'completed', label: 'Completed', description: 'เสร็จสิ้นทุกขั้นตอน', tone: 'text-emerald-700' },
]

const COMPLETED_STATES = new Set(['completed', 'confirmed', 'pass', 'passed', 'finished'])
const WAITING_STATES = new Set(['waiting', 'pending', 'wait'])
const FAILED_STATES = new Set(['fail', 'failed'])

export function normalizeWorkflowValue(value) {
  return String(value || '').trim().toLowerCase().replace(/[_-]+/g, ' ')
}

export function stagePresentation(stage) {
  const normalized = normalizeWorkflowValue(stage)
  if (normalized === 'completed') return { label: 'Completed', className: 'bg-emerald-50 text-emerald-700' }
  if (normalized === 'production finish') return { label: 'Production Finish', className: 'bg-indigo-50 text-indigo-700' }
  if (normalized === 'production start') return { label: 'Production Start', className: 'bg-blue-50 text-blue-700' }
  if (normalized === 'qc') return { label: 'QC', className: 'bg-sky-50 text-sky-700' }
  if (normalized === 'setting die') return { label: 'Setting Die', className: 'bg-violet-50 text-violet-700' }
  return { label: normalized === 'not started' ? 'Not Started' : (stage || '-'), className: 'bg-slate-100 text-slate-600' }
}

export function statePresentation(stage, status, item = {}) {
  let normalizedStage = normalizeWorkflowValue(stage)
  if (normalizedStage.startsWith('setting die')) normalizedStage = 'setting die'
  if (normalizedStage.startsWith('qc inspection')) normalizedStage = 'qc'
  const normalizedStatus = normalizeWorkflowValue(status)
  const progress = item.setting_die_progress || {}
  const completed = Number(progress.completed || 0)
  const total = Math.max(Number(progress.total || 0), 0)

  if (normalizedStage === 'completed') return { label: 'Completed', className: 'bg-emerald-50 text-emerald-700' }
  if (normalizedStage === 'not started') {
    if (normalizedStatus === 'accepted') return { label: 'Plan Accepted', className: 'bg-amber-50 text-amber-700' }
    return { label: 'Waiting for Action', className: 'bg-amber-50 text-amber-700' }
  }
  if (normalizedStage === 'setting die') {
    if (total && completed >= total) return { label: 'Setting Die Completed', className: 'bg-emerald-50 text-emerald-700' }
    if (total) return { label: `Process ${Math.min(completed + 1, total)} of ${total} in progress`, className: 'bg-blue-50 text-blue-700' }
    if (['done', 'finished'].includes(normalizedStatus)) return { label: 'Step Completed', className: 'bg-emerald-50 text-emerald-700' }
    if (normalizedStatus === 'incomplete') return { label: 'Incomplete', className: 'bg-amber-50 text-amber-700' }
    if (normalizedStatus === 'not started') return { label: 'Not Started', className: 'bg-slate-100 text-slate-600' }
    return { label: 'In Progress', className: 'bg-blue-50 text-blue-700' }
  }
  if (normalizedStage === 'qc') {
    if (['pass', 'passed'].includes(normalizedStatus)) return { label: 'QC Passed', className: 'bg-emerald-50 text-emerald-700' }
    if (FAILED_STATES.has(normalizedStatus)) return { label: 'QC Failed', className: 'bg-red-50 text-red-700' }
    return { label: 'QC Pending', className: 'bg-amber-50 text-amber-700' }
  }
  if (normalizedStage === 'production start') {
    if (normalizedStatus === 'confirmed') return { label: 'Production Started', className: 'bg-emerald-50 text-emerald-700' }
    return { label: 'Awaiting Start Confirmation', className: 'bg-amber-50 text-amber-700' }
  }
  if (normalizedStage === 'production finish') {
    if (COMPLETED_STATES.has(normalizedStatus)) return { label: 'Completed', className: 'bg-emerald-50 text-emerald-700' }
    return { label: 'Awaiting Finish Confirmation', className: 'bg-amber-50 text-amber-700' }
  }
  if (COMPLETED_STATES.has(normalizedStatus)) return { label: normalizedStatus === 'pass' ? 'Passed' : 'Confirmed', className: 'bg-emerald-50 text-emerald-700' }
  if (FAILED_STATES.has(normalizedStatus)) return { label: 'Failed', className: 'bg-red-50 text-red-700' }
  if (WAITING_STATES.has(normalizedStatus)) return { label: 'Waiting for Action', className: 'bg-amber-50 text-amber-700' }
  if (normalizedStatus === 'in progress') return { label: 'In Progress', className: 'bg-blue-50 text-blue-700' }
  if (normalizedStatus === 'done') return { label: 'Step Completed', className: 'bg-emerald-50 text-emerald-700' }
  if (normalizedStatus === 'accepted') return { label: 'Plan Accepted', className: 'bg-blue-50 text-blue-700' }
  return { label: status ? normalizedStatus.replace(/\b\w/g, (character) => character.toUpperCase()) : '-', className: 'bg-slate-100 text-slate-600' }
}

export function nextActionForItem(item = {}) {
  const stage = normalizeWorkflowValue(item.current_step)
  const status = normalizeWorkflowValue(item.status)
  const progress = item.setting_die_progress || {}
  const completed = Number(progress.completed || 0)
  const total = Math.max(Number(progress.total || 0), 0)

  if (stage === 'completed') return 'No further action'
  if (stage === 'not started') return 'Start Setting Die'
  if (stage === 'setting die') {
    if (total && completed >= total) return 'Proceed to QC Inspection'
    return total ? `Continue Setting Die Process ${Math.min(completed + 1, total)}` : 'Continue Setting Die'
  }
  if (stage === 'qc') {
    if (['pass', 'passed'].includes(status)) return 'Proceed to Production Start'
    if (FAILED_STATES.has(status)) return 'Resolve QC Failure'
    return 'Complete QC Inspection'
  }
  if (stage === 'production start') return status === 'confirmed' ? 'Proceed to Production Finish' : 'Confirm Production Start'
  if (stage === 'production finish') return COMPLETED_STATES.has(status) ? 'No further action' : 'Confirm Production Finish'
  return 'Review workflow status'
}

export function filterDashboardItems(items, bucket) {
  const values = Array.isArray(items) ? items : []
  return bucket === 'total' ? values : values.filter((item) => item.dashboard_bucket === bucket)
}

export function workflowDestination(item = {}) {
  const stage = normalizeWorkflowValue(item.current_step)
  if (stage === 'completed') return { type: 'detail', menu: null }
  if (stage === 'qc') return { type: 'workflow', menu: 'qc' }
  if (stage === 'production start') return { type: 'workflow', menu: 'production-start' }
  if (stage === 'production finish') return { type: 'workflow', menu: 'production-finish' }
  return { type: 'workflow', menu: 'production' }
}

export function findWorkflowTarget(records, target, { useIdAsPlanId = false } = {}) {
  const values = Array.isArray(records) ? records : []
  if (!target) return null
  const targetPlanId = Number(target.planId)
  if (Number.isFinite(targetPlanId)) {
    const byPlan = values.find((record) => Number(useIdAsPlanId ? record.id : record.plan_id) === targetPlanId)
    if (byPlan) return byPlan
  }
  const lotNo = String(target.lotNo || '').trim()
  return lotNo ? values.find((record) => String(record.lot_no || '').trim() === lotNo) || null : null
}
