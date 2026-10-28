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
  const frame = screen.getByTitle('Page preview')
  expect(frame).toHaveAttribute('sandbox', '')
  expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
  expect(frame).toHaveAttribute('src', '/api/pages/public/public-link/content')
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
  await waitFor(() => expect(api.shareArtifactTeam).toHaveBeenCalledWith('a1', 'team-a'))
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
