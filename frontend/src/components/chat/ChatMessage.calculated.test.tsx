import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ChatMessage } from './ChatMessage'

// NIH R01 budget ticket: figures chat worked out from the sheet were labelled
// "may come from the model's general knowledge". They are calculations.

vi.mock('../../api/feedback', () => ({ submitChatFeedback: vi.fn() }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), isOpen: false }),
  useCertificationPanelOptional: () => null,
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ selectedDocuments: [], openDocument: vi.fn() }) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))

const { CalculationSteps } = await import('./ToolCallDisplay')

describe('calculated figures', () => {
  it('lists a calculate step\'s figure with its working, not as general knowledge', () => {
    render(<ChatMessage message={{
      role: 'assistant',
      content: 'Y1 direct costs are $253,000.',
      calculated_figures: [{ figure: '$253,000', formula: 'Y1 direct: 200000 + 15000 + 8000 + 20000 + 10000 = 253,000' }],
    }} />)
    const list = screen.getByRole('list', { name: 'Calculations', hidden: true })
    expect(list).toHaveTextContent('Y1 direct: 200000 + 15000 + 8000 + 20000 + 10000 = 253,000')
    expect(screen.queryByText(/general knowledge/)).toBeNull()
  })

  it('shows the working, with range checks as Yes/No and refused steps called out', () => {
    render(<CalculationSteps steps={[
      { label: 'Y5 direct', expression: '140000 + 0 + 5000 + 15000 + 10000', result: '170,000' },
      { label: 'Y5 in range', expression: '51000 <= (49000) <= 57000', check: false, result: 'false' },
      { label: 'Bad', expression: 'sum(1,250,000)', error: 'Write numbers without thousands separators' },
    ]} />)
    fireEvent.click(screen.getByText('Show the working'))
    const rows = screen.getAllByRole('row')
    expect(within(rows[1]).getByText('170,000')).toBeTruthy()
    expect(within(rows[2]).getByText('No')).toBeTruthy()
    expect(within(rows[3]).getByText(/Not computed/)).toBeTruthy()
  })
})
