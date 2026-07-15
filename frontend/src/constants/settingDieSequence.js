function positiveProcessNumber(value, fallback = 1) {
  const number = Number(value)
  return Number.isInteger(number) && number > 0 ? number : fallback
}

export function settingDieProcessRows(job = {}) {
  if (Array.isArray(job.process_dies) && job.process_dies.length) return job.process_dies
  const count = positiveProcessNumber(job.process_die_count)
  return Array.from({ length: count }, (_, index) => ({
    process_die_no: index + 1,
    status: 'not_started',
    setting_die_id: null,
    is_saved: false,
  }))
}

export function settingDieProcessSaved(process) {
  if (!process) return false
  if (Object.prototype.hasOwnProperty.call(process, 'is_saved')) return process.is_saved === true
  return Boolean(process.setting_die_id && ['done', 'finished'].includes(String(process.status || '').toLowerCase()))
}

export function settingDieEligibility(job, processDieNo) {
  const processNo = positiveProcessNumber(processDieNo)
  if (processNo === 1) return { allowed: true, message: '', previousProcessNo: null }
  const previousProcessNo = processNo - 1
  const previousProcess = settingDieProcessRows(job)
    .find((process) => positiveProcessNumber(process.process_die_no) === previousProcessNo)
  const allowed = settingDieProcessSaved(previousProcess)
  return {
    allowed,
    previousProcessNo,
    message: allowed ? '' : `Complete Process Die ${previousProcessNo} first`,
  }
}
