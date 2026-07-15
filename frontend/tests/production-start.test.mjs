import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
const table = source('src/components/ProductionStartTable.vue')
const view = source('src/views/ProductionStartView.vue')
const form = source('src/components/ProductionStartFormModal.vue')

test('Edit is visibly and behaviorally blocked until confirmation', () => {
  assert.match(table, /:disabled="item\.confirm_status !== 'confirmed'"/)
  assert.match(table, /Confirm Production Start first/)
  assert.match(table, /cursor-not-allowed/)
  assert.match(table, /item\.confirm_status === 'confirmed' && emit\('edit'/)

  const handler = view.slice(view.indexOf('async function openEditModal'), view.indexOf('function closeFormModal'))
  assert.ok(handler.indexOf("current.confirm_status !== 'confirmed'") < handler.indexOf('getProductionStartDetail(startId)'))
  assert.match(handler, /data\.production_start\?\.confirm_status !== 'confirmed'/)
})

test('Confirm uses shared dialog, permanent label, and duplicate request guard', () => {
  assert.match(table, /✓ Confirmed/)
  assert.match(table, />\s*Confirm\s*</)
  assert.match(view, /title="Confirm Production Start"/)
  assert.match(view, /Editing will become available after confirmation/)
  assert.match(view, /if \(!canManageProductionStart\.value \|\| isConfirming\.value \|\| !confirmTarget\.value\) return/)
  assert.match(view, /:busy="isConfirming"/)
})

test('Edit mode fixes Lot No while create mode keeps eligible selector', () => {
  assert.match(form, /v-if="isEditMode"[\s\S]*:value="form\.lotNo"[\s\S]*readonly/)
  assert.match(form, /Fixed from Production Plan/)
  assert.match(form, /v-else class="block"[\s\S]*<select v-model="form\.lotNo"/)
  assert.match(form, /if \(start\?\.id\)[\s\S]*planOptions\.value = \[\][\s\S]*else[\s\S]*loadPlanOptions/)
})

test('Production Start Time is read-only and stamped only through dedicated action', () => {
  assert.doesNotMatch(form, /datetime-local|type="date"|type="time"/)
  assert.match(form, /'Not stamped'/)
  assert.match(form, /'Production Start Time'/)
  assert.match(form, /✓ Stamped/)
  assert.match(form, /Stored timestamp is read-only/)
  assert.match(form, /title="Confirm Timestamp"/)
  assert.match(form, /This timestamp can only be recorded once/)

  const request = form.slice(form.indexOf('function requestStamp'), form.indexOf('function cancelStamp'))
  assert.doesNotMatch(request, /stampProductionStartTime/)
  const confirm = form.slice(form.indexOf('async function confirmStamp'), form.indexOf('async function submitForm'))
  assert.match(confirm, /if \(!canStamp\.value \|\| !stampDialogOpen\.value\) return/)
  assert.match(confirm, /isStamping\.value = true/)
  assert.match(confirm, /await stampProductionStartTime\(form\.startId\)/)
})

test('normal Save submits no timestamp or mutable workflow identity', () => {
  const submit = form.slice(form.indexOf('async function submitForm'), form.indexOf('</script>'))
  assert.doesNotMatch(submit, /timeStart|start-time-start|start-part-no|start-die-no|start-qty|plan_id|part_id/)
  assert.match(submit, /formData\.append\('start-id', form\.startId\)/)
  assert.match(submit, /if \(!isEditMode\.value\) formData\.append\('start-lot-no', form\.lotNo\)/)
})

test('API client exposes dedicated server timestamp route', () => {
  const client = source('src/api/client.js')
  assert.match(client, /\/api\/production_start\/\$\{startId\}\/timestamps\/time_start\/stamp/)
})
