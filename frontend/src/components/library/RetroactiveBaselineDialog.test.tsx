import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { RetroactiveBaselineDialog } from './RetroactiveBaselineDialog'
import { pinRetroactiveBaseline } from '../../api/library'
import type { CatalogCoverageItem } from '../../types/library'
vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('../../api/library', () => ({ pinRetroactiveBaseline: vi.fn() }))
const item = { item_kind: 'workflow', item_id: 'wf-1', name: 'Review proposal' } as CatalogCoverageItem
beforeEach(() => vi.clearAllMocks())
function setup() {
  const onClose = vi.fn(), onSaved = vi.fn()
  render(<RetroactiveBaselineDialog item={item} onClose={onClose} onSaved={onSaved} />)
  fireEvent.click(screen.getByRole('button', { name: 'Add regression input' }))
  fireEvent.change(screen.getByLabelText('Input 1'), { target: { value: 'Review deadline evidence' } })
  return { onClose, onSaved }
}
it('retains failed input and prevents dismissal or duplicate writes while pending', async () => {
  let reject!: (reason: Error) => void
  vi.mocked(pinRetroactiveBaseline).mockImplementationOnce(() => new Promise((_, no) => { reject = no }))
  const { onClose } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Pin baseline' }))
  fireEvent.keyDown(document, { key: 'Escape' })
  fireEvent.click(screen.getByRole('button', { name: 'Pinning…' }))
  expect(onClose).not.toHaveBeenCalled()
  expect(pinRetroactiveBaseline).toHaveBeenCalledOnce()
  await act(async () => reject(new Error('Temporarily unavailable')))
  expect(screen.getByRole('alert')).toHaveTextContent('Temporarily unavailable')
  expect(screen.getByLabelText('Input 1')).toHaveValue('Review deadline evidence')
  expect(screen.getByRole('button', { name: 'Pin baseline' })).toBeEnabled()
})
it('treats a caveated pin as accepted and refreshes on Escape without another write', async () => {
  vi.mocked(pinRetroactiveBaseline).mockResolvedValue({ ok: true, pinned_at: '', live_passes_baseline: false, live_score: 60, pinned_score: 90 })
  const { onSaved, onClose } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Pin baseline' }))
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Baseline pinned with caveat'))
  fireEvent.click(screen.getByRole('button', { name: 'Pin baseline' }))
  expect(pinRetroactiveBaseline).toHaveBeenCalledOnce()
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(onSaved).toHaveBeenCalledOnce()
  expect(onClose).not.toHaveBeenCalled()
})
