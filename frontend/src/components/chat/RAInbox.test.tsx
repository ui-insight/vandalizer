import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RAInbox } from './RAInbox'
import type { Obligation } from '../../api/obligations'

// The RA inbox on Home (#999): Done is shared, Dismiss and Hide inbox are personal.

const navigate = vi.fn()
const viewDocument = vi.fn()
const workspace = vi.hoisted(() => ({ focusedObligationUuid: null as string | null, activeProjectRole: 'owner' }))
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  Link: ({ children, to, hash, ...rest }: { children: React.ReactNode; to: string; hash?: string }) => <a href={`${to}${hash ? `#${hash}` : ''}`} {...rest}>{children}</a>,
}))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ viewDocument, ...workspace }) }))
const api = vi.hoisted(() => ({
  getInbox: vi.fn(),
  setObligationDone: vi.fn(),
  setObligationDismissed: vi.fn(),
  setObligationKept: vi.fn(),
  setInboxHidden: vi.fn(),
  downloadDeadlineCalendar: vi.fn(),
}))
vi.mock('../../api/obligations', async (actual) => {
  const real = await actual<typeof import('../../api/obligations')>()
  return { ...api, plainQuote: real.plainQuote, quoteSearchTerms: real.quoteSearchTerms }
})

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
  localStorage.clear()
  workspace.activeProjectRole = 'owner'
  workspace.focusedObligationUuid = null
  api.downloadDeadlineCalendar.mockResolvedValue(undefined)
  api.getInbox.mockResolvedValue({ items: [DEADLINE, CAP, LETTER], inbox_hidden: false })
  api.setObligationDone.mockResolvedValue({})
  api.setObligationDismissed.mockResolvedValue({})
  api.setInboxHidden.mockResolvedValue({ inbox_hidden: true })
})

const daysFromNow = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}T00:00:00`
}

// Support ticket: deadlines were only a flat list on Home, with no calendar
// file and nothing a reminder could link to.
describe('RA inbox upcoming view and calendar', () => {
  const OVERDUE = item({ uuid: 'qpcr', title: 'Validated qPCR assay protocol', due_at: daysFromNow(-121), due_text: null })
  const WEEK = item({ uuid: 'invoice', title: 'Invoice', due_at: daysFromNow(2), due_text: null })
  const MONTH = item({ uuid: 'results', title: 'Semi-annual results', due_at: daysFromNow(14), due_text: null })
  const LATER = item({ uuid: 'final', title: 'Final report', due_at: daysFromNow(200), due_text: null })

  it('groups deadlines as overdue, this week, next 30 days and later, then what is needed', async () => {
    api.getInbox.mockResolvedValue({ items: [LATER, MONTH, LETTER, WEEK, OVERDUE, CAP], inbox_hidden: false })
    render(<RAInbox />)
    await screen.findByRole('region', { name: 'RA inbox' })
    const groups = screen.getAllByRole('group').map(g => g.getAttribute('aria-label'))
    expect(groups).toEqual(['Overdue', 'Due this week', 'Next 30 days', 'Later', 'Needed and limits'])
    expect(screen.getByRole('group', { name: 'Overdue' })).toHaveTextContent('Validated qPCR assay protocol')
    expect(screen.getByRole('group', { name: 'Overdue' })).toHaveTextContent('121 days past')
    expect(screen.getByRole('group', { name: 'Needed and limits' })).toHaveTextContent('Direct-cost cap')
  })

  it('downloads a calendar file per deadline and for all deadlines', async () => {
    api.getInbox.mockResolvedValue({ items: [WEEK, LETTER], inbox_hidden: false })
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Add "Invoice" to your calendar' }))
    expect(api.downloadDeadlineCalendar).toHaveBeenCalledWith({ obligation: 'invoice' })
    expect(screen.queryByRole('button', { name: /Add "Signed community-partner letter"/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Download a calendar file with all your open deadlines' }))
    expect(api.downloadDeadlineCalendar).toHaveBeenLastCalledWith('all')
    expect(screen.getByRole('link', { name: 'Deadline reminder settings' })).toHaveAttribute('href', '/account#deadline-reminders')
  })

  it("highlights the item a reminder links to, or says it's no longer open", async () => {
    workspace.focusedObligationUuid = 'results'
    api.getInbox.mockResolvedValue({ items: [WEEK, MONTH], inbox_hidden: false })
    const { unmount } = render(<RAInbox />)
    const row = (await screen.findByText('Semi-annual results')).closest('li')
    expect(row).toHaveAttribute('aria-current', 'true')
    expect(screen.getByText('Invoice').closest('li')).not.toHaveAttribute('aria-current')
    unmount()

    workspace.focusedObligationUuid = 'gone'
    render(<RAInbox />)
    expect(await screen.findByText(/The deadline from that reminder is no longer open here/)).toBeInTheDocument()
  })
})

describe('RA inbox', () => {
  it('retains a calculated deadline formula and opens the timing and anchor evidence', async () => {
    const timing = { ...source, quote: 'Final report is due within 60 days after the end of the Period of Performance.', role: 'timing' }
    const period = { ...source, page: 2, quote: 'Period of Performance ends December 31, 2027.', role: 'period_of_performance' }
    api.getInbox.mockResolvedValue({ items: [item({
      title: 'Final report', due_at: '2028-02-29T00:00:00', due_text: null, sources: [timing, period],
      deadline_calculation: { rule: timing.quote, anchor_kind: 'performance_period_end', anchor_date: '2027-12-31',
        offset_days: 60, formula: '2027-12-31 + 60 calendar days = 2028-02-29' },
    })], inbox_hidden: false })
    render(<RAInbox />)
    const inbox = await screen.findByRole('region', { name: 'RA inbox' })
    expect(inbox).toHaveTextContent('Feb 29, 2028')
    fireEvent.click(screen.getByText('How this date was calculated'))
    expect(screen.getByText('2027-12-31 + 60 calendar days = 2028-02-29')).toBeVisible()
    expect(screen.getByText(timing.quote)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Open the timing rule in sponsor-amendment.pdf at page 1' }))
    expect(viewDocument).toHaveBeenLastCalledWith('amend', 'sponsor-amendment.pdf', expect.objectContaining({ page: 1 }))
    fireEvent.click(screen.getByRole('button', { name: 'Open the period of performance in sponsor-amendment.pdf at page 2' }))
    expect(viewDocument).toHaveBeenLastCalledWith('amend', 'sponsor-amendment.pdf', expect.objectContaining({ page: 2 }))
  })

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

  it('Hide inbox collapses to a Show inbox line in the same place, and Show brings it back', async () => {
    const { unmount } = render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Hide inbox' }))
    expect(screen.queryByRole('region', { name: 'RA inbox' })).not.toBeInTheDocument()
    const collapsed = screen.getByRole('group', { name: 'RA inbox (hidden)' })
    expect(collapsed).toHaveTextContent('Due and needed (3)')
    const show = screen.getByRole('button', { name: 'Show inbox' })
    expect(show).toHaveFocus()
    // Collapsing is not the account setting: nothing is turned off for good.
    expect(api.setInboxHidden).not.toHaveBeenCalled()

    // Remembered on this browser across visits.
    unmount()
    render(<RAInbox />)
    fireEvent.click(await screen.findByRole('button', { name: 'Show inbox' }))
    expect(screen.getByRole('region', { name: 'RA inbox' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide inbox' })).toHaveFocus()
    expect(screen.getByText('Sponsor deadline')).toBeInTheDocument()
  })

  it('collapses even when browser storage is unavailable', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    try {
      render(<RAInbox />)
      fireEvent.click(await screen.findByRole('button', { name: 'Hide inbox' }))
      expect(screen.getByRole('button', { name: 'Show inbox' })).toBeInTheDocument()
    } finally {
      setItem.mockRestore()
    }
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

  it('shows a limit with nothing to compare as the limit alone, exactly as saved', async () => {
    api.getInbox.mockResolvedValue({ items: [
      item({ uuid: 'ob-7', kind: 'limit', title: 'Indirect cost rate limit', due_at: null, due_text: null, limit_value: 22.5, unit: '%' }),
      item({ uuid: 'ob-8', kind: 'limit', title: 'Indirect cost cap', due_at: null, due_text: null, limit_value: 9555, unit: '$' }),
    ], inbox_hidden: false })
    render(<RAInbox />)
    const inbox = await screen.findByRole('region', { name: 'RA inbox' })
    expect(inbox).toHaveTextContent('22.5% limit')
    expect(inbox).toHaveTextContent('$9,555 limit')
    expect(inbox).not.toHaveTextContent('within')
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

// Support ticket: inside the NIFA project, "Due and needed" listed the NIH
// project's qPCR protocol and semi-annual results above NIFA's own item.
describe('RA inbox inside a project', () => {
  it("asks for only that project's items and says so", async () => {
    render(<RAInbox projectUuid="nifa" />)
    await screen.findByText('Sponsor deadline')
    expect(api.getInbox).toHaveBeenCalledWith(false, 'nifa')
    expect(screen.getByText('This project')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hide inbox' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: "Download a calendar file with this project's open deadlines" }))
    expect(api.downloadDeadlineCalendar).toHaveBeenCalledWith({ project: 'nifa' })
  })

  it('stays open inside a project after Home collapsed the inbox', async () => {
    localStorage.setItem('home:ra-inbox-collapsed', '1')
    render(<RAInbox projectUuid="nifa" />)
    expect(await screen.findByText('Sponsor deadline')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show inbox' })).not.toBeInTheDocument()
  })

  it('says an empty project has nothing due, instead of showing other projects', async () => {
    api.getInbox.mockResolvedValue({ items: [], inbox_hidden: false, project_count: 1 })
    render(<RAInbox projectUuid="empty" />)
    expect(await screen.findByText('Nothing due or missing in this project. Only deadlines and materials saved to it appear here.')).toBeInTheDocument()
  })

  it('labels the Home list as covering all your projects', async () => {
    render(<RAInbox />)
    await screen.findByText('Sponsor deadline')
    expect(api.getInbox).toHaveBeenCalledWith(false, undefined)
    expect(screen.getByText('All your projects')).toBeInTheDocument()
  })
})

describe('RA inbox item whose source file was deleted', () => {
  const GONE = item({
    sources: [{ ...source, document_uuid: 'gone', document_title: '16-delete-test.pdf', deleted: true }],
    source_deleted: true, kept_without_source: false,
  })

  it('flags the item and does not offer the deleted file to open', async () => {
    api.getInbox.mockResolvedValue({ items: [GONE], inbox_hidden: false })
    render(<RAInbox />)

    const flag = await screen.findByRole('group', { name: 'Source file deleted for "Sponsor deadline"' })
    expect(flag).toHaveTextContent('Source file deleted. Reminders are paused. Keep this item or dismiss it?')
    // The chip is text, not a button: clicking a source attaches it to chat.
    expect(screen.getByText('16-delete-test.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Open 16-delete-test\.pdf/ })).not.toBeInTheDocument()
    expect(viewDocument).not.toHaveBeenCalled()
  })

  it('Keep clears the question and leaves the item in the list', async () => {
    api.getInbox.mockResolvedValue({ items: [GONE], inbox_hidden: false })
    api.setObligationKept.mockResolvedValue({})
    render(<RAInbox />)

    fireEvent.click(await screen.findByRole('button', { name: 'Keep "Sponsor deadline" for everyone on the project' }))

    await waitFor(() => expect(screen.queryByRole('group', { name: /Source file deleted/ })).not.toBeInTheDocument())
    expect(api.setObligationKept).toHaveBeenCalledWith('ob-1', true)
    expect(screen.getByText('Sponsor deadline')).toBeInTheDocument()
    expect(screen.getByText(/file deleted/)).toBeInTheDocument()
  })

  it('Dismiss hides the item from this Home', async () => {
    api.getInbox.mockResolvedValue({ items: [GONE], inbox_hidden: false })
    render(<RAInbox />)

    fireEvent.click(await screen.findByRole('button', { name: 'Dismiss "Sponsor deadline" from your Home' }))

    await waitFor(() => expect(api.setObligationDismissed).toHaveBeenCalledWith('ob-1', true))
    await waitFor(() => expect(screen.queryByText('Sponsor deadline')).not.toBeInTheDocument())
  })

  it('asks nothing of an item whose file is still there', async () => {
    render(<RAInbox />)
    await screen.findByText('Sponsor deadline')
    expect(screen.queryByRole('group', { name: /Source file deleted/ })).not.toBeInTheDocument()
  })
})

describe('project workspace inbox', () => {
  it('omits project links only inside the scoped project and retains source links', async () => {
    const view = render(<RAInbox projectUuid="proj-1" />)
    await screen.findByText('Sponsor deadline')
    expect(screen.queryByRole('button', { name: 'Community Resilience Pilot' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Open sponsor-amendment.pdf/ })).toHaveLength(3)
    view.unmount()
    render(<RAInbox />)
    expect((await screen.findAllByRole('button', { name: 'Community Resilience Pilot' }))).toHaveLength(3)
  })
  it('keeps personal dismiss and calendar for viewers while hiding shared mutations', async () => {
    workspace.activeProjectRole = 'viewer'
    api.getInbox.mockResolvedValue({ items: [DEADLINE, item({ uuid: 'deleted', source_deleted: true })], inbox_hidden: false })
    render(<RAInbox projectUuid="proj-1" />)
    await screen.findAllByText('Sponsor deadline')
    expect(screen.queryByRole('button', { name: /Mark .* done/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Keep .* everyone/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Add .* to your calendar/ })).toHaveLength(2)
    fireEvent.click(screen.getAllByRole('button', { name: /Hide .* from your Home/ })[0])
    await waitFor(() => expect(api.setObligationDismissed).toHaveBeenCalledWith('ob-1', true))
    expect(api.setObligationDone).not.toHaveBeenCalled()
  })
})
