import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RenameDialog } from './RenameDialog'
import { CreateFolderDialog } from './CreateFolderDialog'
import { MoveFileDialog } from './MoveFileDialog'
import { listAllFolders } from '../../api/folders'
vi.mock('../../api/folders', () => ({ listAllFolders: vi.fn() }))

describe('file mutation recovery', () => {
  for (const operation of ['rename', 'create']) {
    it(`preserves a failed ${operation} draft and prevents duplicate pending submissions`, async () => {
      let resolve!: () => void
      const submit = vi.fn().mockRejectedValueOnce(new Error('Service unavailable')).mockReturnValueOnce(new Promise<void>(r => { resolve = r }))
      const close = vi.fn()
      render(operation === 'rename' ? <RenameDialog currentName="Original.txt" onSubmit={submit} onClose={close} /> : <CreateFolderDialog onSubmit={submit} onClose={close} />)
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'Preserved name' } })
      fireEvent.submit(input.closest('form')!)
      expect(await screen.findByRole('alert')).toHaveTextContent('Your entry is preserved')
      expect(input).toHaveValue('Preserved name')
      fireEvent.submit(input.closest('form')!); fireEvent.submit(input.closest('form')!)
      fireEvent.keyDown(screen.getByRole('dialog').parentElement!, { key: 'Escape' })
      expect(submit).toHaveBeenCalledTimes(2)
      expect(close).not.toHaveBeenCalled()
      await act(async () => resolve())
    })
  }
  it('retries folder loading and keeps a failed destination available', async () => {
    vi.mocked(listAllFolders).mockRejectedValueOnce(new Error('Offline')).mockResolvedValue([{ uuid: 'destination', title: 'Archive', path: 'Archive', parent_id: '0', team_id: null, is_shared_team_root: false }])
    const submit = vi.fn().mockRejectedValueOnce(new Error('Move unavailable')).mockResolvedValue(undefined)
    render(<MoveFileDialog fileNames={['Original.txt']} currentFolderId={null} onSubmit={submit} onClose={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Retry folders' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Archive' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Move unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Archive' }))
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2))
    expect(submit.mock.calls).toEqual([['destination'], ['destination']])
  })
})
