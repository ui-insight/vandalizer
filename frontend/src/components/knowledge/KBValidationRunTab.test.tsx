import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { KBValidationRunTab } from './KBValidationRunTab'
import { importBatches, resolveRunSelection, VALIDATE_SELECTED_MAX } from './kbQuestionSet'
import type { KBTestQuery, KBValidationResult } from '../../api/knowledge'

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


const savedRun: KBValidationResult = {
  kb_uuid: 'kb-1', kb_title: 'Policies', raw_score: 80, num_test_queries: 1, num_sources: 1,
  source_health: { total: 1, healthy: 1, unhealthy: 0, ratio: 1, details: [] },
  chunk_coverage: { total: 1, with_chunks: 1, without_chunks: 0, ratio: 1, total_chunks: 1 },
  retrieval_precision: { total_queries: 1, avg_precision: 1, details: [{
    query_uuid: 'a1', query: 'What is the saved deadline?', expected_answer: 'October 15',
    expected_sources: ['Policy.pdf'], actual_answer: 'October 30', retrieved_sources: ['Policy.pdf'],
    judge: { score: 0, verdict: 'FAIL', confidence: 1, reasoning: 'The deadline is incorrect.', evidence: 'Due October 15', missing_facts: ['Correct deadline'], hallucinated_facts: [] },
  }] },
}

describe('validation result evidence', () => {
  it('shows the expectation saved with the run and the failed answer together', () => {
    renderTab({ latestRun: savedRun, queries: [q('a1', { expected_answer: 'A later edited expectation' })] })
    fireEvent.click(screen.getByRole('button', { name: /What is the saved deadline/ }))
    expect(screen.getByText('October 15')).toBeVisible()
    expect(screen.getByText('October 30')).toBeVisible()
    expect(screen.getByText('The deadline is incorrect.')).toBeVisible()
    expect(screen.getByText('Expected sources')).toBeVisible()
    expect(screen.queryByText('A later edited expectation')).not.toBeInTheDocument()
  })
  it('labels missing historical expectations without borrowing from the current test set', () => {
    renderTab({ latestRun: { ...savedRun, retrieval_precision: { ...savedRun.retrieval_precision, details: [{ ...savedRun.retrieval_precision.details[0], expected_answer: undefined }] } } })
    fireEvent.click(screen.getByRole('button', { name: /What is the saved deadline/ }))
    expect(screen.getByText('No expected answer was saved with this run.')).toBeVisible()
  })
})

describe('pre-run expectations and limits', () => {
  it('previews only the selected scope and makes missing expected answers explicit', () => {
    renderTab({ queries: [q('ready', { query: 'Included question', expected_answer: 'A supported answer', expected_source_labels: ['Source A'] }), q('missing', { query: 'Excluded question' })], selectedUuids: ['ready'] })
    fireEvent.click(screen.getByText('Preview selected questions (1)'))
    const preview = within(screen.getByRole('region', { name: 'Selected question preview' }))
    expect(preview.getByText('Included question')).toBeInTheDocument()
    expect(preview.getByText(/Expected answer: A supported answer/)).toBeInTheDocument()
    expect(preview.getByText(/Expected sources: Source A/)).toBeInTheDocument()
    expect(preview.queryByText('Excluded question')).not.toBeInTheDocument()
    expect(screen.getByText(/1 of 1 questions have expected answers/)).toBeInTheDocument()
    expect(screen.getByText(/A cost estimate and per-check spending limit are not available/)).toBeInTheDocument()
  })
  it('distinguishes the comparison, answer grading and skipped questions', () => {
    renderTab({ queries: [q('missing')] })
    expect(screen.getByText(/1 without expected answers will receive retrieval checks but no answer grade/)).toBeInTheDocument()
    expect(screen.getByText(/same questions are answered with the KB and with the model alone/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Mode:' }), { target: { value: 'judge' } })
    expect(screen.getByText(/It does not measure how well the model answers without the KB/)).toBeInTheDocument()
  })
})
