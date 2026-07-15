import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import {
  settingDieEligibility,
  settingDieProcessSaved,
} from '../src/constants/settingDieSequence.js'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const processRow = (process_die_no, overrides = {}) => ({
  process_die_no,
  status: 'not_started',
  setting_die_id: null,
  is_saved: false,
  ...overrides,
})
const job = (...process_dies) => ({ id: 15, process_die_count: 3, process_dies })

test('Process 1 is always eligible', () => {
  assert.equal(settingDieEligibility(job(), 1).allowed, true)
})

test('later processes stay blocked while immediately previous process is not saved', () => {
  const plan = job(processRow(1), processRow(2), processRow(3))
  assert.deepEqual(settingDieEligibility(plan, 2), {
    allowed: false,
    previousProcessNo: 1,
    message: 'Complete Process Die 1 first',
  })
  assert.equal(settingDieEligibility(plan, 3).allowed, false)
})

test('Process 2 unlocks after Process 1 valid save', () => {
  const plan = job(processRow(1, { status: 'done', setting_die_id: 101, is_saved: true }), processRow(2), processRow(3))
  assert.equal(settingDieEligibility(plan, 2).allowed, true)
  assert.equal(settingDieEligibility(plan, 3).allowed, false)
})

test('Process 3 unlocks only after Process 2 valid save', () => {
  const plan = job(
    processRow(1, { status: 'done', setting_die_id: 101, is_saved: true }),
    processRow(2, { status: 'done', setting_die_id: 102, is_saved: true }),
    processRow(3),
  )
  assert.equal(settingDieEligibility(plan, 3).allowed, true)
})

test('record without valid saved state does not unlock next process', () => {
  assert.equal(settingDieProcessSaved(processRow(1, { setting_die_id: 101, status: 'incomplete' })), false)
  assert.equal(settingDieEligibility(job(processRow(1, { setting_die_id: 101, status: 'incomplete' }), processRow(2)), 2).allowed, false)
})

test('table and view both guard disabled Setting Die action', () => {
  const table = fs.readFileSync(path.join(frontendRoot, 'src/components/ProductionTable.vue'), 'utf8')
  const view = fs.readFileSync(path.join(frontendRoot, 'src/views/ProductionView.vue'), 'utf8')
  assert.match(table, /:disabled="!settingDieEligibility\(job, process\.process_die_no\)\.allowed"/)
  assert.match(table, /if \(!settingDieEligibility\(job, processDieNo\)\.allowed\) return/)
  assert.match(view, /if \(!eligibility\.allowed\) \{/)
  assert.match(view, /noticeMessage\.value = eligibility\.message/)
})
