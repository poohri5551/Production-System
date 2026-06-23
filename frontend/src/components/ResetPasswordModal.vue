<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true,
  },
  user: {
    type: Object,
    default: null,
  },
  isSubmitting: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['close', 'submit'])

const form = reactive({
  newPassword: '',
  confirmPassword: '',
})

const canSubmit = computed(() => {
  return Boolean(form.newPassword.length >= 8 && form.newPassword === form.confirmPassword)
})

watch(
  () => props.isOpen,
  (isOpen) => {
    if (!isOpen) return
    form.newPassword = ''
    form.confirmPassword = ''
  },
  { immediate: true },
)

function submitModal() {
  if (!canSubmit.value || props.isSubmitting) return
  emit('submit', {
    newPassword: form.newPassword,
    confirmPassword: form.confirmPassword,
  })
}
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex items-start justify-between gap-4 border-b border-blue-100 bg-white/95 p-6">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-amber-600">Admin password reset</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">Reset User Password</h2>
          <p class="mt-1 text-sm text-slate-500">
            User: <span class="font-semibold text-slate-800">{{ user?.username || '-' }}</span>
          </p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-5 overflow-y-auto p-6" @submit.prevent="submitModal">
        <div class="rounded-3xl border border-amber-100 bg-amber-50 p-4 text-sm text-amber-700">
          This updates only the selected user's password. The old password and password hash are never shown.
        </div>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">New Password</span>
          <input
            v-model="form.newPassword"
            name="new_password"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
          />
        </label>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Confirm Password</span>
          <input
            v-model="form.confirmPassword"
            name="confirm_password"
            type="password"
            required
            minlength="8"
            autocomplete="new-password"
            class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
          />
        </label>

        <p v-if="form.newPassword && form.newPassword.length < 8" class="text-sm text-amber-700">
          Password must be at least 8 characters.
        </p>
        <p v-if="form.confirmPassword && form.newPassword !== form.confirmPassword" class="text-sm text-amber-700">
          Password confirmation does not match.
        </p>

        <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ errorMessage }}
        </p>

        <div class="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="emit('close')">
            Cancel
          </button>
          <button
            type="submit"
            :disabled="isSubmitting || !canSubmit"
            class="rounded-2xl bg-amber-600 px-5 py-3 font-semibold text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ isSubmitting ? 'Resetting...' : 'Confirm Reset' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
