<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  bulkDeleteProductionStarts,
  confirmProductionStart,
  getProductionStartDetail,
  getProductionStarts,
} from '../api/client'
import ProductionStartFormModal from '../components/ProductionStartFormModal.vue'
import ProductionStartTable from '../components/ProductionStartTable.vue'
import WorkflowConfirmationDialog from '../components/WorkflowConfirmationDialog.vue'
import { can } from '../permissions'
import { findWorkflowTarget } from '../constants/workflowStatus'

const props = defineProps({
  permissions: {
    type: Array,
    default: () => [],
  },
  focusTarget: { type: Object, default: null },
})

const emit = defineEmits(['focus-result'])

const starts = ref([])
const selectedIds = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const highlightedStartId = ref(null)
const showFormModal = ref(false)
const editStart = ref(null)
const confirmTarget = ref(null)
const isConfirming = ref(false)
const bulkDeleteState = reactive({
  isOpen: false,
  adminPassword: '',
  isSubmitting: false,
  error: '',
})

const canManageProductionStart = computed(() => can(props.permissions, 'production_start.manage'))
const hasSelectedStarts = computed(() => canManageProductionStart.value && selectedIds.value.length > 0)
let highlightTimer = null

onMounted(() => {
  loadProductionStarts()
})

async function loadProductionStarts() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionStarts()
    if (Array.isArray(data)) {
      starts.value = data
      selectedIds.value = selectedIds.value.filter((id) => data.some((item) => item.id === id))
      isLoading.value = false
      await applyFocusTarget()
      return
    }
    errorMessage.value = data.message || 'Cannot load Production Start records'
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}

async function applyFocusTarget() {
  if (!props.focusTarget) return
  const record = findWorkflowTarget(starts.value, props.focusTarget)
  if (!record) {
    emit('focus-result', { found: false, lotNo: props.focusTarget.lotNo })
    return
  }
  highlightedStartId.value = record.id
  await nextTick()
  document.getElementById(`production-start-row-${record.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  emit('focus-result', { found: true, lotNo: record.lot_no })
  if (highlightTimer) window.clearTimeout(highlightTimer)
  highlightTimer = window.setTimeout(() => { highlightedStartId.value = null }, 5000)
}

watch(() => props.focusTarget?.token, () => {
  if (!isLoading.value && props.focusTarget) applyFocusTarget()
})

onUnmounted(() => {
  if (highlightTimer) window.clearTimeout(highlightTimer)
})

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((selectedId) => selectedId !== id)
    : [...selectedIds.value, id]
}

function openCreateModal() {
  if (!canManageProductionStart.value) return
  editStart.value = null
  showFormModal.value = true
}

async function openEditModal(startId) {
  if (!canManageProductionStart.value) return
  noticeMessage.value = ''
  errorMessage.value = ''

  const current = starts.value.find((item) => Number(item.id) === Number(startId))
  if (!current || current.confirm_status !== 'confirmed') {
    errorMessage.value = 'Confirm Production Start first'
    return
  }

  try {
    const data = await getProductionStartDetail(startId)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot load Production Start'
      return
    }
    if (data.production_start?.confirm_status !== 'confirmed') {
      errorMessage.value = 'Confirm Production Start first'
      return
    }
    editStart.value = data.production_start
    showFormModal.value = true
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function closeFormModal() {
  showFormModal.value = false
  editStart.value = null
}

function handleSaved() {
  showFormModal.value = false
  editStart.value = null
  noticeMessage.value = 'Production Start saved successfully.'
  loadProductionStarts()
}

function requestConfirmStart(start) {
  if (!canManageProductionStart.value || isConfirming.value || start?.confirm_status === 'confirmed') return
  noticeMessage.value = ''
  errorMessage.value = ''
  confirmTarget.value = start
}

function cancelConfirmStart() {
  if (isConfirming.value) return
  confirmTarget.value = null
}

async function confirmStart() {
  if (!canManageProductionStart.value || isConfirming.value || !confirmTarget.value) return
  isConfirming.value = true
  noticeMessage.value = ''
  errorMessage.value = ''

  try {
    const data = await confirmProductionStart(confirmTarget.value.id)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot confirm Production Start'
      return
    }
    noticeMessage.value = data.already_confirmed
      ? 'Production Start was already confirmed.'
      : 'Production Start confirmed successfully.'
    confirmTarget.value = null
    await loadProductionStarts()
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isConfirming.value = false
  }
}

function openBulkDelete() {
  if (!canManageProductionStart.value) return
  bulkDeleteState.isOpen = true
  bulkDeleteState.adminPassword = ''
  bulkDeleteState.error = ''
}

function closeBulkDelete() {
  if (bulkDeleteState.isSubmitting) return
  bulkDeleteState.isOpen = false
}

async function submitBulkDelete() {
  if (bulkDeleteState.isSubmitting || !canManageProductionStart.value) return
  bulkDeleteState.error = ''
  bulkDeleteState.isSubmitting = true

  try {
    const data = await bulkDeleteProductionStarts(selectedIds.value, bulkDeleteState.adminPassword)
    if (!data.success) {
      bulkDeleteState.error = data.message || 'Cannot delete selected Production Start records'
      return
    }
    noticeMessage.value = `Deleted ${data.deleted || selectedIds.value.length} selected Production Start record(s).`
    selectedIds.value = []
    bulkDeleteState.isOpen = false
    await loadProductionStarts()
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
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">for production start</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">เริ่มต้นการผลิต</h1>
        <p class="mt-2 max-w-2xl text-slate-500">
          ใช้สำหรับเพิ่มรายการเริ่มต้นการผลิตและยืนยันการเริ่มต้นการผลิต
        </p>
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          v-if="canManageProductionStart"
          type="button"
          :disabled="!hasSelectedStarts"
          class="grid h-11 w-11 place-items-center rounded-2xl border border-red-100 bg-red-50 text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title="ลบรายการที่เลือก"
          aria-label="ลบรายการที่เลือก"
          @click="openBulkDelete"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button v-if="canManageProductionStart" type="button" class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700" title="เพิ่ม Production Start" aria-label="เพิ่ม Production Start" @click="openCreateModal">
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>

    <p v-if="noticeMessage" class="rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
      {{ noticeMessage }}
    </p>
    <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
      {{ errorMessage }}
    </p>

    <div v-if="isLoading" class="shell-card p-10 text-center text-slate-500">
      Loading Production Start records...
    </div>
    <div v-else-if="!starts.length" class="shell-card p-10 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">ST</div>
      <h2 class="text-lg font-semibold text-slate-900">ไม่พบรายการเริ่มต้นการผลิต</h2>
      <p class="mt-2 text-sm text-slate-500">เพิ่มรายการเริ่มต้นการผลิตใหม่โดยใช้แผน Die ที่ใช้งานอยู่</p>
    </div>
    <ProductionStartTable
      v-else
      :starts="starts"
      :selected-ids="selectedIds"
      :can-manage-production-start="canManageProductionStart"
      :highlighted-id="highlightedStartId"
      @toggle-select="toggleSelect"
      @confirm="requestConfirmStart"
      @edit="openEditModal"
    />

    <ProductionStartFormModal v-if="showFormModal" :start="editStart" @close="closeFormModal" @saved="handleSaved" @changed="loadProductionStarts" />

    <WorkflowConfirmationDialog
      v-if="confirmTarget"
      title="Confirm Production Start"
      message="Confirm this Production Start record? Editing will become available after confirmation."
      :details="[
        { label: 'Lot No.', value: confirmTarget.lot_no },
        { label: 'Part No.', value: confirmTarget.part_no },
        { label: 'Die No.', value: confirmTarget.die_no },
      ]"
      confirm-label="Confirm"
      busy-label="Confirming..."
      :busy="isConfirming"
      @cancel="cancelConfirmStart"
      @confirm="confirmStart"
    />

    <div v-if="bulkDeleteState.isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Delete selected Production Start records</h2>
        <p class="mt-2 text-sm text-slate-500">
          You are deleting {{ selectedIds.length }} Production Start record(s). Enter admin password to continue.
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
