<script setup>
import { reactive, ref, watch } from 'vue'
import { saveSettingDie, sendSettingDieToQCLine } from '../api/client'

const props = defineProps({
  job: {
    type: Object,
    required: true,
  },
  setting: {
    type: Object,
    default: null,
  },
  canSendToQc: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  lotNo: '',
  planNo: '',
  processDie: '',
  dh: '',
  spm: '',
  timeStart: '',
  timeEnd: '',
  material: '',
  materialStart: '',
  materialEnd: '',
  adjustStart: '',
  adjustEnd: '',
  technician: '',
})

const isSubmitting = ref(false)
const isSendingToQC = ref(false)
const errorMessage = ref('')

// UI labels only. Keep existing form fields and backend payload names unchanged.
const timeFieldLabels = {
  timeStart: 'Time Start Setting Die',
  timeEnd: 'Time End Setting Die',
  materialStart: 'Time Start Setting Material',
  materialEnd: 'Time End Setting Material',
  adjustStart: 'Time Start Adjust Accuracy Part',
  adjustEnd: 'Time End Adjust Accuracy Part',
}

watch(
  () => [props.job, props.setting],
  () => {
    const setting = props.setting || {}
    form.lotNo = setting.lot_no || ''
    form.planNo = setting.plan_no || ''
    form.processDie = setting.process_die || ''
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
    errorMessage.value = ''
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
  form[fieldName] = currentDatetimeLocal()
}

async function submitForm() {
  if (isSubmitting.value || isSendingToQC.value) return
  errorMessage.value = ''
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

async function sendToQCLine() {
  if (isSubmitting.value || isSendingToQC.value) return
  if (!form.planNo.trim()) {
    errorMessage.value = 'Plan No. is required before sending to QC Line.'
    return
  }

  errorMessage.value = ''
  isSendingToQC.value = true

  try {
    const saveResult = await saveCurrentSettingDie()
    if (!saveResult.success) {
      errorMessage.value = saveResult.message || 'Cannot save Setting Die before sending to QC Line'
      return
    }

    const sendResult = await sendSettingDieToQCLine(form.planNo)
    if (!sendResult.success) {
      errorMessage.value = sendResult.message || 'Cannot send Setting Die to QC Line'
      return
    }

    emit('saved', sendResult.created ? 'Setting Die saved and sent to QC Line.' : 'This plan is already waiting in QC Line.')
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isSendingToQC.value = false
  }
}

function saveCurrentSettingDie() {
  const formData = new FormData()
  formData.append('plan_id', props.job.id)
  formData.append('set-part-no', props.job.part_no || '')
  formData.append('set-lot-no', form.lotNo)
  formData.append('set-die-no', props.job.die_no || '')
  formData.append('set-plan-no', form.planNo)
  formData.append('set-process-die', form.processDie)
  formData.append('set-dh', form.dh)
  formData.append('set-spm', form.spm)
  formData.append('set-time-start', form.timeStart)
  formData.append('set-time-end', form.timeEnd)
  formData.append('set-material', form.material)
  formData.append('custom-time-1', form.materialStart)
  formData.append('custom-time-2', form.materialEnd)
  formData.append('custom-time-3', form.adjustStart)
  formData.append('custom-time-4', form.adjustEnd)
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
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">Setting Die</h2>
          <p class="mt-1 text-sm text-slate-500">
            Plan #{{ job.id }} / Part {{ job.part_no || '-' }} / Die {{ job.die_no || '-' }}
          </p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-6 overflow-y-auto p-6" @submit.prevent="submitForm">
        <div class="grid gap-4 md:grid-cols-3">
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Part No.</span>
            <input :value="job.part_no || ''" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Lot No.</span>
            <input v-model="form.lotNo" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Die No.</span>
            <input :value="job.die_no || ''" type="text" readonly class="mt-2 w-full rounded-2xl border border-blue-100 bg-slate-50 px-4 py-3 text-slate-500 outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Plan No.</span>
            <input v-model="form.planNo" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Process Die</span>
            <input v-model="form.processDie" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">D/H</span>
            <input v-model="form.dh" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">SPM</span>
            <input v-model="form.spm" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Material</span>
            <input v-model="form.material" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
          <label class="block">
            <span class="text-sm font-medium text-slate-700">Technician</span>
            <input v-model="form.technician" type="text" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
          </label>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.timeStart }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.timeStart" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('timeStart')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.timeEnd }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.timeEnd" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('timeEnd')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.materialStart }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.materialStart" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('materialStart')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.materialEnd }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.materialEnd" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('materialEnd')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.adjustStart }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.adjustStart" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('adjustStart')">Stamp</button>
            </div>
          </label>
          <label class="block rounded-3xl border border-blue-100 p-4">
            <span class="text-sm font-medium text-slate-700">{{ timeFieldLabels.adjustEnd }}</span>
            <div class="mt-2 flex gap-2">
              <input v-model="form.adjustEnd" type="datetime-local" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
              <button type="button" class="rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700" @click="stamp('adjustEnd')">Stamp</button>
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
          <button v-if="canSendToQc" type="button" :disabled="isSubmitting || isSendingToQC" class="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-3 font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60" @click="sendToQCLine">
            {{ isSendingToQC ? 'Sending...' : 'Send to QC Line' }}
          </button>
          <button type="submit" :disabled="isSubmitting || isSendingToQC" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : 'Save Setting Die' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
