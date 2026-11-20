import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AskOwnerPanel, OwnerFeedbackPanel } from './PageFeedbackPanel'
import { PublishedPageContent } from './PublishedPageContent'
import type { PageFeedbackItem } from '../../api/pageFeedback'

// Support ticket: team members and public-link viewers couldn't ask about a
// figure or flag a section, and the owner had nowhere to see such questions.

const api = vi.hoisted(() => ({
  listPageFeedback: vi.fn(), askPageOwner: vi.fn(), askPublicPageOwner: vi.fn(),
  answerPageFeedback: vi.fn(), setPageFeedbackStatus: vi.fn(), updatePageFeedbackSettings: vi.fn(),
}))
vi.mock('../../api/pageFeedback', async (actual) => {
  const real = await actual<typeof import('../../api/pageFeedback')>()
  return { ...api, asChangeRequest: real.asChangeRequest }
})

const SPOT = { path: '1/0/0/1', text: '$20,000' }
const ITEM: PageFeedbackItem = {
  uuid: 'fb1', revision: 'r1', version: 3, anchor: SPOT, message: 'Is Equipment Y2 $20k the microscope quote?',
  kind: 'question', status: 'open', author_kind: 'member', author_name: 'Pat Kim', created_at: '2026-11-03T10:00:00Z', answer: null,
}

beforeEach(() => { vi.clearAllMocks() })

describe('page frame messaging', () => {
  it('reports picks from its own frame only, and tells the frame to pick and to show a spot', () => {
    const onPick = vi.fn()
    const { rerender } = render(<PublishedPageContent src="/api/pages/p/revisions/r1/content" picking onPick={onPick} />)
    const frame = screen.getByTitle('Published page content') as HTMLIFrameElement
    const post = vi.spyOn(frame.contentWindow!, 'postMessage')
    fireEvent.load(frame)
    expect(post).toHaveBeenCalledWith({ type: 'vandalizer:pick-mode', on: true }, '*')
    const message = (data: unknown, source: Window | null) => act(() => { window.dispatchEvent(new MessageEvent('message', { data, source })) })
    message({ type: 'vandalizer:page-pick', path: '1/0/0/1', text: '$20,000' }, window)
    expect(onPick).not.toHaveBeenCalled()
    message({ type: 'vandalizer:page-pick', path: 'body > script', text: '$20,000' }, frame.contentWindow)
    expect(onPick).toHaveBeenLastCalledWith({ path: null, text: '$20,000' })
    message({ type: 'vandalizer:page-pick', path: '1/0/0/1', text: '$20,000' }, frame.contentWindow)
    expect(onPick).toHaveBeenLastCalledWith(SPOT)
    rerender(<PublishedPageContent src="/api/pages/p/revisions/r1/content" spot={SPOT} />)
    expect(post).toHaveBeenCalledWith({ type: 'vandalizer:show-spot', path: '1/0/0/1', text: '$20,000' }, '*')
  })
})

describe('Ask the owner', () => {
  it('lets a team member pick a figure and send a question', async () => {
    api.askPageOwner.mockResolvedValue(ITEM)
    const onFrame = vi.fn()
    const onAsked = vi.fn()
    const props = { audience: { kind: 'member' as const, uuid: 'p', revision: 'r1' }, onFrame, sharedBy: 'Shared by Dana Reyes, University of Idaho Office of Sponsored Programs', publicQuestions: false, answers: [], onAsked }
    const { rerender } = render(<AskOwnerPanel {...props} picked={null} />)
    expect(screen.getByText('Shared by Dana Reyes, University of Idaho Office of Sponsored Programs')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ask the owner' }))
    expect(onFrame).toHaveBeenLastCalledWith({ picking: true, spot: null })
    expect(screen.getByRole('status')).toHaveTextContent('Click the figure, row or section')
    rerender(<AskOwnerPanel {...props} picked={SPOT} />)
    expect(screen.getByText('$20,000').closest('p')).toHaveTextContent('About: $20,000')
    fireEvent.click(screen.getByRole('radio', { name: 'Flag a problem' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'What looks wrong?' }), { target: { value: 'Y2 should be $25,000 per the quote.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to the owner' }))
    await waitFor(() => expect(api.askPageOwner).toHaveBeenCalledWith('p', { revision: 'r1', anchor: SPOT, message: 'Y2 should be $25,000 per the quote.', kind: 'flag' }))
    expect(await screen.findByText(/You’ll get their answer in your notifications/)).toBeInTheDocument()
    expect(onAsked).toHaveBeenCalled()
  })

  it('offers public viewers the question form only when the owner allows it', async () => {
    const base = { audience: { kind: 'public' as const, token: 't' }, picked: null, onFrame: vi.fn(), sharedBy: 'Shared by Dana Reyes', answers: [], onAsked: vi.fn() }
    const { unmount } = render(<AskOwnerPanel {...base} publicQuestions={false} />)
    expect(screen.queryByRole('button', { name: 'Ask the owner' })).not.toBeInTheDocument()
    unmount()
    api.askPublicPageOwner.mockResolvedValue({ ok: true })
    render(<AskOwnerPanel {...base} publicQuestions />)
    fireEvent.click(screen.getByRole('button', { name: 'Ask the owner' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask about the whole page' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Your question' }), { target: { value: 'Is Y2 equipment allowable?' } })
    fireEvent.change(screen.getByRole('textbox', { name: /Email for the answer/ }), { target: { value: 'po@agency.example' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to the owner' }))
    await waitFor(() => expect(api.askPublicPageOwner).toHaveBeenCalledWith('t', {
      anchor: null, message: 'Is Y2 equipment allowable?', kind: 'question', name: '', email: 'po@agency.example', website: '' }))
    expect(await screen.findByText(/You’ll get their answer by email/)).toBeInTheDocument()
  })

  it('shows answers the asker got', () => {
    render(<AskOwnerPanel audience={{ kind: 'member', uuid: 'p', revision: 'r1' }} picked={null} onFrame={vi.fn()} sharedBy="Shared by Dana" publicQuestions={false}
      answers={[{ ...ITEM, status: 'answered', answer: { text: 'Yes, the Zeiss quote.', by_name: 'Dana Reyes', at: '2026-11-03T11:00:00Z', on_page: false } }]} onAsked={vi.fn()} />)
    expect(screen.getByRole('list', { name: 'Answers from the owner' })).toHaveTextContent('Dana Reyes: Yes, the Zeiss quote.')
  })
})

describe('the owner’s questions', () => {
  it('shows the linked question on the page, answers it and turns it into a change request', async () => {
    api.listPageFeedback.mockResolvedValue({ role: 'owner', items: [ITEM], settings: { public_questions: false, contact: null }, shared_by: 'Shared by Dana Reyes' })
    api.answerPageFeedback.mockResolvedValue({ ...ITEM, status: 'answered' })
    const onFrame = vi.fn()
    const onRequestChanges = vi.fn()
    render(<OwnerFeedbackPanel uuid="p" onFrame={onFrame} focus="fb1" onRequestChanges={onRequestChanges} />)
    expect(await screen.findByText('Is Equipment Y2 $20k the microscope quote?')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Questions from viewers\s*· 1 open/ })).toBeInTheDocument()
    await waitFor(() => expect(onFrame).toHaveBeenCalledWith({ picking: false, spot: SPOT }))
    fireEvent.click(screen.getByRole('button', { name: 'Turn into Request changes' }))
    expect(onRequestChanges).toHaveBeenCalledWith('On “$20,000” (version 3), Pat Kim asked: Is Equipment Y2 $20k the microscope quote?\n\nUpdate the page to address this.')
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Your answer' }), { target: { value: 'Yes, the Zeiss quote.' } })
    fireEvent.click(screen.getByRole('checkbox', { name: /Also show it on the page/ }))
    expect(screen.getByText('Pat Kim gets it in their notifications.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    await waitFor(() => expect(api.answerPageFeedback).toHaveBeenCalledWith('p', 'fb1', 'Yes, the Zeiss quote.', true))
  })

  it('lets the owner allow public questions', async () => {
    api.listPageFeedback.mockResolvedValue({ role: 'owner', items: [], settings: { public_questions: false, contact: null }, shared_by: 'Shared by Dana Reyes' })
    api.updatePageFeedbackSettings.mockResolvedValue({ settings: { public_questions: true, contact: null }, shared_by: 'Shared by Dana Reyes' })
    render(<OwnerFeedbackPanel uuid="p" onFrame={vi.fn()} onRequestChanges={vi.fn()} />)
    fireEvent.click(await screen.findByRole('checkbox', { name: /Let people with the public link ask questions/ }))
    await waitFor(() => expect(api.updatePageFeedbackSettings).toHaveBeenCalledWith('p', { public_questions: true }))
  })
})
