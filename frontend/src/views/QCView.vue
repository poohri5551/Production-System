<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  bulkDeleteQCInspections,
  getQCInspectionDetail,
  getQCInspections,
} from '../api/client'
import QCDetailModal from '../components/QCDetailModal.vue'
import QCFormModal from '../components/QCFormModal.vue'
import QCTable from '../components/QCTable.vue'
import { can } from '../permissions'

const props = defineProps({
  permissions: {
    type: Array,
    default: () => [],
  },
})

const filters = reactive({
  partNo: '',
  lotNo: '',
})

const inspections = ref([])
const selectedIds = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const showFormModal = ref(false)
const editInspection = ref(null)
const detailState = reactive({ isOpen: false, isLoading: false, error: '', inspection: null })
const bulkDeleteState = reactive({
  isOpen: false,
  adminPassword: '',
  isSubmitting: false,
  error: '',
})

const canManageQC = computed(() => can(props.permissions, 'qc.manage'))
const hasSelectedInspections = computed(() => canManageQC.value && selectedIds.value.length > 0)

onMounted(() => {
  loadQC()
})

async function loadQC() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getQCInspections(filters)
    if (Array.isArray(data)) {
      inspections.value = data
      selectedIds.value = selectedIds.value.filter((id) => data.some((qc) => qc.id === id))
      return
    }
    errorMessage.value = data.message || 'Cannot load QC inspections'
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}

function clearFilters() {
  filters.partNo = ''
  filters.lotNo = ''
  loadQC()
}

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((selectedId) => selectedId !== id)
    : [...selectedIds.value, id]
}

function openCreateModal() {
  if (!canManageQC.value) return
  editInspection.value = null
  showFormModal.value = true
}

async function openEditModal(qcId) {
  if (!canManageQC.value) return
  noticeMessage.value = ''
  errorMessage.value = ''

  try {
    const data = await getQCInspectionDetail(qcId)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load QC inspection'
      return
    }
    editInspection.value = data.qc
    showFormModal.value = true
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function closeFormModal() {
  showFormModal.value = false
  editInspection.value = null
}

function handleSaved() {
  showFormModal.value = false
  editInspection.value = null
  noticeMessage.value = 'QC Inspection saved successfully.'
  loadQC()
}

async function openDetail(qcId) {
  detailState.isOpen = true
  detailState.isLoading = true
  detailState.error = ''
  detailState.inspection = null

  try {
    const data = await getQCInspectionDetail(qcId)
    if (!data.success) {
      detailState.error = data.message || 'Cannot load QC detail'
      return
    }
    detailState.inspection = data.qc
  } catch (error) {
    detailState.error = error.message || 'Cannot connect to backend'
  } finally {
    detailState.isLoading = false
  }
}

function closeDetail() {
  detailState.isOpen = false
}

function openBulkDelete() {
  if (!canManageQC.value) return
  bulkDeleteState.isOpen = true
  bulkDeleteState.adminPassword = ''
  bulkDeleteState.error = ''
}

function closeBulkDelete() {
  if (bulkDeleteState.isSubmitting) return
  bulkDeleteState.isOpen = false
}

async function submitBulkDelete() {
  if (bulkDeleteState.isSubmitting || !canManageQC.value) return
  bulkDeleteState.error = ''
  bulkDeleteState.isSubmitting = true

  try {
    const data = await bulkDeleteQCInspections(selectedIds.value, bulkDeleteState.adminPassword)
    if (!data.success) {
      bulkDeleteState.error = data.message || 'Cannot delete selected QC inspections'
      return
    }
    noticeMessage.value = `Deleted ${data.deleted || selectedIds.value.length} selected QC inspection(s).`
    selectedIds.value = []
    bulkDeleteState.isOpen = false
    await loadQC()
  } catch (error) {
    bulkDeleteState.error = error.message || 'Cannot connect to backend'
  } finally {
    bulkDeleteState.isSubmitting = false
  }
}
</script>

<template>
  <section class="space-y-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">FOR QC INSPECTION</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">การตรวจสอบคุณภาพ</h1>
        <p class="mt-2 max-w-2xl text-slate-500">
          ใช้สำหรับตรวจสอบและจัดการ QC Inspections 
        </p>
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          v-if="canManageQC"
          type="button"
          :disabled="!hasSelectedInspections"
          class="grid h-11 w-11 place-items-center rounded-2xl border border-red-100 bg-red-50 text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title="ลบรายการที่เลือก"
          aria-label="ลบรายการที่เลือก"
          @click="openBulkDelete"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button v-if="canManageQC" type="button" class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700" title="เพิ่ม QC Inspection" aria-label="เพิ่ม QC Inspection" @click="openCreateModal">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>

    <form class="grid gap-3 rounded-3xl border border-blue-100 bg-white p-4 shadow-sm md:grid-cols-[1fr_1fr_auto_auto]" @submit.prevent="loadQC">
      <input v-model="filters.partNo" type="text" placeholder="ค้นหา Part No." class="rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
      <input v-model="filters.lotNo" type="text" placeholder="ค้นหา Lot No." class="rounded-2xl border border-blue-100 px-4 py-3 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-100" />
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
      Loading QC inspections...
    </div>
    <div v-else-if="!inspections.length" class="shell-card p-10 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">QC</div>
      <h2 class="text-lg font-semibold text-slate-900">ไม่พบรายการตรวจสอบคุณภาพ</h2>
      <p class="mt-2 text-sm text-slate-500">ลองล้างตัวกรองหรือเพิ่มรายการตรวจสอบคุณภาพใหม่</p>
    </div>
    <QCTable
      v-else
      :inspections="inspections"
      :selected-ids="selectedIds"
      :can-manage-qc="canManageQC"
      @toggle-select="toggleSelect"
      @view="openDetail"
      @edit="openEditModal"
    />

    <QCFormModal v-if="showFormModal" :inspection="editInspection" @close="closeFormModal" @saved="handleSaved" />
    <QCDetailModal v-if="detailState.isOpen && detailState.inspection && !detailState.isLoading && !detailState.error" :inspection="detailState.inspection" :can-notify-operator="canManageQC" @close="closeDetail" />

    <div v-if="detailState.isOpen && (detailState.isLoading || detailState.error)" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 text-center shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">QC Detail</h2>
        <p v-if="detailState.isLoading" class="mt-4 text-slate-500">Loading QC detail...</p>
        <p v-else class="mt-4 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          {{ detailState.error }}
        </p>
        <button type="button" class="mt-6 rounded-2xl border border-slate-200 px-5 py-3 font-semibold text-slate-600 hover:bg-slate-50" @click="closeDetail">
          Close
        </button>
      </section>
    </div>

    <div v-if="bulkDeleteState.isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Delete selected QC inspections</h2>
        <p class="mt-2 text-sm text-slate-500">
          You are deleting {{ selectedIds.length }} QC inspection(s). Enter admin password to continue.
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
