import assert from 'node:assert/strict'
import test from 'node:test'

import {
  filterDashboardItems,
  findWorkflowTarget,
  nextActionForItem,
  statePresentation,
  workflowDestination,
} from '../src/constants/workflowStatus.js'

const items = [
  { plan_id: 1, lot_no: 'LOT-1', dashboard_bucket: 'waiting' },
  { plan_id: 2, lot_no: 'LOT-2', dashboard_bucket: 'in_progress' },
  { plan_id: 3, lot_no: 'LOT-3', dashboard_bucket: 'qc' },
  { plan_id: 4, lot_no: 'LOT-4', dashboard_bucket: 'completed' },
]

test('Dashboard card filtering uses canonical mutually exclusive bucket', () => {
  assert.equal(filterDashboardItems(items, 'total').length, 4)
  assert.deepEqual(filterDashboardItems(items, 'waiting').map((item) => item.plan_id), [1])
  assert.deepEqual(filterDashboardItems(items, 'in_progress').map((item) => item.plan_id), [2])
  assert.deepEqual(filterDashboardItems(items, 'qc').map((item) => item.plan_id), [3])
  assert.deepEqual(filterDashboardItems(items, 'completed').map((item) => item.plan_id), [4])
})

test('stage navigation maps to activeMenu destinations', () => {
  const cases = [
    ['Not Started', 'production'],
    ['Setting Die', 'production'],
    ['QC', 'qc'],
    ['Production Start', 'production-start'],
    ['Production Finish', 'production-finish'],
  ]
  for (const [current_step, menu] of cases) {
    assert.deepEqual(workflowDestination({ current_step }), { type: 'workflow', menu })
  }
  assert.deepEqual(workflowDestination({ current_step: 'Completed' }), { type: 'detail', menu: null })
})

test('raw statuses become human-readable stage-aware states', () => {
  assert.equal(statePresentation('Not Started', 'accepted').label, 'Plan Accepted')
  assert.equal(statePresentation('Setting Die', 'in_progress', { setting_die_progress: { completed: 1, total: 3 } }).label, 'Process 2 of 3 in progress')
  assert.equal(statePresentation('QC', 'pass').label, 'QC Passed')
  assert.equal(statePresentation('QC', 'fail').label, 'QC Failed')
  assert.equal(statePresentation('Production Start', 'confirmed').label, 'Production Started')
  assert.equal(statePresentation('Production Finish', 'pending').label, 'Awaiting Finish Confirmation')
  assert.doesNotMatch(statePresentation('', 'in_progress').label, /_/)
})

test('Next Action follows supported workflow states', () => {
  assert.equal(nextActionForItem({ current_step: 'Not Started', status: 'accepted' }), 'Start Setting Die')
  assert.equal(nextActionForItem({ current_step: 'Setting Die', setting_die_progress: { completed: 1, total: 3 } }), 'Continue Setting Die Process 2')
  assert.equal(nextActionForItem({ current_step: 'Setting Die', setting_die_progress: { completed: 3, total: 3 } }), 'Proceed to QC Inspection')
  assert.equal(nextActionForItem({ current_step: 'QC', status: 'pending' }), 'Complete QC Inspection')
  assert.equal(nextActionForItem({ current_step: 'QC', status: 'pass' }), 'Proceed to Production Start')
  assert.equal(nextActionForItem({ current_step: 'Production Start', status: 'confirmed' }), 'Proceed to Production Finish')
  assert.equal(nextActionForItem({ current_step: 'Production Finish', status: 'pending' }), 'Confirm Production Finish')
  assert.equal(nextActionForItem({ current_step: 'Completed', status: 'completed' }), 'No further action')
})

test('focus identity prefers plan_id before Lot No. fallback', () => {
  const records = [
    { id: 10, plan_id: 99, lot_no: 'SAME' },
    { id: 11, plan_id: 15, lot_no: 'OTHER' },
  ]
  assert.equal(findWorkflowTarget(records, { planId: 15, lotNo: 'SAME' }).id, 11)
  assert.equal(findWorkflowTarget(records, { planId: null, lotNo: 'SAME' }).id, 10)
  assert.equal(findWorkflowTarget([{ id: 15, lot_no: 'LOT' }], { planId: 15 }, { useIdAsPlanId: true }).id, 15)
})
