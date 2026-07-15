<script setup>
import { ref } from 'vue'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'
import { settingDieEligibility, settingDieProcessRows } from '../constants/settingDieSequence'

const props = defineProps({
  jobs: {
    type: Array,
    required: true,
  },
  selectedIds: {
    type: Array,
    required: true,
  },
  canDeleteProduction: {
    type: Boolean,
    default: false,
  },
  canAcceptProduction: {
    type: Boolean,
    default: false,
  },
  canManageSettingDie: {
    type: Boolean,
    default: false,
  },
  highlightedId: { type: [Number, String], default: null },
})

const emit = defineEmits(['toggle-select', 'view', 'accept', 'setting'])
const expandedIds = ref([])

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

function isExpanded(jobId) {
  return expandedIds.value.includes(jobId)
}

function toggleExpanded(jobId) {
  expandedIds.value = isExpanded(jobId)
    ? expandedIds.value.filter((id) => id !== jobId)
    : [...expandedIds.value, jobId]
}

function requestSettingDie(job, processDieNo) {
  if (!settingDieEligibility(job, processDieNo).allowed) return
  emit('setting', job, processDieNo)
}

</script>

<template>
  <div class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
    <div class="overflow-x-auto">
      <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
        <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th v-if="props.canDeleteProduction" class="px-4 py-4">
              <span class="sr-only">Select</span>
            </th>
            <th class="px-4 py-4">
              <span class="sr-only">Expand</span>
            </th>
            <th class="px-4 py-4">Lot No.</th>
            <th class="px-4 py-4">Date</th>
            <th class="px-4 py-4">Part No.</th>
            <th class="px-4 py-4">Picture Part</th>
            <th class="px-4 py-4">Die No.</th>
            <th class="px-4 py-4">Q'ty</th>
            <th class="px-4 py-4">Status</th>
            <th class="px-4 py-4">Action</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <template v-for="job in props.jobs" :key="job.id">
            <tr :id="`production-row-${job.id}`" class="transition duration-700 hover:bg-blue-50/50" :class="Number(props.highlightedId) === Number(job.id) ? 'bg-blue-100 ring-2 ring-inset ring-blue-500' : ''">
              <td v-if="props.canDeleteProduction" class="px-4 py-4">
                <input
                  type="checkbox"
                  class="h-4 w-4 rounded border-blue-200 text-blue-600 focus:ring-blue-500"
                  :checked="props.selectedIds.includes(job.id)"
                  @change="emit('toggle-select', job.id)"
                />
              </td>
              <td class="px-4 py-4">
                <button
                  type="button"
                  class="grid h-8 w-8 place-items-center rounded-xl border border-blue-100 text-blue-700 hover:bg-blue-50"
                  :title="isExpanded(job.id) ? 'Collapse processes' : 'Expand processes'"
                  :aria-label="isExpanded(job.id) ? 'Collapse processes' : 'Expand processes'"
                  @click="toggleExpanded(job.id)"
                >
                  <svg class="h-4 w-4 transition" :class="isExpanded(job.id) ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="m9 6 6 6-6 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </button>
              </td>
              <td class="px-4 py-4 font-semibold text-slate-900">{{ job.lot_no || '-' }}</td>
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
                <WorkflowStatusBadge stage="Not Started" :status="job.status" />
              </td>
              <td class="px-4 py-4">
                <div class="flex flex-wrap gap-2">
                  <button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" @click="emit('view', job.id)">
                    View
                  </button>
                  <button
                    v-if="props.canAcceptProduction && job.status === 'pending'"
                    type="button"
                    class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-100"
                    @click="emit('accept', job.id)"
                  >
                    Accept
                  </button>
                </div>
              </td>
            </tr>
            <template v-if="isExpanded(job.id)">
              <tr
                v-for="process in settingDieProcessRows(job)"
                :key="`${job.id}-process-${process.process_die_no}`"
                class="bg-slate-50/70"
              >
                <td v-if="props.canDeleteProduction" class="px-4 py-3"></td>
                <td class="px-4 py-3"></td>
                <td colspan="3" class="px-4 py-3">
                  <div class="flex flex-wrap items-center gap-3">
                    <span class="font-semibold text-slate-800">Process Die {{ process.process_die_no }}</span>
                    <WorkflowStatusBadge stage="Setting Die" :status="process.status" />
                  </div>
                </td>
                <td colspan="4" class="px-4 py-3 text-sm text-slate-500">
                  Setting Die record: {{ process.setting_die_id || '-' }}
                </td>
                <td class="px-4 py-3">
                  <button
                    v-if="props.canManageSettingDie && job.status !== 'pending'"
                    type="button"
                    :disabled="!settingDieEligibility(job, process.process_die_no).allowed"
                    class="rounded-xl border px-3 py-2 text-xs font-semibold transition"
                    :class="settingDieEligibility(job, process.process_die_no).allowed ? 'border-slate-200 bg-white text-slate-700 hover:bg-blue-50 hover:text-blue-700' : 'cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400 opacity-70'"
                    :title="settingDieEligibility(job, process.process_die_no).allowed ? 'Open Setting Die' : settingDieEligibility(job, process.process_die_no).message"
                    @click="requestSettingDie(job, process.process_die_no)"
                  >
                    Setting Die
                  </button>
                  <p v-if="props.canManageSettingDie && job.status !== 'pending' && !settingDieEligibility(job, process.process_die_no).allowed" class="mt-1 max-w-32 text-xs leading-4 text-slate-400">
                    {{ settingDieEligibility(job, process.process_die_no).message }}
                  </p>
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>
