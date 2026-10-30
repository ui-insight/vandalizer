import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'

vi.mock('../api/artifacts', async original => ({ ...await original<typeof api>(),
  getArtifact: vi.fn(), publishArtifact: vi.fn(), unpublishArtifact: vi.fn(),
  publishArtifactVersion: vi.fn(), unpublishArtifactVersion: vi.fn(),
}))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([{ uuid: 'team', name: 'Research team' }]) }))
let saved: api.Artifact
const link = (revision: string) => ({ revision, token: `public-${revision}`, published_at: '2026-10-29T00:00:00Z' })
beforeEach(() => {
  vi.clearAllMocks()
  saved = { uuid: 'page', title: 'Revised budget', can_manage: true, team_id: null,
    latest_revision: 'v3', published_revision: 'v1', public_token: 'main', public_sharing_enabled: true,
    publications: [], revisions: [1, 2, 3].map(version => ({ uuid: `v${version}`, title: `Budget ${version}`, version, created_at: '2026-10-29T00:00:00Z', warnings: [] })),
  }
  vi.mocked(api.getArtifact).mockImplementation(async () => saved)
  vi.mocked(api.publishArtifactVersion).mockImplementation(async (_id, revision) => {
    saved = { ...saved, publications: [...saved.publications!, link(revision)] }
    return saved
  })
  vi.mocked(api.unpublishArtifactVersion).mockImplementation(async (_id, revision) => {
    saved = { ...saved, publications: saved.publications!.filter(p => p.revision !== revision) }
    return { ok: true }
  })
})

it('publishes old and revised versions at separate links without moving the main link', async () => {
  render(<ArtifactPage uuid="page" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByText(/Publishing updates changes what everyone sees at the main public link/)).toBeVisible()
  expect(api.publishArtifactVersion).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Version to publish'), { target: { value: 'v1' } })
  fireEvent.click(screen.getByRole('button', { name: 'Publish as separate link' }))
  const original = await screen.findByLabelText('Public link for version 1')
  expect(original).toHaveValue(`${window.location.origin}/a/public-v1`)
  expect(api.publishArtifactVersion).toHaveBeenCalledWith('page', 'v1')
  expect(screen.getByRole('button', { name: 'Separate link published' })).toBeDisabled()

  fireEvent.change(screen.getByLabelText('Version to publish'), { target: { value: 'v3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Publish as separate link' }))
  expect(await screen.findByLabelText('Public link for version 3')).toHaveValue(`${window.location.origin}/a/public-v3`)
  expect(screen.getByLabelText('Public link for version 1')).toHaveValue(`${window.location.origin}/a/public-v1`)
  expect(screen.queryByLabelText('Public link for version 2')).not.toBeInTheDocument()
  expect(screen.getByLabelText('Published page link')).toHaveValue(`${window.location.origin}/a/main`)
  expect(screen.getByLabelText('Current audience versions')).toHaveTextContent('Public link shows:Version 1')
  expect(screen.getByRole('link', { name: 'Open version 1' })).toHaveAttribute('href', `${window.location.origin}/a/public-v1`)
  expect(api.publishArtifact).not.toHaveBeenCalled()
  expect(api.publishArtifactVersion).toHaveBeenCalledTimes(2)
})

it('copies and removes only the chosen separate link', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
  try {
    saved.publications = [link('v1'), link('v3')]
    render(<ArtifactPage uuid="page" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
    fireEvent.click(screen.getByRole('button', { name: 'Copy version 1 link' }))
    await screen.findByText('Version link copied.')
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/a/public-v1`)
    fireEvent.click(screen.getByRole('button', { name: 'Remove version 1 link' }))
    await waitFor(() => expect(screen.queryByLabelText('Public link for version 1')).not.toBeInTheDocument())
    expect(api.unpublishArtifactVersion).toHaveBeenCalledWith('page', 'v1')
    expect(api.unpublishArtifact).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Public link for version 3')).toBeInTheDocument()
    expect(screen.getByLabelText('Published page link')).toBeInTheDocument()
  } finally { vi.unstubAllGlobals() }
})

it.each(['publish', 'remove'])('retains selected and existing versions when %s fails', async operation => {
  saved.publications = [link('v1')]
  if (operation === 'publish') vi.mocked(api.publishArtifactVersion).mockRejectedValueOnce(new Error('Could not publish.'))
  else vi.mocked(api.unpublishArtifactVersion).mockRejectedValueOnce(new Error('Could not remove.'))
  render(<ArtifactPage uuid="page" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  fireEvent.click(screen.getByRole('button', { name: operation === 'publish' ? 'Publish as separate link' : 'Remove version 1 link' }))
  expect(await screen.findByRole('alert')).toHaveTextContent(operation === 'publish' ? 'Could not publish.' : 'Could not remove.')
  expect(screen.getByLabelText('Version to publish')).toHaveValue('v3')
  expect(screen.getByLabelText('Public link for version 1')).toBeInTheDocument()
  expect(screen.queryByLabelText('Public link for version 3')).not.toBeInTheDocument()
})

it('blocks separate publication while workspace access is unsaved', async () => {
  render(<ArtifactPage uuid="page" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  await screen.findByRole('option', { name: 'Research team' })
  fireEvent.change(screen.getByLabelText('Workspace page access'), { target: { value: 'team' } })
  expect(screen.getByRole('button', { name: 'Publish as separate link' })).toBeDisabled()
  expect(api.publishArtifactVersion).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Discard access changes' }))
  expect(screen.getByRole('button', { name: 'Publish as separate link' })).toBeEnabled()
})

it('respects the deployment switch but permits revoking existing version links', async () => {
  saved.public_sharing_enabled = false
  saved.publications = [link('v1')]
  render(<ArtifactPage uuid="page" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share' }))
  expect(screen.getByRole('button', { name: 'Publish as separate link' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Remove version 1 link' })).toBeEnabled()
})

it('identifies separate-only publication without claiming the selected draft is public', async () => {
  saved.published_revision = null
  saved.public_token = null
  saved.publications = [link('v1')]
  render(<ArtifactPage uuid="page" />)
  expect(await screen.findByText('Published version links')).toBeInTheDocument()
  expect(screen.getByText('Unpublished changes')).toBeInTheDocument()
  expect(screen.queryByText('Private · only you')).not.toBeInTheDocument()
  expect(screen.queryByText(/version 0/)).not.toBeInTheDocument()
  expect(within(screen.getByLabelText('Page version')).getByRole('option', { name: 'Version 1 · published' })).toBeInTheDocument()
})
