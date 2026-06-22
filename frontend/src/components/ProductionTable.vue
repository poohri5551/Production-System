<script setup>
defineProps({
  jobs: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  canManageProduction: {
    type: Boolean,
    default: false,
  },
  canManageSettingDie: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['toggle-select', 'view', 'accept', 'setting'])

function formatDate(dateString) {
  if (!dateString) return '-'
  const date = new Date(String(dateString).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return dateString
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`
}

function imageUrl(path) {
  return path ? `/static/uploads/${path}` : ''
}
</script>

<template>
  <div class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th v-if="canManageProduction" class="px-4 py-4">
              <span class="sr-only">Select</span>
            </th>
            <th class="px-4 py-4">Plan</th>
            <th class="px-4 py-4">Part No.</th>
            <th class="px-4 py-4">Picture Part</th>
            <th class="px-4 py-4">Die No.</th>
            <th class="px-4 py-4">Q'ty</th>
            <th class="px-4 py-4">Status</th>
            <th class="px-4 py-4">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="job in jobs" :key="job.id" class="transition hover:bg-blue-50/50">
            <td v-if="canManageProduction" class="px-4 py-4">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-blue-200 text-blue-600 focus:ring-blue-500"
                :checked="selectedIds.includes(job.id)"
                @change="emit('toggle-select', job.id)"
              />
            </td>
            <td class="px-4 py-4 font-medium text-slate-900">{{ formatDate(job.prod_date) }}</td>
            <td class="px-4 py-4 text-slate-700">{{ job.part_no || '-' }}</td>
            <td class="px-4 py-4">
              <div class="grid h-12 w-12 place-items-center overflow-hidden rounded-2xl border border-blue-100 bg-blue-50 text-blue-300">
                <img v-if="job.image_path" :src="imageUrl(job.image_path)" alt="Part" class="h-full w-full object-cover" />
                <span v-else>Image</span>
              </div>
            </td>
            <td class="px-4 py-4 text-slate-700">{{ job.die_no || '-' }}</td>
            <td class="px-4 py-4 font-semibold text-slate-900">{{ job.qty || '-' }}</td>
            <td class="px-4 py-4">
              <span
                class="inline-flex rounded-full px-3 py-1 text-xs font-semibold"
                :class="job.status === 'pending' ? 'bg-amber-50 text-amber-700' : 'bg-blue-50 text-blue-700'"
              >
                {{ job.status === 'pending' ? 'Pending' : 'Accepted' }}
              </span>
            </td>
            <td class="px-4 py-4">
              <div class="flex flex-wrap gap-2">
                <button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" @click="emit('view', job.id)">
                  View
                </button>
                <button
                  v-if="canManageProduction && job.status === 'pending'"
                  type="button"
                  class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                  @click="emit('accept', job.id)"
                >
                  Accept
                </button>
                <button
                  v-else-if="canManageSettingDie && job.status !== 'pending'"
                  type="button"
                  class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500"
                  title="Open Setting Die"
                  @click="emit('setting', job)"
                >
                  Setting Die
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
