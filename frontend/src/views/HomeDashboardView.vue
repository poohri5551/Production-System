<script setup>
import { onMounted, reactive, ref } from 'vue'
import { getDashboardPartsStatus, getDashboardPartStatusDetail } from '../api/client'
import DashboardDetailModal from '../components/DashboardDetailModal.vue'

const summary = reactive({
  total: 0,
  waiting: 0,
  in_progress: 0,
  qc: 0,
  completed: 0,
})
const items = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const detailState = reactive({
  isOpen: false,
  isLoading: false,
  error: '',
  detail: null,
})

const cards = [
  { key: 'total', label: 'Total', tone: 'text-slate-950' },
  { key: 'waiting', label: 'Waiting', tone: 'text-amber-700' },
  { key: 'in_progress', label: 'In Progress', tone: 'text-blue-700' },
  { key: 'qc', label: 'QC', tone: 'text-sky-700' },
  { key: 'completed', label: 'Completed', tone: 'text-emerald-700' },
]

onMounted(() => {
  loadDashboard()
})

function resetSummary() {
  Object.assign(summary, {
    total: 0,
    waiting: 0,
    in_progress: 0,
    qc: 0,
    completed: 0,
  })
}

async function loadDashboard() {
  if (isLoading.value) return
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getDashboardPartsStatus()
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load dashboard'
      items.value = []
      resetSummary()
      return
    }
    Object.assign(summary, {
      total: data.summary?.total || 0,
      waiting: data.summary?.waiting || 0,
      in_progress: data.summary?.in_progress || 0,
      qc: data.summary?.qc || 0,
      completed: data.summary?.completed || 0,
    })
    items.value = data.items || []
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
    items.value = []
    resetSummary()
  } finally {
    isLoading.value = false
  }
}

async function openDetail(planId) {
  if (!planId) return
  detailState.isOpen = true
  detailState.isLoading = true
  detailState.error = ''
  detailState.detail = null

  try {
    const data = await getDashboardPartStatusDetail(planId)
    if (!data.success) {
      detailState.error = data.message || 'Cannot load dashboard detail'
      return
    }
    detailState.detail = data
  } catch (error) {
    detailState.error = error.message || 'Cannot connect to backend'
  } finally {
    detailState.isLoading = false
  }
}

function closeDetail() {
  detailState.isOpen = false
  detailState.detail = null
  detailState.error = ''
}

function formatDateTime(value) {
  if (!value) return '-'
  const date = new Date(String(value).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return value
  const pad = (number) => String(number).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`
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
  <section class="space-y-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Production dashboard</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">สถานะของแผนการผลิต</h1>
        <p class="mt-2 max-w-2xl text-slate-500">
          ติดตามสถานะของแผนการผลิตว่าอยู่ในขั้นตอนใด 
        </p>
      </div>
      <button
        type="button"
        class="grid h-11 w-11 place-items-center rounded-2xl border border-blue-100 text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="isLoading"
        aria-label="Refresh dashboard"
        title="Refresh"
        @click="loadDashboard"
      >
        <svg class="h-5 w-5" :class="{ 'animate-spin': isLoading }" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M20 6v5h-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M4 18v-5h5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M18.5 9A7 7 0 0 0 6.4 6.2L4 8.5M5.5 15A7 7 0 0 0 17.6 17.8L20 15.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <article v-for="card in cards" :key="card.key" class="rounded-3xl border border-blue-100 bg-white p-5 shadow-sm">
        <p class="text-sm text-slate-500">{{ card.label }}</p>
        <p class="mt-2 text-3xl font-semibold" :class="card.tone">{{ summary[card.key] }}</p>
      </article>
    </div>

    <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <div v-if="isLoading" class="shell-card p-10 text-center text-slate-500">
      Loading dashboard...
    </div>
    <div v-else-if="!items.length" class="shell-card p-10 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">DB</div>
      <h2 class="text-lg font-semibold text-slate-900">ไม่พบแผนการผลิต</h2>
      <p class="mt-2 text-sm text-slate-500">เริ่มต้นแผนการผลิตเพื่อติดตามสถานะของชิ้นงาน</p>
    </div>

    <div v-else class="overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-sm">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-blue-100 text-left text-sm">
          <thead class="bg-blue-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th class="px-4 py-4">Plan No.</th>
              <th class="px-4 py-4">Part No.</th>
              <th class="px-4 py-4">Die No.</th>
              <th class="px-4 py-4">Zone</th>
              <th class="px-4 py-4">Current Step</th>
              <th class="px-4 py-4">Status</th>
              <th class="px-4 py-4">Last Updated</th>
              <th class="px-4 py-4">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="item in items" :key="item.plan_id" class="cursor-pointer transition hover:bg-blue-50/50" @click="openDetail(item.plan_id)">
              <td class="px-4 py-4 font-semibold text-slate-900">{{ item.plan_no || '-' }}</td>
              <td class="px-4 py-4 text-slate-700">{{ item.part_no || '-' }}</td>
              <td class="px-4 py-4 text-slate-700">{{ item.die_no || '-' }}</td>
              <td class="px-4 py-4 text-slate-700">{{ item.zone || '-' }}</td>
              <td class="px-4 py-4">
                <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="stepClass(item.current_step)">
                  {{ item.current_step || '-' }}
                </span>
              </td>
              <td class="px-4 py-4">
                <span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold" :class="statusClass(item.status)">
                  {{ item.status || '-' }}
                </span>
              </td>
              <td class="whitespace-nowrap px-4 py-4 text-slate-700">{{ formatDateTime(item.last_updated) }}</td>
              <td class="px-4 py-4">
                <button type="button" class="rounded-xl border border-blue-100 bg-white px-3 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-50" @click.stop="openDetail(item.plan_id)">
                  View
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="detailState.isOpen && (detailState.isLoading || detailState.error)" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 text-center shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Dashboard Detail</h2>
        <p v-if="detailState.isLoading" class="mt-4 text-slate-500">Loading detail...</p>
        <p v-else class="mt-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ detailState.error }}
        </p>
        <button type="button" class="mt-6 rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="closeDetail">
          Close
        </button>
      </section>
    </div>

    <DashboardDetailModal v-if="detailState.isOpen && detailState.detail && !detailState.isLoading && !detailState.error" :detail="detailState.detail" @close="closeDetail" />
  </section>
</template>
