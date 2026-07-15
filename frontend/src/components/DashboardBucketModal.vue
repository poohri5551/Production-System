<script setup>
import { computed, ref } from 'vue'
import WorkflowStatusBadge from './WorkflowStatusBadge.vue'
import { filterDashboardItems, nextActionForItem } from '../constants/workflowStatus'

const props = defineProps({
  bucket: { type: Object, required: true },
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'select'])
const search = ref('')

const bucketItems = computed(() => filterDashboardItems(props.items, props.bucket.key))
const filteredItems = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  if (!query) return bucketItems.value
  return bucketItems.value.filter((item) => [item.lot_no, item.part_no]
    .some((value) => String(value || '').toLocaleLowerCase().includes(query)))
})

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-3 py-5 backdrop-blur-sm" @click.self="emit('close')">
    <section role="dialog" aria-modal="true" :aria-label="`${bucket.label} Lots`" class="flex max-h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <header class="flex flex-col gap-4 border-b border-blue-100 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Dashboard group</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ bucket.label }} — {{ bucketItems.length }} Lots</h2>
          <p class="mt-1 text-sm text-slate-500">{{ bucket.description }}</p>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200" aria-label="Close Lot list" @click="emit('close')">Close</button>
      </header>

      <div class="border-b border-blue-100 p-5 sm:p-6">
        <label class="block max-w-xl">
          <span class="text-sm font-medium text-slate-700">Search Lot No. or Part No.</span>
          <span class="mt-2 flex gap-2">
            <input v-model="search" type="search" class="min-w-0 flex-1 rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" placeholder="Type partial Lot No. or Part No." autofocus />
            <button v-if="search" type="button" class="rounded-2xl border border-slate-200 px-4 text-sm font-semibold text-slate-600 hover:bg-slate-50" @click="search = ''">Clear</button>
          </span>
        </label>
        <p class="mt-3 text-sm text-slate-500">{{ filteredItems.length }} result{{ filteredItems.length === 1 ? '' : 's' }}</p>
      </div>

      <div class="overflow-y-auto p-4 sm:p-6">
        <div v-if="!filteredItems.length" class="rounded-3xl bg-slate-50 p-10 text-center">
          <h3 class="font-semibold text-slate-900">No matching Lots</h3>
          <p class="mt-2 text-sm text-slate-500">Clear search or try another Lot No. / Part No.</p>
        </div>

        <div v-else class="grid gap-3 lg:hidden">
          <button v-for="item in filteredItems" :key="item.plan_id" type="button" class="rounded-3xl border border-blue-100 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50 focus:outline-none focus:ring-4 focus:ring-blue-100" @click="emit('select', item)">
            <span class="flex items-start justify-between gap-3">
              <span><span class="block text-xs text-slate-500">Lot No.</span><span class="font-semibold text-slate-950">{{ item.lot_no || '-' }}</span></span>
              <span class="text-sm font-semibold text-blue-700">Open</span>
            </span>
            <span class="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-600"><span>Part: {{ item.part_no || '-' }}</span><span>Die: {{ item.die_no || '-' }}</span><span>Zone: {{ item.zone || '-' }}</span><span>{{ formatDateTime(item.last_updated) }}</span></span>
            <span class="mt-3 flex flex-wrap gap-2"><WorkflowStatusBadge kind="stage" :stage="item.current_step" /><WorkflowStatusBadge :stage="item.current_step" :status="item.status" :item="item" /></span>
            <span class="mt-3 block text-sm"><span class="text-slate-500">Next:</span> <span class="font-medium text-slate-800">{{ nextActionForItem(item) }}</span></span>
          </button>
        </div>

        <div v-if="filteredItems.length" class="hidden overflow-x-auto rounded-3xl border border-blue-100 lg:block">
          <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
            <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500"><tr><th class="px-4 py-4">Lot No.</th><th class="px-4 py-4">Part No.</th><th class="px-4 py-4">Die No.</th><th class="px-4 py-4">Zone</th><th class="px-4 py-4">Current Stage</th><th class="px-4 py-4">State</th><th class="px-4 py-4">Next Action</th><th class="px-4 py-4">Last Updated</th><th class="px-4 py-4">Action</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
              <tr v-for="item in filteredItems" :key="item.plan_id" class="transition hover:bg-blue-50/50">
                <td class="px-4 py-4 font-semibold text-slate-950">{{ item.lot_no || '-' }}</td><td class="px-4 py-4">{{ item.part_no || '-' }}</td><td class="px-4 py-4">{{ item.die_no || '-' }}</td><td class="px-4 py-4">{{ item.zone || '-' }}</td>
                <td class="px-4 py-4"><WorkflowStatusBadge kind="stage" :stage="item.current_step" /></td><td class="px-4 py-4"><WorkflowStatusBadge :stage="item.current_step" :status="item.status" :item="item" /></td>
                <td class="max-w-xs px-4 py-4 font-medium text-slate-700">{{ nextActionForItem(item) }}</td><td class="whitespace-nowrap px-4 py-4 text-slate-600">{{ formatDateTime(item.last_updated) }}</td>
                <td class="px-4 py-4"><button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" :aria-label="`Open Lot ${item.lot_no || ''}`" @click="emit('select', item)">Open</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>
