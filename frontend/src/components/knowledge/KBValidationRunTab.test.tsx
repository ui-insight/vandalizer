import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { KBValidationRunTab } from './KBValidationRunTab'
import { importBatches, resolveRunSelection, VALIDATE_SELECTED_MAX } from './kbQuestionSet'
import type { KBTestQuery } from '../../api/knowledge'

function q(uuid: string, overrides: Partial<KBTestQuery> = {}): KBTestQuery {
  return {
    uuid,
    query: `Question ${uuid}?`,
    expected_source_labels: [],
    expected_answer_contains: null,
    expected_answer: null,
    category: 'factual',
    notes: null,
    external_id: null,
    auto_generated: false,
    source_chunk_ids: [],
    last_judged_score: null,
    last_judged_at: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

const older = { import_batch_id: 'b-old', import_batch_label: 'fy25.csv', import_batch_at: '2026-08-01T00:00:00Z' }
const newer = { import_batch_id: 'b-new', import_batch_label: 'fy26.xlsx', import_batch_at: '2026-09-20T00:00:00Z' }

// Support ticket: an import appends to the combined test set, and Run now ran
// all of it — no way to measure the newly imported file on its own, and no
// statement of what a run would cover before it started.
const QUERIES = [
  q('a1', older),
  q('a2', { ...older, category: 'summary' }),
  q('n1', newer),
  q('n2', { ...newer, category: 'boundary' }),
  q('n3', newer),
  q('m1', { category: null }),
]

function renderTab(props: Partial<Parameters<typeof KBValidationRunTab>[0]> = {}) {
  const onRun = vi.fn()
  render(
    <KBValidationRunTab
      kbReady
      canManage
      queries={QUERIES}
      latestRun={null}
      running={false}
      error={null}
      onRun={onRun}
      {...props}
    />,
  )
  return onRun
}

describe('KBValidationRunTab question selection', () => {
  it('states the full set before running, and runs it as a full run', () => {
    const onRun = renderTab()

    const status = screen.getByText(/will run/).closest('[role="status"]') as HTMLElement
    expect(status).toHaveTextContent('6 questions will run — factual 3 · boundary 1 · summary 1 · uncategorized 1')
    expect(status).toHaveTextContent(/Full run/)

    fireEvent.click(screen.getByRole('button', { name: 'Run 6 questions' }))
    expect(onRun).toHaveBeenCalledWith('judge+baseline', undefined)
  })

  it('runs only a chosen import batch, as a subset', () => {
    const onRun = renderTab()

    fireEvent.change(screen.getByLabelText(/Questions:/), { target: { value: 'batch:b-new' } })

    const status = screen.getByText(/will run/).closest('[role="status"]') as HTMLElement
    expect(status).toHaveTextContent('3 questions will run — factual 2 · boundary 1')
    expect(status).toHaveTextContent(/Subset run \(3 of 6\)/)

    fireEvent.click(screen.getByRole('button', { name: 'Run 3 questions' }))
    expect(onRun).toHaveBeenCalledWith('judge+baseline', ['n1', 'n2', 'n3'])
  })

  it('narrows by category and updates the count', () => {
    const onRun = renderTab()
    fireEvent.change(screen.getByLabelText(/Questions:/), { target: { value: 'batch:b-new' } })

    const chips = screen.getByRole('group', { name: 'Categories to include' })
    fireEvent.click(within(chips).getByRole('button', { name: 'boundary 1' }))

    expect(screen.getByText(/will run/).closest('[role="status"]')).toHaveTextContent('2 questions will run — factual 2')
    fireEvent.click(screen.getByRole('button', { name: 'Run 2 questions' }))
    expect(onRun).toHaveBeenCalledWith('judge+baseline', ['n1', 'n3'])
  })

  it('opens on a selection handed over from Test Queries, in judge mode', () => {
    const onRun = renderTab({ selectedUuids: ['a2', 'm1'] })

    expect(screen.getByText(/will run/).closest('[role="status"]'))
      .toHaveTextContent('2 questions will run — summary 1 · uncategorized 1')
    fireEvent.click(screen.getByRole('button', { name: 'Run 2 questions' }))
    expect(onRun).toHaveBeenCalledWith('judge', ['a2', 'm1'])
  })
})

describe('kbQuestionSet helpers', () => {
  it('lists import batches newest first with their sizes', () => {
    expect(importBatches(QUERIES).map(b => [b.label, b.count])).toEqual([['fy26.xlsx', 3], ['fy25.csv', 2]])
  })

  it('blocks an empty or oversized subset but not an empty KB', () => {
    expect(resolveRunSelection(QUERIES, 'all', null, new Set(['factual', 'summary', 'boundary', 'uncategorized'])).blockedReason)
      .toMatch(/No questions/)
    const many = Array.from({ length: VALIDATE_SELECTED_MAX + 2 }, (_, i) => q(`x${i}`, i === 0 ? { category: 'summary' } : {}))
    expect(resolveRunSelection(many, 'all', null, new Set(['summary'])).blockedReason).toMatch(/limited to 500/)
    // The whole oversized set is a full run, which has no cap.
    expect(resolveRunSelection(many, 'all', null, new Set()).blockedReason).toBeNull()
    expect(resolveRunSelection([], 'all', null, new Set())).toMatchObject({ blockedReason: null, queryUuids: undefined })
  })
})
