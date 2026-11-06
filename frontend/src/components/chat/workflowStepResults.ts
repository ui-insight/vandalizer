/**
 * Readable completed-step results for a paused or canceled workflow run.
 *
 * `steps_output` is keyed by step name; each entry is usually
 * `{ step_name, output, input }`. A Document step's output is the input files'
 * uuids, which mean nothing to an approver, so they are named from the run's
 * recorded documents instead.
 */
export interface StepResult {
  name: string
  kind: 'documents' | 'text' | 'fields' | 'data' | 'empty'
  /** documents: file names; fields: [label, value] pairs. */
  items?: string[]
  fields?: [string, string][]
  text?: string
}

const DOC_ID = /^(?:[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value)

function scalar(value: unknown): string | null {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value) && value.every(v => v == null || ['string', 'number', 'boolean'].includes(typeof v))) {
    return value.map(v => (v == null ? '—' : String(v))).join(', ')
  }
  return null
}

export function describeStepResults(
  stepsOutput: Record<string, unknown> | null | undefined,
  documents: { uuid?: string; title?: string | null }[] = [],
): StepResult[] {
  if (!stepsOutput) return []
  const titles = new Map(documents.filter(d => d.uuid).map(d => [String(d.uuid).toLowerCase(), d.title || 'Untitled file']))
  return Object.entries(stepsOutput).map(([key, entry]) => {
    const name = isRecord(entry) && typeof entry.step_name === 'string' && entry.step_name ? entry.step_name : key
    const output = isRecord(entry) && 'output' in entry ? entry.output : entry
    if (output == null || output === '' || (Array.isArray(output) && !output.length)) return { name, kind: 'empty' }
    if (Array.isArray(output) && output.every(v => typeof v === 'string' && DOC_ID.test(v))) {
      const named = (output as string[]).map(id => titles.get(id.toLowerCase()))
      const unknown = named.filter(t => !t).length
      const items = named.filter((t): t is string => !!t)
      if (unknown) items.push(`${unknown} ${unknown === 1 ? 'file' : 'files'}`)
      return { name, kind: 'documents', items }
    }
    if (typeof output === 'string') return { name, kind: 'text', text: output }
    if (isRecord(output)) {
      const fields = Object.entries(output).map(([label, value]) => [label, scalar(value)] as const)
      if (fields.length && fields.every(([, value]) => value !== null)) {
        return { name, kind: 'fields', fields: fields as [string, string][] }
      }
    }
    const flat = scalar(output)
    if (flat !== null) return { name, kind: 'text', text: flat }
    return { name, kind: 'data', text: JSON.stringify(output, null, 2) }
  })
}

/** The same results as plain text, for the copy button. */
export function stepResultsText(results: StepResult[]): string {
  return results.map(result => {
    const body = result.kind === 'documents' ? (result.items ?? []).join('\n')
      : result.kind === 'fields' ? (result.fields ?? []).map(([label, value]) => `${label}: ${value}`).join('\n')
      : result.kind === 'empty' ? '(no output)'
      : result.text ?? ''
    return `## ${result.name}\n\n${body}`
  }).join('\n\n')
}
