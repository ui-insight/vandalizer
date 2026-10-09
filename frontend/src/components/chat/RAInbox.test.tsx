import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RAInbox } from './RAInbox'
import type { Obligation } from '../../api/obligations'

// The RA inbox on Home (#999): Done is shared, Dismiss and Hide inbox are personal.

const navigate = vi.fn()
const viewDocument = vi.fn()
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ viewDocument }) }))
const api = vi.hoisted(() => ({
  getInbox: vi.fn(),
  setObligationDone: vi.fn(),
  setObligationDismissed: vi.fn(),
  setInboxHidden: vi.fn(),
}))
vi.mock('../../api/obligations', () => api)

const source = { document_uuid: 'amend', document_title: 'sponsor-amendment.pdf', page: 1, quote: 'The new sponsor deadline is November 19, 2026 at 5:00 p.m. Pacific Time.', role: 'evidence' }
const item = (over: Partial<Obligation>): Obligation => ({
  uuid: 'ob-1', project_uuid: 'proj-1', project_title: 'Community Resilience Pilot', kind: 'deadline',
  title: 'Sponsor deadline', deadline_type: 'sponsor_submission', due_at: '2099-11-19T17:00:00', due_text: '5:00 p.m. Pacific Time',
  limit_value: null, observed_value: null, unit: null, in_conflict: false, sources: [source], status: 'open',
  supersedes: null, superseded_by: null, dismissed: false, ...over,
})
const DEADLINE = item({})
const CAP = item({ uuid: 'ob-2', kind: 'limit', title: 'Direct-cost cap', due_at: null, due_text: null, limit_value: 180000, observed_value: 200000, unit: '$', in_conflict: true })
const LETTER = item({ uuid: 'ob-3', kind: 'required_material', title: 'Signed community-partner letter', due_at: null, due_text: null })

beforeEach(() => {
  vi.clearAllMocks()
  api.getInbox.mockResolvedValue({ items: [DEADLINE, CAP, LETTER], inbox_hidden: false })
  api.setObligationDone.mockResolvedValue({})
  api.setObligationDismissed.mockResolvedValue({})
  api.setInboxHidden.mockResolvedValue({ inbox_hidden: true })
})

describe('RA inbox', () => {
  it('lists what is due and needed, each with its source', async () => {
    render(<RAInbox />)
    const inbox = await screen.findByRole('region', { name: 'RA inbox' })
    expect(inbox).toHaveTextContent('Sponsor deadline')
    expect(inbox).toHaveTextContent('Nov 19, 2099, 5:00 p.m. Pacific Time')
    expect(inbox).toHaveTextContent('$200,000 exceeds the $180,000 limit')
    expect(inbox).toHaveTextContent('Still needed')
    fireEvent.click(screen.getAllByRole('button', { name: 'Open sponsor-amendment.pdf at page 1' })[0])
    expect(viewDocument).toHaveBeenCalledWith('amend', 'sponsor-amendment.pdf', expect.objectContaining({ page: 1 }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Community Resilience Pilot' })[0])
    expect(navigate).toHaveBeenCalledWith({ to: '/', search: { project: 'proj-1' } })
  })

  it('removes an item marked done', async () => {
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark "Signed community-partner letter" done for everyone on the project' }))
    await waitFor(() => expect(screen.queryByText('Signed community-partner letter')).not.toBeInTheDocument())
    expect(api.setObligationDone).toHaveBeenCalledWith('ob-3', true)
  })

  it('dismisses an item from this Home and can restore it', async () => {
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Hide "Direct-cost cap" from your Home' }))
    await waitFor(() => expect(screen.queryByText('Direct-cost cap')).not.toBeInTheDocument())
    expect(api.setObligationDismissed).toHaveBeenCalledWith('ob-2', true)
    api.getInbox.mockResolvedValue({ items: [DEADLINE, { ...CAP, dismissed: true }, LETTER], inbox_hidden: false })
    fireEvent.click(screen.getByRole('button', { name: 'Show dismissed (1)' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(api.setObligationDismissed).toHaveBeenCalledWith('ob-2', false))
  })

  it('hides the whole inbox for this account', async () => {
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: /Hide this inbox from your Home/ }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument())
    expect(api.setInboxHidden).toHaveBeenCalledWith(true)
  })

  it('shows nothing when the inbox is hidden or empty', async () => {
    api.getInbox.mockResolvedValueOnce({ items: [DEADLINE], inbox_hidden: true })
    const { unmount } = render(<RAInbox />)
    await act(async () => {})
    expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument()
    unmount()
    api.getInbox.mockResolvedValueOnce({ items: [], inbox_hidden: false })
    render(<RAInbox />)
    await act(async () => {})
    expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument()
  })

  it('keeps the item and says so when a change fails', async () => {
    api.setObligationDone.mockRejectedValueOnce(new Error('Only the project owner and editors can change its inbox.'))
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark "Sponsor deadline" done for everyone on the project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Only the project owner and editors')
    expect(screen.getByText('Sponsor deadline')).toBeInTheDocument()
  })
})
