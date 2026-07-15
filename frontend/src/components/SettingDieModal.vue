<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  approveSettingDieCorrection,
  finishSettingDieCorrection,
  rejectSettingDieCorrection,
  reopenSettingDieCorrection,
  requestSettingDieCorrection,
  saveSettingDie,
  sendSettingDieToQCLine,
} from '../api/client'
import WorkflowConfirmationDialog from './WorkflowConfirmationDialog.vue'

const props = defineProps({
  job: { type: Object, required: true },
  setting: { type: Object, default: null },
  processDieNo: { type: Number, default: 1 },
  canSendToQc: { type: Boolean, default: false },
  userRole: { type: String, default: '' },
})

const emit = defineEmits(['close', 'saved'])
const form = reactive({
  lotNo: '', dh: '', spm: '', timeStart: '', timeEnd: '', material: '',
  materialStart: '', materialEnd: '', adjustStart: '', adjustEnd: '', technician: '',
})
const workflowState = ref({})
const dialogType = ref('')
const isSubmitting = ref(false)
const isSendingToQC = ref(false)
const isWorkflowBusy = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const timeStartRequiredMessage = 'กรุณา Stamp เวลา Time Start Setting Die ก่อนบันทึก'

const positiveNumber = (value, fallback = 1) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}
const currentProcessNo = computed(() => positiveNumber(props.processDieNo))
const processDieCount = computed(() => positiveNumber(props.job?.process_die_count))
const isLastProcess = computed(() => currentProcessNo.value === processDieCount.value)
const modalTitle = computed(() => `Setting Die - Process ${currentProcessNo.value}`)
const canSaveSettingDie = computed(() => Boolean(form.timeStart))
const correction = computed(() => workflowState.value?.correction || null)
const correctionStatus = computed(() => workflowState.value?.correction_status || correction.value?.status || '')
const initialSent = computed(() => Boolean(workflowState.value?.setting_die_sent))
const isLocked = computed(() => initialSent.value && correctionStatus.value !== 'open')
const isApprover = computed(() => ['Admin', 'Sup'].includes(props.userRole))
const approvalRequired = computed(() => Boolean(workflowState.value?.approval_required))
const canShowInitialSend = computed(() => props.canSendToQc && isLastProcess.value)
const canStartCorrection = computed(() => initialSent.value && !correctionStatus.value)
const workflowLabel = computed(() => {
  if (!initialSent.value) return 'Editable - initial QC handoff not sent'
  if (correctionStatus.value === 'pending_approval') return 'Correction Approval Pending'
  if (correctionStatus.value === 'open') return 'Correction in Progress'
  if (workflowState.value?.historical_downstream_requires_review) return 'Updated - Downstream Review Required'
  if (workflowState.value?.qc_recheck_required) return 'Updated - QC Recheck Required'
  return 'Locked - Sent to QC Line'
})

const timeFieldLabels = {
  timeStart: 'Time Start Setting Die',
  timeEnd: 'Time End Setting Die',
  materialStart: 'Time Start Setting Material',
  materialEnd: 'Time End Setting Material',
  adjustStart: 'Time Start Adjust Accuracy Part',
  adjustEnd: 'Time End Adjust Accuracy Part',
}
const timeFields = Object.entries(timeFieldLabels).map(([name, label]) => ({ name, label }))
const visibleTimeFields = computed(() => (
  isLastProcess.value ? timeFields : timeFields.filter((field) => !['adjustStart', 'adjustEnd'].includes(field.name))
))

watch(
  () => [props.job, props.setting, props.processDieNo],
  () => {
    const setting = props.setting || {}
    form.lotNo = setting.lot_no || props.job?.lot_no || ''
    form.dh = setting.dh || ''
    form.spm = setting.spm || ''
    form.timeStart = toDatetimeLocal(setting.time_start)
    form.timeEnd = toDatetimeLocal(setting.time_end)
    form.material = setting.material || ''
    form.materialStart = toDatetimeLocal(setting.custom_time_1)
    form.materialEnd = toDatetimeLocal(setting.custom_time_2)
    form.adjustStart = toDatetimeLocal(setting.custom_time_3)
    form.adjustEnd = toDatetimeLocal(setting.custom_time_4)
    form.technician = setting.technician || ''
    workflowState.value = { ...(props.job?.workflow || {}) }
    errorMessage.value = ''
    noticeMessage.value = ''
  },
  { immediate: true },
)

function toDatetimeLocal(value) {
  if (!value) return ''
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return ''
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function currentDatetimeLocal() {
  const date = new Date()
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function stamp(fieldName) {
  if (form[fieldName] || isLocked.value) return
  const label = timeFieldLabels[fieldName] || 'this field'
  if (!window.confirm(`ยืนยัน Stamp เวลา ${label} ใช่ไหม? หลังจาก Stamp แล้วจะแก้ไขไม่ได้`)) return
  form[fieldName] = currentDatetimeLocal()
}

function displayDatetime(value) {
  if (!value) return 'ยังไม่ได้ Stamp'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ')
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function validateTimeStart() {
  if (form.timeStart) return true
  errorMessage.value = timeStartRequiredMessage
  return false
}

function applyWorkflow(data) {
  if (data?.workflow) workflowState.value = { ...data.workflow }
}

async function submitForm() {
  if (isLocked.value) {
    errorMessage.value = 'Setting Die is locked. Reopen an approved correction before editing.'
    return
  }
  if (isSubmitting.value || isSendingToQC.value || isWorkflowBusy.value) return
  errorMessage.value = ''
  if (!validateTimeStart()) return
  isSubmitting.value = true
  try {
    const data = await saveCurrentSettingDie()
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot save Setting Die'
      return
    }
    emit('saved', 'Setting Die saved successfully.')
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isSubmitting.value = false
  }
}

function openDialog(type) {
  errorMessage.value = ''
  noticeMessage.value = ''
  dialogType.value = type
}

const dialogConfig = computed(() => {
  const details = [
    { label: 'Lot No.', value: form.lotNo },
    { label: 'Part No.', value: props.job?.part_no },
  ]
  const stage = workflowState.value?.downstream_stage || 'QC not started'
  if (dialogType.value === 'send') return {
    title: 'Confirm Send to QC Line',
    message: 'Send this Lot to QC Line? This initial handoff can only be sent once.',
    details: [...details, { label: 'Destination', value: 'QC Line' }],
    confirmLabel: 'Confirm Send', busyLabel: 'Sending...', requireReason: false, danger: false,
  }
  if (dialogType.value === 'reopen' || dialogType.value === 'request') return {
    title: dialogType.value === 'request' ? 'Request Setting Die Correction' : 'Reopen Setting Die for Correction',
    message: dialogType.value === 'request'
      ? 'QC passed or Production progressed. Admin or Sup approval is required, and downstream history will remain for review.'
      : stage === 'qc_in_progress'
        ? 'QC inspection has started. Completing this correction makes the current QC review stale and requires a full recheck.'
        : 'This Lot has already been sent to QC. The corrected revision must be reviewed by QC.',
    details: [...details, { label: 'Current downstream state', value: stage }],
    confirmLabel: dialogType.value === 'request' ? 'Request Correction' : 'Reopen for Correction',
    busyLabel: 'Submitting...', requireReason: true, reasonLabel: 'Reason for correction', danger: true,
  }
  if (dialogType.value === 'approve') return {
    title: 'Approve Setting Die Correction', message: 'Approve this request and unlock Setting Die for correction?',
    details: [...details, { label: 'Current downstream state', value: stage }, { label: 'Reason', value: correction.value?.reason }],
    confirmLabel: 'Approve', busyLabel: 'Approving...', requireReason: false, danger: false,
  }
  if (dialogType.value === 'reject') return {
    title: 'Reject Setting Die Correction', message: 'Reject this request? Setting Die will remain locked.',
    details: [...details, { label: 'Current downstream state', value: stage }, { label: 'Requested reason', value: correction.value?.reason }],
    confirmLabel: 'Reject', busyLabel: 'Rejecting...', requireReason: true, reasonLabel: 'Rejection reason', danger: true,
  }
  return {
    title: 'Finish Setting Die Correction',
    message: 'Finalize this revision and notify QC of the update? The original QC handoff remains permanently sent.',
    details: [...details, { label: 'Next revision', value: correction.value?.target_revision }],
    confirmLabel: 'Finish Correction', busyLabel: 'Finishing...', requireReason: false, danger: false,
  }
})

async function confirmDialog(reason = '') {
  if (isWorkflowBusy.value || isSendingToQC.value) return
  const action = dialogType.value
  if (action === 'send') {
    if (!validateTimeStart() || !form.lotNo.trim()) return
    isSendingToQC.value = true
  } else {
    isWorkflowBusy.value = true
  }
  errorMessage.value = ''
  try {
    let data
    if (action === 'send') {
      const saveResult = await saveCurrentSettingDie()
      if (!saveResult.success) data = saveResult
      else data = await sendSettingDieToQCLine(form.lotNo, props.job.id)
    } else if (action === 'reopen') {
      data = await reopenSettingDieCorrection(props.job.id, reason)
    } else if (action === 'request') {
      data = await requestSettingDieCorrection(props.job.id, reason)
    } else if (action === 'approve') {
      data = await approveSettingDieCorrection(correction.value.id)
    } else if (action === 'reject') {
      data = await rejectSettingDieCorrection(correction.value.id, reason)
    } else {
      data = await finishSettingDieCorrection(correction.value.id)
    }
    if (!data?.success) {
      errorMessage.value = data?.message || 'Workflow action failed'
      return
    }
    applyWorkflow(data)
    dialogType.value = ''
    if (action === 'send') {
      workflowState.value = { ...workflowState.value, setting_die_sent: true, setting_die_locked: true }
      emit('saved', data.already_sent ? 'Initial QC Line handoff was already sent.' : 'Setting Die saved and sent to QC Line.')
    } else if (action === 'finish') {
      emit('saved', `Correction completed at revision ${data.revision}. QC recheck required.`)
    } else if (action === 'reject') {
      emit('saved', 'Correction request rejected. Setting Die remains locked.')
    } else {
      noticeMessage.value = action === 'request' ? 'Correction approval requested.' : action === 'approve' ? 'Correction approved and opened.' : 'Correction opened. Setting Die editing is enabled.'
      if (data.correction) {
        workflowState.value = {
          ...workflowState.value,
          correction: data.correction,
          correction_status: data.correction.status,
          setting_die_locked: data.correction.status !== 'open',
        }
      }
    }
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isSendingToQC.value = false
    isWorkflowBusy.value = false
  }
}

function saveCurrentSettingDie() {
  const formData = new FormData()
  formData.append('plan_id', props.job.id)
  formData.append('process_die_no', props.processDieNo || 1)
  formData.append('set-part-no', props.job.part_no || '')
  formData.append('set-die-no', props.job.die_no || '')
  formData.append('set-lot-no', form.lotNo)
  formData.append('set-dh', form.dh)
  formData.append('set-spm', form.spm)
  formData.append('set-time-start', form.timeStart)
  formData.append('set-time-end', form.timeEnd)
  formData.append('set-material', form.material)
  formData.append('custom-time-1', form.materialStart)
  formData.append('custom-time-2', form.materialEnd)
  if (isLastProcess.value) {
    formData.append('custom-time-3', form.adjustStart)
    formData.append('custom-time-4', form.adjustEnd)
  }
  formData.append('set-technician', form.technician)
  return saveSettingDie(formData)
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex flex-col gap-4 border-b border-blue-100 bg-white/95 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Production workflow</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ modalTitle }}</h2>
          <p class="mt-1 text-sm text-slate-500">Plan #{{ job.id }} / Part {{ job.part_no || '-' }} / Die {{ job.die_no || '-' }}</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">Close</button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <div class="rounded-2xl border px-4 py-3" :class="isLocked ? 'border-slate-200 bg-slate-50 text-slate-700' : correctionStatus === 'open' ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-blue-100 bg-blue-50 text-blue-700'">
          <p class="font-semibold">{{ workflowLabel }}</p>
          <p class="mt-1 text-sm">Revision {{ workflowState.setting_die_revision || 1 }}. {{ workflowState.next_action || '' }}</p>
        </div>

        <div class="grid gap-4 md:grid-cols-3">
          <label class="block"><span class="text-sm font-medium text-slate-700">Part No.</span><input :value="job.part_no || ''" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Lot No.</span><input v-model="form.lotNo" type="text" required readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Die No.</span><input :value="job.die_no || ''" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">D/H</span><input v-model="form.dh" :disabled="isLocked" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">SPM</span><input v-model="form.spm" :disabled="isLocked" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Material</span><input v-model="form.material" :disabled="isLocked" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Technician</span><input v-model="form.technician" :disabled="isLocked" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100" /></label>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label v-for="field in visibleTimeFields" :key="field.name" class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ field.label }}</span>
            <div class="mt-2 flex flex-col gap-2 sm:flex-row">
              <div class="min-w-0 flex-1 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3">
                <p class="font-medium" :class="form[field.name] ? 'text-slate-900' : 'text-slate-400'">{{ displayDatetime(form[field.name]) }}</p>
                <p v-if="form[field.name]" class="mt-1 text-xs text-slate-500">Stamped แล้ว แก้ไขไม่ได้</p>
              </div>
              <button type="button" :disabled="Boolean(form[field.name]) || isLocked" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500" @click="stamp(field.name)">Stamp</button>
            </div>
          </label>
        </div>

        <p v-if="noticeMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ noticeMessage }}</p>
        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{{ errorMessage }}</p>
        <p v-else-if="!canSaveSettingDie && !isLocked" class="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">{{ timeStartRequiredMessage }}</p>

        <div class="flex flex-wrap justify-end gap-3">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">Close</button>

          <button v-if="initialSent" type="button" disabled class="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 font-semibold text-emerald-700 disabled:cursor-not-allowed">✓ Sent to QC Line</button>
          <button v-else-if="canShowInitialSend" type="button" :disabled="isSubmitting || isSendingToQC || !canSaveSettingDie" :title="canSaveSettingDie ? 'Send initial handoff to QC Line' : timeStartRequiredMessage" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500" @click="openDialog('send')">{{ isSendingToQC ? 'Sending...' : 'Send to QC Line' }}</button>

          <button v-if="canStartCorrection" type="button" class="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-3 font-semibold text-amber-800 hover:bg-amber-100" @click="openDialog(approvalRequired ? 'request' : 'reopen')">{{ approvalRequired ? 'Request Correction' : 'Reopen for Correction' }}</button>
          <button v-if="correctionStatus === 'pending_approval'" type="button" disabled class="rounded-2xl border border-slate-200 bg-slate-100 px-5 py-3 font-semibold text-slate-600 disabled:cursor-not-allowed">Correction Approval Pending</button>
          <button v-if="correctionStatus === 'pending_approval' && isApprover" type="button" class="rounded-2xl bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-700" @click="openDialog('approve')">Approve</button>
          <button v-if="correctionStatus === 'pending_approval' && isApprover" type="button" class="rounded-2xl bg-red-600 px-5 py-3 font-semibold text-white hover:bg-red-700" @click="openDialog('reject')">Reject</button>
          <button v-if="correctionStatus === 'open' && isLastProcess" type="button" :disabled="isSubmitting || isWorkflowBusy" class="rounded-2xl bg-amber-600 px-5 py-3 font-semibold text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60" @click="openDialog('finish')">Finish Correction</button>

          <button v-if="!isLocked" type="submit" :disabled="isSubmitting || isSendingToQC || isWorkflowBusy || !canSaveSettingDie" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">{{ isSubmitting ? 'Saving...' : 'Save Setting Die' }}</button>
        </div>
      </form>
    </section>

    <WorkflowConfirmationDialog
      v-if="dialogType"
      v-bind="dialogConfig"
      :busy="isSendingToQC || isWorkflowBusy"
      @cancel="dialogType = ''"
      @confirm="confirmDialog"
    />
  </div>
</template>
