import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KBValidationRunTab } from './KBValidationRunTab'

vi.mock('../../utils/truncationWarning', () => ({ useIsAdmin: () => false }))

function renderTab(grader: Parameters<typeof KBValidationRunTab>[0]['grader']) {
  render(
    <KBValidationRunTab
      kbReady canManage queries={[]} latestRun={null}
      running={false} error={null} onRun={vi.fn()} grader={grader}
    />,
  )
}

// Support ticket: one NSF KB and one 120-question set were graded by
// gpt-oss-120b one day and qwen3.8-27b the next, and the only place the user
// could see it was History, after the fact.
describe('KBValidationRunTab grader', () => {
  it('names the grader before the run starts', () => {
    renderTab({ model: 'openai/gpt-oss-120b', configured: true, fallback: null })
    expect(screen.getByTestId('validation-grader')).toHaveTextContent('Graded by openai/gpt-oss-120b')
  })

  it('says when the grader is the default by omission', () => {
    renderTab({ model: 'openai/gpt-oss-120b', configured: false, fallback: null })
    expect(screen.getByTestId('validation-grader')).toHaveTextContent('(default model)')
  })

  it('warns when the chosen grader is gone', () => {
    renderTab({
      model: 'openai/gpt-oss-120b', configured: true,
      fallback: { configured: 'qwen/qwen3.6-27b', used: 'openai/gpt-oss-120b' },
    })
    expect(screen.getByTestId('validation-grader')).toHaveTextContent('qwen/qwen3.6-27b is no longer configured')
  })

  it('shows nothing until the grader is known', () => {
    renderTab(null)
    expect(screen.queryByTestId('validation-grader')).toBeNull()
  })
})
