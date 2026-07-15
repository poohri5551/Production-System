<script setup>
import { computed, onMounted, ref } from 'vue'
import { getForecastMonths, getForecastRows, saveForecastLots } from '../api/client'
import { chooseDefaultForecastMonth, FORECAST_COLUMN_LABELS } from '../constants/forecast'

const months = ref([])
const selectedMonth = ref(null)
const rowsByMonth = ref({})
const isLoading = ref(false)
const isSaving = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')
const searchQuery = ref('')

const numberFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
const selectedMonthIndex = computed(() => months.value.findIndex((item) => item.month === selectedMonth.value))
const selectedMonthInfo = computed(() => months.value[selectedMonthIndex.value] || null)
const selectedRows = computed(() => rowsByMonth.value[selectedMonth.value] || [])
const allRows = computed(() => Object.values(rowsByMonth.value).flat())
const validDirtyRows = computed(() => allRows.value.filter((row) => row.isDirty && !row.validationError))
const hasInvalidRows = computed(() => allRows.value.some((row) => row.isDirty && row.validationError))
const canSave = computed(() => validDirtyRows.value.length > 0 && !isSaving.value)
const normalizedSearchQuery = computed(() => searchQuery.value.trim().toLocaleLowerCase())
const filteredRows = computed(() => {
  if (!normalizedSearchQuery.value) return selectedRows.value
  return selectedRows.value.filter((row) => String(row.part_no ?? '').toLocaleLowerCase().includes(normalizedSearchQuery.value))
})
const canPrevious = computed(() => selectedMonthIndex.value > 0 && !isLoading.value)
const canNext = computed(() => selectedMonthIndex.value >= 0 && selectedMonthIndex.value < months.value.length - 1 && !isLoading.value)

onMounted(loadMonths)

function hydrateRow(item) {
  const lotCount = item.lot_count === null || item.lot_count === undefined ? null : Number(item.lot_count)
  return {
    ...item,
    originalLotCount: lotCount,
    lotInput: lotCount === null ? '' : String(lotCount),
    isDirty: false,
    validationError: '',
  }
}

async function loadMonths() {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await getForecastMonths()
    if (!data.success) throw new Error(data.message || 'Cannot load FORECAST months.')
    months.value = (data.months || []).slice().sort((left, right) => left.month.localeCompare(right.month))
    const activeMonths = new Set(months.value.map((item) => item.month))
    rowsByMonth.value = Object.fromEntries(
      Object.entries(rowsByMonth.value).filter(([month]) => activeMonths.has(month)),
    )
    selectedMonth.value = activeMonths.has(selectedMonth.value)
      ? selectedMonth.value
      : chooseDefaultForecastMonth(months.value)
    if (selectedMonth.value) await loadMonth(selectedMonth.value)
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend.'
  } finally {
    isLoading.value = false
  }
}

async function loadMonth(month) {
  if (Object.prototype.hasOwnProperty.call(rowsByMonth.value, month)) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await getForecastRows(month)
    if (!data.success) throw new Error(data.message || 'Cannot load FORECAST data.')
    rowsByMonth.value = { ...rowsByMonth.value, [month]: (data.items || []).map(hydrateRow) }
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend.'
  } finally {
    isLoading.value = false
  }
}

async function selectMonthByOffset(offset) {
  const target = months.value[selectedMonthIndex.value + offset]
  if (!target) return
  selectedMonth.value = target.month
  noticeMessage.value = ''
  await loadMonth(target.month)
}

function parseLotInput(value) {
  const text = String(value ?? '').trim()
  if (!text) return { value: null, error: '' }
  if (!/^[1-9]\d*$/.test(text)) return { value: null, error: 'Lot must be a positive whole number.' }
  const parsed = Number(text)
  if (!Number.isSafeInteger(parsed) || parsed > 2147483647) return { value: null, error: 'Lot is too large.' }
  return { value: parsed, error: '' }
}

function updateLot(row) {
  noticeMessage.value = ''
  const result = parseLotInput(row.lotInput)
  row.validationError = result.error
  row.isDirty = result.error ? true : result.value !== row.originalLotCount
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return ''
  const parsed = Number(value)
  return Number.isFinite(parsed) ? numberFormatter.format(parsed) : ''
}

function quantityPerLot(row) {
  const lot = parseLotInput(row.lotInput)
  if (lot.error || lot.value === null) return ''
  const quantity = Number(row.quantity)
  return Number.isFinite(quantity) ? formatNumber(quantity / lot.value) : ''
}

async function saveChanges() {
  if (!canSave.value) return
  isSaving.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  const items = validDirtyRows.value.map((row) => ({
    id: row.id,
    month: row.month,
    lot_count: parseLotInput(row.lotInput).value,
  }))
  try {
    const data = await saveForecastLots(items)
    if (!data.success) {
      if (data.code === 'forecast_month_inactive') await loadMonths()
      throw new Error(data.message || 'Cannot save FORECAST changes.')
    }
    for (const authoritative of data.items || []) {
      const monthRows = rowsByMonth.value[authoritative.month] || []
      const index = monthRows.findIndex((row) => row.id === authoritative.id)
      if (index >= 0) monthRows[index] = hydrateRow(authoritative)
    }
    noticeMessage.value = `Saved ${data.updated_count ?? items.length} FORECAST row(s).`
  } catch (error) {
    errorMessage.value = error.message || 'Cannot connect to backend.'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <section class="min-w-0 space-y-5">
    <div>
      <p class="text-sm font-medium uppercase tracking-[0.22em] text-blue-600">FOR PC ONLY</p>
      <h1 class="mt-2 text-3xl font-semibold text-slate-950">FORECAST</h1>
    </div>

    <div class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
      <div class="min-w-0 flex-1 sm:max-w-md">
        <label class="relative block">
          <span class="sr-only">Search Part No.</span>
          <input v-model="searchQuery" type="search" placeholder="Search Part No."
            class="w-full rounded-2xl border border-blue-100 bg-blue-50/50 px-4 py-3 text-slate-900 outline-none transition focus:border-blue-500 focus:bg-white focus:ring-4 focus:ring-blue-100" />
        </label>
        <p v-if="normalizedSearchQuery" class="mt-2 px-1 text-xs text-slate-500" aria-live="polite">
          {{ filteredRows.length }} {{ filteredRows.length === 1 ? 'result' : 'results' }}
        </p>
      </div>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div v-if="months.length" class="flex items-center justify-center gap-2 rounded-2xl border border-blue-100 bg-white p-1.5 shadow-sm" aria-label="FORECAST month navigation">
          <button type="button" :disabled="!canPrevious" aria-label="Previous imported month"
            class="grid h-9 w-10 place-items-center rounded-xl text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-30"
            @click="selectMonthByOffset(-1)">‹</button>
          <span class="min-w-24 text-center text-sm font-semibold text-slate-900">{{ selectedMonthInfo?.label }}</span>
          <button type="button" :disabled="!canNext" aria-label="Next imported month"
            class="grid h-9 w-10 place-items-center rounded-xl text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-30"
            @click="selectMonthByOffset(1)">›</button>
        </div>
        <button type="button" :disabled="!canSave"
          class="inline-flex h-12 items-center justify-center rounded-2xl bg-blue-600 px-5 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          @click="saveChanges">
          {{ isSaving ? 'Saving...' : `Save Changes${validDirtyRows.length ? ` (${validDirtyRows.length})` : ''}` }}
        </button>
      </div>
    </div>

    <p v-if="noticeMessage" class="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{{ noticeMessage }}</p>
    <p v-if="errorMessage" class="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">{{ errorMessage }}</p>
    <p v-if="hasInvalidRows" class="rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-700">
      Invalid Lot rows are not sent. Valid changed rows from every loaded month remain saveable.
    </p>

    <div v-if="isLoading && !selectedRows.length" class="shell-card p-10 text-center text-slate-500">Loading FORECAST...</div>
    <div v-else-if="!months.length && !errorMessage" class="shell-card p-10 text-center">
      <h2 class="text-lg font-semibold text-slate-900">No imported FORECAST months</h2>
      <p class="mt-2 text-sm text-slate-500">Run separately approved monthly migration and import first.</p>
    </div>
    <div v-else-if="selectedMonth && !selectedRows.length && !errorMessage" class="shell-card p-10 text-center">
      <h2 class="text-lg font-semibold text-slate-900">No FORECAST data for {{ selectedMonthInfo?.label }}</h2>
    </div>
    <div v-else-if="normalizedSearchQuery && !filteredRows.length" class="shell-card p-10 text-center">
      <h2 class="text-lg font-semibold text-slate-900">No matching Part No. found</h2>
      <p class="mt-2 text-sm text-slate-500">Try another search.</p>
    </div>
    <div v-else-if="selectedRows.length" class="shell-card min-w-0 overflow-hidden">
      <div class="max-h-[calc(100vh-18rem)] overflow-auto">
        <table class="w-full min-w-[680px] table-fixed border-collapse text-left">
          <colgroup>
            <col class="w-[45%]" />
            <col class="w-[18.33%]" />
            <col class="w-[18.33%]" />
            <col class="w-[18.34%]" />
          </colgroup>
          <thead class="sticky top-0 z-10 bg-blue-50 text-sm text-blue-800">
            <tr>
              <th rowspan="2" class="border-b border-r border-blue-100 px-5 py-3 align-middle font-semibold">Part No.</th>
              <th colspan="3" class="border-b border-blue-100 px-5 py-3 text-center text-base font-semibold">{{ selectedMonthInfo?.label }}</th>
            </tr>
            <tr>
              <th class="px-5 py-3 text-center font-semibold">{{ FORECAST_COLUMN_LABELS.quantity }}</th>
              <th class="px-5 py-3 text-center font-semibold">{{ FORECAST_COLUMN_LABELS.lotCount }}</th>
              <th class="px-5 py-3 text-center font-semibold">{{ FORECAST_COLUMN_LABELS.quantityPerLot }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-blue-50 bg-white">
            <tr v-for="row in filteredRows" :key="`${row.month}:${row.id}`" :class="row.isDirty ? 'bg-amber-50/50' : ''">
              <td class="whitespace-nowrap px-5 py-3 font-medium text-slate-900">{{ row.part_no }}</td>
              <td class="whitespace-nowrap px-5 py-3 text-center tabular-nums text-slate-700">{{ formatNumber(row.quantity) }}</td>
              <td class="px-5 py-3">
                <div class="mx-auto w-32">
                  <input v-model="row.lotInput" type="number" min="1" max="2147483647" step="1" inputmode="numeric"
                    class="w-full rounded-xl border bg-white px-3 py-2 text-center tabular-nums outline-none transition focus:ring-4"
                    :class="row.validationError ? 'border-red-300 focus:border-red-500 focus:ring-red-100' : 'border-blue-100 focus:border-blue-500 focus:ring-blue-100'"
                    :aria-invalid="Boolean(row.validationError)" @input="updateLot(row)" />
                  <p v-if="row.validationError" class="mt-1 text-xs text-red-600">{{ row.validationError }}</p>
                </div>
              </td>
              <td class="whitespace-nowrap px-5 py-3 text-center font-semibold tabular-nums text-blue-700">{{ quantityPerLot(row) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
