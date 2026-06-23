<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  getProductionStartPlanDetail,
  getProductionStartPlanOptions,
  saveProductionStart,
} from '../api/client'

const props = defineProps({
  start: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  startId: '',
  planNo: '',
  lotNo: '',
  partNo: '',
  dieNo: '',
  qty: '',
  timeStart: '',
  planId: '',
  partId: '',
})

const planOptions = ref([])
const isLoadingPlans = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref('')

const canSubmit = computed(() => {
  return Boolean(form.planNo && form.lotNo && form.partNo && form.dieNo && form.qty && form.timeStart)
})

watch(
  () => props.start,
  (start) => {
    resetForm(start)
    loadPlanOptions(start?.plan_no || '')
  },
  { immediate: true },
)

function resetForm(start = null) {
  form.startId = start?.id || ''
  form.planNo = start?.plan_no || ''
  form.lotNo = start?.lot_no || ''
  form.partNo = start?.part_no || ''
  form.dieNo = start?.die_no || ''
  form.qty = start?.qty || ''
  form.timeStart = toDatetimeLocal(start?.time_start) || currentDatetimeLocal()
  form.planId = start?.plan_id || ''
  form.partId = start?.part_id || ''
  errorMessage.value = ''
}

async function loadPlanOptions(selectedPlanNo = '') {
  isLoadingPlans.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionStartPlanOptions()
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
        die_no: form.dieNo,
        qty: form.qty,
        plan_id: form.planId,
        part_id: form.partId,
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
    applyPlan({})
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.plan_no === form.planNo)
  if (isCompletePlan(cachedPlan)) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getProductionStartPlanDetail(form.planNo)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load selected Plan No.'
      applyPlan({})
      return
    }
    if (!isCompletePlan(data.plan)) {
      errorMessage.value = 'Selected Plan No. is missing Lot, Part, Die, or Q ty.'
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

function stamp() {
  form.timeStart = currentDatetimeLocal()
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
  if (!canSubmit.value) {
    errorMessage.value = 'Production Start data is incomplete.'
    return
  }
  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('start-id', form.startId)
  formData.append('start-plan-no', form.planNo)
  formData.append('start-lot-no', form.lotNo)
  formData.append('start-part-no', form.partNo)
  formData.append('start-die-no', form.dieNo)
  formData.append('start-qty', form.qty)
  formData.append('start-time-start', form.timeStart)

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
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ form.startId ? 'Edit Production Start' : 'Production Start' }}</h2>
          <p class="mt-1 text-sm text-slate-500">Plan options come from active Setting Die records and exclude plans with active Production Start.</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <label class="block">
          <span class="text-sm font-medium text-slate-700">Plan No.</span>
          <select v-model="form.planNo" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" @change="handlePlanChange">
            <option value="">{{ isLoadingPlans ? 'Loading Plan No...' : '-- Select Plan No. --' }}</option>
            <option v-for="plan in planOptions" :key="plan.plan_no" :value="plan.plan_no">
              {{ plan.plan_no }} / Lot {{ plan.lot_no || '-' }} / Part {{ plan.part_no || '-' }} / Die {{ plan.die_no || '-' }}
            </option>
          </select>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Lot No.</span>
            <input v-model="form.lotNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Part No.</span>
            <input v-model="form.partNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Die No.</span>
            <input v-model="form.dieNo" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Q'ty to produce</span>
            <input v-model="form.qty" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Plan ID</p>
            <p class="font-semibold text-slate-900">{{ form.planId || '-' }}</p>
          </div>
          <div class="rounded-2xl border border-blue-100 bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Part ID</p>
            <p class="font-semibold text-slate-900">{{ form.partId || '-' }}</p>
          </div>
        </div>

        <label class="block rounded-3xl border border-blue-100 p-4">
          <span class="text-sm font-medium text-slate-700">Production Start Time</span>
          <div class="mt-2 flex gap-2">
            <input v-model="form.timeStart" type="datetime-local" required class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
            <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp">Stamp</button>
          </div>
        </label>

        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" :disabled="isSubmitting || isLoadingPlans || !canSubmit" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : form.startId ? 'Save Changes' : 'Save Production Start' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
