<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  message: { type: String, required: true },
  details: { type: Array, default: () => [] },
  confirmLabel: { type: String, default: 'Confirm' },
  busyLabel: { type: String, default: 'Working...' },
  busy: { type: Boolean, default: false },
  requireReason: { type: Boolean, default: false },
  reasonLabel: { type: String, default: 'Reason' },
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['cancel', 'confirm'])
const reason = ref('')
const error = ref('')
const canConfirm = computed(() => !props.busy && (!props.requireReason || Boolean(reason.value.trim())))

watch(() => props.title, () => {
  reason.value = ''
  error.value = ''
})

function confirm() {
  if (!canConfirm.value) {
    error.value = `${props.reasonLabel} is required.`
    return
  }
  emit('confirm', reason.value.trim())
}
</script>

<template>
  <div class="fixed inset-0 z-[70] grid place-items-center bg-slate-950/50 px-4 py-8 backdrop-blur-sm" role="dialog" aria-modal="true" :aria-label="title">
    <section class="w-full max-w-lg rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
      <h3 class="text-xl font-semibold text-slate-950">{{ title }}</h3>
      <dl v-if="details.length" class="mt-4 grid gap-3 rounded-2xl bg-slate-50 p-4 sm:grid-cols-2">
        <div v-for="item in details" :key="item.label">
          <dt class="text-xs font-medium uppercase tracking-wide text-slate-500">{{ item.label }}</dt>
          <dd class="mt-1 font-semibold text-slate-900">{{ item.value || '-' }}</dd>
        </div>
      </dl>
      <p class="mt-4 text-sm leading-6 text-slate-600">{{ message }}</p>
      <label v-if="requireReason" class="mt-5 block">
        <span class="text-sm font-medium text-slate-700">{{ reasonLabel }}</span>
        <textarea v-model="reason" rows="4" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
      </label>
      <p v-if="error" class="mt-3 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
      <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <button type="button" :disabled="busy" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60" @click="emit('cancel')">
          Cancel
        </button>
        <button type="button" :disabled="!canConfirm" class="rounded-2xl px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60" :class="danger ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'" @click="confirm">
          {{ busy ? busyLabel : confirmLabel }}
        </button>
      </div>
    </section>
  </div>
</template>
