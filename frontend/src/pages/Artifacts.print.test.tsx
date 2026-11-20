import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'

vi.mock('../api/artifacts', async importOriginal => ({
  ...await importOriginal<typeof import('../api/artifacts')>(),
  getArtifact: vi.fn(), getPublicArtifact: vi.fn(),
}))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([]) }))

const item: api.Artifact = {
  uuid: 'page1', title: 'Budget draft', latest_revision: 'r2', published_revision: 'r1',
  team_id: null, can_manage: true,
  revisions: [
    { uuid: 'r1', title: 'Budget', version: 1, created_at: '2026-10-01T12:00:00Z', warnings: [] },
    { uuid: 'r2', title: 'Budget draft', version: 2, created_at: '2026-10-02T12:00:00Z', warnings: [] },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getArtifact).mockResolvedValue(item)
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'Budget', revision: 'r1', version: 1, updated_at: '2026-10-01T12:00:00Z' })
})

it('prints the selected revision in a separate tab and keeps previews sandboxed', async () => {
  render(<ArtifactPage uuid="page1" />)
  const print = await screen.findByRole('link', { name: 'Print / Save as PDF' })
  expect(print).toHaveAttribute('href', '/api/pages/page1/revisions/r2/content?view=print')
  expect(print).toHaveAttribute('target', '_blank')
  expect(print).toHaveAttribute('rel', 'noopener noreferrer')
  fireEvent.change(screen.getByLabelText('Page version'), { target: { value: 'r1' } })
  expect(print).toHaveAttribute('href', '/api/pages/page1/revisions/r1/content?view=print')
  expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute('href', '/api/pages/page1/revisions/r1/content?view=full')
  const sandbox = screen.getByTitle('Page preview').getAttribute('sandbox')
  expect(sandbox).not.toBeNull()
  expect(sandbox?.split(' ')).not.toContain('allow-scripts')
  expect(sandbox?.split(' ')).not.toContain('allow-same-origin')
  expect(screen.getByTitle('Page preview')).toHaveAttribute('src', '/api/pages/page1/revisions/r1/content')
})

it('keeps the public revision binding on print and full-page links', async () => {
  render(<ArtifactPage publicToken="public-token" />)
  expect(await screen.findByRole('link', { name: 'Print / Save as PDF' })).toHaveAttribute('href', '/api/pages/public/public-token/content?revision=r1&view=print')
  expect(screen.getByRole('link', { name: 'Open full page' })).toHaveAttribute('href', '/api/pages/public/public-token/content?revision=r1&view=full')
})

it('allows a team reader to print only the version they can see', async () => {
  vi.mocked(api.getArtifact).mockResolvedValue({ ...item, can_manage: false, latest_revision: 'r1', revisions: [item.revisions[0]] })
  render(<ArtifactPage uuid="page1" />)
  expect(await screen.findByRole('link', { name: 'Print / Save as PDF' })).toHaveAttribute('href', '/api/pages/page1/revisions/r1/content?view=print')
  expect(screen.queryByLabelText('Page version')).not.toBeInTheDocument()
})
