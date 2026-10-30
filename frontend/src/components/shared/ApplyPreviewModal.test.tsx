import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { ApplyPreviewModal } from './ApplyPreviewModal'
beforeAll(() => { HTMLElement.prototype.scrollIntoView = vi.fn() })
vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => children }))
const preview = { total: 1, will_change: 1, improvements: 0, regressions: 1, significant_regressions: 1, net_delta: -0.2, noise_sigma: 0.01, items: [] }
describe('apply review', () => {
  it('requires a new acknowledgment each time the review opens', () => {
    const props = { preview, itemNoun: 'query', itemNounPlural: 'queries', onConfirm: vi.fn(), onCancel: vi.fn(), applying: false }
    const { rerender } = render(<ApplyPreviewModal {...props} open />)
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled()
    rerender(<ApplyPreviewModal {...props} open={false} />)
    rerender(<ApplyPreviewModal {...props} open />)
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
  })
  it('keeps a pending operation open and displays failure inside the review', () => {
    const onCancel = vi.fn()
    const props = { preview, itemNoun: 'query', itemNounPlural: 'queries', onConfirm: vi.fn(), onCancel }
    const { rerender } = render(<ApplyPreviewModal {...props} open applying />)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog'))
    expect(onCancel).not.toHaveBeenCalled()
    rerender(<ApplyPreviewModal {...props} open applying={false} error="Server unavailable" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Server unavailable')
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog'))
    expect(onCancel).toHaveBeenCalledTimes(2)
  })
})
