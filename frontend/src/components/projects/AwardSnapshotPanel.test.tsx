import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AwardSnapshotPanel, snapshotSummary } from './AwardSnapshotPanel'
import type { AwardSnapshot } from '../../api/awardSnapshot'

// Support ticket: a project had no single place showing where its award stood.

const navigate = vi.fn()
const viewDocument = vi.fn()
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ activeProjectUuid: 'proj', railDocked: false, viewDocument }) }))
const api = vi.hoisted(() => ({ getAwardSnapshot: vi.fn(), buildAwardSnapshot: vi.fn(), shareAwardSnapshot: vi.fn() }))
vi.mock('../../api/awardSnapshot', () => api)

const src = { document_uuid: 'subaward', document_title: 'Subaward.pdf', page_approximate: false }
const SNAPSHOT: AwardSnapshot = {
  project: { uuid: 'proj', title: 'NIH Subaward WSU-UI-2025-1132', state: 'awarded' },
  status: 'ready',
  facts: [
    { key: 'Sponsor', label: 'Sponsor', value: 'National Institutes of Health', ...src, page: 1, quote: 'Prime sponsor: National Institutes of Health', support: 'supported' },
    { key: 'Total award amount', label: 'Total amount', value: '$243,200', ...src, page: 2, quote: 'Total subaward amount: $243,200', support: 'supported' },
    { key: 'Period of performance start', label: 'Period start', value: 'Jan 1, 2026', ...src, page: 1, quote: 'January 1, 2026', support: 'supported' },
    { key: 'Period of performance end', label: 'Period end', value: 'Dec 31, 2027', ...src, page: 1, quote: 'December 31, 2027', support: 'supported' },
    { key: 'Award number', label: 'Award number', value: 'R01AI123456', document_uuid: null, document_title: null, page: null, page_approximate: false, quote: null, support: 'unverified' },
  ],
  budget_years: [{ key: 'Budget period 1 amount', label: 'Year 1', value: '$121,600', ...src, page: 5, quote: 'Year 1 $121,600', support: 'supported' }],
  documents_read: [{ uuid: 'subaward', title: 'Subaward.pdf' }],
  document_count: 1, built_at: '2026-11-01T10:00:00+00:00', error: null, out_of_date: false, page_uuid: null, can_manage: true,
  deadlines: {
    overdue: [{ uuid: 'qpcr', title: 'Validated qPCR assay protocol', due_at: '2026-07-05T00:00:00', due_text: null, days_until: -121, sources: [{ document_uuid: 'subaward', document_title: 'Subaward.pdf', page: 4, quote: 'qPCR', role: 'evidence' }] } as never],
    upcoming: [{ uuid: 'results', title: 'Semi-annual results', due_at: '2026-11-17T00:00:00', due_text: null, days_until: 14, sources: [] } as never],
    done: [], needed: [],
  },
  last_run: { title: 'Subaward Extraction', type: 'search_set_run', status: 'completed', at: '2026-10-30T12:00:00+00:00' },
  pages: [{ uuid: 'p1', title: 'Budget memo', updated_at: null }],
  generated_at: '2026-11-03T10:00:00+00:00',
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><AwardSnapshotPanel /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  try { localStorage.clear() } catch { /* jsdom */ }
  api.getAwardSnapshot.mockResolvedValue(SNAPSHOT)
})

describe('Award snapshot panel', () => {
  it('summarizes the award in one line', () => {
    expect(snapshotSummary(SNAPSHOT)).toBe('$243,200 · Jan 1, 2026 – Dec 31, 2027 · 1 overdue · next: Semi-annual results, Nov 17, 2026')
    expect(snapshotSummary({ ...SNAPSHOT, status: 'not_built', facts: [], deadlines: { overdue: [], upcoming: [], done: [], needed: [] } })).toBe('Not built yet')
  })

  it('opens to facts with their pages, unconfirmed facts marked, live deadlines and activity', async () => {
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Award snapshot/ }))
    expect(screen.getByText('National Institutes of Health')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Open Subaward.pdf, p. 2' }))
    expect(viewDocument).toHaveBeenCalledWith('subaward', 'Subaward.pdf', { terms: ['Total subaward amount: $243,200'], page: 2 })
    expect(screen.getByText('R01AI123456').parentElement).toHaveTextContent('Source not found')
    expect(screen.getByRole('group', { name: 'Overdue' })).toHaveTextContent('Validated qPCR assay protocol · Jul 5, 2026 · 121 days past')
    expect(screen.getByRole('group', { name: 'Upcoming' })).toHaveTextContent('in 14 days')
    expect(screen.getByRole('group', { name: 'Done' })).toHaveTextContent('None marked done yet.')
    expect(screen.getByText(/Subaward Extraction · completed/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Validated qPCR assay protocol/ }))
    expect(navigate).toHaveBeenCalledWith({ to: '/', search: { deadline: 'qpcr' } })
  })

  it('builds, and shares as a Page that opens', async () => {
    api.getAwardSnapshot.mockResolvedValue({ ...SNAPSHOT, status: 'not_built', facts: [], budget_years: [], built_at: null })
    api.buildAwardSnapshot.mockResolvedValue({ ...SNAPSHOT, status: 'building' })
    api.shareAwardSnapshot.mockResolvedValue({ uuid: 'page-1', title: 't', revision: 'r' })
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Build snapshot/ }))
    await waitFor(() => expect(api.buildAwardSnapshot).toHaveBeenCalledWith('proj'))
    expect(await screen.findByText('Reading the documents…')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Share as Page/ }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith({ to: '/pages/$uuid', params: { uuid: 'page-1' } }))
  })

  it('offers no build or share to a viewer', async () => {
    api.getAwardSnapshot.mockResolvedValue({ ...SNAPSHOT, can_manage: false, status: 'not_built', facts: [] })
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Award snapshot/ }))
    expect(screen.queryByRole('button', { name: /Build snapshot|Share as Page/ })).not.toBeInTheDocument()
    expect(screen.getByText(/A project owner or editor can build it/)).toBeInTheDocument()
  })
})
