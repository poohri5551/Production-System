<script setup>
import { computed, ref, watch } from 'vue'
import { createProductionStartFromQC } from '../api/client'
import WorkflowConfirmationDialog from './WorkflowConfirmationDialog.vue'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'

const props = defineProps({
  inspection: { type: Object, required: true },
  canNotifyOperator: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const isNotifying = ref(false)
const isConfirming = ref(false)
const operatorNotified = ref(false)
const notifyMessage = ref('')
const notifyError = ref('')

watch(() => props.inspection, () => {
  operatorNotified.value = Boolean(props.inspection?.operator_notified_at)
  isConfirming.value = false
  notifyMessage.value = ''
  notifyError.value = ''
}, { immediate: true })

const qcPass = computed(() => ['pass', 'passed'].includes(String(props.inspection.status || '').trim().toLowerCase()))
const revisionCurrent = computed(() => Number(props.inspection.qc_revision_current) === 1 || props.inspection.qc_revision_current === true)
const canSend = computed(() => props.canNotifyOperator && qcPass.value && revisionCurrent.value && !operatorNotified.value)
const unavailableReason = computed(() => {
  if (!revisionCurrent.value) return 'QC recheck required for latest Setting Die revision.'
  if (!qcPass.value) return 'Cannot notify Operator: QC status must be Pass.'
  return ''
})

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function imageUrl(path) {
  return path ? `/static/uploads/${path}` : ''
}

function requestNotify() {
  notifyError.value = ''
  if (!canSend.value) {
    notifyError.value = unavailableReason.value
    return
  }
  isConfirming.value = true
}

async function confirmNotify() {
  if (!canSend.value || isNotifying.value) return
  isNotifying.value = true
  notifyError.value = ''
  notifyMessage.value = ''
  try {
    const data = await createProductionStartFromQC(props.inspection)
    if (!data.success) {
      notifyError.value = data.message || 'Cannot notify Operator'
      return
    }
    operatorNotified.value = true
    isConfirming.value = false
    notifyMessage.value = data.already_sent
      ? 'Initial Operator handoff was already sent.'
      : 'Operator notified. Production Start record prepared once.'
  } catch (error) {
    notifyError.value = error.message || 'Cannot connect to backend'
  } finally {
    isNotifying.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex flex-col gap-4 border-b border-blue-100 bg-white/95 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div><p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">QC detail</p><h2 class="mt-2 text-2xl font-semibold text-slate-950">QC Inspection Detail</h2></div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">Close</button>
      </div>

      <div class="space-y-5 overflow-y-auto p-6">
        <div v-if="!revisionCurrent" class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800">
          <p class="font-semibold">QC Recheck Required</p>
          <p class="mt-1 text-sm">This inspection reviewed Setting Die revision {{ inspection.setting_die_revision || 1 }}. Current revision is {{ inspection.current_setting_die_revision || '-' }}.</p>
        </div>
        <div v-else-if="qcPass" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-emerald-700">
          <p class="font-semibold">QC Current - Setting Die revision {{ inspection.setting_die_revision || 1 }}</p>
        </div>
        <div v-else class="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800">
          <p class="font-semibold">QC Review Required - Current Revision</p>
          <p class="mt-1 text-sm">Complete QC inspection for Setting Die revision {{ inspection.setting_die_revision || 1 }}.</p>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Lot No.</p><p class="font-semibold text-slate-900">{{ inspection.lot_no || '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Part No.</p><p class="font-semibold text-slate-900">{{ inspection.part_no || '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Result (%)</p><p class="font-semibold text-slate-900">{{ inspection.percent_result ? `${inspection.percent_result}%` : '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Start</p><p class="font-semibold text-slate-900">{{ formatDateTime(inspection.time_start) }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">End</p><p class="font-semibold text-slate-900">{{ formatDateTime(inspection.time_end) }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">State</p><WorkflowStatusBadge class="mt-2" stage="QC" :status="inspection.status" /></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Problem Area</p><p class="font-semibold text-slate-900">{{ inspection.problem_area || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Point</p><p class="font-semibold text-slate-900">{{ inspection.problem_point || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Cause</p><p class="font-semibold text-slate-900">{{ inspection.cause || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Solution</p><p class="font-semibold text-slate-900">{{ inspection.solution || '-' }}</p></div>
        </div>

        <div class="rounded-2xl border border-blue-100 p-4"><img v-if="inspection.image_path" :src="imageUrl(inspection.image_path)" alt="QC problem" class="max-h-80 rounded-2xl object-contain" /><p v-else class="text-sm text-slate-500">No image attached.</p></div>
        <p v-if="notifyMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ notifyMessage }}</p>
        <p v-if="notifyError" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{{ notifyError }}</p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">Close</button>
          <button v-if="operatorNotified" type="button" disabled class="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 font-semibold text-emerald-700 disabled:cursor-not-allowed">✓ Operator Notified</button>
          <button v-else-if="canNotifyOperator" type="button" :disabled="!canSend || isNotifying" :title="unavailableReason" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500" @click="requestNotify">{{ isNotifying ? 'Notifying...' : 'Notify Operator' }}</button>
        </div>
      </div>
    </section>

    <WorkflowConfirmationDialog
      v-if="isConfirming"
      title="Confirm Notify Operator"
      message="Notify Operator that this Lot is ready for Production Start? This initial handoff can only be sent once."
      :details="[
        { label: 'Lot No.', value: inspection.lot_no },
        { label: 'Part No.', value: inspection.part_no },
        { label: 'Destination', value: 'Operator / Production Start' },
      ]"
      confirm-label="Confirm Notify"
      busy-label="Notifying..."
      :busy="isNotifying"
      @cancel="isConfirming = false"
      @confirm="confirmNotify"
    />
  </div>
</template>
