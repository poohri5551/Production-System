<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  getProductionFinishPlanDetail,
  getProductionFinishPlanOptions,
  saveProductionFinish,
  stampProductionFinishTimestamp,
} from '../api/client'
import WorkflowConfirmationDialog from './WorkflowConfirmationDialog.vue'

const props = defineProps({
  finish: { type: Object, default: null },
})

const emit = defineEmits(['close', 'saved', 'changed'])

const form = reactive({
  finishId: '',
  lotNo: '',
  partNo: '',
  dieNo: '',
  plannedQty: '',
  actualQty: '',
  note: '',
  timeFinish: '',
  holdTime: '',
  planId: '',
  partId: '',
})

const planOptions = ref([])
const isLoadingPlans = ref(false)
const isSubmitting = ref(false)
const isStamping = ref(false)
const stampDialogField = ref('')
const errorMessage = ref('')
const noticeMessage = ref('')

const isEditMode = computed(() => Boolean(form.finishId))
const canSubmit = computed(() => {
  return !isEditMode.value && Boolean(form.lotNo && form.actualQty !== '')
})
const activeTimestamp = computed(() => {
  if (stampDialogField.value === 'time_finish') {
    return {
      formKey: 'timeFinish',
      title: 'Confirm Finish Timestamp',
      message: 'Record the current time as Production Finish Time? This timestamp can only be recorded once.',
      confirmLabel: 'Confirm Stamp',
      busyLabel: 'Stamping...',
    }
  }
  if (stampDialogField.value === 'hold_time') {
    return {
      formKey: 'holdTime',
      title: 'Confirm Hold Production',
      message: 'Record the current time as Hold Production Time? This timestamp can only be recorded once.',
      confirmLabel: 'Confirm Hold',
      busyLabel: 'Holding...',
    }
  }
  return null
})
const confirmationDetails = computed(() => [
  { label: 'Lot No.', value: form.lotNo },
  { label: 'Part No.', value: form.partNo },
])

watch(
  () => props.finish,
  (finish) => {
    resetForm(finish)
    if (!finish?.id) loadPlanOptions()
  },
  { immediate: true },
)

function resetForm(finish = null) {
  form.finishId = finish?.id || ''
  form.lotNo = finish?.lot_no || ''
  form.partNo = finish?.part_no || ''
  form.dieNo = finish?.die_no || ''
  form.plannedQty = finish?.planned_qty || ''
  form.actualQty = finish?.actual_qty || ''
  form.note = finish?.note || ''
  form.timeFinish = finish?.time_finish || ''
  form.holdTime = finish?.hold_time || ''
  form.planId = finish?.plan_id || ''
  form.partId = finish?.part_id || ''
  stampDialogField.value = ''
  errorMessage.value = ''
  noticeMessage.value = ''
}

async function loadPlanOptions() {
  isLoadingPlans.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionFinishPlanOptions()
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
  if (!form.lotNo) {
    applyPlan({})
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.lot_no === form.lotNo)
  if (cachedPlan?.lot_no) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getProductionFinishPlanDetail(form.lotNo)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load selected Lot No.'
      applyPlan({})
      return
    }
    if (!data.plan?.lot_no) {
      errorMessage.value = 'Selected Lot No. is missing Lot No.'
      applyPlan({})
      return
    }
    applyPlan(data.plan)
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function applyPlan(plan) {
  form.lotNo = plan?.lot_no || ''
  form.partNo = plan?.part_no || ''
  form.dieNo = plan?.die_no || ''
  form.plannedQty = plan?.qty || ''
  form.planId = plan?.plan_id || ''
  form.partId = plan?.part_id || ''
}

function displayDatetime(value, emptyLabel) {
  if (!value) return emptyLabel
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ')
  const pad = (number) => String(number).padStart(2, '0')
  const hour = date.getHours()
  const displayHour = hour % 12 || 12
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())}/${date.getFullYear()} ${pad(displayHour)}:${pad(date.getMinutes())} ${hour >= 12 ? 'PM' : 'AM'}`
}

function requestTimestamp(field) {
  if (!form.finishId || isStamping.value || stampDialogField.value) return
  if (field === 'time_finish' && form.timeFinish) return
  if (field === 'hold_time' && form.holdTime) return
  errorMessage.value = ''
  noticeMessage.value = ''
  stampDialogField.value = field
}

function cancelTimestamp() {
  if (isStamping.value) return
  stampDialogField.value = ''
}

async function confirmTimestamp() {
  const config = activeTimestamp.value
  const field = stampDialogField.value
  if (!config || !form.finishId || isStamping.value) return
  isStamping.value = true
  errorMessage.value = ''
  try {
    const data = await stampProductionFinishTimestamp(form.finishId, field)
    if (!data.success && !data.already_stamped) {
      errorMessage.value = data.message || 'Cannot record Production Finish timestamp'
      return
    }
    if (!data.timestamp) {
      errorMessage.value = 'Timestamp result was unclear. Close and reopen this Production Finish.'
      return
    }
    form[config.formKey] = data.timestamp
    stampDialogField.value = ''
    noticeMessage.value = data.already_stamped
      ? `${field === 'time_finish' ? 'Production Finish Time' : 'Hold Production Time'} was already recorded.`
      : `${field === 'time_finish' ? 'Production Finish Time stamped' : 'Production hold recorded'} successfully.`
    emit('changed')
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend. Close and reopen this Production Finish.'
  } finally {
    isStamping.value = false
  }
}

async function submitForm() {
  if (isSubmitting.value) return
  if (!canSubmit.value) {
    errorMessage.value = 'Production Finish data is incomplete.'
    return
  }
  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('finish-lot-no', form.lotNo)
  formData.append('finish-actual-qty', form.actualQty)
  formData.append('finish-note', form.note)

  try {
    const data = await saveProductionFinish(formData)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot save Production Finish'
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
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Final workflow step</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ isEditMode ? 'Production Finish Timestamps' : 'Production Finish' }}</h2>
          <p class="mt-1 text-sm text-slate-500">{{ isEditMode ? 'Recorded timestamps are permanent and read-only.' : 'Save Production Finish, then use its Timestamps action to record server time.' }}</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <label v-if="!isEditMode" class="block">
          <span class="text-sm font-medium text-slate-700">Lot No.</span>
          <select v-model="form.lotNo" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" @change="handlePlanChange">
            <option value="">{{ isLoadingPlans ? 'Loading Lot No...' : '-- Select Lot No. --' }}</option>
            <option v-for="plan in planOptions" :key="plan.lot_no" :value="plan.lot_no">
              {{ plan.lot_no }} / Part {{ plan.part_no || '-' }} / Qty {{ plan.qty || '-' }}
            </option>
          </select>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Actual Q'ty</span>
            <input v-if="!isEditMode" v-model="form.actualQty" type="number" min="0" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
            <p v-else class="mt-2 rounded-2xl bg-slate-50 px-4 py-3 font-semibold text-slate-900">{{ form.actualQty || '-' }}</p>
          </label>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Part No.</p>
            <p class="font-semibold text-slate-900">{{ form.partNo || '-' }}</p>
          </div>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Die No.</p>
            <p class="font-semibold text-slate-900">{{ form.dieNo || '-' }}</p>
          </div>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Planned Q'ty</p>
            <p class="font-semibold text-slate-900">{{ form.plannedQty || '-' }}</p>
          </div>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Plan ID / Part ID</p>
            <p class="font-semibold text-slate-900">{{ form.planId || '-' }} / {{ form.partId || '-' }}</p>
          </div>
        </div>

        <label v-if="!isEditMode" class="block">
          <span class="text-sm font-medium text-slate-700">Note</span>
          <textarea v-model="form.note" rows="3" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"></textarea>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Finish Time</span>
            <div class="mt-2 flex flex-col gap-2 sm:flex-row">
              <div class="min-w-0 flex-1 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 font-medium" :class="form.timeFinish ? 'text-slate-900' : 'text-slate-400'">{{ displayDatetime(form.timeFinish, 'Not stamped') }}</div>
              <button v-if="form.timeFinish" type="button" disabled class="cursor-not-allowed rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">✓ Stamped</button>
              <button v-else type="button" :disabled="!form.finishId || isStamping || Boolean(stampDialogField)" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500" @click="requestTimestamp('time_finish')">{{ isStamping && stampDialogField === 'time_finish' ? 'Stamping...' : 'Stamp' }}</button>
            </div>
          </div>
          <div class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Hold Production</span>
            <div class="mt-2 flex flex-col gap-2 sm:flex-row">
              <div class="min-w-0 flex-1 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 font-medium" :class="form.holdTime ? 'text-slate-900' : 'text-slate-400'">{{ displayDatetime(form.holdTime, 'Not held') }}</div>
              <button v-if="form.holdTime" type="button" disabled class="cursor-not-allowed rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">✓ Held</button>
              <button v-else type="button" :disabled="!form.finishId || isStamping || Boolean(stampDialogField)" class="rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-semibold text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500" @click="requestTimestamp('hold_time')">{{ isStamping && stampDialogField === 'hold_time' ? 'Holding...' : 'Hold' }}</button>
            </div>
          </div>
        </div>

        <p v-if="noticeMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ noticeMessage }}</p>
        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button v-if="!isEditMode" type="submit" :disabled="isSubmitting || isLoadingPlans || !canSubmit" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : 'Save Production Finish' }}
          </button>
        </div>
      </form>
    </section>
    <WorkflowConfirmationDialog
      v-if="activeTimestamp"
      :title="activeTimestamp.title"
      :message="activeTimestamp.message"
      :details="confirmationDetails"
      :confirm-label="activeTimestamp.confirmLabel"
      :busy-label="activeTimestamp.busyLabel"
      :busy="isStamping"
      @cancel="cancelTimestamp"
      @confirm="confirmTimestamp"
    />
  </div>
</template>
