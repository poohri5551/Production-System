import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const srcRoot = path.join(frontendRoot, 'src')

function source(relativePath) {
  return fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
}

function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name)
    return entry.isDirectory() ? sourceFiles(fullPath) : [fullPath]
  })
}

test('current Vue contract exposes lot_no only', () => {
  const oldIdentifier = /plan_no|planNo|Plan No\.?|PLAN No\.?|PLAN NO\.?/
  const offenders = sourceFiles(srcRoot)
    .filter((file) => oldIdentifier.test(fs.readFileSync(file, 'utf8')))
    .map((file) => path.relative(frontendRoot, file))
  assert.deepEqual(offenders, [])
})

test('Setting Die renders one read-only canonical Lot No.', () => {
  const setting = source('src/components/SettingDieModal.vue')
  assert.equal((setting.match(/>Lot No\.</g) || []).length, 1)
  assert.equal((setting.match(/formData\.append\('set-lot-no'/g) || []).length, 1)
  assert.match(setting, /v-model="form\.lotNo" type="text" required readonly/)
})

test('QC, Start, and Finish submit one canonical Lot No.', () => {
  const cases = [
    ['src/components/QCFormModal.vue', 'qc-lot-no'],
    ['src/components/ProductionStartFormModal.vue', 'start-lot-no'],
    ['src/components/ProductionFinishFormModal.vue', 'finish-lot-no'],
  ]
  for (const [file, field] of cases) {
    const contents = source(file)
    assert.equal((contents.match(new RegExp(`formData\\.append\\('${field}'`, 'g')) || []).length, 1)
  }
})
