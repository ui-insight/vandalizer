#!/usr/bin/env node
/**
 * Export the certification lesson content from the panel's MODULES array
 * (src/pages/Certification.tsx) and the reflective modules' self-assessment
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
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const srcPath = path.join(here, '../src/pages/Certification.tsx')
const assessPath = path.join(here, '../src/components/certification/SelfAssessment.tsx')
const outPath = path.join(here, '../../backend/certification-data/lessons.json')

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
      title: l.title,
      objective: l.objective ?? '',
      content: l.content,
      variant: l.variant ?? 'concept',
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

writeFileSync(outPath, JSON.stringify(out, null, 2) + '\n')
const counts = Object.entries(out).map(([id, m]) => `${id}:${m.lessons.length}`).join(' ')
console.log(`Wrote ${outPath}\nLessons per module — ${counts}`)
