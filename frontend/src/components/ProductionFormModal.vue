<script setup>
import { reactive, ref } from 'vue'
import { createProductionJob } from '../api/client'

const emit = defineEmits(['close', 'saved'])

const form = reactive({
  date: '',
  zone: '',
  partNo: '',
  dieNo: '',
  qty: '',
})

const imageFile = ref(null)
const errorMessage = ref('')
const isSubmitting = ref(false)

function handleFileChange(event) {
  imageFile.value = event.target.files?.[0] || null
}

function resetForm() {
  form.date = ''
  form.zone = ''
  form.partNo = ''
  form.dieNo = ''
  form.qty = ''
  imageFile.value = null
  errorMessage.value = ''
}

async function submitForm() {
  if (isSubmitting.value) return
  errorMessage.value = ''
  isSubmitting.value = true

  const formData = new FormData()
  formData.append('prod-date', form.date)
  formData.append('prod-zone', form.zone)
  formData.append('prod-part-no', form.partNo)
  formData.append('prod-die-no', form.dieNo)
  formData.append('prod-qty', form.qty)
  if (imageFile.value) {
    formData.append('prod-image', imageFile.value)
  }

  try {
    const data = await createProductionJob(formData)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot save production plan'
      return
    }
    resetForm()
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
    <section class="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
      <div class="mb-6 flex items-start justify-between gap-4">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Production Plan</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">เพิ่มแผนการผลิต</h2>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="grid gap-4 sm:grid-cols-2" @submit.prevent="submitForm">
        <label class="block">
          <span class="text-sm font-medium text-slate-700">Date</span>
          <input v-model="form.date" name="prod-date" type="date" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Zone</span>
          <select v-model="form.zone" name="prod-zone" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
            <option value="">-- Select Zone --</option>
            <option value="A">Zone A</option>
            <option value="B">Zone B</option>
            <option value="C">Zone C</option>
            <option value="Q">Zone Q</option>
          </select>
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Part No.</span>
          <input v-model="form.partNo" name="prod-part-no" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Die No.</span>
          <input v-model="form.dieNo" name="prod-die-no" type="text" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Q'ty</span>
          <input v-model="form.qty" name="prod-qty" type="number" min="1" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Picture Part</span>
          <input name="prod-image" type="file" accept="image/*" class="mt-2 w-full rounded-2xl border border-dashed border-blue-200 bg-blue-50/40 px-4 py-3 text-sm" @change="handleFileChange" />
        </label>

        <p v-if="errorMessage" class="sm:col-span-2 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="sm:col-span-2 mt-2 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button type="submit" :disabled="isSubmitting" class="rounded-2xl bg-blue-600 px-5 py-3 font-semibold text-white shadow-lg shadow-blue-600/20 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60">
            {{ isSubmitting ? 'Saving...' : 'Save Production' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
