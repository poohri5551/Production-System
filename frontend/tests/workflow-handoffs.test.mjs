import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')

test('initial handoffs use reusable confirmation dialog and persistent sent labels', () => {
  const setting = source('src/components/SettingDieModal.vue')
  const qc = source('src/components/QCDetailModal.vue')
  assert.match(setting, /WorkflowConfirmationDialog/)
  assert.match(setting, /Confirm Send to QC Line/)
  assert.match(setting, /This initial handoff can only be sent once/)
  assert.match(setting, /✓ Sent to QC Line/)
  assert.match(qc, /Confirm Notify Operator/)
  assert.match(qc, /✓ Operator Notified/)
  assert.match(qc, /isConfirming\.value = true/)
})

test('Setting Die exposes lock, correction, approval, and recheck states', () => {
  const setting = source('src/components/SettingDieModal.vue')
  for (const text of [
    'Locked - Sent to QC Line',
    'Reopen for Correction',
    'Request Correction',
    'Correction Approval Pending',
    'Correction in Progress',
    'Finish Correction',
    'QC Recheck Required',
    'Downstream Review Required',
  ]) assert.match(setting, new RegExp(text))
  assert.match(setting, /\['Admin', 'Sup'\]/)
  assert.match(setting, /Reason for correction/)
})

test('QC stale revision disables Operator handoff', () => {
  const qc = source('src/components/QCDetailModal.vue')
  assert.match(qc, /qc_revision_current/)
  assert.match(qc, /QC recheck required for latest Setting Die revision/)
  assert.match(qc, /QC Review Required - Current Revision/)
  assert.match(qc, /const canSend = computed\(\(\) => props\.canNotifyOperator && qcPass\.value && revisionCurrent\.value/)
})

test('API separates original handoffs from correction actions', () => {
  const client = source('src/api/client.js')
  assert.match(client, /\/api\/qc\/from_setting_die/)
  assert.match(client, /\/api\/setting_die\/corrections\/reopen/)
  assert.match(client, /\/api\/setting_die\/corrections\/request/)
  assert.match(client, /\/finish`/)
})
