import { act, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ChatActivityIndicator, activityLabel } from './ChatActivityIndicator'

it('names the actual tool before its arguments have finished streaming', () => {
  const { rerender } = render(<ChatActivityIndicator activity={{ phase: 'tool_preparing', tool_name: 'search_knowledge_base' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Preparing tool · Searching knowledge base')
  rerender(<ChatActivityIndicator activity={{ phase: 'tool_preparing', tool_name: 'run_extraction' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Running extraction')
  rerender(<ChatActivityIndicator activity={{ phase: 'context', content: 'Loading 3 attached documents.' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading 3 attached documents.')
})

it('names every parallel tool and its source without revealing generated arguments', () => {
  const label = activityLabel(null, [
    { tool_name: 'search_knowledge_base', tool_call_id: 'search', args: { kb_uuid: 'kb', query: 'eligibility' } },
    { tool_name: 'create_html_artifact', tool_call_id: 'page', args: { title: 'Grant readiness', html: '<script>hidden draft</script>' } },
  ], { kb: 'Research policies' })
  expect(label).toContain('Searching knowledge base · Research policies · eligibility')
  expect(label).toContain('Preparing your page preview · Grant readiness')
  expect(label).not.toContain('hidden draft')
})


it.each(['create_html_artifact', 'revise_html_artifact'])('keeps an elapsed timer during %s preparation and releases it on unmount', toolName => {
  vi.useFakeTimers()
  try {
    const activity = { phase: 'tool_preparing' as const, tool_name: toolName, tool_call_id: 'page' }
    const view = render(<ChatActivityIndicator activity={activity} />)
    expect(screen.getByText('0:00 elapsed')).toHaveAttribute('aria-hidden', 'true')
    act(() => { vi.advanceTimersByTime(65000) })
    expect(screen.getByText('1:05 elapsed')).toBeInTheDocument()
    view.rerender(<ChatActivityIndicator activity={{ ...activity }} />)
    expect(screen.getByText('1:05 elapsed')).toBeInTheDocument()
    view.rerender(<ChatActivityIndicator activity={{ ...activity, tool_call_id: 'another-page' }} />)
    expect(screen.getByText('0:00 elapsed')).toBeInTheDocument()
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  } finally {
    vi.useRealTimers()
  }
})
