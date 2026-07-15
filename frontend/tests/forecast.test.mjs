import assert from 'node:assert/strict'
import test from 'node:test'

import { chooseDefaultForecastMonth } from '../src/constants/forecast.js'

const months = [
  { month: '2026-06', label: 'Jun-69' },
  { month: '2026-07', label: 'Jul-69' },
  { month: '2026-09', label: 'Sep-69' },
]

test('selects current imported month', () => {
  assert.equal(chooseDefaultForecastMonth(months, new Date(2026, 6, 14)), '2026-07')
})

test('selects latest imported month not after current month', () => {
  assert.equal(chooseDefaultForecastMonth(months, new Date(2026, 7, 1)), '2026-07')
})

test('selects earliest imported month when all are in future', () => {
  assert.equal(chooseDefaultForecastMonth(months, new Date(2025, 0, 1)), '2026-06')
})
