import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CertificationChatRecovery, hasCertificationContext } from './CertificationChatRecovery'
import type { ChatMessage } from '../../types/chat'

const course = vi.hoisted(() => ({ openPanel: vi.fn(), refresh: vi.fn().mockResolvedValue(undefined), loading: false }))
vi.mock('../../contexts/CertificationPanelContext', () => ({ useCertificationPanelOptional: () => course }))
beforeEach(() => { vi.clearAllMocks(); course.loading = false })

it.each(['Start the Vandalizer certification course — show me where to begin.', 'Continue my certification — show my progress and the next module.', 'Resume certification'])('opens and rereads the selected course after a failed kickoff: %s', content => {
  render(<CertificationChatRecovery messages={[{ role: 'user', content }]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Open course without chat' }))
  expect(course.openPanel).toHaveBeenCalledTimes(1)
  expect(course.refresh).toHaveBeenCalledTimes(1)
  expect(screen.getByText(/before retrying an uncertain action/)).toBeInTheDocument()
})

it('opens the course while an existing progress read is pending without starting another read', () => {
  course.loading = true
  render(<CertificationChatRecovery messages={[{ role: 'user', content: 'Start certification' }]} />)
  fireEvent.click(screen.getByRole('button', { name: 'Open course without chat' }))
  expect(course.openPanel).toHaveBeenCalledOnce()
  expect(course.refresh).not.toHaveBeenCalled()
})

it('recognizes streamed and retained course tools even when the learner just answers a question', () => {
  const call = { tool_name: 'get_certification_module', tool_call_id: 'course', args: {} }
  const answer: ChatMessage = { role: 'user', content: 'I am unsure about this source.' }
  const histories: ChatMessage[][] = [
    [{ role: 'assistant', content: '', tool_calls: [call] }, answer],
    [{ role: 'assistant', content: '', segments: [{ kind: 'tool_call', call }] }, answer],
    [{ role: 'assistant', content: '', tool_results: [{ ...call, content: {}, quality: null }] }, answer],
    [{ role: 'assistant', content: '', segments: [{ kind: 'tool_result', result: { ...call, content: {}, quality: null } }] }, answer],
  ]
  for (const messages of histories) expect(hasCertificationContext(messages)).toBe(true)
  expect(hasCertificationContext([answer], [call])).toBe(true)
})

it.each(['What does this TLS certificate mean?', 'Summarize certification requirements in this grant.', 'Please continue the extraction.'])('does not turn an unrelated failed chat into a course invitation: %s', content => {
  render(<CertificationChatRecovery messages={[{ role: 'user', content }, { role: 'assistant', content: 'Start certification' }]} />)
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(course.openPanel).not.toHaveBeenCalled()
})
