import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { describeStepResults, stepResultsText } from './workflowStepResults'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

const { CompletedStepResults } = await import('./ToolCallDisplay')

// The paused run from the support ticket (Test Approval gate, 1/2 steps).
const stepsOutput = {
  Document: { step_name: 'Document', output: ['09283713632D42B3B2356B9B3BFCF9AA'], input: null },
  Prompt: { input: null, output: '## Subaward Summary\n\n### What the document says\n- **Total amount:** $50,000\n- **Period:** January 1, 2027 – December 31, 2027' },
}
const documents = [{ uuid: '09283713632D42B3B2356B9B3BFCF9AA', title: 'approval-gate-test.docx' }]

describe('Completed step results on a paused run', () => {
  it('shows each step by name, documents by file name, and prompt output as formatted text', () => {
    render(<CompletedStepResults stepsOutput={stepsOutput} documents={documents} />)
    fireEvent.click(screen.getByText('Completed step results'))
    const region = screen.getByRole('region', { name: 'Completed workflow step results' })
    expect(within(region).getByRole('heading', { name: 'Document' })).toBeTruthy()
    expect(within(region).getByText('approval-gate-test.docx')).toBeTruthy()
    expect(within(region).getByRole('heading', { name: 'Subaward Summary' })).toBeTruthy()
    expect(within(region).getByText('Total amount:').tagName).toBe('STRONG')
    const text = region.textContent ?? ''
    expect(text).not.toContain('09283713632D42B3B2356B9B3BFCF9AA')
    expect(text).not.toContain('\\n')
    expect(text).not.toContain('**')
    expect(text).not.toContain('"step_name"')
  })

  it('names unknown files by count, lists flat fields, and keeps nested data readable', () => {
    const results = describeStepResults({
      Document: { output: ['ABCDEF0123456789ABCDEF0123456789', '09283713632D42B3B2356B9B3BFCF9AA'] },
      Extract: { output: { 'Award amount': '$50,000', Sponsor: 'NIH', Years: [2027, 2028] } },
      Nested: { output: { budget: { y1: 1 } } },
      Empty: { output: '' },
    }, documents)
    expect(results[0]).toEqual({ name: 'Document', kind: 'documents', items: ['approval-gate-test.docx', '1 file'] })
    expect(results[1].fields).toEqual([['Award amount', '$50,000'], ['Sponsor', 'NIH'], ['Years', '2027, 2028']])
    expect(results[2].kind).toBe('data')
    expect(results[3].kind).toBe('empty')
    expect(stepResultsText(results.slice(0, 2))).toBe('## Document\n\napproval-gate-test.docx\n1 file\n\n## Extract\n\nAward amount: $50,000\nSponsor: NIH\nYears: 2027, 2028')
  })
})
