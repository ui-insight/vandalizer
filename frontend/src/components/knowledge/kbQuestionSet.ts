import type { KBTestQuery } from '../../api/knowledge'

/** Which questions a Run-now validation covers. Imports append to the one
 * combined test set, so an evaluator measuring a newly imported file needs
 * to pick it out rather than re-run everything. */
export type QuestionScope = 'all' | 'selected' | 'user' | 'auto' | `batch:${string}`

// Mirrors _VALIDATE_SELECTED_MAX in backend/app/routers/knowledge.py.
export const VALIDATE_SELECTED_MAX = 500

// Mirrors UNCATEGORIZED in backend/app/services/kb_validation_service.py.
export const UNCATEGORIZED = 'uncategorized'

export interface ImportBatch {
  id: string
  label: string
  at: string | null
  count: number
}

/** The import batches present in the set, newest first, so the file just
 * imported is the first choice offered. */
export function importBatches(queries: KBTestQuery[]): ImportBatch[] {
  const byId = new Map<string, ImportBatch>()
  for (const q of queries) {
    if (!q.import_batch_id) continue
    const b = byId.get(q.import_batch_id)
    if (b) b.count += 1
    else byId.set(q.import_batch_id, {
      id: q.import_batch_id,
      label: q.import_batch_label || 'Imported file',
      at: q.import_batch_at ?? null,
      count: 1,
    })
  }
  return [...byId.values()].sort((a, b) => (b.at ?? '').localeCompare(a.at ?? ''))
}

export function scopeQueries(
  queries: KBTestQuery[],
  scope: QuestionScope,
  selected: string[] | null,
): KBTestQuery[] {
  if (scope === 'all') return queries
  if (scope === 'user') return queries.filter(q => !q.auto_generated)
  if (scope === 'auto') return queries.filter(q => q.auto_generated)
  if (scope === 'selected') {
    const wanted = new Set(selected ?? [])
    return queries.filter(q => wanted.has(q.uuid))
  }
  const batchId = scope.slice('batch:'.length)
  return queries.filter(q => q.import_batch_id === batchId)
}

export const categoryOf = (q: KBTestQuery) => q.category || UNCATEGORIZED

/** Category distribution, largest first (ties alphabetical). */
export function categoryCounts(queries: KBTestQuery[]): [string, number][] {
  const counts = new Map<string, number>()
  for (const q of queries) counts.set(categoryOf(q), (counts.get(categoryOf(q)) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

/** What a run over ``scope`` minus ``excludedCategories`` would send.
 * ``queryUuids`` is undefined for the whole set — a full run, the only kind
 * that becomes the KB's quality score; anything narrower is a subset run. */
export function resolveRunSelection(
  queries: KBTestQuery[],
  scope: QuestionScope,
  selected: string[] | null,
  excludedCategories: Set<string>,
): { questions: KBTestQuery[]; queryUuids: string[] | undefined; blockedReason: string | null } {
  const questions = scopeQueries(queries, scope, selected)
    .filter(q => !excludedCategories.has(categoryOf(q)))
  const isFull = questions.length === queries.length
  // A KB with no test queries still validates (health + coverage only).
  const blockedReason =
    questions.length === 0 && queries.length > 0 ? 'No questions match this selection.'
    : !isFull && questions.length > VALIDATE_SELECTED_MAX
      ? `A subset run is limited to ${VALIDATE_SELECTED_MAX} questions (${questions.length} selected) — narrow it, or run all questions.`
      : null
  return { questions, queryUuids: isFull ? undefined : questions.map(q => q.uuid), blockedReason }
}
