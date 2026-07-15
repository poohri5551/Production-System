import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
const form = source('src/components/QCFormModal.vue')

test('Part No. is fixed from Production Plan and never submitted as editable identity', () => {
  assert.match(form, /Fixed from Production Plan/)
  assert.doesNotMatch(form, /v-model="form\.partNo"/)
  assert.doesNotMatch(form, /formData\.append\('qc-part-no'/)
  assert.match(form, /formData\.append\('qc-plan-id', form\.planId\)/)
})

test('both QC workflow timestamps use read-only one-shot controls', () => {
  assert.match(form, /apiField: 'time_start'/)
  assert.match(form, /apiField: 'time_end'/)
  assert.doesNotMatch(form, /datetime-local|type="date"|type="time"/)
  assert.doesNotMatch(form, /qc-time-start|qc-time-end/)
  assert.match(form, /'Not stamped'/)
  assert.match(form, /'✓ Stamped'/)
  assert.match(form, /Stored timestamp is read-only/)
})

test('Stamp confirmation mutates only after confirm and blocks duplicate actions', () => {
  assert.match(form, /title: 'Confirm Timestamp'/)
  assert.match(form, /This timestamp can only be recorded once/)
  assert.match(form, /function requestStamp\(field\)/)
  assert.match(form, /stampDialogField\.value = field\.apiField/)
  assert.doesNotMatch(form.slice(form.indexOf('function requestStamp'), form.indexOf('function cancelStamp')), /stampQCInspectionTimestamp/)
  assert.match(form, /if \(!field \|\| isStamping\.value \|\| form\[field\.formKey\]\) return/)
  assert.match(form, /isStamping\.value = true[\s\S]*await stampQCInspectionTimestamp/)
  assert.match(form, /:busy="isStamping"/)
})

test('ambiguous stamp outcome reloads authoritative timestamps', () => {
  assert.match(form, /async function refreshAuthoritativeTimestamps/)
  assert.match(form, /await getQCInspectionDetail\(form\.qcId\)/)
  assert.match(form, /Reload this QC inspection before trying again/)
})

test('Lot change clears stale QC identity and timestamps before applying next plan', () => {
  const changeBlock = form.slice(form.indexOf('async function handlePlanChange'), form.indexOf('function applyPlan'))
  for (const reset of [
    "form.qcId = ''",
    "form.planId = ''",
    "form.partNo = ''",
    "form.timeStart = ''",
    "form.timeEnd = ''",
  ]) assert.match(changeBlock, new RegExp(reset.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
  assert.match(changeBlock, /const token = \+\+planLoadToken/)
  assert.match(changeBlock, /if \(token !== planLoadToken\) return/)
})

test('API uses dedicated QC stamp routes', () => {
  const client = source('src/api/client.js')
  assert.match(client, /\/api\/qc\/\$\{qcId\}\/timestamps\/\$\{field\}\/stamp/)
  assert.match(client, /\/api\/qc\/plan\/\$\{planId\}\/timestamps\/\$\{field\}\/stamp/)
})
