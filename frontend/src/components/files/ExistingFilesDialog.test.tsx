import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ExistingFilesDialog } from './ExistingFilesDialog'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { moveFile } from '../../api/files'

vi.mock('../../api/documents', () => ({ searchDocuments: vi.fn() }))
vi.mock('../../api/files', () => ({ moveFile: vi.fn() }))
const file = (uuid: string, folder = 'source') => ({ uuid, title: `${uuid}.pdf`, folder }) as SearchResult
const destination = { uuid: 'project-folder', title: 'Subaward' }
function setup(props: Partial<React.ComponentProps<typeof ExistingFilesDialog>> = {}) {
  const close = vi.fn(), attach = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(qc, 'invalidateQueries')
  render(<QueryClientProvider client={qc}><ExistingFilesDialog onClose={close} onAttach={attach} {...props} /></QueryClientProvider>)
  return { close, attach, invalidate }
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(searchDocuments).mockResolvedValue({ items: [file('award'), file('budget')], total: 2 })
  vi.mocked(moveFile).mockResolvedValue({ ok: true })
})

it('attaches existing UUIDs without moving them and marks attached files', async () => {
  const { attach, close } = setup({ attachedUuids: ['budget'] })
  fireEvent.click(await screen.findByRole('checkbox', { name: 'award.pdf' }))
  expect(screen.getByRole('checkbox', { name: /budget.pdf/ })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Attach 1 file' }))
  expect(attach).toHaveBeenCalledExactlyOnceWith([{ uuid: 'award', title: 'award.pdf' }])
  expect(close).toHaveBeenCalledOnce()
  expect(moveFile).not.toHaveBeenCalled()
})

it('keeps selections across searches and ignores stale search responses', async () => {
  let finish!: (result: { items: SearchResult[]; total: number }) => void
  const { attach } = setup()
  fireEvent.click(await screen.findByRole('checkbox', { name: 'award.pdf' }))
  vi.mocked(searchDocuments).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'old' } })
  await waitFor(() => expect(searchDocuments).toHaveBeenCalledWith('old', 100))
  vi.mocked(searchDocuments).mockResolvedValueOnce({ items: [file('latest')], total: 1 })
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'latest' } })
  fireEvent.click(await screen.findByRole('checkbox', { name: 'latest.pdf' }))
  await act(async () => finish({ items: [file('stale')], total: 1 }))
  expect(screen.queryByText('stale.pdf')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Attach 2 files' }))
  expect(attach.mock.calls[0][0].map((item: SearchResult) => item.uuid)).toEqual(['award', 'latest'])
})

it('retries search errors without presenting them as an empty library', async () => {
  vi.mocked(searchDocuments).mockRejectedValueOnce(new Error('Offline'))
  setup()
  fireEvent.click(await screen.findByRole('button', { name: 'Retry files' }))
  expect(await screen.findByRole('checkbox', { name: 'award.pdf' })).toBeEnabled()
})

it('previews the destination, waits for the Move click, and retries only failed files', async () => {
  vi.mocked(moveFile).mockResolvedValueOnce({ ok: true }).mockRejectedValueOnce(new Error('Permission denied'))
  const { close, invalidate } = setup({ destination })
  fireEvent.click(await screen.findByRole('checkbox', { name: 'award.pdf' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'budget.pdf' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('Subaward')
  expect(screen.getByRole('dialog')).toHaveTextContent('They leave their current folder')
  expect(moveFile).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Move 2 files here' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('budget.pdf: Permission denied')
  expect(close).not.toHaveBeenCalled()
  expect(screen.getByRole('checkbox', { name: /award.pdf/ })).toBeDisabled()
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['documents'] })
  fireEvent.click(screen.getByRole('button', { name: 'Move 1 file here' }))
  await waitFor(() => expect(close).toHaveBeenCalledOnce())
  expect(vi.mocked(moveFile).mock.calls).toEqual([['award', 'project-folder'], ['budget', 'project-folder'], ['budget', 'project-folder']])
})

it('blocks duplicate submissions and closing while a move is pending', async () => {
  let finish!: (value: { ok: boolean }) => void
  vi.mocked(moveFile).mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const { close } = setup({ destination })
  fireEvent.click(await screen.findByRole('checkbox', { name: 'award.pdf' }))
  const move = screen.getByRole('button', { name: 'Move 1 file here' })
  fireEvent.click(move); fireEvent.click(move)
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  expect(moveFile).toHaveBeenCalledOnce()
  expect(close).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: 'Close file picker' })).toBeDisabled()
  await act(async () => finish({ ok: true }))
  expect(close).toHaveBeenCalledOnce()
})

it('marks files already in the project folder as unavailable to move again', async () => {
  vi.mocked(searchDocuments).mockResolvedValueOnce({ items: [file('award', destination.uuid)], total: 1 })
  setup({ destination })
  expect(await screen.findByRole('checkbox', { name: /award.pdf/ })).toBeDisabled()
  expect(moveFile).not.toHaveBeenCalled()
})
