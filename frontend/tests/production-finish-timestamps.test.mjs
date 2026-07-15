import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
const form = source('src/components/ProductionFinishFormModal.vue')

test('Finish and Hold timestamps have no manual date or time controls', () => {
  assert.doesNotMatch(form, /datetime-local|type="date"|type="time"/)
  assert.match(form, /displayDatetime\(form\.timeFinish, 'Not stamped'\)/)
  assert.match(form, /displayDatetime\(form\.holdTime, 'Not held'\)/)
  assert.match(form, /✓ Stamped/)
  assert.match(form, /✓ Held/)
})

test('each action opens exact confirmation before dedicated mutation', () => {
  assert.match(form, /Confirm Finish Timestamp/)
  assert.match(form, /Record the current time as Production Finish Time\? This timestamp can only be recorded once\./)
  assert.match(form, /Confirm Hold Production/)
  assert.match(form, /Record the current time as Hold Production Time\? This timestamp can only be recorded once\./)
  assert.match(form, /Confirm Stamp/)
  assert.match(form, /Confirm Hold/)
  const request = form.slice(form.indexOf('function requestTimestamp'), form.indexOf('function cancelTimestamp'))
  assert.doesNotMatch(request, /stampProductionFinishTimestamp/)
  const confirm = form.slice(form.indexOf('async function confirmTimestamp'), form.indexOf('async function submitForm'))
  assert.match(confirm, /isStamping\.value = true/)
  assert.match(confirm, /await stampProductionFinishTimestamp\(form\.finishId, field\)/)
})

test('normal Save submits no timestamps and guards duplicate requests', () => {
  const submit = form.slice(form.indexOf('async function submitForm'), form.indexOf('</script>'))
  assert.doesNotMatch(submit, /finish-time-finish|finish-hold-time/)
  assert.match(form, /if \(!form\.finishId \|\| isStamping\.value \|\| stampDialogField\.value\) return/)
  assert.match(form, /:disabled="!form\.finishId \|\| isStamping \|\| Boolean\(stampDialogField\)"/)
})

test('API client and table expose dedicated timestamp workflow', () => {
  const client = source('src/api/client.js')
  const table = source('src/components/ProductionFinishTable.vue')
  assert.match(client, /\/api\/production_finish\/\$\{finishId\}\/timestamps\/\$\{field\}\/stamp/)
  assert.match(table, /emit\('timestamps', item\)/)
})
