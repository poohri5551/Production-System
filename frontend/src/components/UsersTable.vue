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
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
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
                  class="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="emit('edit-role', user)"
                >
                  Role
                </button>
                <button
                  type="button"
                  :disabled="isActionBusy"
                  class="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="emit('reset-password', user)"
                >
                  Reset Password
                </button>
                <button
                  type="button"
                  :disabled="isActionBusy || user.username === 'admin'"
                  class="rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="emit('delete-user', user)"
                >
                  Delete
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
