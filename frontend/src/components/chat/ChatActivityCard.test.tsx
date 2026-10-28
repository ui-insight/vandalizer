import { act, fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ChatActivityCard } from './ChatActivityCard'
import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'

const page: ToolCallInfo = { tool_name: 'create_html_artifact', tool_call_id: 'page', args: { title: 'Grant readiness', html: '<script>hidden draft</script>' } }

it('shows page generation before any tool call exists and distinguishes preview from save', () => {
  const jump = vi.fn()
  const { rerender } = render(<ChatActivityCard activity={{ phase: 'tool_preparing', tool_name: 'create_html_artifact' }} onViewActivity={jump} />)
  expect(screen.getByRole('status')).toHaveTextContent('Designing your page')
  fireEvent.click(screen.getByRole('button', { name: 'View activity' }))
  expect(jump).toHaveBeenCalledOnce()
  rerender(<ChatActivityCard calls={[page]} onViewActivity={jump} />)
  expect(screen.getByRole('status')).toHaveTextContent('Preparing your page preview')
  expect(screen.queryByText(/hidden draft/)).not.toBeInTheDocument()
  rerender(<ChatActivityCard calls={[{ ...page, args: { ...page.args, confirmed: true } }]} onViewActivity={jump} />)
  expect(screen.getByRole('status')).toHaveTextContent('Saving your page')
})

it('keeps working visible between tools and reports approvals and failures honestly', () => {
  const results: ToolResultInfo[] = [
    { ...page, content: { needs_confirmation: true }, quality: null },
    { tool_name: 'search_knowledge_base', tool_call_id: 'search', content: [{ error: 'Source unavailable' }], quality: null },
  ]
  render(<ChatActivityCard activity={{ phase: 'reviewing' }} results={results} onViewActivity={() => {}} />)
  expect(screen.getByRole('status')).toHaveTextContent('Reviewing tool results')
  fireEvent.click(screen.getByRole('button', { name: '2 tool responses' }))
  expect(screen.getByText('Awaiting approval')).toBeVisible()
  expect(screen.getByText('Needs attention')).toBeVisible()
  expect(screen.queryByText('Completed')).not.toBeInTheDocument()
})

it('shows parallel tools, readable document names, and elapsed time without invented percentages', () => {
  vi.useFakeTimers()
  try {
    render(<ChatActivityCard calls={[page, { tool_name: 'get_document_text', tool_call_id: 'doc', args: { document_uuid: 'd1' } }]} names={{ d1: 'Funding opportunity.pdf' }} onViewActivity={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('2 tools working in parallel')
    fireEvent.click(screen.getByRole('button', { name: '0 tool responses · 2 active' }))
    expect(screen.getByText('Funding opportunity.pdf')).toBeVisible()
    act(() => { vi.advanceTimersByTime(65_000) })
    expect(screen.getByLabelText('Elapsed time: 1m 5s')).toBeVisible()
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument()
  } finally { vi.useRealTimers() }
})
