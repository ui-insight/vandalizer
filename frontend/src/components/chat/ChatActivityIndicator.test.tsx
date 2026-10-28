import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
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
