import type { SourceCurrency } from '../../types/knowledge'

/**
 * Plain-language rendering of a KB source's refresh / ingestion provenance
 * (`source.currency`, see backend app/utils/kb_source_currency.py). Used by
 * the source row and the inspector so both say the same thing.
 */

export interface SourceCurrencyDescription {
  /** Short status word for a chip. */
  label: string
  tone: 'ok' | 'warn' | 'error' | 'muted'
  /** One line for the source row, e.g. "Refresh failed Aug 27, 2026 — serving text from Jun 24, 2026". */
  summary: string
}

export function formatCurrencyDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatCurrencyDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString()
}

/** First 12 hex characters — enough to eyeball a match; the full hash sits in the tooltip / inspector. */
export function shortHash(hash: string | null | undefined): string | null {
  if (!hash) return null
  return hash.slice(0, 12)
}

export function describeSourceCurrency(c: SourceCurrency | null | undefined): SourceCurrencyDescription | null {
  if (!c) return null
  const attempted = formatCurrencyDate(c.last_refresh_attempted_at)
  const retained = formatCurrencyDate(c.content_retrieved_at)
  const ingested = formatCurrencyDate(c.last_ingested_at)
  const retainedClause = retained ? ` — serving text from ${retained}` : ''

  switch (c.status) {
    case 'refreshed':
      return { label: 'Refreshed', tone: 'ok', summary: `Refreshed ${attempted ?? retained ?? ''}`.trim() }
    case 'unchanged': {
      const checked = formatCurrencyDate(c.last_retrieved_at) ?? attempted
      return {
        label: 'Unchanged',
        tone: 'ok',
        summary: `Checked ${checked ?? ''} — unchanged since ${retained ?? '?'}`.replace('Checked  —', 'Checked —').trim(),
      }
    }
    case 'retained_previous':
      return {
        label: 'Retained previous',
        tone: 'warn',
        summary: `Refresh failed${attempted ? ` ${attempted}` : ''}${retainedClause}`,
      }
    case 'retrieval_failed':
      return {
        label: 'Retrieval failed',
        tone: 'error',
        summary: `Retrieval failed${attempted ? ` ${attempted}` : ''} — no usable text`,
      }
    case 'ingestion_failed':
      return {
        label: 'Indexing failed',
        tone: 'error',
        summary: `Indexing failed${attempted ? ` ${attempted}` : ''}${retainedClause}`,
      }
    case 'ingested':
      return { label: 'Indexed', tone: 'muted', summary: ingested ? `Indexed ${ingested}` : 'Indexed' }
    case 'never_ingested':
    default:
      return { label: 'Not indexed', tone: 'muted', summary: 'Not indexed yet' }
  }
}
