import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'

vi.mock('../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof api>(), getArtifact: vi.fn(), getPublicArtifact: vi.fn(), artifactSource: vi.fn(), reviseArtifact: vi.fn(), publishArtifact: vi.fn(), unpublishArtifact: vi.fn(), shareArtifactTeam: vi.fn(), deleteArtifact: vi.fn() }))
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
  expect(frame).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')
  expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
  expect(frame).toHaveAttribute('src', '/api/pages/public/public-link/content?revision=r2')
  expect(screen.getByRole('link', { name: 'Download HTML' })).toHaveAttribute('href', '/api/pages/public/public-link/content?revision=r2&download=true')
  expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute('href', '/api/pages/public/public-link/content?revision=r2&view=full')
})

it('does not invent an update date when public metadata has an invalid timestamp', async () => {
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'Published report', revision: 'r2', version: 2, updated_at: 'invalid' })
  render(<ArtifactPage publicToken="public-link" />)
  expect(await screen.findByText('Last updated date unavailable')).toBeInTheDocument()
  expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
})

it('shows the renamed library name for the latest version and preserves historical titles', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, title: 'Renamed award dashboard' })
  render(<ArtifactPage uuid="a1" />)
  expect(await screen.findByRole('heading', { name: 'Renamed award dashboard' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Page version'), { target: { value: 'r1' } })
  expect(screen.getByRole('heading', { name: 'Published report' })).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Page version'), { target: { value: 'r2' } })
  expect(screen.getByRole('heading', { name: 'Renamed award dashboard' })).toBeInTheDocument()
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

it('clears previous feedback on opening delete while still showing deletion failures', async () => {
  const third = { ...item, latest_revision: 'r3', revisions: [...item.revisions,
    { uuid: 'r3', title: 'Latest report', created_at: '', warnings: [] },
  ] }
  vi.mocked(api.getArtifact).mockResolvedValue(third)
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  vi.mocked(api.getArtifact).mockResolvedValue({ ...third, published_revision: 'r3' })
  fireEvent.click(screen.getByRole('button', { name: 'Publish updates · version 3' }))
  const published = 'Version 3 published. Anyone with the link can view it.'
  await screen.findByText(published)
  fireEvent.click(screen.getByRole('button', { name: 'Close Share page' }))
  fireEvent.click(screen.getByText('Advanced page options'))
  fireEvent.click(screen.getByRole('button', { name: 'Delete page' }))
  const dialog = within(screen.getByRole('dialog', { name: 'Delete this page?' }))
  expect(dialog.getByText(/This deletes every saved version/)).toBeInTheDocument()
  expect(dialog.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.queryByText(published)).not.toBeInTheDocument()
  expect(api.deleteArtifact).not.toHaveBeenCalled()

  vi.mocked(api.deleteArtifact).mockRejectedValueOnce(new Error('Could not delete page. Try again.'))
  fireEvent.click(dialog.getByRole('button', { name: 'Delete permanently' }))
  expect(await dialog.findByRole('alert')).toHaveTextContent('Could not delete page. Try again.')
  expect(api.deleteArtifact).toHaveBeenCalledWith('a1')
  fireEvent.click(dialog.getByRole('button', { name: 'Keep page' }))
  expect(screen.queryByText(published)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Delete page' }))
  expect(within(screen.getByRole('dialog', { name: 'Delete this page?' })).queryByRole('alert')).not.toBeInTheDocument()
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
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r2')
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeEnabled()
  expect(api.publishArtifact).not.toHaveBeenCalled()
})

it('publishes the latest version from Share while the page behind it previews the published version', async () => {
  const shared = { ...item, team_id: 'team-a', team_revision: 'r1' }
  vi.mocked(api.getArtifact).mockResolvedValue(shared)
  render(<ArtifactPage uuid="a1" />)
  fireEvent.change(await screen.findByLabelText('Page version'), { target: { value: 'r1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Share' }))
  const dialog = within(screen.getByRole('dialog', { name: 'Share page' }))
  const summary = dialog.getByLabelText('Current audience versions')
  expect(summary).toHaveTextContent('Your team sees:Version 1')
  expect(summary).toHaveTextContent('Public link shows:Version 1')
  expect(summary).toHaveTextContent('Latest saved:Version 2')
  expect(dialog.getByText('Version 2 is newer than the published version.')).toBeVisible()
  expect(dialog.getByLabelText('Version to publish')).toHaveValue('r2')
  expect(dialog.getByRole('link', { name: 'Preview version 2' })).toHaveAttribute('href', '/api/pages/a1/revisions/r2/content')
  expect(within(dialog.getByLabelText('Version shared with team')).getByRole('option', { name: 'Version 1 · shared with team' })).toBeInTheDocument()

  vi.mocked(api.getArtifact).mockResolvedValue({ ...shared, published_revision: 'r2' })
  fireEvent.click(dialog.getByRole('button', { name: 'Publish updates · version 2' }))
  await dialog.findByText('Version 2 published. Anyone with the link can view it.')
  expect(api.publishArtifact).toHaveBeenCalledWith('a1', 'r2')
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  expect(summary).toHaveTextContent('Your team sees:Version 1')
  expect(summary).toHaveTextContent('Public link shows:Version 2')
  expect(dialog.queryByText(/is newer than the published version/)).not.toBeInTheDocument()
  expect(dialog.getByRole('button', { name: 'Published' })).toBeDisabled()
  fireEvent.click(dialog.getByRole('button', { name: 'Close Share page' }))
  expect(screen.getByLabelText('Page version')).toHaveValue('r1')
})

it('lets the owner choose a public version independently of team access and the page preview', async () => {
  const third = { ...item, team_id: 'team-a', team_revision: 'r1', latest_revision: 'r3',
    revisions: [...item.revisions, { uuid: 'r3', title: 'Latest draft', created_at: '', warnings: [] }],
  }
  vi.mocked(api.getArtifact).mockResolvedValue(third)
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r3')
  fireEvent.change(screen.getByLabelText('Version to publish'), { target: { value: 'r1' } })
  expect(screen.getByRole('button', { name: 'Published' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Version to publish'), { target: { value: 'r2' } })
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r1')
  expect(screen.getByRole('button', { name: 'Save access' })).toBeDisabled()
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Public link shows:Version 1')
  expect(api.publishArtifact).not.toHaveBeenCalled()
  vi.mocked(api.getArtifact).mockResolvedValue({ ...third, published_revision: 'r2' })
  fireEvent.click(screen.getByRole('button', { name: 'Publish updates · version 2' }))
  await screen.findByText('Version 2 published. Anyone with the link can view it.')
  expect(api.publishArtifact).toHaveBeenCalledWith('a1', 'r2')
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r2')
  expect(screen.getByLabelText('Version shared with team')).toHaveValue('r1')
  fireEvent.click(screen.getByRole('button', { name: 'Close Share page' }))
  expect(screen.getByLabelText('Page version')).toHaveValue('r3')
  fireEvent.click(screen.getByRole('button', { name: 'Share' }))
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r3')
})

it('retains the public selection and live audience versions when publishing fails', async () => {
  vi.mocked(api.publishArtifact).mockRejectedValueOnce(new Error('Publication failed. Try again.'))
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  fireEvent.click(screen.getByRole('button', { name: 'Publish updates · version 2' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Publication failed. Try again.')
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r2')
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Public link shows:Version 1')
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Your team sees:Not shared with a team')
  expect(screen.getByRole('button', { name: 'Publish updates · version 2' })).toBeEnabled()
})

it('defaults direct Share links to the latest saved version and identifies unpublished access', async () => {
  window.history.replaceState(null, '', '/pages/a1#share')
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, published_revision: null, public_token: null })
  try {
    render(<ArtifactPage uuid="a1" />)
    const dialog = within(await screen.findByRole('dialog', { name: 'Share page' }))
    expect(dialog.getByLabelText('Version to publish')).toHaveValue('r2')
    expect(dialog.getByLabelText('Current audience versions')).toHaveTextContent('Public link shows:Not published')
    expect(dialog.getByRole('button', { name: 'Publish version 2' })).toBeEnabled()
    expect(api.publishArtifact).not.toHaveBeenCalled()
  } finally {
    window.history.replaceState(null, '', '/')
  }
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
  fireEvent.change(screen.getByLabelText('Version to publish'), { target: { value: 'r1' } })
  fireEvent.change(screen.getByLabelText('Version shared with team'), { target: { value: 'r2' } })
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r1')
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Your team sees:Version 1')
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, team_id: 'team-a', team_revision: 'r2' })
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a', 'r2'))
  await screen.findByText('Workspace access updated.')
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Your team sees:Version 2')
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Public link shows:Version 1')
  expect(screen.getByLabelText('Version to publish')).toHaveValue('r1')
  expect(api.publishArtifact).not.toHaveBeenCalled()
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
