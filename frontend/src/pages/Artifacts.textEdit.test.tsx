import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ArtifactPage from './Artifacts'
import * as api from '../api/artifacts'
import * as feedback from '../api/pageFeedback'

// Support ticket: fixing one heading on a Page took a chat round trip, and the
// only manual option was the raw HTML editor.

vi.mock('../api/artifacts', async importOriginal => ({ ...await importOriginal<typeof api>(), getArtifact: vi.fn(), saveTextEdits: vi.fn() }))
vi.mock('../api/teams', () => ({ listTeams: vi.fn().mockResolvedValue([]) }))
vi.mock('../api/pageFeedback', async importOriginal => ({ ...await importOriginal<typeof feedback>(), listPageFeedback: vi.fn(), getPublicPageFeedback: vi.fn() }))

const owned: api.Artifact = { uuid: 'a1', title: 'NIH R01 Budget Dashboard', latest_revision: 'r5', published_revision: 'r5', public_token: 'tok',
  team_id: null, can_manage: true, public_sharing_enabled: true,
  revisions: [{ uuid: 'r5', title: 'NIH R01 Budget Dashboard', created_at: '', warnings: [], version: 5 }] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.getArtifact).mockResolvedValue(owned)
})

it('lets the owner edit text in place and saves it as a new version without touching the public link', async () => {
  render(<ArtifactPage uuid="a1" />)
  fireEvent.click(await screen.findByRole('button', { name: 'Edit text' }))
  const frame = screen.getByTitle('Published page content') as HTMLIFrameElement
  expect(frame.src).toContain('/api/pages/a1/revisions/r5/content')
  expect(screen.getByRole('region', { name: 'Edit text' })).toHaveTextContent('Saving creates version 6')
  const save = screen.getByRole('button', { name: 'Save new version' })
  expect(save).toBeDisabled()
  const fromFrame = (data: unknown) => act(() => { window.dispatchEvent(new MessageEvent('message', { data, source: frame.contentWindow })) })
  fromFrame({ type: 'vandalizer:edit-count', count: 1 })
  expect(screen.getByText('1 block changed')).toBeInTheDocument()
  vi.mocked(api.saveTextEdits).mockResolvedValue({ ...owned, latest_revision: 'r6', version: 6, notes: [],
    revisions: [...owned.revisions, { uuid: 'r6', title: 'NIH R01 Budget Dashboard', created_at: '', warnings: [], version: 6 }] })
  vi.mocked(api.getArtifact).mockResolvedValue({ ...owned, latest_revision: 'r6',
    revisions: [...owned.revisions, { uuid: 'r6', title: 'NIH R01 Budget Dashboard', created_at: '', warnings: [], version: 6 }] })
  fireEvent.click(screen.getByRole('button', { name: 'Save new version' }))
  const edit = { tag: 'h1', index: 0, original: 'NIH R01 Budget Dashbord', text: 'NIH R01 Budget Dashboard' }
  fromFrame({ type: 'vandalizer:edits', edits: [edit] })
  await waitFor(() => expect(api.saveTextEdits).toHaveBeenCalledWith('a1', 'r5', [edit]))
  expect(await screen.findByText(/Saved as version 6\. Your public link still shows the published version/)).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Edit text' })).not.toBeInTheDocument()
})
