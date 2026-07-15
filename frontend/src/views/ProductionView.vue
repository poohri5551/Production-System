<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  acceptProductionJob,
  bulkDeleteProductionJobs,
  getProductionJobDetail,
  getProductionJobs,
} from '../api/client'
import ProductionFormModal from '../components/ProductionFormModal.vue'
import ProductionTable from '../components/ProductionTable.vue'
import SettingDieModal from '../components/SettingDieModal.vue'
import { can } from '../permissions'
import { findWorkflowTarget } from '../constants/workflowStatus'
import { settingDieEligibility } from '../constants/settingDieSequence'

const props = defineProps({
  role: { type: String, default: '' },
  permissions: {
    type: Array,
    default: () => [],
  },
  focusTarget: { type: Object, default: null },
})

const emit = defineEmits(['focus-result'])

const filters = reactive({
  zone: '',
  partNo: '',
  dieNo: '',
})

const jobs = ref([])
const selectedIds = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const highlightedJobId = ref(null)
const showCreateModal = ref(false)
const detailState = reactive({ isOpen: false, isLoading: false, error: '', job: null, setting: null })
const settingModalState = reactive({ isOpen: false, isLoading: false, error: '', job: null, setting: null, processDieNo: 1 })
const bulkDeleteState = reactive({
  isOpen: false,
  adminPassword: '',
  isSubmitting: false,
  error: '',
})

const canCreateProduction = computed(() => can(props.permissions, 'production.create'))
const canAcceptProduction = computed(() => can(props.permissions, 'production.accept'))
const canDeleteProduction = computed(() => can(props.permissions, 'production.delete'))
const canManageSettingDie = computed(() => can(props.permissions, 'setting_die.manage'))
const canSendSettingDieToQC = computed(() => can(props.permissions, 'setting_die.send_to_qc'))
const hasSelectedJobs = computed(() => canDeleteProduction.value && selectedIds.value.length > 0)
let highlightTimer = null

onMounted(() => {
  loadJobs()
})

async function loadJobs() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionJobs(filters)
    if (Array.isArray(data)) {
      jobs.value = data
      selectedIds.value = selectedIds.value.filter((id) => data.some((job) => job.id === id))
      isLoading.value = false
      await applyFocusTarget()
      return
    }
    errorMessage.value = data.message || 'Cannot load production jobs'
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}

async function applyFocusTarget() {
  if (!props.focusTarget) return
  const record = findWorkflowTarget(jobs.value, props.focusTarget, { useIdAsPlanId: true })
  if (!record) {
    emit('focus-result', { found: false, lotNo: props.focusTarget.lotNo })
    return
  }
  highlightedJobId.value = record.id
  await nextTick()
  document.getElementById(`production-row-${record.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  emit('focus-result', { found: true, lotNo: record.lot_no })
  if (highlightTimer) window.clearTimeout(highlightTimer)
  highlightTimer = window.setTimeout(() => { highlightedJobId.value = null }, 5000)
}

watch(() => props.focusTarget?.token, () => {
  if (!isLoading.value && props.focusTarget) applyFocusTarget()
})

onUnmounted(() => {
  if (highlightTimer) window.clearTimeout(highlightTimer)
})

function clearFilters() {
  filters.zone = ''
  filters.partNo = ''
  filters.dieNo = ''
  loadJobs()
}

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((selectedId) => selectedId !== id)
    : [...selectedIds.value, id]
}

function closeCreateModal() {
  showCreateModal.value = false
}

function handleCreated() {
  showCreateModal.value = false
  noticeMessage.value = 'Production plan saved successfully.'
  loadJobs()
}

async function acceptJob(jobId) {
  if (!canAcceptProduction.value) return
  noticeMessage.value = ''
  errorMessage.value = ''

  try {
    const data = await acceptProductionJob(jobId)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot accept job'
      return
    }
    noticeMessage.value = 'Job accepted successfully.'
    await loadJobs()
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

async function openDetail(jobId) {
  detailState.isOpen = true
  detailState.isLoading = true
  detailState.error = ''
  detailState.job = null
  detailState.setting = null

  try {
    const data = await getProductionJobDetail(jobId)
    if (!data.success) {
      detailState.error = data.message || 'Cannot load job detail'
      return
    }
    detailState.job = data.job
    detailState.setting = data.setting
  } catch (error) {
    detailState.error = error.message || 'Cannot connect to backend'
  } finally {
    detailState.isLoading = false
  }
}

function closeDetail() {
  detailState.isOpen = false
}

async function openSettingDie(job, processDieNo = 1) {
  if (!canManageSettingDie.value) return
  const currentJob = jobs.value.find((item) => Number(item.id) === Number(job?.id)) || job
  const eligibility = settingDieEligibility(currentJob, processDieNo)
  if (!eligibility.allowed) {
    errorMessage.value = ''
    noticeMessage.value = eligibility.message
    return
  }
  noticeMessage.value = ''
  settingModalState.isOpen = true
  settingModalState.isLoading = true
  settingModalState.error = ''
  settingModalState.job = job
  settingModalState.setting = null
  settingModalState.processDieNo = processDieNo

  try {
    const data = await getProductionJobDetail(job.id, processDieNo)
    if (!data.success) {
      settingModalState.error = data.message || 'Cannot load Setting Die'
      return
    }
    settingModalState.job = data.job || job
    settingModalState.setting = data.setting || null
  } catch (error) {
    settingModalState.error = error.message || 'Cannot connect to backend'
  } finally {
    settingModalState.isLoading = false
  }
}

function closeSettingDie() {
  if (settingModalState.isLoading) return
  settingModalState.isOpen = false
}

function handleSettingDieSaved(message = 'Setting Die saved successfully.') {
  settingModalState.isOpen = false
  noticeMessage.value = message
  loadJobs()
}

function openBulkDelete() {
  if (!canDeleteProduction.value) return
  bulkDeleteState.isOpen = true
  bulkDeleteState.adminPassword = ''
  bulkDeleteState.error = ''
}

function closeBulkDelete() {
  if (bulkDeleteState.isSubmitting) return
  bulkDeleteState.isOpen = false
}

async function submitBulkDelete() {
  if (bulkDeleteState.isSubmitting || !canDeleteProduction.value) return
  bulkDeleteState.error = ''
  bulkDeleteState.isSubmitting = true

  try {
    const data = await bulkDeleteProductionJobs(selectedIds.value, bulkDeleteState.adminPassword)
    if (!data.success) {
      bulkDeleteState.error = data.message || 'Cannot delete selected jobs'
      return
    }
    noticeMessage.value = `Deleted ${data.deleted || selectedIds.value.length} selected job(s).`
    selectedIds.value = []
    bulkDeleteState.isOpen = false
    await loadJobs()
  } catch (error) {
    bulkDeleteState.error = error.message || 'Cannot connect to backend'
  } finally {
    bulkDeleteState.isSubmitting = false
  }
}

function imageUrl(path) {
  return path ? `/static/uploads/${path}` : ''
}

function formatDate(dateString) {
  if (!dateString) return '-'
  const date = new Date(String(dateString).replace(' GMT', ''))
  if (Number.isNaN(date.getTime())) return dateString
  const pad = (value) => String(value).padStart(2, '0')
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`
}
</script>

<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">FOR PRODUCTION PLAN & SETTING DIE</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">แผนการผลิตและตั้งค่า Die</h1>
        <p class="mt-2 max-w-2xl text-slate-500">
          ใช้สำหรับเพิ่มแผนการผลิตและการตั้งค่า Die 
        </p>
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          v-if="canDeleteProduction"
          type="button"
          :disabled="!hasSelectedJobs"
          class="grid h-11 w-11 place-items-center rounded-2xl border border-red-100 bg-red-50 text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title="ลบรายการที่เลือก"
          aria-label="ลบรายการที่เลือก"
          @click="openBulkDelete"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button v-if="canCreateProduction" type="button" class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700" title="เพิ่ม Production" aria-label="เพิ่ม Production" @click="showCreateModal = true">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>

    <form class="grid gap-3 rounded-3xl border border-blue-100 bg-white p-4 shadow-sm md:grid-cols-[160px_1fr_1fr_auto_auto]" @submit.prevent="loadJobs">
      <select v-model="filters.zone" class="rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100">
        <option value="">เลือกโซน</option>
        <option value="A">Zone A</option>
        <option value="B">Zone B</option>
        <option value="C">Zone C</option>
        <option value="Q">Zone Q</option>
      </select>
      <input v-model="filters.partNo" type="text" placeholder="ค้นหา Part No." class="rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
      <input v-model="filters.dieNo" type="text" placeholder="ค้นหา Die No." class="rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
      <button type="submit" class="grid h-12 w-12 place-items-center rounded-2xl bg-blue-600 text-white hover:bg-blue-700" title="ค้นหา" aria-label="ค้นหา">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="m20 20-4.2-4.2M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
        </svg>
      </button>
      <button type="button" class="grid h-12 w-12 place-items-center rounded-2xl border border-blue-100 text-blue-700 hover:bg-blue-50" title="ล้างตัวกรอง" aria-label="ล้างตัวกรอง" @click="clearFilters">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M7 7 17 17M17 7 7 17" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
        </svg>
      </button>
    </form>

    <p v-if="noticeMessage" class="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
      {{ noticeMessage }}
    </p>
    <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <div v-if="isLoading" class="shell-card p-10 text-center text-slate-500">
      Loading production jobs...
    </div>
    <div v-else-if="!jobs.length" class="shell-card p-10 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">Search</div>
      <h2 class="text-lg font-semibold text-slate-900">ไม่พบรายการแผนการผลิต</h2>
      <p class="mt-2 text-sm text-slate-500">ลองล้างตัวกรองหรือเพิ่มแผนการผลิตใหม่</p>
    </div>
    <ProductionTable
      v-else
      :jobs="jobs"
      :selected-ids="selectedIds"
      :can-delete-production="canDeleteProduction"
      :can-accept-production="canAcceptProduction"
      :can-manage-setting-die="canManageSettingDie"
      :highlighted-id="highlightedJobId"
      @toggle-select="toggleSelect"
      @view="openDetail"
      @accept="acceptJob"
      @setting="openSettingDie"
    />

    <ProductionFormModal v-if="showCreateModal" @close="closeCreateModal" @saved="handleCreated" />

    <SettingDieModal
      v-if="settingModalState.isOpen && settingModalState.job && !settingModalState.isLoading && !settingModalState.error"
      :job="settingModalState.job"
      :setting="settingModalState.setting"
      :process-die-no="settingModalState.processDieNo"
      :can-send-to-qc="canSendSettingDieToQC"
      :user-role="role"
      @close="closeSettingDie"
      @saved="handleSettingDieSaved"
    />

    <div v-if="settingModalState.isOpen && (settingModalState.isLoading || settingModalState.error)" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 text-center shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Setting Die</h2>
        <p v-if="settingModalState.isLoading" class="mt-4 text-slate-500">Loading Setting Die...</p>
        <p v-else class="mt-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ settingModalState.error }}
        </p>
        <button type="button" class="mt-6 rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="closeSettingDie">
          Close
        </button>
      </section>
    </div>

    <div v-if="detailState.isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-blue-100 bg-white shadow-2xl">
        <div class="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-blue-100 bg-white/95 p-6 backdrop-blur">
          <div>
            <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">Production detail</p>
            <h2 class="mt-2 text-2xl font-semibold text-slate-950">Plan detail</h2>
          </div>
          <button type="button" class="rounded-full bg-slate-100 px-3 py-1 text-slate-500 hover:bg-slate-200" @click="closeDetail">Close</button>
        </div>

        <div class="overflow-y-auto p-6">
          <div v-if="detailState.isLoading" class="py-10 text-center text-slate-500">Loading detail...</div>
          <p v-else-if="detailState.error" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ detailState.error }}
          </p>
          <div v-else-if="detailState.job" class="grid gap-4 md:grid-cols-2">
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Plan / ID</p>
            <p class="font-semibold text-slate-900">#{{ detailState.job.id }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Date</p>
            <p class="font-semibold text-slate-900">{{ formatDate(detailState.job.prod_date) }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Zone</p>
            <p class="font-semibold text-slate-900">{{ detailState.job.zone || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Part No.</p>
            <p class="font-semibold text-slate-900">{{ detailState.job.part_no || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Die No.</p>
            <p class="font-semibold text-slate-900">{{ detailState.job.die_no || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Q'ty</p>
            <p class="font-semibold text-slate-900">{{ detailState.job.qty || '-' }}</p>
          </div>
          <div class="rounded-2xl bg-blue-50 p-4">
            <p class="text-xs text-slate-500">Status</p>
            <p class="font-semibold text-slate-900">{{ detailState.job.status || '-' }}</p>
          </div>
          <div class="md:col-span-2 rounded-2xl border border-blue-100 p-4">
            <img v-if="detailState.job.image_path" :src="imageUrl(detailState.job.image_path)" alt="Part" class="max-h-64 rounded-2xl object-contain" />
            <p v-else class="text-slate-500">No image attached</p>
          </div>
          <div class="md:col-span-2 rounded-2xl border border-slate-100 p-4">
            <h3 class="font-semibold text-slate-900">Setting Die</h3>
            <p v-if="!detailState.setting" class="mt-2 text-sm text-slate-500">No setting die data yet.</p>
            <dl v-else class="mt-3 grid gap-3 text-sm md:grid-cols-2">
              <div><dt class="text-slate-500">Lot No.</dt><dd class="font-medium">{{ detailState.setting.lot_no || '-' }}</dd></div>
              <div><dt class="text-slate-500">Process Die</dt><dd class="font-medium">{{ detailState.setting.process_die || '-' }}</dd></div>
              <div><dt class="text-slate-500">Technician</dt><dd class="font-medium">{{ detailState.setting.technician || '-' }}</dd></div>
            </dl>
          </div>
          </div>
        </div>
      </section>
    </div>

    <div v-if="bulkDeleteState.isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Delete selected jobs</h2>
        <p class="mt-2 text-sm text-slate-500">
          You are deleting {{ selectedIds.length }} production job(s). Enter admin password to continue.
        </p>
        <label class="mt-5 block">
          <span class="text-sm font-medium text-slate-700">Admin Password</span>
          <input v-model="bulkDeleteState.adminPassword" type="password" class="mt-2 w-full rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
        </label>
        <p v-if="bulkDeleteState.error" class="mt-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ bulkDeleteState.error }}
        </p>
        <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="closeBulkDelete">
            Cancel
          </button>
          <button type="button" :disabled="bulkDeleteState.isSubmitting || !bulkDeleteState.adminPassword" class="rounded-2xl bg-red-600 px-5 py-3 font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60" @click="submitBulkDelete">
            {{ bulkDeleteState.isSubmitting ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
