import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'

vi.mock('../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof api>(), getArtifact: vi.fn(), getPublicArtifact: vi.fn(), artifactSource: vi.fn(), reviseArtifact: vi.fn(), publishArtifact: vi.fn(), unpublishArtifact: vi.fn(), shareArtifactTeam: vi.fn() }))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([{ uuid: 'team-a', name: 'Research team' }]) }))
const item: api.Artifact = { uuid: 'a1', title: 'Private draft', latest_revision: 'r2', published_revision: 'r1', public_token: 'public-link', team_id: null, can_manage: true, public_sharing_enabled: true, revisions: [
  { uuid: 'r1', title: 'Published report', created_at: '', warnings: [] },
  { uuid: 'r2', title: 'Private draft', created_at: '', warnings: [] },
] }
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getArtifact).mockResolvedValue(item)
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'Published report', revision: 'r2', version: 2, updated_at: '2026-03-10T15:30:00Z' })
})

it('shows the pinned public page without loading private metadata or management controls', async () => {
  render(<ArtifactPage publicToken="public-link" />)
  await screen.findByRole('heading', { name: 'Published report' })
  expect(api.getArtifact).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Edit HTML' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument()
  expect(screen.queryByText('Unpublished changes')).not.toBeInTheDocument()
  expect(screen.getByText('Published · version 2')).toBeInTheDocument()
  const updated = screen.getByText(/Last updated/).querySelector('time')
  expect(updated).toHaveAttribute('datetime', '2026-03-10T15:30:00Z')
  expect(updated).toHaveTextContent('2026')
  expect(updated).toHaveTextContent('UTC')
  const frame = screen.getByTitle('Page preview')
  expect(frame).toHaveAttribute('sandbox', '')
  expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
  expect(frame).toHaveAttribute('src', '/api/pages/public/public-link/content?revision=r2')
  expect(screen.getByRole('link', { name: 'Download HTML' })).toHaveAttribute('href', '/api/pages/public/public-link/content?revision=r2&download=true')
  expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute('href', '/api/pages/public/public-link/content?revision=r2')
})

it('does not invent an update date when public metadata has an invalid timestamp', async () => {
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'Published report', revision: 'r2', version: 2, updated_at: 'invalid' })
  render(<ArtifactPage publicToken="public-link" />)
  expect(await screen.findByText('Last updated date unavailable')).toBeInTheDocument()
  expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
})

it('publishes exactly the selected saved revision and revokes an existing link', async () => {
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByText(/compare figures and source notes with the original documents/)).toBeInTheDocument()
  expect(api.publishArtifact).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Publish updates · version 2' }))
  await waitFor(() => expect(api.publishArtifact).toHaveBeenCalledWith('a1', 'r2'))
  await screen.findByText('Version 2 published. Anyone with the link can view it.')
  fireEvent.click(screen.getByRole('button', { name: 'Remove public link' }))
  await waitFor(() => expect(api.unpublishArtifact).toHaveBeenCalledWith('a1'))
})

it('retains an unsaved edit when the server rejects a stale base revision', async () => {
  vi.mocked(api.artifactSource).mockResolvedValue({ title: 'Private draft', html: '<main>Original</main>' })
  vi.mocked(api.reviseArtifact).mockRejectedValue(new Error('This page changed. Reload before saving another revision.'))
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit HTML' }))
  fireEvent.change(await screen.findByLabelText('HTML'), { target: { value: '<main>Unsaved edit</main>' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save new version' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('HTML')).toHaveValue('<main>Unsaved edit</main>')
  expect(api.reviseArtifact).toHaveBeenCalledWith('a1', 'Private draft', '<main>Unsaved edit</main>', 'r2')
  expect(api.publishArtifact).not.toHaveBeenCalled()
})

it('requires explicit access saving and respects the deployment publish switch', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, public_sharing_enabled: false })
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team-a' } })
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a', 'r1'))
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeDisabled()
})

it('shows a revoked public link error without rendering an iframe', async () => {
  vi.mocked(api.getPublicArtifact).mockRejectedValue(new Error('Page not found'))
  render(<ArtifactPage publicToken="revoked" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Page not found')
  expect(screen.queryByTitle('Page preview')).not.toBeInTheDocument()
})


it('distinguishes a live publication from an unpublished draft beside the title', async () => {
  render(<ArtifactPage uuid="a1" />)
  expect(await screen.findByText('Published · version 1')).toBeInTheDocument()
  expect(screen.getByText('Unpublished changes')).toBeInTheDocument()
  expect(screen.queryByText('Private · only you')).not.toBeInTheDocument()
  expect(screen.getByText('Workspace access: only you')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Pages' })).toHaveAttribute('href', '/?mode=files&files=pages')
  fireEvent.change(screen.getByLabelText('Page version'), { target: { value: 'r1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Share' }))
  expect(screen.getByRole('button', { name: 'Published' })).toBeDisabled()
  expect(api.publishArtifact).not.toHaveBeenCalled()
})

it('shows only the shared version to a team member without owner notices or controls', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, can_manage: false, team_id: 'team-a',
    team_revision: 'r1', latest_revision: 'r1', title: 'Published report',
    revisions: [{ ...item.revisions[0], version: 2 }],
  })
  render(<ArtifactPage uuid="a1" />)
  await screen.findByText('Team access · version 2')
  expect(screen.getByText('Shared version 2')).toBeInTheDocument()
  expect(screen.queryByLabelText('Page version')).not.toBeInTheDocument()
  expect(screen.queryByText('Unpublished changes')).not.toBeInTheDocument()
  expect(screen.queryByText(/Publish updates when/)).not.toBeInTheDocument()
  expect(screen.queryByText(/Share only when/)).not.toBeInTheDocument()
  expect(screen.queryByText(/Workspace access:.*you/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete page' })).not.toBeInTheDocument()
  expect(screen.getByTitle('Page preview')).toHaveAttribute('src', '/api/pages/a1/revisions/r1/content')
  expect(screen.getByRole('link', { name: 'Download HTML' })).toHaveAttribute('href', '/api/pages/a1/revisions/r1/content?download=true')
})

it('lets the owner change the team version explicitly and explains the sharing boundary', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, team_id: 'team-a', team_revision: 'r1' })
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r1')
  expect(screen.getByText(/Other versions and future drafts stay owner-only/)).toBeInTheDocument()
  expect(screen.getByText('Currently shared: version 1.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save access' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Version shared with team'), { target: { value: 'r2' } })
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a', 'r2'))
})

it('defaults a new team share to the latest saved version when nothing is published', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, published_revision: null, public_token: null })
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team-a' } })
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r2')
})

it.each([false, true])('requires saving the team selection before publishing (already published: %s)', async published => {
  const initial = published ? item : { ...item, published_revision: null, public_token: null }
  vi.mocked(api.getArtifact).mockResolvedValue(initial)
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team-a' } })
  fireEvent.change(screen.getByLabelText('Version shared with team'), { target: { value: 'r2' } })
  const publishName = published ? 'Publish updates · version 2' : 'Publish version 2'
  const publish = screen.getByRole('button', { name: publishName })
  expect(publish).toBeDisabled()
  expect(publish).toHaveAccessibleDescription(/unsaved workspace access changes/)
  fireEvent.click(publish)
  expect(api.publishArtifact).not.toHaveBeenCalled()
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  expect(screen.getByLabelText('Workspace page access')).toHaveValue('team-a')

  const shared = { ...initial, team_id: 'team-a', team_revision: 'r2' }
  vi.mocked(api.getArtifact).mockResolvedValue(shared)
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await screen.findByText('Workspace access updated.')
  expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a', 'r2')
  expect(screen.queryByText(/unsaved workspace access changes/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: publishName })).toBeEnabled()
  expect(api.publishArtifact).not.toHaveBeenCalled()

  vi.mocked(api.getArtifact).mockResolvedValue({ ...shared, published_revision: 'r2', public_token: 'public-link' })
  fireEvent.click(screen.getByRole('button', { name: publishName }))
  await screen.findByText('Version 2 published. Anyone with the link can view it.')
  expect(api.publishArtifact).toHaveBeenCalledWith('a1', 'r2')
  expect(screen.getByLabelText('Workspace page access')).toHaveValue('team-a')
  expect(screen.getByText('Workspace access: you and your team')).toBeInTheDocument()
})

it.each(['version', 'team'])('can explicitly discard an unsaved %s change before publishing', async change => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, team_id: 'team-a', team_revision: 'r1' })
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  if (change === 'version') fireEvent.change(screen.getByLabelText('Version shared with team'), { target: { value: 'r2' } })
  else fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: '' } })
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Discard access changes' }))
  expect(screen.getByLabelText('Workspace page access')).toHaveValue('team-a')
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r1')
  expect(screen.getByRole('button', { name: 'Save access' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeEnabled()
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
})

it('retains the selection and publishing warning when saving access fails', async () => {
  vi.mocked(api.shareArtifactTeam).mockRejectedValueOnce(new Error('Could not save access. Try again.'))
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team-a' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not save access. Try again.')
  expect(screen.getByLabelText('Workspace page access')).toHaveValue('team-a')
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeDisabled()
  expect(screen.getByText(/unsaved workspace access changes/)).toBeInTheDocument()
  expect(api.publishArtifact).not.toHaveBeenCalled()
})

it('preserves unsaved team and version selections when removing a public link refreshes the Page', async () => {
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team-a' } })
  fireEvent.change(screen.getByLabelText('Version shared with team'), { target: { value: 'r2' } })
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, published_revision: null, public_token: null })
  fireEvent.click(screen.getByRole('button', { name: 'Remove public link' }))
  await screen.findByText('Public link removed. Downloaded copies cannot be recalled.')
  expect(screen.getByLabelText('Workspace page access')).toHaveValue('team-a')
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r2')
  expect(screen.getByText(/unsaved workspace access changes/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Publish version 2' })).toBeDisabled()
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
})
