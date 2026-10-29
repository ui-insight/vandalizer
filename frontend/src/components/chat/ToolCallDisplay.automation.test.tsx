import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine } from './ToolCallDisplay'
import { ChatMessage } from './ChatMessage'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openAutomation: vi.fn() }) }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null, useCertificationPanel: () => ({}) }))

const call = { tool_name: 'create_automation', tool_call_id: 'auto', args: { name: 'NIH PDFs' } }
const settings = [
  { label: 'File types', value: '.pdf' },
  { label: 'Exclude patterns', value: 'draft*, temp_*' },
  { label: 'Batch mode', value: 'On' },
  { label: 'Save results to', value: 'Results' },
  { label: 'Result format', value: 'csv' },
  { label: 'File naming pattern', value: '{document_name}_{date}' },
  { label: 'Email notification', value: 'Automation owner, reviewer@example.org' },
  { label: 'Send email', value: 'On success only' },
  { label: 'Status', value: 'Paused' },
]
const result = (content: Record<string, unknown>) => ({ tool_name: 'create_automation', tool_call_id: 'auto', quality: null, content })

describe('automation approval options', () => {
  it('does not hide a revised configuration as a duplicate approval', () => {
    const calls = ['pdf', 'docx', 'pdf'].map((extension, index) => ({
      ...call, tool_call_id: `auto-${index}`, args: { name: 'NIH PDFs', file_types: [extension] },
    }))
    render(<ChatMessage message={{ role: 'assistant', content: '',
      segments: calls.map(call => ({ kind: 'tool_call', call })),
      tool_results: calls.map(call => ({ ...result({ needs_confirmation: true, preview: 'Create NIH automation.',
        automation_settings: [{ label: 'File types', value: `.${call.args.file_types[0]}` }],
      }), tool_call_id: call.tool_call_id })),
    }} />)
    expect(screen.getAllByLabelText('Automation settings')).toHaveLength(2)
    expect(screen.getByText('.pdf')).toBeVisible()
    expect(screen.getByText('.docx')).toBeVisible()
  })

  it('shows every resolved option inside the approval card before creation', () => {
    const approve = vi.fn()
    render(<ToolStatusLine call={call} result={result({ needs_confirmation: true,
      preview: 'Run NIH R01 Extraction when a document is added to Certification Lab. Created Paused.',
      automation_settings: settings,
    })} onConfirm={approve} />)
    const review = screen.getByRole('region', { name: 'Review proposed action' })
    for (const row of settings) {
      expect(within(review).getByLabelText('Automation settings')).toHaveTextContent(row.label)
      expect(within(review).getByLabelText('Automation settings')).toHaveTextContent(row.value)
    }
    expect(approve).not.toHaveBeenCalled()
    fireEvent.click(within(review).getByRole('button', { name: 'Create automation' }))
    expect(approve).toHaveBeenCalledWith('Yes, go ahead')
  })

  it('uses Paused on the created receipt and retains the approved settings', () => {
    render(<ToolStatusLine call={call} result={result({ id: 'auto-1', enabled: false,
      message: 'Automation NIH PDFs created (Paused).', automation_settings: settings,
    })} />)
    expect(screen.getByRole('status')).toHaveTextContent('Paused')
    expect(screen.getByLabelText('Automation settings')).toHaveTextContent('.pdf')
    expect(screen.getByRole('button', { name: 'Open automation' })).toBeVisible()
    expect(screen.queryByText(/disabled/i)).not.toBeInTheDocument()
  })

  it('keeps older receipts without structured settings readable', () => {
    render(<ToolStatusLine call={call} result={result({ needs_confirmation: true, preview: 'Create NIH PDFs.' })} />)
    expect(screen.getByRole('region', { name: 'Review proposed action' })).toHaveTextContent('Create NIH PDFs.')
    expect(screen.queryByLabelText('Automation settings')).not.toBeInTheDocument()
  })
})
