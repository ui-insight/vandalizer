import assert from 'node:assert/strict'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const repository = fileURLToPath(new URL('../../', import.meta.url))
const outputs = ['lessons.json', 'panel-modules.json', 'course-structure.json', 'editorial-corrections.json']
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'certification-export-qa-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const files = ['frontend/scripts/export-lessons.mjs', ...['modules.ts', 'SelfAssessment.tsx', 'constants.ts', 'editorialCorrections.json'].map(name => `frontend/src/components/certification/${name}`), ...outputs.map(name => `backend/certification-data/${name}`)]
  for (const name of files) { mkdirSync(dirname(join(root, name)), { recursive: true }); copyFileSync(join(repository, name), join(root, name)) }
  const run = () => spawnSync(process.execPath, [join(root, 'frontend/scripts/export-lessons.mjs'), '--check'], { encoding: 'utf8' })
  const valid = run()
  assert.equal(valid.status, 0, valid.stderr)
  return { root, run }
}

for (const name of outputs) test(`stale ${name} fails the read-only export gate`, t => {
  const { root, run } = fixture(t)
  const path = join(root, 'backend/certification-data', name)
  const value = JSON.parse(readFileSync(path, 'utf8'))
  if (name === 'lessons.json') value.ai_literacy.lessons[0].diagram = 'flowchart LR\nSource --> Changed'
  else if (name === 'panel-modules.json') value[0].lessons[0].title = 'A stale panel title'
  else if (name === 'course-structure.json') value.levels[0].xp = 999
  else value.notices[0].paragraphs[0] = 'A stale correction'
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
  const before = readFileSync(path)
  const result = run()
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /Certification lesson export is stale/)
  assert.deepEqual(readFileSync(path), before, 'A check must not rewrite the rejected export')
})

test('a changed reflection question cannot leave the chat export stale', t => {
  const { root, run } = fixture(t)
  const path = join(root, 'frontend/src/components/certification/SelfAssessment.tsx')
  const original = readFileSync(path, 'utf8')
  const question = 'Which best describes your experience with AI tools?'
  assert.ok(original.includes(question))
  writeFileSync(path, original.replace(question, 'Changed reflection question for isolated export QA?'))
  const exported = join(root, 'backend/certification-data/lessons.json')
  const before = readFileSync(exported)
  const result = run()
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /Certification lesson export is stale/)
  assert.deepEqual(readFileSync(exported), before)
})

test('changed practice feedback fails even when lesson text and IDs agree', t => {
  const { root, run } = fixture(t)
  const path = join(root, 'backend/certification-data/lessons.json')
  const value = JSON.parse(readFileSync(path, 'utf8'))
  const lesson = Object.values(value).flatMap(module => module.lessons).find(item => item.knowledge_check)
  assert.ok(lesson)
  lesson.knowledge_check.options[0].explanation = 'Stale practice feedback'
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
  const result = run()
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /Certification lesson export is stale/)
})
