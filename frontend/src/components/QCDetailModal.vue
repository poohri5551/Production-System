<script setup>
import { ref } from 'vue'
import { createProductionStartFromQC } from '../api/client'

const props = defineProps({
  inspection: {
    type: Object,
    required: true,
  },
  canNotifyOperator: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close'])

const isNotifying = ref(false)
const notifyMessage = ref('')
const notifyError = ref('')

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

async function notifyOperator() {
  if (!props.canNotifyOperator) return
  if (String(props.inspection.status || '').toLowerCase() !== 'pass') {
    notifyError.value = 'Cannot notify operator: QC status must be Pass.'
    notifyMessage.value = ''
    return
  }
  if (isNotifying.value) return
  isNotifying.value = true
  notifyError.value = ''
  notifyMessage.value = ''

  try {
    const data = await createProductionStartFromQC(props.inspection)
    if (!data.success) {
      notifyError.value = data.message || 'Cannot notify operator'
      return
    }
    notifyMessage.value = 'Operator notification sent. Production Start record was prepared by backend.'
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
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">QC detail</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">QC Inspection Detail</h2>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <div class="space-y-5 overflow-y-auto p-6">
        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Lot No.</p><p class="font-semibold text-slate-900">{{ inspection.lot_no || '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Plan No.</p><p class="font-semibold text-slate-900">{{ inspection.plan_no || '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Part No.</p><p class="font-semibold text-slate-900">{{ inspection.part_no || '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Result (%)</p><p class="font-semibold text-slate-900">{{ inspection.percent_result ? `${inspection.percent_result}%` : '-' }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Start</p><p class="font-semibold text-slate-900">{{ formatDateTime(inspection.time_start) }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">End</p><p class="font-semibold text-slate-900">{{ formatDateTime(inspection.time_end) }}</p></div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Status</p>
            <p class="font-semibold" :class="String(inspection.status || '').toLowerCase() === 'pass' ? 'text-emerald-700' : 'text-red-700'">{{ inspection.status || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4"><p class="text-xs text-slate-500">Problem Area</p><p class="font-semibold text-slate-900">{{ inspection.problem_area || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Point</p><p class="font-semibold text-slate-900">{{ inspection.problem_point || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Cause</p><p class="font-semibold text-slate-900">{{ inspection.cause || '-' }}</p></div>
          <div class="rounded-2xl border border-blue-100 p-4 md:col-span-2"><p class="text-xs text-slate-500">Solution</p><p class="font-semibold text-slate-900">{{ inspection.solution || '-' }}</p></div>
        </div>

        <div class="rounded-2xl border border-blue-100 p-4">
          <img v-if="inspection.image_path" :src="imageUrl(inspection.image_path)" alt="QC problem" class="max-h-80 rounded-2xl object-contain" />
          <p v-else class="text-sm text-slate-500">No image attached.</p>
        </div>

        <p v-if="notifyMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ notifyMessage }}</p>
        <p v-if="notifyError" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{{ notifyError }}</p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Close
          </button>
          <button v-if="canNotifyOperator" type="button" :disabled="isNotifying" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60" @click="notifyOperator">
            {{ isNotifying ? 'Sending...' : 'Notify Operator: Start Production' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>
