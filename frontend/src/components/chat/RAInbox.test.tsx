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

  it('shows nothing when the inbox is hidden or there are no projects to cover', async () => {
    api.getInbox.mockResolvedValueOnce({ items: [DEADLINE], inbox_hidden: true, project_count: 1 })
    const { unmount } = render(<RAInbox />)
    await act(async () => {})
    expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument()
    unmount()
    api.getInbox.mockResolvedValueOnce({ items: [], inbox_hidden: false, project_count: 0 })
    const { container } = render(<RAInbox />)
    await act(async () => {})
    expect(container).toBeEmptyDOMElement()
  })

  it('says what an empty inbox covered instead of vanishing (#1014 item 34)', async () => {
    api.getInbox.mockResolvedValueOnce({ items: [], inbox_hidden: false, project_count: 3 })
    render(<RAInbox />)
    expect(await screen.findByText(/Nothing due or missing in your 3 projects/)).toHaveTextContent(
      'Only deadlines and materials saved to a project appear here.',
    )
    expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument()
  })

  it('opens both the limit and the figure that breaks it (#1014 item 33)', async () => {
    const limitSource = { document_uuid: 'notice', document_title: 'sponsor-notice.pdf', page: 3, quote: 'The maximum direct-cost request is $180,000.', role: 'limit' }
    const observedSource = { document_uuid: 'prop', document_title: 'proposal-draft.pdf', page: 2, quote: 'Direct-cost total: $200,000', role: 'observed' }
    api.getInbox.mockResolvedValue({ items: [{ ...CAP, sources: [limitSource, observedSource] }], inbox_hidden: false })
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open the limit in sponsor-notice.pdf at page 3' }))
    expect(viewDocument).toHaveBeenLastCalledWith('notice', 'sponsor-notice.pdf', expect.objectContaining({ page: 3 }))
    fireEvent.click(screen.getByRole('button', { name: 'Open the observed value in proposal-draft.pdf at page 2' }))
    expect(viewDocument).toHaveBeenLastCalledWith('prop', 'proposal-draft.pdf', expect.objectContaining({ page: 2 }))
  })

  it('says it is loading instead of showing nothing (#1014 item 55)', async () => {
    let resolve!: (v: unknown) => void
    api.getInbox.mockReturnValueOnce(new Promise(r => { resolve = r }))
    render(<RAInbox />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading project obligations')
    await act(async () => { resolve({ items: [DEADLINE], inbox_hidden: false }) })
    expect(await screen.findByRole('region', { name: 'RA inbox' })).toBeInTheDocument()
  })

  it('refreshes when you come back, and keeps the list if that refresh fails (#1014 item 57)', async () => {
    render(<RAInbox />)
    await screen.findByText('Sponsor deadline')
    api.getInbox.mockResolvedValueOnce({ items: [DEADLINE, CAP, LETTER, item({ uuid: 'ob-4', title: 'Internal routing deadline' })], inbox_hidden: false })
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(await screen.findByText('Internal routing deadline')).toBeInTheDocument()
    api.getInbox.mockRejectedValueOnce(new Error('offline'))
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    expect(screen.getByText('Internal routing deadline')).toBeInTheDocument()
    expect(screen.queryByText(/could not be loaded/)).not.toBeInTheDocument()
  })

  it('keeps the item and says so when a change fails', async () => {
    api.setObligationDone.mockRejectedValueOnce(new Error('Only the project owner and editors can change its inbox.'))
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Mark "Sponsor deadline" done for everyone on the project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Only the project owner and editors')
    expect(screen.getByText('Sponsor deadline')).toBeInTheDocument()
  })
})
