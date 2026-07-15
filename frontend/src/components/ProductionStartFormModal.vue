<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  getProductionStartDetail,
  getProductionStartPlanDetail,
  getProductionStartPlanOptions,
  saveProductionStart,
  stampProductionStartTime,
} from '../api/client'
import WorkflowConfirmationDialog from './WorkflowConfirmationDialog.vue'

const props = defineProps({
  start: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close', 'saved', 'changed'])

const form = reactive({
  startId: '',
  lotNo: '',
  partNo: '',
  dieNo: '',
  qty: '',
  timeStart: '',
  planId: '',
  partId: '',
  confirmStatus: 'waiting',
})

const planOptions = ref([])
const isLoadingPlans = ref(false)
const isSubmitting = ref(false)
const isStamping = ref(false)
const stampDialogOpen = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')

const isEditMode = computed(() => Boolean(form.startId))
const isConfirmed = computed(() => form.confirmStatus === 'confirmed')
const canSubmit = computed(() => {
  if (isEditMode.value) return isConfirmed.value
  return Boolean(form.lotNo && form.partNo && form.dieNo && form.qty)
})
const canStamp = computed(() => (
  isEditMode.value
  && isConfirmed.value
  && !form.timeStart
  && !isStamping.value
))
const stampDetails = computed(() => [
  { label: 'Lot No.', value: form.lotNo },
  { label: 'Part No.', value: form.partNo },
  { label: 'Field', value: 'Production Start Time' },
])

watch(
  () => props.start,
  (start) => {
    resetForm(start)
    if (start?.id) {
      planOptions.value = []
    } else {
      loadPlanOptions()
    }
  },
  { immediate: true },
)

function resetForm(start = null) {
  form.startId = start?.id || ''
  form.lotNo = start?.lot_no || ''
  form.partNo = start?.part_no || ''
  form.dieNo = start?.die_no || ''
  form.qty = start?.qty || ''
  form.timeStart = start?.time_start || ''
  form.planId = start?.plan_id || ''
  form.partId = start?.part_id || ''
  form.confirmStatus = start?.confirm_status || 'waiting'
  stampDialogOpen.value = false
  errorMessage.value = ''
  noticeMessage.value = ''
}

async function loadPlanOptions() {
  isLoadingPlans.value = true
  errorMessage.value = ''
  try {
    const data = await getProductionStartPlanOptions()
    if (!Array.isArray(data)) {
      errorMessage.value = data.message || 'Cannot load Lot No. options'
      return
    }
    planOptions.value = data
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoadingPlans.value = false
  }
}

async function handlePlanChange() {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (!form.lotNo) {
    applyPlan({})
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.lot_no === form.lotNo)
  if (isCompletePlan(cachedPlan)) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getProductionStartPlanDetail(form.lotNo)
    if (!data.success || !isCompletePlan(data.plan)) {
      errorMessage.value = data.message || 'Selected Lot No. is missing Part, Die, or Q ty.'
      applyPlan({})
      return
    }
    applyPlan(data.plan)
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function isCompletePlan(plan) {
  return Boolean(plan?.lot_no && plan?.part_no && plan?.die_no && plan?.qty)
}

function applyPlan(plan) {
  form.lotNo = plan?.lot_no || ''
  form.partNo = plan?.part_no || ''
  form.dieNo = plan?.die_no || ''
  form.qty = plan?.qty || ''
  form.planId = plan?.plan_id || ''
  form.partId = plan?.part_id || ''
}

function displayDatetime(value) {
  if (!value) return 'Not stamped'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ')
  const pad = (number) => String(number).padStart(2, '0')
  const hour = date.getHours()
  const displayHour = hour % 12 || 12
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())}/${date.getFullYear()} ${pad(displayHour)}:${pad(date.getMinutes())} ${hour >= 12 ? 'PM' : 'AM'}`
}

function requestStamp() {
  if (!canStamp.value) return
  errorMessage.value = ''
  noticeMessage.value = ''
  stampDialogOpen.value = true
}

function cancelStamp() {
  if (isStamping.value) return
  stampDialogOpen.value = false
}

async function refreshAuthoritativeStart() {
  if (!form.startId) return
  const data = await getProductionStartDetail(form.startId)
  if (data.success) {
    form.timeStart = data.production_start?.time_start || ''
    form.confirmStatus = data.production_start?.confirm_status || form.confirmStatus
  }
}

async function confirmStamp() {
  if (!canStamp.value || !stampDialogOpen.value) return
  isStamping.value = true
  errorMessage.value = ''
  try {
    const data = await stampProductionStartTime(form.startId)
    if (!data.success && !data.already_stamped) {
      errorMessage.value = data.message || 'Cannot stamp Production Start Time'
      return
    }
    if (!data.timestamp) {
      await refreshAuthoritativeStart()
      errorMessage.value = 'Timestamp result was unclear. Reload this Production Start before trying again.'
      return
    }
    form.timeStart = data.timestamp
    stampDialogOpen.value = false
    noticeMessage.value = data.already_stamped
      ? 'Production Start Time was already stamped.'
      : 'Production Start Time stamped successfully.'
    emit('changed')
  } catch (error) {
    await refreshAuthoritativeStart().catch(() => {})
    errorMessage.value = error.message || 'Cannot connect to backend. Reload this Production Start before trying again.'
  } finally {
    isStamping.value = false
  }
}

async function submitForm() {
  if (isSubmitting.value) return
  if (!canSubmit.value) {
    errorMessage.value = isEditMode.value ? 'Confirm Production Start first' : 'Production Start data is incomplete.'
    return
  }
  errorMessage.value = ''
  noticeMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('start-id', form.startId)
  if (!isEditMode.value) formData.append('start-lot-no', form.lotNo)

  try {
    const data = await saveProductionStart(formData)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot save Production Start'
      return
    }
    emit('saved')
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex flex-col gap-4 border-b border-blue-100 bg-white/95 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Operator workflow</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ isEditMode ? 'Edit Production Start' : 'Production Start' }}</h2>
          <p class="mt-1 text-sm text-slate-500">{{ isEditMode ? 'Lot identity is fixed from the authoritative Production Plan.' : 'Choose an eligible Lot to create an unconfirmed Production Start record.' }}</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">Close</button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <label v-if="isEditMode" class="block">
          <span class="text-sm font-medium text-slate-700">Lot No.</span>
          <input :value="form.lotNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 font-semibold text-slate-700 outline-none" />
          <span class="mt-2 block text-xs text-slate-500">Fixed from Production Plan.</span>
        </label>
        <label v-else class="block">
          <span class="text-sm font-medium text-slate-700">Lot No.</span>
          <select v-model="form.lotNo" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" @change="handlePlanChange">
            <option value="">{{ isLoadingPlans ? 'Loading Lot No...' : '-- Select Lot No. --' }}</option>
            <option v-for="plan in planOptions" :key="plan.lot_no" :value="plan.lot_no">{{ plan.lot_no }} / Part {{ plan.part_no || '-' }} / Die {{ plan.die_no || '-' }}</option>
          </select>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block"><span class="text-sm font-medium text-slate-700">Part No.</span><input :value="form.partNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Die No.</span><input :value="form.dieNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
          <label class="block"><span class="text-sm font-medium text-slate-700">Q'ty to produce</span><input :value="form.qty" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" /></label>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4"><p class="text-xs text-slate-500">Plan ID</p><p class="font-semibold text-slate-900">{{ form.planId || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4"><p class="text-xs text-slate-500">Part ID</p><p class="font-semibold text-slate-900">{{ form.partId || '-' }}</p></div>
        </div>

        <div class="block rounded-3xl border border-blue-100 p-4">
          <span class="text-sm font-medium text-slate-700">Production Start Time</span>
          <div class="mt-2 flex flex-col gap-2 sm:flex-row">
            <div class="min-w-0 flex-1 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3">
              <p class="font-medium" :class="form.timeStart ? 'text-slate-900' : 'text-slate-400'">{{ displayDatetime(form.timeStart) }}</p>
              <p class="mt-1 text-xs text-slate-500">Stored timestamp is read-only.</p>
            </div>
            <button v-if="form.timeStart" type="button" disabled class="cursor-not-allowed rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">✓ Stamped</button>
            <button v-else type="button" :disabled="!canStamp" :title="!isEditMode || !isConfirmed ? 'Confirm Production Start first' : 'Record current server time'" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500" @click="requestStamp">{{ isStamping ? 'Stamping...' : 'Stamp' }}</button>
          </div>
        </div>

        <p v-if="noticeMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ noticeMessage }}</p>
        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{{ errorMessage }}</p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">Cancel</button>
          <button type="submit" :disabled="isSubmitting || isLoadingPlans || !canSubmit" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">{{ isSubmitting ? 'Saving...' : isEditMode ? 'Save Changes' : 'Save Production Start' }}</button>
        </div>
      </form>
    </section>

    <WorkflowConfirmationDialog
      v-if="stampDialogOpen"
      title="Confirm Timestamp"
      message="Record the current server time for Production Start? This timestamp can only be recorded once."
      :details="stampDetails"
      confirm-label="Confirm Stamp"
      busy-label="Stamping..."
      :busy="isStamping"
      @cancel="cancelStamp"
      @confirm="confirmStamp"
    />
  </div>
</template>
