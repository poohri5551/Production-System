<script setup>
defineProps({
  inspections: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  canManageQc: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['toggle-select', 'view', 'edit'])

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

function statusClass(status) {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'pass') return 'bg-emerald-50 text-emerald-700'
  if (normalized === 'waiting') return 'bg-amber-50 text-amber-700'
  if (normalized === 'fail') return 'bg-red-50 text-red-700'
  return 'bg-slate-50 text-slate-500'
}
</script>

<template>
  <div class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th v-if="canManageQc" class="px-4 py-4">
              <span class="sr-only">Select</span>
            </th>
            <th class="px-4 py-4">Date / Time</th>
            <th class="px-4 py-4">Plan No.</th>
            <th class="px-4 py-4">Part No.</th>
            <th class="px-4 py-4">Lot No.</th>
            <th class="px-4 py-4">Result (%)</th>
            <th class="px-4 py-4">Status</th>
            <th class="px-4 py-4">Action / Image</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="qc in inspections" :key="qc.id" class="transition hover:bg-blue-50/50">
            <td v-if="canManageQc" class="px-4 py-4">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-blue-200 text-blue-600 focus:ring-blue-500"
                :checked="selectedIds.includes(qc.id)"
                @change="emit('toggle-select', qc.id)"
              />
            </td>
            <td class="whitespace-nowrap px-4 py-4 font-medium text-slate-900">{{ formatDateTime(qc.time_start) }}</td>
            <td class="px-4 py-4 font-medium text-slate-900">{{ qc.plan_no || '-' }}</td>
            <td class="px-4 py-4 text-slate-700">{{ qc.part_no || '-' }}</td>
            <td class="px-4 py-4 text-slate-700">{{ qc.lot_no || '-' }}</td>
            <td class="px-4 py-4 font-semibold text-slate-900">{{ qc.percent_result ? `${qc.percent_result}%` : '-' }}</td>
            <td class="px-4 py-4">
              <span
                class="inline-flex rounded-full px-3 py-1 text-xs font-semibold"
                :class="statusClass(qc.status)"
              >
                {{ qc.status || '-' }}
              </span>
            </td>
            <td class="px-4 py-4">
              <div class="flex flex-wrap gap-2">
                <button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" @click="emit('view', qc.id)">
                  View
                </button>
                <button v-if="canManageQc" type="button" class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100" @click="emit('edit', qc.id)">
                  Edit
                </button>
                <a v-if="qc.image_path" :href="imageUrl(qc.image_path)" target="_blank" rel="noreferrer" class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100">
                  Image
                </a>
                <span v-else class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-400">No image</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
