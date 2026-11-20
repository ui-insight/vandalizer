/**
 * The fields a workflow extraction step runs with when no saved extraction set
 * is linked.
 *
 * The editor stores them as `extractions` (a list). Older workflows, including
 * the seeded catalog, store them as `searchphrases` (one comma-separated
 * string) or `keys`. The engine reads all three, in that order of preference
 * (workflow_engine.ExtractionNode), so those steps run, but the editor only
 * read `extractions` and showed them with no fields at all.
 */
type TaskData = Record<string, unknown>

const LEGACY_KEYS = ['searchphrases', 'keys'] as const

function asFields(value: unknown): string[] {
  const parts = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : []
  return parts.map(part => String(part ?? '').trim()).filter(Boolean)
}

/** The step's own fields, read the way the engine reads them. */
export function inlineExtractionFields(data: TaskData): string[] {
  for (const key of [...LEGACY_KEYS, 'extractions'] as const) {
    const fields = asFields(data[key])
    if (fields.length) return fields
  }
  return []
}

/**
 * Store an edited field list. The older keys are removed: the engine prefers
 * them, so leaving one behind would run the old fields, not the edited ones.
 */
export function withInlineExtractionFields<T extends TaskData>(data: T, fields: string[]): T {
  const next: TaskData = { ...data, extractions: fields }
  for (const key of LEGACY_KEYS) delete next[key]
  return next as T
}

/** Drop every inline field list, as when a saved set is linked and takes over. */
export function withoutInlineExtractionFields<T extends TaskData>(data: T): T {
  const next: TaskData = { ...data }
  for (const key of [...LEGACY_KEYS, 'extractions'] as const) delete next[key]
  return next as T
}
