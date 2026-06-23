<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  getProductionFinishPlanDetail,
  getProductionFinishPlanOptions,
  saveProductionFinish,
} from '../api/client'

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  planNo: '',
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
const errorMessage = ref('')

const canSubmit = computed(() => {
  return Boolean(form.planNo && form.lotNo && form.actualQty !== '' && form.timeFinish)
})

watch(
  () => true,
  () => {
    resetForm()
    loadPlanOptions()
  },
  { immediate: true },
)

function resetForm() {
  form.planNo = ''
  form.lotNo = ''
  form.partNo = ''
  form.dieNo = ''
  form.plannedQty = ''
  form.actualQty = ''
  form.note = ''
  form.timeFinish = currentDatetimeLocal()
  form.holdTime = ''
  form.planId = ''
  form.partId = ''
  errorMessage.value = ''
}

async function loadPlanOptions() {
  isLoadingPlans.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionFinishPlanOptions()
    if (!Array.isArray(data)) {
      errorMessage.value = data.message || 'Cannot load Plan No. options'
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
  if (!form.planNo) {
    applyPlan({})
    return
  }

  const cachedPlan = planOptions.value.find((plan) => plan.plan_no === form.planNo)
  if (cachedPlan?.lot_no) {
    applyPlan(cachedPlan)
    return
  }

  try {
    const data = await getProductionFinishPlanDetail(form.planNo)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load selected Plan No.'
      applyPlan({})
      return
    }
    if (!data.plan?.lot_no) {
      errorMessage.value = 'Selected Plan No. is missing Lot No.'
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

function stamp(fieldName) {
  form[fieldName] = currentDatetimeLocal()
}

function currentDatetimeLocal() {
  const date = new Date()
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
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
  formData.append('finish-plan-no', form.planNo)
  formData.append('finish-lot-no', form.lotNo)
  formData.append('finish-actual-qty', form.actualQty)
  formData.append('finish-note', form.note)
  formData.append('finish-time-finish', form.timeFinish)
  formData.append('finish-hold-time', form.holdTime)

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
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">Production Finish</h2>
          <p class="mt-1 text-sm text-slate-500">Choose an active Production Start plan, then record actual output and finish time.</p>
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
              {{ plan.plan_no }} / Lot {{ plan.lot_no || '-' }} / Part {{ plan.part_no || '-' }} / Qty {{ plan.qty || '-' }}
            </option>
          </select>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Lot No.</span>
            <input v-model="form.lotNo" type="text" readonly required class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Actual Q'ty</span>
            <input v-model="form.actualQty" type="number" min="0" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
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

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Note</span>
          <textarea v-model="form.note" rows="3" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"></textarea>
        </label>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Finish Time</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.timeFinish" type="datetime-local" required class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('timeFinish')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">Hold Production</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.holdTime" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl border border-blue-100 px-4 py-3 text-sm font-semibold text-blue-700 hover:bg-blue-50" @click="stamp('holdTime')">Hold</button>
            </div>
          </label>
        </div>

        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" :disabled="isSubmitting || isLoadingPlans || !canSubmit" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : 'Save Production Finish' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
