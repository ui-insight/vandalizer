import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { KnowledgeBasesTab } from './KnowledgeBasesTab'
import { AdminViewState } from './shared/AdminViewState'
import type { AdminKBListResponse, AdminKBSummary } from '../../api/admin'

const list = vi.fn()
const rename = vi.fn()
vi.mock('../../api/admin', () => ({ getAdminKnowledgeBases: (...args: unknown[]) => list(...args) }))
vi.mock('../../api/knowledge', () => ({ updateKnowledgeBase: (...args: unknown[]) => rename(...args) }))
const kb = (uuid: string, title = uuid): AdminKBSummary => ({ uuid, title, status: 'ready', verified: false, tags: [], total_sources: 2, total_chunks: 8, owner_id: 'owner', owner_email: 'owner@example.test', team_id: null, team_name: null, created_at: null, updated_at: null })
const page = (title = 'Research policy', total = 1): AdminKBListResponse => ({ knowledge_bases: [kb(title)], total })
const search = (value: string) => {
  fireEvent.change(screen.getByRole('textbox', { name: 'Search knowledge bases' }), { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Search all records' }))
}
beforeEach(() => { list.mockReset().mockResolvedValue(page()); rename.mockReset().mockResolvedValue({}) })

it('submits full-inventory search and status, resetting later pages', async () => {
  list.mockResolvedValue({ knowledge_bases: Array.from({ length: 2 }, (_, i) => kb(`Record ${i}`)), total: 503 })
  render(<KnowledgeBasesTab canEdit />)
  await screen.findByText('Record 1')
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100 })))
  list.mockResolvedValue(page('Late match'))
  search(' late-owner@example.test ')
  await screen.findByText('Late match')
  expect(list).toHaveBeenLastCalledWith({ search: 'late-owner@example.test', status: '', sort: 'title', offset: 0, limit: 100 })
  fireEvent.change(screen.getByRole('combobox', { name: 'Knowledge base status' }), { target: { value: 'error' } })
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'late-owner@example.test', status: 'error', offset: 0 })))
  expect(screen.getByRole('option', { name: 'building' })).toBeInTheDocument()
})

it('sorts the full inventory and resets pagination', async () => {
  list.mockResolvedValue({ knowledge_bases: Array.from({ length: 2 }, (_, i) => kb(`Record ${i}`)), total: 503 })
  render(<KnowledgeBasesTab canEdit={false} />)
  await screen.findByText('Record 1')
  fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 100 })))
  await screen.findByRole('button', { name: 'Updated' })
  fireEvent.click(screen.getByRole('button', { name: 'Updated' }))
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'updated', offset: 0 })))
  expect(screen.queryByRole('button', { name: /^Rename / })).not.toBeInTheDocument()
})

it('ignores a late response from an earlier search', async () => {
  let finishOld!: (value: AdminKBListResponse) => void
  list.mockImplementation(({ search }) => search === 'old' ? new Promise(resolve => { finishOld = resolve }) : Promise.resolve(page(search || 'Initial')))
  render(<KnowledgeBasesTab canEdit />)
  await screen.findByText('Initial')
  search('old')
  await waitFor(() => expect(finishOld).toBeTypeOf('function'))
  search('new')
  await screen.findByText('new')
  await act(async () => finishOld(page('Obsolete response')))
  expect(screen.queryByText('Obsolete response')).not.toBeInTheDocument()
  expect(screen.getByText('new')).toBeInTheDocument()
})

it('retries failed searches with the same scope', async () => {
  render(<KnowledgeBasesTab canEdit />)
  await screen.findByText('Research policy')
  list.mockRejectedValueOnce(new Error('Search unavailable'))
  search('missing')
  await screen.findByRole('alert')
  expect(screen.queryByText('Research policy')).not.toBeInTheDocument()
  list.mockResolvedValue({ knowledge_bases: [], total: 0 })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
  await screen.findByText('No knowledge bases match these filters.')
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'missing' }))
})

it('keeps failed rename drafts and returns focus after successful retry', async () => {
  render(<KnowledgeBasesTab canEdit />)
  fireEvent.click(await screen.findByRole('button', { name: 'Rename Research policy' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Knowledge base title' }), { target: { value: 'Updated policy' } })
  rename.mockRejectedValueOnce(new Error('Rename unavailable'))
  fireEvent.click(screen.getByRole('button', { name: 'Save title for Research policy' }))
  await screen.findByText('Rename unavailable')
  expect(screen.getByRole('textbox', { name: 'Knowledge base title' })).toHaveValue('Updated policy')
  fireEvent.click(screen.getByRole('button', { name: 'Save title for Research policy' }))
  expect(await screen.findByRole('button', { name: 'Rename Updated policy' })).toHaveFocus()
  expect(screen.getByText('Title saved. Refresh to update its position and search matches.')).toBeInTheDocument()
})

it('restores the submitted inventory view after section navigation', async () => {
  const view = () => <AdminViewState scope="kb-view-retention"><KnowledgeBasesTab canEdit /></AdminViewState>
  const mounted = render(view())
  await screen.findByText('Research policy')
  search('regional team')
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'regional team' })))
  mounted.unmount()
  render(view())
  await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'regional team' })))
  expect(screen.getByRole('textbox', { name: 'Search knowledge bases' })).toHaveValue('regional team')
})
