<script setup>
defineProps({
  detail: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['close'])

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function timelineTime(item) {
  return item.time_finish || item.time_end || item.time_start || item.updated_at || item.created_at || ''
}

function statusClass(status) {
  const normalized = String(status || '').toLowerCase()
  if (['completed', 'confirmed', 'pass', 'finished'].includes(normalized)) return 'bg-emerald-50 text-emerald-700'
  if (['waiting', 'pending', 'wait'].includes(normalized)) return 'bg-amber-50 text-amber-700'
  if (['fail', 'failed'].includes(normalized)) return 'bg-red-50 text-red-700'
  return 'bg-blue-50 text-blue-700'
}

function stepClass(step) {
  const normalized = String(step || '').toLowerCase()
  if (normalized.includes('completed')) return 'bg-emerald-50 text-emerald-700'
  if (normalized.includes('finish')) return 'bg-indigo-50 text-indigo-700'
  if (normalized.includes('start')) return 'bg-blue-50 text-blue-700'
  if (normalized.includes('qc')) return 'bg-sky-50 text-sky-700'
  if (normalized.includes('setting')) return 'bg-violet-50 text-violet-700'
  return 'bg-slate-100 text-slate-600'
}
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
    <section class="flex max-h-[90vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
      <div class="flex flex-col gap-4 border-b border-blue-100 bg-white/95 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Part / Plan timeline</p>
          <h2 class="mt-2 text-2xl font-semibold text-slate-950">{{ detail.plan?.plan_no || '-' }}</h2>
          <div class="mt-3 flex flex-wrap gap-2">
            <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="stepClass(detail.current_step)">
              {{ detail.current_step || '-' }}
            </span>
            <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="statusClass(detail.status)">
              {{ detail.status || '-' }}
            </span>
          </div>
        </div>
        <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-500 hover:bg-slate-200" @click="emit('close')">
          Close
        </button>
      </div>

      <div class="space-y-6 overflow-y-auto p-6">
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Plan No.</p>
            <p class="font-semibold text-slate-900">{{ detail.plan?.plan_no || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Part No.</p>
            <p class="font-semibold text-slate-900">{{ detail.plan?.part_no || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Die No.</p>
            <p class="font-semibold text-slate-900">{{ detail.plan?.die_no || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Zone</p>
            <p class="font-semibold text-slate-900">{{ detail.plan?.zone || '-' }}</p>
          </div>
        </div>

        <div class="rounded-3xl border border-blue-100 bg-white p-5">
          <h3 class="text-lg font-semibold text-slate-950">Timeline</h3>
          <div v-if="!detail.timeline?.length" class="mt-4 rounded-2xl bg-slate-50 p-5 text-sm text-slate-500">
            No timeline data found.
          </div>
          <ol v-else class="mt-5 space-y-4">
            <li v-for="item in detail.timeline" :key="`${item.source_table}-${item.source_id}`" class="relative rounded-3xl border border-blue-100 bg-blue-50/40 p-4">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p class="font-semibold text-slate-950">{{ item.step || '-' }}</p>
                  <p class="mt-1 text-sm text-slate-500">
                    {{ formatDateTime(timelineTime(item)) }} / User: {{ item.user || '-' }}
                  </p>
                </div>
                <span class="inline-flex w-fit rounded-full px-3 py-1 text-xs font-semibold" :class="statusClass(item.status)">
                  {{ item.status || '-' }}
                </span>
              </div>
              <div class="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2 lg:grid-cols-4">
                <span>Start: {{ formatDateTime(item.time_start) }}</span>
                <span>End: {{ formatDateTime(item.time_end) }}</span>
                <span>Finish: {{ formatDateTime(item.time_finish) }}</span>
                <span>{{ item.source_table || '-' }} #{{ item.source_id || '-' }}</span>
              </div>
            </li>
          </ol>
        </div>
      </div>
    </section>
  </div>
</template>
