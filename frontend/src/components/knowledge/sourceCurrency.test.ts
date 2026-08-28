import { describe, it, expect } from 'vitest'
import type { SourceCurrency } from '../../types/knowledge'
import { describeSourceCurrency, formatCurrencyDate, shortHash } from './sourceCurrency'

const OLD = '2026-06-24T09:00:00+00:00'
const ATTEMPT = '2026-08-27T15:30:00+00:00'
const old = formatCurrencyDate(OLD)
const attempt = formatCurrencyDate(ATTEMPT)

function currency(overrides: Partial<SourceCurrency>): SourceCurrency {
  return {
    status: 'ingested',
    last_refresh_attempted_at: null,
    last_retrieved_at: OLD,
    last_ingested_at: OLD,
    content_retrieved_at: OLD,
    content_hash: 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
    content_hash_algorithm: 'sha256',
    content_hash_recorded: true,
    last_refresh_outcome: null,
    last_refresh_error: null,
    ...overrides,
  }
}

describe('describeSourceCurrency', () => {
  it('is null without a currency block (older API)', () => {
    expect(describeSourceCurrency(null)).toBeNull()
    expect(describeSourceCurrency(undefined)).toBeNull()
  })

  it('names the retained text date when a refresh failed on a working source', () => {
    const d = describeSourceCurrency(currency({
      status: 'retained_previous', last_refresh_attempted_at: ATTEMPT,
      last_refresh_outcome: 'retrieval_failed', last_refresh_error: 'HTTP 503',
    }))
    expect(d).toEqual({
      label: 'Retained previous', tone: 'warn',
      summary: `Refresh failed ${attempt} — serving text from ${old}`,
    })
  })

  it('reports an unchanged check with the date the text was last actually new', () => {
    const d = describeSourceCurrency(currency({
      status: 'unchanged', last_refresh_attempted_at: ATTEMPT, last_retrieved_at: ATTEMPT,
      last_refresh_outcome: 'unchanged',
    }))
    expect(d?.tone).toBe('ok')
    expect(d?.summary).toBe(`Checked ${attempt} — unchanged since ${old}`)
  })

  it('reports a refresh, a plain first index, and the failure states', () => {
    expect(describeSourceCurrency(currency({
      status: 'refreshed', last_refresh_attempted_at: ATTEMPT, content_retrieved_at: ATTEMPT, last_ingested_at: ATTEMPT,
    }))?.summary).toBe(`Refreshed ${attempt}`)
    expect(describeSourceCurrency(currency({ status: 'ingested' }))?.summary).toBe(`Indexed ${old}`)
    expect(describeSourceCurrency(currency({
      status: 'retrieval_failed', last_refresh_attempted_at: ATTEMPT, content_retrieved_at: null, last_ingested_at: null,
    }))).toMatchObject({ tone: 'error', summary: `Retrieval failed ${attempt} — no usable text` })
    expect(describeSourceCurrency(currency({
      status: 'ingestion_failed', last_refresh_attempted_at: ATTEMPT,
    }))).toMatchObject({ tone: 'error', summary: `Indexing failed ${attempt} — serving text from ${old}` })
    expect(describeSourceCurrency(currency({
      status: 'never_ingested', last_ingested_at: null, content_retrieved_at: null, last_retrieved_at: null, content_hash: null,
    }))).toMatchObject({ tone: 'muted', summary: 'Not indexed yet' })
  })
})

describe('shortHash / formatCurrencyDate', () => {
  it('truncates a hash for the row and tolerates missing values', () => {
    expect(shortHash('abcdef0123456789ffff')).toBe('abcdef012345')
    expect(shortHash(null)).toBeNull()
    expect(formatCurrencyDate('not a date')).toBeNull()
    expect(formatCurrencyDate(null)).toBeNull()
  })
})
