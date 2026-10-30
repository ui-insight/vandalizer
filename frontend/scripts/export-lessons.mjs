#!/usr/bin/env node
/**
 * Export the certification lesson content from the panel's MODULES array
 * (src/components/certification/modules.ts) and the reflective modules' self-assessment
 * questions (src/components/certification/SelfAssessment.tsx) to
 * backend/certification-data/lessons.json, where the chat's certification
 * tools read them. The panel stays the single authored source; rerun this
 * after editing lesson or assessment content:
 *
 *   node scripts/export-lessons.mjs
 *
 * Both arrays must remain pure literals (strings/numbers/arrays/objects) —
 * this script evaluates the extracted text in isolation and fails loudly if
 * it references imports.
 * Supplemental editorialCorrections.json is exported separately; frozen
 * course packages and their assessment requirements are never rewritten.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcPath = path.join(here, '../src/components/certification/modules.ts')
const assessPath = path.join(here, '../src/components/certification/SelfAssessment.tsx')
const outPath = path.join(here, '../../backend/certification-data/lessons.json')
const panelPath = path.join(here, '../../backend/certification-data/panel-modules.json')
const structurePath = path.join(here, '../../backend/certification-data/course-structure.json')
const constantsPath = path.join(here, '../src/components/certification/constants.ts')
const correctionsPath = path.join(here, '../src/components/certification/editorialCorrections.json')
const correctionsOutput = path.join(here, '../../backend/certification-data/editorial-corrections.json')

/** Extract a top-level literal that starts after `marker` and ends at the
 * first line that is exactly `closer` at column 0. */
function extractLiteral(file, marker, opener, closer) {
  const src = readFileSync(file, 'utf8')
  const start = src.indexOf(marker)
  if (start === -1) throw new Error(`${marker} not found in ${file}`)
  // Skip past the declaration's type annotation: the literal begins at the
  // first opener following "= " at the end of a line.
  const assign = src.indexOf(`= ${opener}\n`, start)
  if (assign === -1) throw new Error(`Could not find "= ${opener}" after ${marker}`)
  const open = assign + 2
  const endMatch = new RegExp(`^\\${closer}`, 'm').exec(src.slice(open))
  if (!endMatch) throw new Error(`Could not find end of ${marker}`)
  const text = src.slice(open, open + endMatch.index + 1)
  return new Function(`return ${text}`)()
}

const modules = extractLiteral(srcPath, 'export const MODULES', '[', ']')
const assessments = extractLiteral(assessPath, 'export const MODULE_ASSESSMENTS', '{', '}')

const lessonIds = new Set()
for (const m of modules) for (const lesson of m.lessons) {
  if (!lesson.id || !Number.isInteger(lesson.revision) || lesson.revision < 1 || lessonIds.has(lesson.id)) throw new Error(`Invalid or duplicate lesson identity: ${lesson.id}`)
  lessonIds.add(lesson.id)
}

const out = {}
for (const m of modules) {
  out[m.id] = {
    title: m.title,
    subtitle: m.subtitle ?? '',
    description: m.description ?? '',
    objectives: m.objectives ?? [],
    tips: m.tips ?? [],
    estimated_minutes: m.estimatedMinutes ?? null,
    lessons: (m.lessons ?? []).map((l) => ({
      id: l.id,
      revision: l.revision,
      title: l.title,
      objective: l.objective ?? '',
      content: l.content,
      variant: l.variant ?? 'concept',
      ...(l.diagram ? { diagram: l.diagram } : {}),
      ...(l.knowledgeCheck ? { knowledge_check: l.knowledgeCheck } : {}),
    })),
    ...(assessments[m.id]
      ? {
          assessment: {
            title: assessments[m.id].title,
            subtitle: assessments[m.id].subtitle,
            questions: assessments[m.id].questions.map((q) => ({
              key: q.key,
              question: q.question,
              options: [...q.options],
            })),
          },
        }
      : {}),
  }
}

const serialized = JSON.stringify(out, null, 2) + '\n'
const correctionsSerialized = JSON.stringify(JSON.parse(readFileSync(correctionsPath, 'utf8')), null, 2) + '\n'
const panelSerialized = JSON.stringify(modules, null, 2) + '\n'
const structureSerialized = JSON.stringify({
  levels: extractLiteral(constantsPath, 'export const LEVEL_THRESHOLDS', '[', ']'),
  tiers: extractLiteral(constantsPath, 'export const TIERS', '[', ']'),
}, null, 2) + '\n'
if (process.argv.includes('--check')) {
  if (readFileSync(outPath, 'utf8') !== serialized || readFileSync(panelPath, 'utf8') !== panelSerialized || readFileSync(structurePath, 'utf8') !== structureSerialized || readFileSync(correctionsOutput, 'utf8') !== correctionsSerialized) throw new Error('Certification lesson export is stale. Run node scripts/export-lessons.mjs.')
} else {
  writeFileSync(outPath, serialized)
  writeFileSync(panelPath, panelSerialized)
  writeFileSync(structurePath, structureSerialized)
  writeFileSync(correctionsOutput, correctionsSerialized)
}
const counts = Object.entries(out).map(([id, m]) => `${id}:${m.lessons.length}`).join(' ')
console.log(`${process.argv.includes('--check') ? 'Verified' : 'Wrote'} ${outPath}\nLessons per module — ${counts}`)
