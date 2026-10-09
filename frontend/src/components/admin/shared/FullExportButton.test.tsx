import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { FullExportButton } from './FullExportButton'
import { downloadCSV } from './format'
vi.mock('./format', () => ({ downloadCSV: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
const props = { scope: 'all', filename: 'all.csv', headers: ['ID'], getKey: (item: number) => String(item), row: (item: number) => [item], metadata: { Timezone: 'UTC' } }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
it('reads every page before filtering and downloading, with filter metadata', async () => {
  const fetchPage = vi.fn().mockResolvedValueOnce({ items: [1, 2], total: 3 }).mockResolvedValueOnce({ items: [3], total: 3 })
  render(<FullExportButton {...props} fetchPage={fetchPage} select={items => items.filter(n => n > 1).reverse()} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  await screen.findByText(/Downloaded 2 matching records/)
  expect(fetchPage.mock.calls).toEqual([[0], [2]])
  expect(downloadCSV).toHaveBeenCalledWith('all.csv', ['ID', 'Timezone'], [[3, 'UTC'], [2, 'UTC']])
})
it.each([
  ['incomplete page', { items: [], total: 3 }],
  ['changed total', { items: [3], total: 4 }],
  ['duplicate record', { items: [2], total: 3 }],
])('never downloads a partial file after %s', async (_, second) => {
  const fetchPage = vi.fn().mockResolvedValueOnce({ items: [1, 2], total: 3 }).mockResolvedValueOnce(second)
  render(<FullExportButton {...props} fetchPage={fetchPage} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  await screen.findByRole('alert')
  expect(downloadCSV).not.toHaveBeenCalled()
  expect(screen.getByText('Export all matching records')).toBeEnabled()
})
it('preserves an actionable error and supports a complete retry after service failure', async () => {
  const fetchPage = vi.fn().mockRejectedValueOnce(new Error('Service unavailable')).mockResolvedValueOnce({ items: [1], total: 1 })
  render(<FullExportButton {...props} fetchPage={fetchPage} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable')
  expect(downloadCSV).not.toHaveBeenCalled()
  fireEvent.click(screen.getByText('Export all matching records'))
  await screen.findByText(/Downloaded 1/)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})
it('ignores double clicks and a cancelled late response while allowing a new export', async () => {
  const first = deferred<{ items: number[]; total: number }>()
  const fetchPage = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValueOnce({ items: [2], total: 1 })
  render(<FullExportButton {...props} fetchPage={fetchPage} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  fireEvent.click(screen.getByText('Export all matching records'))
  expect(fetchPage).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByText('Cancel export'))
  fireEvent.click(screen.getByText('Export all matching records'))
  await screen.findByText(/Downloaded 1/)
  await act(async () => first.resolve({ items: [1], total: 1 }))
  expect(downloadCSV).toHaveBeenCalledTimes(1)
  expect(downloadCSV).toHaveBeenLastCalledWith('all.csv', ['ID', 'Timezone'], [[2, 'UTC']])
})
it.each(['scope', 'unmount'])('discards late responses after %s changes', async change => {
  const late = deferred<{ items: number[]; total: number }>()
  const view = render(<FullExportButton {...props} fetchPage={() => late.promise} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  if (change === 'scope') view.rerender(<FullExportButton {...props} scope="new-filter" fetchPage={() => late.promise} />)
  else view.unmount()
  await act(async () => late.resolve({ items: [1], total: 1 }))
  expect(downloadCSV).not.toHaveBeenCalled()
})
it('can export an empty matching result without fetching forever', async () => {
  render(<FullExportButton {...props} fetchPage={async () => ({ items: [], total: 0 })} />)
  fireEvent.click(screen.getByText('Export all matching records'))
  await waitFor(() => expect(downloadCSV).toHaveBeenCalledWith('all.csv', ['ID', 'Timezone'], []))
})
