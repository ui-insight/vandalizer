import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { ChatActivityIndicator } from './ChatActivityIndicator'
import type { ToolCallInfo, ToolResultInfo } from '../../types/chat'

const page: ToolCallInfo = { tool_name: 'create_html_artifact', tool_call_id: 'page', args: { title: 'Grant readiness', html: '<script>hidden draft</script>' } }

it('shows page generation before any tool call exists and distinguishes preview from save', () => {
  const { rerender } = render(<ChatActivityIndicator activity={{ phase: 'tool_preparing', tool_name: 'create_html_artifact' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Designing your page')
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  rerender(<ChatActivityIndicator calls={[page]} />)
  expect(screen.getByRole('status')).toHaveTextContent('Preparing your page preview')
  expect(screen.queryByText(/hidden draft/)).not.toBeInTheDocument()
  rerender(<ChatActivityIndicator calls={[{ ...page, args: { ...page.args, confirmed: true } }]} />)
  expect(screen.getByRole('status')).toHaveTextContent('Saving your page')
})

it('keeps working visible between tools and reports approvals and failures honestly', () => {
  const results: ToolResultInfo[] = [
    { ...page, content: { needs_confirmation: true }, quality: null },
    { tool_name: 'search_knowledge_base', tool_call_id: 'search', content: [{ error: 'Source unavailable' }], quality: null },
  ]
  render(<ChatActivityIndicator activity={{ phase: 'reviewing' }} results={results} />)
  expect(screen.getByRole('status')).toHaveTextContent('Reviewing tool results')
  fireEvent.click(screen.getByRole('button', { name: 'Show tool activity' }))
  expect(screen.getByText('Awaiting approval')).toBeVisible()
  expect(screen.getByText('Needs attention')).toBeVisible()
  expect(screen.queryByText('Completed')).not.toBeInTheDocument()
})

it('reveals readable tool details on demand and can collapse them again', () => {
  render(<ChatActivityIndicator calls={[page, { tool_name: 'get_document_text', tool_call_id: 'doc', args: { document_uuid: 'd1' } }]} names={{ d1: 'Funding opportunity.pdf' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('2 tools working in parallel')
  expect(screen.queryByText('Funding opportunity.pdf')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Show tool activity' }))
  expect(screen.getByText('Funding opportunity.pdf')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Hide tool activity' }))
  expect(screen.queryByText('Funding opportunity.pdf')).not.toBeInTheDocument()
})
