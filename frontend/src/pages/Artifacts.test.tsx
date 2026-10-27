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
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'Published report', revision: 'r1' })
})

it('shows the pinned public page without loading private metadata or management controls', async () => {
  render(<ArtifactPage publicToken="public-link" />)
  await screen.findByRole('heading', { name: 'Published report' })
  expect(api.getArtifact).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Edit HTML' })).not.toBeInTheDocument()
  const frame = screen.getByTitle('Artifact preview')
  expect(frame).toHaveAttribute('sandbox', '')
  expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
  expect(frame).toHaveAttribute('src', '/api/artifacts/public/public-link/content')
})

it('publishes exactly the selected saved revision and revokes an existing link', async () => {
  render(<ArtifactPage uuid="a1" />)
  await screen.findByRole('button', { name: 'Publish selected revision' })
  fireEvent.change(screen.getByLabelText('Artifact revision'), { target: { value: 'r1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Publish selected revision' }))
  await waitFor(() => expect(api.publishArtifact).toHaveBeenCalledWith('a1', 'r1'))
  await screen.findByText('Selected revision published.')
  fireEvent.click(screen.getByRole('button', { name: 'Unpublish and revoke link' }))
  await waitFor(() => expect(api.unpublishArtifact).toHaveBeenCalledWith('a1'))
})

it('retains an unsaved edit when the server rejects a stale base revision', async () => {
  vi.mocked(api.artifactSource).mockResolvedValue({ title: 'Private draft', html: '<main>Original</main>' })
  vi.mocked(api.reviseArtifact).mockRejectedValue(new Error('This artifact changed. Reload before saving another revision.'))
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit HTML' }))
  fireEvent.change(await screen.findByLabelText('HTML'), { target: { value: '<main>Unsaved edit</main>' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save new revision' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('HTML')).toHaveValue('<main>Unsaved edit</main>')
  expect(api.reviseArtifact).toHaveBeenCalledWith('a1', 'Private draft', '<main>Unsaved edit</main>', 'r2')
  expect(api.publishArtifact).not.toHaveBeenCalled()
})

it('requires explicit access saving and respects the deployment publish switch', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, public_sharing_enabled: false })
  render(<ArtifactPage uuid="a1" />)
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Private artifact access'), { target: { value: 'team-a' } })
  expect(api.shareArtifactTeam).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a'))
  expect(screen.getByRole('button', { name: 'Publish selected revision' })).toBeDisabled()
})

it('shows a revoked public link error without rendering an iframe', async () => {
  vi.mocked(api.getPublicArtifact).mockRejectedValue(new Error('Artifact not found'))
  render(<ArtifactPage publicToken="revoked" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Artifact not found')
  expect(screen.queryByTitle('Artifact preview')).not.toBeInTheDocument()
})
