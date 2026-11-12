import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'
import { ApiError } from '../api/client'
import { settingsFrom, draftFrom, DEFAULT_LINK } from '../components/artifacts/PublicLinkControls'

// Public links: expiry, sign-in audience, view record (support ticket).
vi.mock('../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof api>(), getArtifact: vi.fn(), getPublicArtifact: vi.fn(), publishArtifact: vi.fn(), updatePublicLink: vi.fn(), listPublicLinks: vi.fn() }))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([]) }))

const link: api.PublicLinkInfo = {
  expires_at: '2026-12-15T23:59:59Z', expired: false, audience: 'signed_in', emails: ['grants@uidaho.edu'],
  views: { count: 3, last_at: '2026-11-02T17:14:00Z' },
  viewers: [{ name: 'Grants Admin', email: 'grants@uidaho.edu', count: 3, last_at: '2026-11-02T17:14:00Z' }],
}
const item: api.Artifact = { uuid: 'a1', title: 'NIH R01 Budget Dashboard', latest_revision: 'r1', published_revision: 'r1', public_token: 'tok', team_id: null,
  can_manage: true, public_sharing_enabled: true, revisions: [{ uuid: 'r1', title: 'NIH R01 Budget Dashboard', created_at: '', warnings: [] }],
  public_links: { main: link, versions: {} } }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getArtifact).mockResolvedValue(item)
  vi.mocked(api.updatePublicLink).mockResolvedValue(item)
  vi.mocked(api.publishArtifact).mockResolvedValue(item)
})

it('shows expiry and who opened the link, and saves new link settings', async () => {
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByText(/Expires Dec 15, 2026/)).toBeInTheDocument()
  expect(screen.getByText(/Opened 3 times · last opened/)).toBeInTheDocument()
  expect(screen.getByText(/Grants Admin \(grants@uidaho.edu\): 3 times/)).toBeInTheDocument()
  // The form starts from the saved settings.
  expect(screen.getByLabelText('Main link: only these email addresses')).toHaveValue('grants@uidaho.edu')
  fireEvent.change(screen.getByLabelText('Main link expires'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save link settings' }))
  await waitFor(() => expect(api.updatePublicLink).toHaveBeenCalled())
  const [, settings] = vi.mocked(api.updatePublicLink).mock.calls[0]
  expect(settings.audience).toBe('signed_in')
  expect(settings.emails).toEqual(['grants@uidaho.edu'])
  const days = (new Date(settings.expires_at!).getTime() - Date.now()) / 86_400_000
  expect(days).toBeGreaterThan(29.9)
  expect(days).toBeLessThan(30.1)
})

it.each([
  [410, 'This link has expired. Ask the page owner for a new link.', 'This link has expired'],
  [401, 'Not authenticated', 'Sign in to view this page'],
  [403, "This page is shared with specific people, and your account isn't one of them.", 'You can’t open this page'],
])('a refused public link (%s) says why instead of "Page unavailable"', async (status, message, heading) => {
  vi.mocked(api.getPublicArtifact).mockRejectedValue(new ApiError(status, message))
  render(<ArtifactPage publicToken="tok" />)
  expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  expect(screen.queryByText('Page unavailable')).not.toBeInTheDocument()
  if (status === 401) expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', `/landing?next=${encodeURIComponent(window.location.pathname)}`)
})

it('turns the expiry choice into a date the server can check', () => {
  const now = new Date('2026-11-03T12:00:00Z')
  expect(settingsFrom(DEFAULT_LINK, now)).toEqual({ expires_at: null, audience: 'anyone', emails: [] })
  expect(settingsFrom({ ...DEFAULT_LINK, expiry: 'custom', customDate: '' }, now)).toBe('Choose the date the link should expire.')
  expect(settingsFrom({ ...DEFAULT_LINK, expiry: 'custom', customDate: '2026-11-01' }, now)).toBe('Choose an expiry date in the future.')
  const custom = settingsFrom({ ...DEFAULT_LINK, expiry: 'custom', customDate: '2026-12-15' }, now)
  expect(typeof custom !== 'string' && new Date(custom.expires_at!).getDate()).toBe(15)
  // Email addresses only apply to signed-in links.
  expect(settingsFrom({ ...DEFAULT_LINK, emails: 'a@b.edu' }, now)).toMatchObject({ emails: [] })
  expect(settingsFrom({ ...DEFAULT_LINK, audience: 'signed_in', emails: 'a@b.edu, c@d.edu;e@f.edu' }, now)).toMatchObject({ emails: ['a@b.edu', 'c@d.edu', 'e@f.edu'] })
})

it('reopens an expired link asking for a new date, never as a permanent link', () => {
  const draft = draftFrom({ ...link, expires_at: '2026-10-01T23:59:59Z', expired: true })
  expect(draft.expiry).toBe('custom')
  expect(settingsFrom(draft, new Date('2026-11-06T12:00:00Z'))).toBe('Choose the date the link should expire.')
})
