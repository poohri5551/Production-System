<script setup>
defineProps({
  users: {
    type: Array,
    required: true,
  },
  isActionBusy: {
    type: Boolean,
    default: false,
  },
  canManageUsers: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['edit-role', 'delete-user', 'reset-password'])

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function roleClass(role) {
  if (role === 'Admin') return 'border-blue-100 bg-blue-50 text-blue-700'
  if (role === 'Sup') return 'border-emerald-100 bg-emerald-50 text-emerald-700'
  if (role === 'Manager') return 'border-amber-100 bg-amber-50 text-amber-700'
  if (role === 'PC') return 'border-sky-100 bg-sky-50 text-sky-700'
  if (role === 'Technician') return 'border-violet-100 bg-violet-50 text-violet-700'
  if (role === 'QC Line') return 'border-rose-100 bg-rose-50 text-rose-700'
  if (role === 'Operator') return 'border-slate-200 bg-slate-50 text-slate-700'
  return 'border-slate-100 bg-slate-50 text-slate-500'
}
</script>

<template>
  <div class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
    <div class="h-full max-h-[calc(100vh-24rem)] overflow-auto sm:max-h-[calc(100vh-22rem)] lg:max-h-full">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="sticky top-0 z-10 bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th class="px-4 py-4">Username</th>
            <th class="px-4 py-4">Role</th>
            <th class="px-4 py-4">Created</th>
            <th v-if="canManageUsers" class="px-4 py-4">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="user in users" :key="user.id" class="transition hover:bg-blue-50/50">
            <td v-if="canManageUsers" class="px-4 py-4">
              <div class="flex items-center gap-3">
                <div class="grid h-9 w-9 place-items-center rounded-2xl bg-slate-100 text-xs font-bold uppercase text-slate-600">
                  {{ (user.username || '?').slice(0, 2) }}
                </div>
                <div>
                  <p class="font-semibold text-slate-900">{{ user.username || '-' }}</p>
                  <p v-if="user.username === 'admin'" class="text-xs text-slate-500">Main admin account</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-4">
              <span class="inline-flex rounded-full border px-3 py-1 text-xs font-semibold" :class="roleClass(user.role)">
                {{ user.role || '-' }}
              </span>
            </td>
            <td class="whitespace-nowrap px-4 py-4 text-slate-700">{{ formatDateTime(user.created_at) }}</td>
            <td class="px-4 py-4">
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  :disabled="isActionBusy"
                  class="grid h-9 w-9 place-items-center rounded-xl border border-blue-100 bg-blue-50 text-blue-700 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
                  title="Change role"
                  aria-label="Change role"
                  @click="emit('edit-role', user)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4 19a5 5 0 0 1 9.5-2.2" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                    <path d="M17.5 13.5v5M15 16h5" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                    <path d="M18.8 11.5a3.5 3.5 0 0 1 1.7 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                  </svg>
                </button>
                <button
                  type="button"
                  :disabled="isActionBusy"
                  class="grid h-9 w-9 place-items-center rounded-xl border border-amber-100 bg-amber-50 text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  title="Reset password"
                  aria-label="Reset password"
                  @click="emit('reset-password', user)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M15 7.5A4.5 4.5 0 1 1 10.5 3 4.5 4.5 0 0 1 15 7.5Z" stroke="currentColor" stroke-width="2" />
                    <path d="M14 11 21 18M18 15l-2 2M20 17l-2 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
                <button
                  type="button"
                  :disabled="isActionBusy || user.username === 'admin'"
                  class="grid h-9 w-9 place-items-center rounded-xl border border-red-100 bg-red-50 text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                  title="Delete user"
                  aria-label="Delete user"
                  @click="emit('delete-user', user)"
                >
                  <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
