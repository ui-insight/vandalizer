import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

const call = { tool_name: 'get_optimization_run', tool_call_id: 'o1', args: { item_kind: 'extraction', run_uuid: 'r1' } }
const result = (content: unknown) => ({ tool_name: 'get_optimization_run', tool_call_id: 'o1', content, quality: null })

// Support ticket: a 93% result read "score 1/100 (was 1)".
describe('optimization run summary', () => {
  it('shows the score on the screen scale and marks a tie', () => {
    render(<ToolStatusLine call={call} result={result({ status: 'completed', score: 0.93, baseline_score: 0.926, score_percent: 93, baseline_score_percent: 93, tied_with_baseline: true })} />)
    expect(screen.getByText(/Completed, score 93\/100 \(was 93\) · no meaningful difference/)).toBeInTheDocument()
  })

  it('converts a raw 0..1 score from an older result', () => {
    render(<ToolStatusLine call={call} result={result({ status: 'completed', score: 0.93, baseline_score: 0.88 })} />)
    expect(screen.getByText(/Completed, score 93\/100 \(was 88\)/)).toBeInTheDocument()
  })
})
