import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ToolStatusLine, approveLabel } from './ToolCallDisplay'

vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({}) }))
vi.mock('./CertificationCards', () => ({ useCertificationSync: vi.fn(), CertCheckCard: () => null }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => null }))

// v5 chat retest ticket: small display issues.
describe('approval button label', () => {
  it.each([['create_html_artifact', 'Save page'], ['revise_html_artifact', 'Save new version']])('names the Page action for %s', (name, label) => {
    expect(approveLabel(name)).toBe(label)
    const call = { tool_name: name, tool_call_id: 'page-action', args: { title: 'NIH dashboard', base_revision: '0625f9ce', confirmed: false } }
    const { container } = render(<ToolStatusLine call={call} result={{ ...call, content: { needs_confirmation: true, artifact_preview_html: '<h1>Budget</h1>' }, quality: null }} onConfirm={vi.fn()} />)
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    expect(container).not.toHaveTextContent(/artifact|0625f9ce|confirmed/)
  })

  // Support ticket: "Approve approve workflow step", and a reject card whose
  // only button read "Approve reject workflow step".
  it.each([
    ['approve_workflow_step', 'Approve and continue'],
    ['reject_workflow_step', 'Reject run'],
  ])('names the workflow review decision for %s in plain words', (name, label) => {
    const call = { tool_name: name, tool_call_id: 'a1', args: {} }
    // A chat saved before previews carried their label still reads plainly.
    const { unmount } = render(<ToolStatusLine
      call={call}
      result={{ tool_name: name, tool_call_id: 'a1', content: { needs_confirmation: true, preview: 'Paused step' }, quality: null }}
      onConfirm={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    expect(screen.queryByText(/Approve (approve|reject)/)).not.toBeInTheDocument()
    unmount()
  })

  it("uses the preview's own label so the card matches what the Assistant says", () => {
    const call = { tool_name: 'reject_workflow_step', tool_call_id: 'r1', args: {} }
    render(<ToolStatusLine
      call={call}
      result={{ tool_name: 'reject_workflow_step', tool_call_id: 'r1', content: { needs_confirmation: true, preview: 'Paused step', approval_label: 'Reject run' }, quality: null }}
      onConfirm={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: 'Reject run' })).toBeInTheDocument()
    expect(screen.getByText('Reject run', { selector: 'dd' })).toBeInTheDocument()
  })

  it('never doubles the verb for a tool without its own label', () => {
    expect(approveLabel('approve_run_report')).toBe('Approve run report')
    expect(approveLabel('delete_folder')).toBe('Approve delete folder')
  })
})

describe('guided verification step', () => {
  const call = { tool_name: 'propose_test_case', tool_call_id: 'p1', args: {} }
  const result = (content: unknown) => ({ tool_name: 'propose_test_case', tool_call_id: 'p1', content, quality: null })

  it('names the document and its fields', () => {
    render(<ToolStatusLine call={call} result={result({ document_title: 'subaward.pdf', fields: [{}, {}] })} />)
    expect(screen.getByText('"subaward.pdf": 2 fields ready to verify')).toBeInTheDocument()
  })

  it('shows no blank "0 fields" line for a result without fields', () => {
    render(<ToolStatusLine call={call} result={result({ status: 'completed' })} />)
    expect(screen.queryByText(/0 fields ready to verify/)).not.toBeInTheDocument()
    expect(screen.queryByText(/^: /)).not.toBeInTheDocument()
  })
})
