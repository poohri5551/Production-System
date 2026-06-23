<script setup>
import { computed, ref, watch } from 'vue'
import { getAvailableRoles } from '../permissions'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true,
  },
  mode: {
    type: String,
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

const roles = getAvailableRoles()
const selectedRole = ref('Sup')
const adminPassword = ref('')

const isRoleMode = computed(() => props.mode === 'role')
const title = computed(() => (isRoleMode.value ? 'Edit User Role' : 'Delete User'))
const canSubmit = computed(() => {
  if (!adminPassword.value) return false
  if (isRoleMode.value) return roles.includes(selectedRole.value)
  return props.user?.username && props.user.username !== 'admin'
})

watch(
  () => props.isOpen,
  (isOpen) => {
    if (!isOpen) return
    selectedRole.value = roles.includes(props.user?.role) ? props.user.role : 'Sup'
    adminPassword.value = ''
  },
  { immediate: true },
)

function submitModal() {
  if (!canSubmit.value || props.isSubmitting) return
  emit('submit', {
    role: selectedRole.value,
    adminPassword: adminPassword.value,
  })
}
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex items-start justify-between gap-4 border-b border-blue-100 bg-white/95 p-6">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em]" :class="isRoleMode ? 'text-blue-600' : 'text-red-600'">
            Admin confirmation
          </p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ title }}</h2>
          <p class="mt-1 text-sm text-slate-500">
            User: <span class="font-semibold text-slate-800">{{ user?.username || '-' }}</span>
          </p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <form class="space-y-5 overflow-y-auto p-6" @submit.prevent="submitModal">
        <label v-if="isRoleMode" class="block">
          <span class="text-sm font-medium text-slate-700">Role</span>
          <select v-model="selectedRole" name="role" required class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
            <option v-for="role in roles" :key="role" :value="role">{{ role }}</option>
          </select>
        </label>

        <div v-else class="rounded-3xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
          This will permanently delete the selected user account from the users table. The main admin user is protected and cannot be deleted.
        </div>

        <label class="block">
          <span class="text-sm font-medium text-slate-700">Admin Password</span>
          <input v-model="adminPassword" name="admin_password" type="password" required autocomplete="current-password" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>

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
            class="rounded-2xl px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            :class="isRoleMode ? 'bg-blue-600 hover:bg-blue-700' : 'bg-red-600 hover:bg-red-700'"
          >
            {{ isSubmitting ? 'Submitting...' : isRoleMode ? 'Save Role' : 'Delete User' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
