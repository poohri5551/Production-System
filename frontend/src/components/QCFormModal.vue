<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  getQCInspectionDetail,
  getQCPlanDetail,
  getQCPlanOptions,
  saveQCInspection,
  stampQCInspectionTimestamp,
} from '../api/client'
import WorkflowConfirmationDialog from './WorkflowConfirmationDialog.vue'

const props = defineProps({
  inspection: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  qcId: '',
  planId: '',
  partId: '',
  lotNo: '',
  partNo: '',
  timeStart: '',
  timeEnd: '',
  percent: '',
  status: '',
  problemArea: 'none',
  problemPoint: '',
  cause: '',
  solution: '',
  imageFile: null,
})

const planOptions = ref([])
const isLoadingPlans = ref(false)
const isSubmitting = ref(false)
const isStamping = ref(false)
const stampDialogField = ref('')
const uncertainTimestampFields = ref(new Set())
const errorMessage = ref('')
const noticeMessage = ref('')
let planLoadToken = 0

const timestampFields = [
  { formKey: 'timeStart', apiField: 'time_start', label: 'Time Start Inspection Part' },
  { formKey: 'timeEnd', apiField: 'time_end', label: 'Time End Inspection Part' },
]
const activeTimestampField = computed(() => (
  timestampFields.find((field) => field.apiField === stampDialogField.value) || null
))
const stampDialogConfig = computed(() => ({
  title: 'Confirm Timestamp',
  message: 'Record the current server time for this step? This timestamp can only be recorded once.',
  details: [
    { label: 'Lot No.', value: form.lotNo },
    { label: 'Part No.', value: form.partNo },
    { label: 'Field', value: activeTimestampField.value?.label },
  ],
  confirmLabel: 'Confirm Stamp',
  busyLabel: 'Stamping...',
  requireReason: false,
  danger: false,
}))

watch(
  () => props.inspection,
  (inspection) => {
    resetForm(inspection)
    loadPlanOptions(inspection?.lot_no || '')
  },
  { immediate: true },
)

function resetForm(inspection = null) {
  form.qcId = inspection?.id || ''
  form.planId = inspection?.plan_id || ''
  form.partId = inspection?.part_id || ''
  form.lotNo = inspection?.lot_no || ''
  form.partNo = inspection?.part_no || ''
  form.timeStart = inspection?.time_start || ''
  form.timeEnd = inspection?.time_end || ''
  form.percent = inspection?.percent_result || ''
  form.status = inspection?.status || ''
  form.problemArea = inspection?.problem_area || 'none'
  form.problemPoint = inspection?.problem_point || ''
  form.cause = inspection?.cause || ''
  form.solution = inspection?.solution || ''
  form.imageFile = null
  errorMessage.value = ''
  noticeMessage.value = ''
  stampDialogField.value = ''
  isStamping.value = false
  uncertainTimestampFields.value = new Set()
}

async function loadPlanOptions(selectedLotNo = '') {
  isLoadingPlans.value = true
  errorMessage.value = ''

  try {
    const data = await getQCPlanOptions()
    if (!Array.isArray(data)) {
      errorMessage.value = data.message || 'Cannot load Lot No. options'
      return
    }
    const plans = [...data]
    if (selectedLotNo && !plans.some((plan) => plan.lot_no === selectedLotNo)) {
      plans.push({
        plan_id: form.planId,
        part_id: form.partId,
        lot_no: selectedLotNo,
        part_no: form.partNo,
        qc_id: form.qcId,
        qc_time_start: form.timeStart,
        qc_time_end: form.timeEnd,
      })
    }
    planOptions.value = plans
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoadingPlans.value = false
  }
}

async function handlePlanChange() {
  const token = ++planLoadToken
  errorMessage.value = ''
  noticeMessage.value = ''
  stampDialogField.value = ''
  form.qcId = ''
  form.planId = ''
  form.partId = ''
  form.partNo = ''
  form.timeStart = ''
  form.timeEnd = ''
  uncertainTimestampFields.value = new Set()
  if (!form.lotNo) {
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.lot_no === form.lotNo)
  if (cachedPlan?.lot_no && cachedPlan?.part_no) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getQCPlanDetail(form.lotNo)
    if (token !== planLoadToken) return
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load selected Lot No.'
      return
    }
    if (!data.plan?.lot_no || !data.plan?.part_no) {
      errorMessage.value = 'Selected Lot No. is missing Part No.'
      return
    }
    applyPlan(data.plan)
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function applyPlan(plan) {
  form.qcId = plan.qc_id || ''
  form.planId = plan.plan_id || ''
  form.partId = plan.part_id || ''
  form.lotNo = plan.lot_no || ''
  form.partNo = plan.part_no || ''
  form.timeStart = plan.qc_time_start || ''
  form.timeEnd = plan.qc_time_end || ''
}

function handleImageChange(event) {
  form.imageFile = event.target.files?.[0] || null
}

function requestStamp(field) {
  if (
    isStamping.value
    || stampDialogField.value
    || form[field.formKey]
    || uncertainTimestampFields.value.has(field.apiField)
    || (!form.qcId && !form.planId)
  ) return
  errorMessage.value = ''
  noticeMessage.value = ''
  stampDialogField.value = field.apiField
}

function cancelStamp() {
  if (isStamping.value) return
  stampDialogField.value = ''
}

function applyTimestamp(fieldName, timestamp) {
  const field = timestampFields.find((item) => item.apiField === fieldName)
  if (field && timestamp) {
    form[field.formKey] = timestamp
    const uncertain = new Set(uncertainTimestampFields.value)
    uncertain.delete(fieldName)
    uncertainTimestampFields.value = uncertain
  }
}

async function refreshAuthoritativeTimestamps() {
  if (form.qcId) {
    const data = await getQCInspectionDetail(form.qcId)
    if (!data.success || !data.qc) return false
    form.partNo = data.qc.part_no || form.partNo
    form.partId = data.qc.part_id || form.partId
    form.planId = data.qc.plan_id || form.planId
    form.timeStart = data.qc.time_start || ''
    form.timeEnd = data.qc.time_end || ''
    return true
  }
  if (!form.lotNo) return false
  const data = await getQCPlanDetail(form.lotNo)
  if (!data.success || !data.plan) return false
  applyPlan(data.plan)
  return true
}

function markTimestampUncertain(fieldName) {
  uncertainTimestampFields.value = new Set(uncertainTimestampFields.value).add(fieldName)
}

async function confirmStamp() {
  const field = activeTimestampField.value
  if (!field || isStamping.value || form[field.formKey]) return
  isStamping.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const data = await stampQCInspectionTimestamp({
      qcId: form.qcId,
      planId: form.planId,
      field: field.apiField,
    })
    if (data.qc_id) form.qcId = data.qc_id
    if (data.timestamp && (data.success || data.already_stamped)) {
      applyTimestamp(field.apiField, data.timestamp)
      stampDialogField.value = ''
      noticeMessage.value = data.already_stamped
        ? `${field.label} was already stamped. Stored value reloaded.`
        : `${field.label} stamped successfully.`
      return
    }
    errorMessage.value = data.message || `Cannot stamp ${field.label}`
  } catch (error) {
    try {
      const refreshed = await refreshAuthoritativeTimestamps()
      if (refreshed && form[field.formKey]) {
        stampDialogField.value = ''
        noticeMessage.value = `${field.label} was recorded. Stored value reloaded.`
        return
      }
    } catch {
      // Re-query failed; block retry until modal reloads authoritative state.
    }
    markTimestampUncertain(field.apiField)
    stampDialogField.value = ''
    errorMessage.value = `${error.message || 'Cannot connect to backend'} Reload this QC inspection before trying again.`
  } finally {
    isStamping.value = false
  }
}

function displayDatetime(value) {
  if (!value) return 'Not stamped'
  const date = new Date(String(value).replace(' GMT', '').replace(' ', 'T'))
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ')
  return new Intl.DateTimeFormat('en-US', {
    month: '2-digit', day: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  }).format(date)
}

async function submitForm() {
  if (isSubmitting.value) return
  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('qc-id', form.qcId)
  formData.append('qc-plan-id', form.planId)
  formData.append('qc-lot-no', form.lotNo)
  formData.append('qc-percent', form.percent)
  formData.append('qc-status', form.status)
  formData.append('qc-problem-area', form.problemArea)
  formData.append('qc-problem-point', form.problemPoint)
  formData.append('qc-cause', form.cause)
  formData.append('qc-solution', form.solution)
  if (form.imageFile) formData.append('qc-image', form.imageFile)

  try {
    const data = await saveQCInspection(formData, form.qcId)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot save QC Inspection'
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
    <section class="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex flex-col gap-4 border-b border-blue-100 bg-white/95 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Quality control</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ form.qcId ? 'Edit QC Inspection' : 'QC Inspection' }}</h2>
          <p class="mt-1 text-sm text-slate-500">Select a Lot No. from active Setting Die data, then submit using the existing Flask fields.</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Lot No.</span>
            <select v-model="form.lotNo" required :disabled="Boolean(props.inspection?.id)" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:cursor-not-allowed disabled:bg-slate-100" @change="handlePlanChange">
              <option value="">{{ isLoadingPlans ? 'Loading Lot No...' : '-- Select Lot No. --' }}</option>
              <option v-for="plan in planOptions" :key="plan.lot_no" :value="plan.lot_no">
                {{ plan.lot_no }} / Part {{ plan.part_no || '-' }} / Die {{ plan.die_no || '-' }}
              </option>
            </select>
          </label>
          <div class="block md:col-span-2">
            <span class="text-sm font-medium text-slate-700">Part No.</span>
            <div class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 font-semibold text-slate-900">{{ form.partNo || '-' }}</div>
            <p class="mt-1 text-xs text-slate-500">Fixed from Production Plan</p>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div v-for="field in timestampFields" :key="field.apiField" class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ field.label }}</span>
            <div class="mt-2 flex flex-col gap-2 sm:flex-row">
              <div class="min-w-0 flex-1 rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3">
                <p class="font-medium" :class="form[field.formKey] ? 'text-slate-900' : 'text-slate-400'">{{ displayDatetime(form[field.formKey]) }}</p>
                <p v-if="form[field.formKey]" class="mt-1 text-xs text-slate-500">Stored timestamp is read-only.</p>
              </div>
              <button
                type="button"
                :disabled="Boolean(form[field.formKey]) || uncertainTimestampFields.has(field.apiField) || isStamping || Boolean(stampDialogField) || (!form.qcId && !form.planId)"
                class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
                @click="requestStamp(field)"
              >
                {{ isStamping && stampDialogField === field.apiField ? 'Stamping...' : form[field.formKey] ? '✓ Stamped' : 'Stamp' }}
              </button>
            </div>
          </div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Inspection Result (%)</span>
            <input v-model="form.percent" type="number" min="0" max="100" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Status</span>
            <select v-model="form.status" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
              <option value="">-- Select --</option>
              <option value="Wait">Wait</option>
              <option value="Pass">Pass</option>
              <option value="Fail">Fail</option>
            </select>
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Problem Area</span>
            <select v-model="form.problemArea" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
              <option value="none">No problem</option>
              <option value="trim">Trim line</option>
              <option value="surface">Surface</option>
              <option value="hole">Hole</option>
              <option value="appearance">Appearance</option>
            </select>
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Point</span>
            <input v-model="form.problemPoint" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
        </div>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Problem Image</span>
          <input type="file" accept="image/*" class="mt-2 w-full rounded-2xl border border-dashed border-blue-200 bg-white px-4 py-3 text-sm" @change="handleImageChange" />
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Cause</span>
            <textarea v-model="form.cause" rows="3" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"></textarea>
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Solution</span>
            <textarea v-model="form.solution" rows="3" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"></textarea>
          </label>
        </div>

        <p v-if="noticeMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {{ noticeMessage }}
        </p>
        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" :disabled="isSubmitting || isLoadingPlans" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : form.qcId ? 'Save Changes' : 'Save QC Inspection' }}
          </button>
        </div>
      </form>
    </section>
    <WorkflowConfirmationDialog
      v-if="stampDialogField"
      v-bind="stampDialogConfig"
      :busy="isStamping"
      @cancel="cancelStamp"
      @confirm="confirmStamp"
    />
  </div>
</template>
