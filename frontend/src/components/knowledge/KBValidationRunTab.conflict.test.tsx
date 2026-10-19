/**
 * Support ticket (NSF PAPPG 24-1 validation): an answer that contradicted the
 * expected answer but agreed with a retrieved excerpt got partial credit and
 * looked like any other WARN. It now shows as an unresolved conflict, and the
 * accuracy says how many conflicts it includes and what it is without them.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { KBValidationRunTab } from './KBValidationRunTab'
import type { KBJudgeVerdict, KBValidationResult } from '../../api/knowledge'

vi.mock('../../utils/truncationWarning', () => ({ useIsAdmin: () => false }))

const judge = (over: Partial<KBJudgeVerdict>): KBJudgeVerdict => ({
  score: 1, verdict: 'PASS', confidence: 0.9, reasoning: '', evidence: '',
  missing_facts: [], hallucinated_facts: [], ...over,
})

function run(conflicts: number): KBValidationResult {
  return {
    kb_uuid: 'kb', kb_title: 'NSF PAPPG', raw_score: 80, num_test_queries: 2, num_sources: 3,
    mode: 'judge',
    source_health: { total: 3, healthy: 3, unhealthy: 0, ratio: 1, details: [] },
    chunk_coverage: { total: 3, with_chunks: 3, without_chunks: 0, ratio: 1, total_chunks: 90 },
    retrieval_precision: {
      total_queries: 2,
      avg_precision: 1,
      avg_judge_score: 0.5,
      num_queries_judged: 2,
      num_expected_conflicts: conflicts,
      avg_judge_score_excluding_conflicts: conflicts ? 1 : 0.5,
      details: [
        {
          query: 'May a proposer use 9-point text for a figure caption?',
          actual_answer: 'No.',
          judge: judge({
            score: 0, verdict: 'FAIL',
            contradicted_facts: ['A proposer may not use 9-point text for a figure caption'],
            expected_conflict: conflicts > 0,
            conflict_evidence: conflicts > 0 ? 'must be 10 points or larger' : '',
          }),
        },
        { query: 'Who signs the budget?', actual_answer: 'The AOR.', judge: judge({}) },
      ],
    },
  } as unknown as KBValidationResult
}

function renderRun(r: KBValidationResult) {
  render(
    <KBValidationRunTab
      kbReady canManage queries={[]} latestRun={r}
      running={false} error={null} onRun={vi.fn()}
    />,
  )
}

describe('KBValidationRunTab expected-answer conflicts', () => {
  it('says how many conflicts the accuracy includes and what it is without them', () => {
    renderRun(run(1))
    const note = screen.getByText(/has an unresolved conflict/)
    expect(note).toHaveTextContent('1 question has an unresolved conflict')
    expect(note).toHaveTextContent('leaving it out, accuracy is 100%')
  })

  it('marks the conflicting question and shows the excerpt that backs the answer', () => {
    renderRun(run(1))
    expect(screen.getByText('conflict')).toBeInTheDocument()

    fireEvent.click(screen.getByText('May a proposer use 9-point text for a figure caption?'))

    expect(screen.getByText('Unresolved conflict with the expected answer.')).toBeInTheDocument()
    expect(screen.getByText('must be 10 points or larger')).toBeInTheDocument()
    expect(screen.getByText(/Contradicts expected:/).closest('div')).toHaveTextContent('A proposer may not use 9-point text')
  })

  it('shows a plain contradiction without the conflict marker or note', () => {
    renderRun(run(0))
    expect(screen.queryByText(/unresolved conflict/)).toBeNull()
    expect(screen.queryByText('conflict')).toBeNull()

    fireEvent.click(screen.getByText('May a proposer use 9-point text for a figure caption?'))
    expect(screen.getByText(/Contradicts expected:/)).toBeInTheDocument()
  })
})
