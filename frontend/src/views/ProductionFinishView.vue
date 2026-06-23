<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import {
  bulkDeleteProductionFinishes,
  confirmProductionFinish,
  getProductionFinishes,
} from '../api/client'
import ProductionFinishFormModal from '../components/ProductionFinishFormModal.vue'
import ProductionFinishTable from '../components/ProductionFinishTable.vue'
import { can } from '../permissions'

const props = defineProps({
  permissions: {
    type: Array,
    default: () => [],
  },
})

const finishes = ref([])
const selectedIds = ref([])
const isLoading = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const showFormModal = ref(false)
const bulkDeleteState = reactive({
  isOpen: false,
  adminPassword: '',
  isSubmitting: false,
  error: '',
})

const canManageProductionFinish = computed(() => can(props.permissions, 'production_finish.manage'))
const hasSelectedFinishes = computed(() => canManageProductionFinish.value && selectedIds.value.length > 0)

onMounted(() => {
  loadProductionFinishes()
})

async function loadProductionFinishes() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const data = await getProductionFinishes()
    if (Array.isArray(data)) {
      finishes.value = data
      selectedIds.value = selectedIds.value.filter((id) => data.some((item) => item.id === id))
      return
    }
    errorMessage.value = data.message || 'Cannot load Production Finish records'
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  } finally {
    isLoading.value = false
  }
}

function toggleSelect(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((selectedId) => selectedId !== id)
    : [...selectedIds.value, id]
}

function openCreateModal() {
  if (!canManageProductionFinish.value) return
  showFormModal.value = true
}

function closeFormModal() {
  showFormModal.value = false
}

function handleSaved() {
  showFormModal.value = false
  noticeMessage.value = 'Production Finish saved successfully.'
  loadProductionFinishes()
}

async function confirmFinish(finishId) {
  if (!canManageProductionFinish.value) return
  noticeMessage.value = ''
  errorMessage.value = ''

  try {
    const data = await confirmProductionFinish(finishId)
    if (!data.success) {
      errorMessage.value = data.message || 'Cannot confirm Production Finish'
      return
    }
    noticeMessage.value = 'Production Finish confirmed. Active workflow records were marked finished by backend.'
    await loadProductionFinishes()
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend'
  }
}

function openBulkDelete() {
  if (!canManageProductionFinish.value) return
  bulkDeleteState.isOpen = true
  bulkDeleteState.adminPassword = ''
  bulkDeleteState.error = ''
}

function closeBulkDelete() {
  if (bulkDeleteState.isSubmitting) return
  bulkDeleteState.isOpen = false
}

async function submitBulkDelete() {
  if (bulkDeleteState.isSubmitting || !canManageProductionFinish.value) return
  bulkDeleteState.error = ''
  bulkDeleteState.isSubmitting = true

  try {
    const data = await bulkDeleteProductionFinishes(selectedIds.value, bulkDeleteState.adminPassword)
    if (!data.success) {
      bulkDeleteState.error = data.message || 'Cannot delete selected Production Finish records'
      return
    }
    noticeMessage.value = `Deleted ${data.deleted || selectedIds.value.length} selected Production Finish record(s).`
    selectedIds.value = []
    bulkDeleteState.isOpen = false
    await loadProductionFinishes()
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
        <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">For production finish</p>
        <h1 class="mt-2 text-3xl font-semibold tracking-tight text-slate-950">เสร็จสิ้นการผลิต</h1>
        <p class="mt-2 max-w-2xl text-slate-500">
          ใช้สำหรับเพิ่มรายการผลิตที่เสร็จสิ้นแล้วและยืนยันผลการผลิตที่เสร็จสิ้น
        </p>
      </div>
      <div class="flex flex-wrap gap-3">
        <button
          v-if="canManageProductionFinish"
          type="button"
          :disabled="!hasSelectedFinishes"
          class="grid h-11 w-11 place-items-center rounded-2xl border border-red-100 bg-red-50 text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          title="ลบรายการที่เลือก"
          aria-label="ลบรายการที่เลือก"
          @click="openBulkDelete"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 7h14M10 11v6M14 11v6M8 7l1-3h6l1 3M7 7l1 13h8l1-13" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button v-if="canManageProductionFinish" type="button" class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700" title="เพิ่ม Production Finish" aria-label="เพิ่ม Production Finish" @click="openCreateModal">
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
      Loading Production Finish records...
    </div>
    <div v-else-if="!finishes.length" class="shell-card p-10 text-center">
      <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-3xl bg-blue-50 text-blue-500">FN</div>
      <h2 class="text-lg font-semibold text-slate-900">ไม่พบรายการผลิตที่เสร็จสิ้นแล้ว</h2>
      <p class="mt-2 text-sm text-slate-500">ลองตรวจสอบใหม่ในภายหลัง</p>
    </div>
    <ProductionFinishTable
      v-else
      :finishes="finishes"
      :selected-ids="selectedIds"
      :can-manage-production-finish="canManageProductionFinish"
      @toggle-select="toggleSelect"
      @confirm="confirmFinish"
    />

    <ProductionFinishFormModal v-if="showFormModal" @close="closeFormModal" @saved="handleSaved" />

    <div v-if="bulkDeleteState.isOpen" class="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/40 px-4 py-8 backdrop-blur-sm">
      <section class="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-blue-100 bg-white p-6 shadow-2xl">
        <h2 class="text-2xl font-semibold text-slate-950">Delete selected Production Finish records</h2>
        <p class="mt-2 text-sm text-slate-500">
          You are deleting {{ selectedIds.length }} Production Finish record(s). Enter admin password to continue.
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
