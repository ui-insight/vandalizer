import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AwardHighlightFact, AwardHighlights } from '../../api/files'
import { AwardHighlightsDialog } from './AwardHighlightsDialog'

// Support ticket #1200: one click on an award document gives an email to the
// PI with a fixed set of facts, each linked to its page. Nothing is guessed
// and nothing is sent by Vandalizer.

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), viewDocument: vi.fn(), toast: vi.fn() }))
vi.mock('../../api/files', () => ({ fetchAwardHighlights: mocks.fetch }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ viewDocument: mocks.viewDocument }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))

const fact = (label: string, value: string | null, page: number | null = null): AwardHighlightFact => ({
  key: label, label, value, page, page_approximate: false, quote: value ? `${label} quote` : null,
  support: value ? 'supported' : null,
})

const pi = (role: 'pass_through' | 'recipient', label: string, name: string, institution: string, email: string | null) => ({
  role, role_label: label, name: fact('Principal investigator', name, 1), institution: fact('Institution', institution, 1),
  email, email_source: fact('Email', email, email ? 9 : null),
})

function highlights(overrides: Partial<AwardHighlights> = {}): AwardHighlights {
  return {
    document: { uuid: 'DOC1', title: 'FDP Subaward.pdf' },
    facts: [
      fact('Award amount', '$148,500', 1), fact('Start date', '09/01/2025', 1), fact('End date', '08/31/2027', 1),
      fact('Reporting deadlines', null), fact('Invoicing rules', 'Monthly; final invoice within 60 days', 4), fact('Key terms', null),
    ],
    contacts: [fact('Administrative contact', 'Sam Lee, slee@uidaho.edu', 9), fact('Financial contact', null)],
    pis: [
      pi('pass_through', 'Pass-through entity', 'Dr. Ana Ruiz', 'Colorado State University', 'ana.ruiz@colostate.edu'),
      pi('recipient', 'Subrecipient', 'Dr. Lee Park', 'University of Idaho', 'lpark@uidaho.edu'),
    ],
    suggested_pi: 1,
    suggestion_reason: 'your_institution',
    sender_name: 'Rita Admin',
    ...overrides,
  }
}

const openUrl = vi.fn()
const show = () => render(<AwardHighlightsDialog docUuid="DOC1" docTitle="FDP Subaward.pdf" onClose={vi.fn()} openUrl={openUrl} />)
const toField = () => screen.getByLabelText('To') as HTMLInputElement
const message = () => screen.getByLabelText('Message') as HTMLTextAreaElement

beforeEach(() => {
  vi.clearAllMocks()
  mocks.fetch.mockResolvedValue(highlights())
})

describe('Email highlights to PI', () => {
  it('pre-fills the PI at the reader’s institution and writes the fixed facts into the draft', async () => {
    show()
    expect(screen.getByRole('status')).toHaveTextContent('Reading the document')
    await waitFor(() => expect(toField().value).toBe('lpark@uidaho.edu'))
    expect(screen.getByText(/The one at your institution is selected/)).toBeInTheDocument()
    const body = message().value
    expect(body).toContain('Hello Dr. Lee Park,')
    expect(body).toContain('Award amount: $148,500 (p. 1)')
    expect(body).toContain('Invoicing rules: Monthly; final invoice within 60 days (p. 4)')
    expect(body.indexOf('Award amount')).toBeLessThan(body.indexOf('Start date'))
    expect(body.trimEnd().endsWith('Rita Admin')).toBe(true)
  })

  it('shows a missing fact as Not found, in the list and in the draft', async () => {
    show()
    await screen.findByLabelText('Message')
    expect(screen.getAllByText('Not found').length).toBe(3)
    expect(message().value).toContain('Reporting deadlines: Not found in the document')
  })

  it('opens the page a fact came from and steps aside without losing the draft', async () => {
    show()
    fireEvent.change(await screen.findByLabelText('Message'), { target: { value: 'my edits' } })
    fireEvent.click(screen.getByRole('button', { name: 'Open the source of Invoicing rules, page 4' }))
    expect(mocks.viewDocument).toHaveBeenCalledWith('DOC1', 'FDP Subaward.pdf', expect.objectContaining({ page: 4 }))
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Back to email draft' }))
    expect(message().value).toBe('my edits')
  })

  it('asks the reader to choose when it cannot tell which PI, and leaves the address empty until they do', async () => {
    mocks.fetch.mockResolvedValue(highlights({ suggested_pi: null, suggestion_reason: null }))
    show()
    await screen.findByText(/Choose who this goes to/)
    expect(toField().value).toBe('')
    expect(screen.getByRole('button', { name: /Open in email app/ })).toBeDisabled()

    fireEvent.click(screen.getByRole('radio', { name: /Dr\. Ana Ruiz/ }))
    expect(toField().value).toBe('ana.ruiz@colostate.edu')
    expect(message().value).toContain('Hello Dr. Ana Ruiz,')
    expect(screen.getByRole('button', { name: /Open in email app/ })).toBeEnabled()
  })

  it('keeps the reader’s edits when they switch PI', async () => {
    show()
    fireEvent.change(await screen.findByLabelText('Message'), { target: { value: 'my edits' } })
    fireEvent.click(screen.getByRole('radio', { name: /Dr\. Ana Ruiz/ }))
    expect(toField().value).toBe('ana.ruiz@colostate.edu')
    expect(message().value).toBe('my edits')
  })

  it('leaves the address box empty when no address was found for the PI', async () => {
    const one = pi('recipient', 'Subrecipient', 'Dr. Lee Park', 'University of Idaho', null)
    mocks.fetch.mockResolvedValue(highlights({ pis: [one], suggested_pi: 0, suggestion_reason: 'only_one' }))
    show()
    await screen.findByLabelText('Message')
    expect(toField().value).toBe('')
    expect(screen.getByText(/No email address for Dr\. Lee Park was found in the document/)).toBeInTheDocument()
  })

  it('hands the draft to the reader’s own email app, and sends nothing itself', async () => {
    show()
    await waitFor(() => expect(toField().value).toBe('lpark@uidaho.edu'))
    expect(screen.getByText(/Vandalizer does not send this email/)).toBeInTheDocument()
    expect(openUrl).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Open in email app/ }))
    const url = openUrl.mock.calls[0][0] as string
    expect(url.startsWith('mailto:lpark%40uidaho.edu?subject=Award%20highlights')).toBe(true)
    expect(decodeURIComponent(url)).toContain('Award amount: $148,500 (p. 1)\r\n')
    expect(mocks.fetch).toHaveBeenCalledTimes(1)
  })

  it('says why the document could not be read and offers to try again', async () => {
    mocks.fetch.mockRejectedValueOnce(new Error('This document is still being read. Try again when it has finished.'))
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('still being read')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(toField().value).toBe('lpark@uidaho.edu'))
  })
})
