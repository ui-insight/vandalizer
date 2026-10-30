import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { UploadProgress } from './UploadProgress'

describe('UploadProgress', () => {
  it('announces state changes without announcing every percentage update', () => {
    const item = { id: 1, fileName: 'doc.pdf', progress: 10, done: false }
    const { rerender } = render(<UploadProgress uploads={[item]} onDismiss={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('doc.pdf: Uploading')
    rerender(<UploadProgress uploads={[{ ...item, progress: 50 }]} onDismiss={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('doc.pdf: Uploading')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
    expect(screen.getByRole('status')).not.toContainElement(screen.getByRole('progressbar'))
    rerender(<UploadProgress uploads={[{ ...item, progress: 100, done: true }]} onDismiss={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('doc.pdf: Upload complete')
  })

  it('renders nothing when there are no uploads', () => {
    const { container } = render(<UploadProgress uploads={[]} onDismiss={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the error message and a dismiss button for failed uploads', () => {
    const onDismiss = vi.fn()
    render(
      <UploadProgress
        uploads={[{ id: 7, fileName: 'photo.png', progress: 0, done: true, error: 'Unsupported file type' }]}
        onDismiss={onDismiss}
      />,
    )

    expect(screen.getByText('Unsupported file type')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /dismiss failed upload photo\.png/i }))
    expect(onDismiss).toHaveBeenCalledWith(7)
  })

  it('does not show a dismiss button for successful uploads', () => {
    render(
      <UploadProgress
        uploads={[{ id: 1, fileName: 'doc.pdf', progress: 100, done: true }]}
        onDismiss={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
