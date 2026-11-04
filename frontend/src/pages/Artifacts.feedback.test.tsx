import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'
import * as feedback from '../api/pageFeedback'

// Support ticket: shared and public pages didn't say whose they were, and
// viewers had no way to ask the owner about a figure.

vi.mock('../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof api>(), getArtifact: vi.fn(), getPublicArtifact: vi.fn() }))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([]) }))
vi.mock('../api/pageFeedback', async importOriginal => ({ ...await importOriginal<typeof feedback>(), listPageFeedback: vi.fn(), getPublicPageFeedback: vi.fn() }))

const shared: api.Artifact = { uuid: 'a1', title: 'NIH R01 Budget', latest_revision: 'r1', published_revision: null, public_token: null,
  team_id: 'team-a', team_revision: 'r1', can_manage: false, public_sharing_enabled: true,
  revisions: [{ uuid: 'r1', title: 'NIH R01 Budget', created_at: '', warnings: [], version: 3 }] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getArtifact).mockResolvedValue(shared)
  vi.mocked(api.getPublicArtifact).mockResolvedValue({ title: 'NIH R01 Budget', revision: 'r1', version: 3, updated_at: '2026-11-03T10:00:00Z' })
  vi.mocked(feedback.listPageFeedback).mockResolvedValue({ role: 'member', items: [], shared_by: 'Shared by Dana Reyes, University of Idaho Office of Sponsored Programs' })
  vi.mocked(feedback.getPublicPageFeedback).mockResolvedValue({ shared_by: 'Shared by Dana Reyes, University of Idaho Office of Sponsored Programs', public_questions: false, items: [] })
})

it('tells a team member who shared the page and switches the frame to picking when they ask', async () => {
  render(<ArtifactPage uuid="a1" />)
  expect(await screen.findByText('Shared by Dana Reyes, University of Idaho Office of Sponsored Programs', { selector: '.page-shared-by' })).toBeInTheDocument()
  expect(feedback.listPageFeedback).toHaveBeenCalledWith('a1', 'r1')
  expect(screen.getByTitle('Page preview')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Ask the owner' }))
  expect(screen.queryByTitle('Page preview')).not.toBeInTheDocument()
  expect(screen.getByTitle('Published page content')).toHaveAttribute('src', '/api/pages/a1/revisions/r1/content?view=embed')
})

it('names the owner on a public page and offers questions only if the owner allows them', async () => {
  render(<ArtifactPage publicToken="public-link" />)
  expect(await screen.findByText('Shared by Dana Reyes, University of Idaho Office of Sponsored Programs', { selector: '.page-shared-by' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Ask the owner' })).not.toBeInTheDocument()
})
