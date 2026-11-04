import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../../api/artifacts'
import { AskOwnerDialog, OwnerQuestions, PageNotes } from './PageQuestions'

vi.mock('../../api/artifacts', () => ({
  questionAnchors: vi.fn(), publicQuestionAnchors: vi.fn(), askQuestion: vi.fn(), askPublicQuestion: vi.fn(),
  listQuestions: vi.fn(), answerQuestion: vi.fn(), closeQuestion: vi.fn(),
}))
const mocked = vi.mocked(api)
const anchors = { anchors: [{ id: 't0r1c2', label: 'Equipment · Y2 · $20k' }] }
const question: api.PageQuestion = {
  uuid: 'q1', artifact_uuid: 'page', revision: 'r2', version: 2, anchor_id: 't0r1c2', anchor_label: 'Equipment · Y2 · $20k',
  message: 'Is this $20k or $15k?', status: 'open', created_at: '2026-11-03T00:00:00Z', answer: null,
  asker: { kind: 'public', name: 'Dr. Lee', email: 'lee@wsu.edu' },
}
beforeEach(() => { vi.clearAllMocks() })

describe('Ask the owner', () => {
  it('lets a public-link viewer flag a figure and requires an email for the answer', async () => {
    mocked.publicQuestionAnchors.mockResolvedValue(anchors)
    mocked.askPublicQuestion.mockResolvedValue({ ok: true })
    const sent = vi.fn()
    render(<AskOwnerDialog token="tok" onClose={vi.fn()} onSent={sent} />)
    await screen.findByRole('option', { name: 'Equipment · Y2 · $20k' })
    fireEvent.change(screen.getByLabelText('About'), { target: { value: 't0r1c2' } })
    fireEvent.change(screen.getByLabelText('Your question or note'), { target: { value: 'Is this $20k or $15k?' } })
    const submit = screen.getByRole('button', { name: 'Send to owner' })
    expect(submit).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Your email (for the answer)'), { target: { value: 'lee@wsu.edu' } })
    fireEvent.click(submit)
    await waitFor(() => expect(sent).toHaveBeenCalledOnce())
    expect(mocked.askPublicQuestion).toHaveBeenCalledWith('tok', expect.objectContaining({
      message: 'Is this $20k or $15k?', anchor_id: 't0r1c2', email: 'lee@wsu.edu', website: '',
    }))
  })

  it('sends a team member\'s question for the version they see', async () => {
    mocked.questionAnchors.mockResolvedValue(anchors)
    mocked.askQuestion.mockResolvedValue(question)
    render(<AskOwnerDialog uuid="page" revision="r2" onClose={vi.fn()} onSent={vi.fn()} />)
    expect(screen.queryByLabelText('Your email (for the answer)')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Your question or note'), { target: { value: 'Where is this from?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to owner' }))
    await waitFor(() => expect(mocked.askQuestion).toHaveBeenCalledWith('page', { message: 'Where is this from?', anchor_id: null, revision: 'r2' }))
  })
})

describe('Owner questions', () => {
  it('answers, can show the answer on the page, and highlights the focused question\'s spot', async () => {
    mocked.listQuestions.mockResolvedValue([question])
    mocked.answerQuestion.mockResolvedValue({ ...question, status: 'answered' })
    const show = vi.fn()
    render(<OwnerQuestions uuid="page" focus="q1" onShow={show} onRequestChanges={vi.fn()} onClose={vi.fn()} onChanged={vi.fn()} />)
    await screen.findByText('Is this $20k or $15k?')
    expect(show).toHaveBeenCalledWith(question)
    expect(screen.getByText('Public link')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Answer Dr. Lee <lee@wsu.edu>'), { target: { value: 'Revised vendor quote.' } })
    fireEvent.click(screen.getByLabelText(/Show the question and answer on the page/))
    fireEvent.click(screen.getByRole('button', { name: 'Send answer' }))
    await waitFor(() => expect(mocked.answerQuestion).toHaveBeenCalledWith('page', 'q1', 'Revised vendor quote.', true))
  })

  it('turns a question into a change request with one click', async () => {
    mocked.listQuestions.mockResolvedValue([question])
    const request = vi.fn()
    render(<OwnerQuestions uuid="page" onShow={vi.fn()} onRequestChanges={request} onClose={vi.fn()} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Turn into a change request' }))
    expect(request.mock.calls[0][0]).toContain('A viewer asked about Equipment · Y2 · $20k: "Is this $20k or $15k?"')
  })
})

it('shows answers the owner chose to put on the page', () => {
  render(<PageNotes notes={[{ about: 'Equipment · Y2 · $20k', question: 'Why $20k?', answer: 'Vendor quote.', answered_at: '' }]} />)
  expect(screen.getByRole('region', { name: 'Notes from the page owner' })).toHaveTextContent('Vendor quote.')
})
