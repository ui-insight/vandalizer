import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SavePageTemplate } from './SavePageTemplate'
import { TemplatesBrowser } from './TemplatesBrowser'
import { ChatPageCard } from './ChatPageCard'
import * as api from '../../api/pageTemplates'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { listTeams } from '../../api/teams'

const workspace = vi.hoisted(() => ({ sendChatMessage: vi.fn(), triggerNewChat: vi.fn(), setWorkspaceMode: vi.fn() }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => workspace }))
vi.mock('../../api/pageTemplates', async original => ({ ...await original<typeof api>(), preparePageTemplate: vi.fn(), savePageTemplate: vi.fn(), browsePageTemplates: vi.fn(), sharePageTemplate: vi.fn(), deletePageTemplate: vi.fn() }))
vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
vi.mock('../../api/teams', () => ({ listTeams: vi.fn() }))
const template: api.PageTemplate = { uuid: 't1', name: 'NIH Budget Dashboard', description: 'Reusable award budget', owner_name: 'Alex', team_id: null, can_manage: true, created_at: '2026-10-29' }
const draft: api.TemplateDraft = { draft_id: 'safe-design', preview_html: '<h1>Not in this file</h1>', fields: [{ id: 'field_1', label: 'Award title', bar: false }] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.preparePageTemplate).mockResolvedValue(draft)
  vi.mocked(api.savePageTemplate).mockResolvedValue(template)
  vi.mocked(api.browsePageTemplates).mockResolvedValue({ items: [template], total: 1, page: 1, page_size: 20 })
  vi.mocked(searchDocuments).mockResolvedValue({ items: [{ uuid: 'new-budget', title: 'New award.xlsx' } as SearchResult], total: 1 })
  vi.mocked(listTeams).mockResolvedValue([{ uuid: 'team', name: 'Research office' }] as Awaited<ReturnType<typeof listTeams>>)
  vi.mocked(api.sharePageTemplate).mockResolvedValue({ ok: true })
})

it('reviews a server-cleared design and saves its name, description and reusable guidance without raw Page HTML', async () => {
  render(<SavePageTemplate source={{ artifact_uuid: 'page', revision: 'r2' }} onClose={vi.fn()} />)
  await screen.findByLabelText('Template name')
  expect(api.preparePageTemplate).toHaveBeenCalledWith({ artifact_uuid: 'page', revision: 'r2', preview_id: undefined })
  expect(screen.getByRole('button', { name: 'Save template' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Template name'), { target: { value: template.name } })
  fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'A standard design' } })
  fireEvent.change(screen.getByLabelText('Reusable guidance'), { target: { value: 'Review the source.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save template' }))
  await screen.findByText('Template saved privately. It contains the design and empty fields.')
  expect(api.savePageTemplate).toHaveBeenCalledExactlyOnceWith({ draft_id: 'safe-design', name: template.name, description: 'A standard design', guidance: 'Review the source.', field_labels: { field_1: 'Award title' } })
  expect(screen.getByRole('link', { name: 'Open Templates' })).toHaveAttribute('href', '/?mode=files&files=templates')
})

it('offers Save as template beside Save page without approving or saving the original Page', async () => {
  const decide = vi.fn()
  render(<ChatPageCard title="Original Page" html="<p>Original data</p>" previewId="preview" needsApproval decision={null} decisionError={null} onDecide={decide} revising={false} templateCheck={{ filled: 24, missing: 2, retained: 0, source_title: 'New award.xlsx', template_name: template.name }} />)
  expect(screen.getByText('24 values filled from New award.xlsx · 0 kept from the template.')).toBeInTheDocument()
  expect(screen.getByText(/2 fields show/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save as template' }))
  await screen.findByLabelText('Template name')
  expect(api.preparePageTemplate).toHaveBeenCalledWith({ preview_id: 'preview', artifact_uuid: undefined, revision: undefined })
  expect(decide).not.toHaveBeenCalled()
  expect(api.savePageTemplate).not.toHaveBeenCalled()
})

it('shows template ownership and scope, then starts a fresh Page request with only the selected new file', async () => {
  render(<TemplatesBrowser />)
  await screen.findByText(template.name)
  expect(screen.getByText('Private')).toBeInTheDocument()
  expect(screen.getByText('By Alex')).toBeInTheDocument()
  expect(screen.getByTitle(`${template.name} thumbnail`)).toHaveAttribute('src', '/api/page-templates/t1/content')
  fireEvent.click(screen.getByRole('button', { name: 'Use template' }))
  const dialog = screen.getByRole('dialog', { name: `Use ${template.name}` })
  expect(within(dialog).getByRole('button', { name: 'Build Page preview' })).toBeDisabled()
  fireEvent.click(await within(dialog).findByRole('radio', { name: 'New award.xlsx' }))
  expect(workspace.sendChatMessage).not.toHaveBeenCalled()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Build Page preview' }))
  expect(workspace.triggerNewChat).toHaveBeenCalledOnce()
  expect(workspace.setWorkspaceMode).toHaveBeenCalledWith('chat')
  expect(workspace.sendChatMessage).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('template=t1'), { documentUuids: ['new-budget'] })
  expect(workspace.sendChatMessage.mock.calls[0][0]).toContain('Not in this file')
})

it('shares only the template after an explicit access choice', async () => {
  render(<TemplatesBrowser />)
  fireEvent.click(await screen.findByRole('button', { name: 'Share template' }))
  await screen.findByRole('option', { name: 'Research office' })
  fireEvent.change(screen.getByLabelText('Template access'), { target: { value: 'team' } })
  expect(api.sharePageTemplate).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save access' }))
  await waitFor(() => expect(api.sharePageTemplate).toHaveBeenCalledWith('t1', 'team'))
})

it('keeps read-only team designs usable without management actions', async () => {
  vi.mocked(api.browsePageTemplates).mockResolvedValue({ items: [{ ...template, team_id: 'team', can_manage: false }], total: 1, page: 1, page_size: 20 })
  render(<TemplatesBrowser />)
  await screen.findByRole('button', { name: 'Use template' })
  expect(screen.getByText('Team')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Share template' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete template' })).not.toBeInTheDocument()
})

it('recovers a failed design preparation and keeps the reviewed form after a save failure', async () => {
  vi.mocked(api.preparePageTemplate).mockRejectedValueOnce(new Error('Design unavailable'))
  vi.mocked(api.savePageTemplate).mockRejectedValueOnce(new Error('Save interrupted'))
  render(<SavePageTemplate source={{ preview_id: 'preview' }} onClose={vi.fn()} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Design unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry design' }))
  fireEvent.change(await screen.findByLabelText('Template name'), { target: { value: 'Reviewed design' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save template' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Save interrupted')
  expect(screen.getByLabelText('Template name')).toHaveValue('Reviewed design')
  fireEvent.click(screen.getByRole('button', { name: 'Save template' }))
  await screen.findByText('Template saved privately. It contains the design and empty fields.')
})

it('keeps the source selection unavailable until the file search recovers', async () => {
  vi.mocked(searchDocuments).mockRejectedValueOnce(new Error('Files unavailable'))
  render(<TemplatesBrowser />)
  fireEvent.click(await screen.findByRole('button', { name: 'Use template' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Files unavailable')
  expect(screen.getByRole('button', { name: 'Build Page preview' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry files' }))
  await screen.findByRole('radio', { name: 'New award.xlsx' })
  expect(workspace.sendChatMessage).not.toHaveBeenCalled()
})
