<script setup>
import { reactive, ref, watch } from 'vue'
import { getQCPlanDetail, getQCPlanOptions, saveQCInspection } from '../api/client'

const props = defineProps({
  inspection: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  qcId: '',
  lotNo: '',
  planNo: '',
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
const errorMessage = ref('')

watch(
  () => props.inspection,
  (inspection) => {
    resetForm(inspection)
    loadPlanOptions(inspection?.plan_no || '')
  },
  { immediate: true },
)

function resetForm(inspection = null) {
  form.qcId = inspection?.id || ''
  form.lotNo = inspection?.lot_no || ''
  form.planNo = inspection?.plan_no || ''
  form.partNo = inspection?.part_no || ''
  form.timeStart = toDatetimeLocal(inspection?.time_start)
  form.timeEnd = toDatetimeLocal(inspection?.time_end)
  form.percent = inspection?.percent_result || ''
  form.status = inspection?.status || ''
  form.problemArea = inspection?.problem_area || 'none'
  form.problemPoint = inspection?.problem_point || ''
  form.cause = inspection?.cause || ''
  form.solution = inspection?.solution || ''
  form.imageFile = null
  errorMessage.value = ''
}

async function loadPlanOptions(selectedPlanNo = '') {
  isLoadingPlans.value = true
  errorMessage.value = ''

  try {
    const data = await getQCPlanOptions()
    if (!Array.isArray(data)) {
      errorMessage.value = data.message || 'Cannot load Plan No. options'
      return
    }
    const plans = [...data]
    if (selectedPlanNo && !plans.some((plan) => plan.plan_no === selectedPlanNo)) {
      plans.push({
        plan_no: selectedPlanNo,
        lot_no: form.lotNo,
        part_no: form.partNo,
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
  errorMessage.value = ''
  if (!form.planNo) {
    form.lotNo = ''
    form.partNo = ''
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.plan_no === form.planNo)
  if (cachedPlan?.lot_no && cachedPlan?.part_no) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getQCPlanDetail(form.planNo)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load selected Plan No.'
      return
    }
    if (!data.plan?.lot_no || !data.plan?.part_no) {
      errorMessage.value = 'Selected Plan No. is missing Lot No. or Part No.'
      return
    }
    applyPlan(data.plan)
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function applyPlan(plan) {
  form.lotNo = plan.lot_no || ''
  form.partNo = plan.part_no || ''
}

function handleImageChange(event) {
  form.imageFile = event.target.files?.[0] || null
}

function stamp(fieldName) {
  form[fieldName] = currentDatetimeLocal()
}

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

async function submitForm() {
  if (isSubmitting.value) return
  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('qc-id', form.qcId)
  formData.append('qc-lot-no', form.lotNo)
  formData.append('qc-plan-no', form.planNo)
  formData.append('qc-part-no', form.partNo)
  formData.append('qc-time-start', form.timeStart)
  formData.append('qc-time-end', form.timeEnd)
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
          <p class="mt-1 text-sm text-slate-500">Select a Plan No. from active Setting Die data, then submit using the existing Flask fields.</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Lot No.</span>
            <input v-model="form.lotNo" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Plan No.</span>
            <select v-model="form.planNo" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" @change="handlePlanChange">
              <option value="">{{ isLoadingPlans ? 'Loading Plan No...' : '-- Select Plan No. --' }}</option>
              <option v-for="plan in planOptions" :key="plan.plan_no" :value="plan.plan_no">
                {{ plan.plan_no }} / Lot {{ plan.lot_no || '-' }} / Part {{ plan.part_no || '-' }} / Die {{ plan.die_no || '-' }}
              </option>
            </select>
          </label>
          <label class="block md:col-span-2">
            <span class="text-sm font-medium text-slate-700">Part No.</span>
            <input v-model="form.partNo" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Time Start Inspection Part</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.timeStart" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('timeStart')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Time End Inspection Part</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.timeEnd" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('timeEnd')">Stamp</button>
            </div>
          </label>
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
  </div>
</template>
