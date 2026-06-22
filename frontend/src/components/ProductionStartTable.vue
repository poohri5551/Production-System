<script setup>
defineProps({
  starts: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  canManageProductionStart: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['toggle-select', 'confirm', 'edit'])

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
</script>

<template>
  <div class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th v-if="canManageProductionStart" class="px-4 py-4"><span class="sr-only">Select</span></th>
            <th class="px-4 py-4">Plan No.</th>
            <th class="px-4 py-4">Lot No.</th>
            <th class="px-4 py-4">Part No.</th>
            <th class="px-4 py-4">Die No.</th>
            <th class="px-4 py-4">Q'ty</th>
            <th class="px-4 py-4">Start Time</th>
            <th v-if="canManageProductionStart" class="px-4 py-4">Manage</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="item in starts" :key="item.id" class="transition hover:bg-blue-50/50">
            <td v-if="canManageProductionStart" class="px-4 py-4">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-blue-200 text-blue-600 focus:ring-blue-500"
                :checked="selectedIds.includes(item.id)"
                @change="emit('toggle-select', item.id)"
              />
            </td>
            <td class="px-4 py-4 font-medium text-slate-900">{{ item.plan_no || '-' }}</td>
            <td class="px-4 py-4 text-slate-700">{{ item.lot_no || '-' }}</td>
            <td class="px-4 py-4 text-slate-700">{{ item.part_no || '-' }}</td>
            <td class="px-4 py-4 text-slate-700">{{ item.die_no || '-' }}</td>
            <td class="px-4 py-4 font-semibold text-slate-900">{{ item.qty || '-' }}</td>
            <td class="whitespace-nowrap px-4 py-4 text-slate-700">{{ formatDateTime(item.time_start) }}</td>
            <td v-if="canManageProductionStart" class="px-4 py-4">
              <div class="flex flex-wrap gap-2">
                <button
                  v-if="item.confirm_status === 'confirmed'"
                  type="button"
                  disabled
                  class="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700"
                >
                  Confirmed
                </button>
                <button
                  v-else
                  type="button"
                  class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                  @click="emit('confirm', item.id)"
                >
                  Waiting
                </button>
                <button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" @click="emit('edit', item.id)">
                  Edit
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
