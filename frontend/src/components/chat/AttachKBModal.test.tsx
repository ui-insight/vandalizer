import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import React from 'react'
import { AttachKBModal } from './AttachKBModal'
import { listKnowledgeBasesV2 } from '../../api/knowledge'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('../../api/knowledge', () => ({ listKnowledgeBasesV2: vi.fn() }))

const mockList = vi.mocked(listKnowledgeBasesV2)

function kb(uuid: string, title: string, status = 'ready') {
  return { uuid, title, status, description: null, total_sources: 1, total_chunks: 4 }
}

beforeEach(() => {
  mockList.mockReset()
  mockList.mockResolvedValue({
    items: [
      kb('kb-1', 'Export Control'),
      kb('kb-2', 'Uniform Guidance'),
      kb('kb-3', 'Broken bookmark', 'unavailable'),
    ],
    total: 3,
  } as never)
})

describe('AttachKBModal', () => {
  it('attaches several knowledge bases at once', async () => {
    const onAttach = vi.fn()
    const onClose = vi.fn()
    render(
      <AttachKBModal attachedUuids={[]} maxAttached={3} onAttach={onAttach} onClose={onClose} />,
    )

    fireEvent.click(await screen.findByRole('button', { name: /Export Control/ }))
    fireEvent.click(screen.getByRole('button', { name: /Uniform Guidance/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Attach 2' }))

    expect(onAttach).toHaveBeenCalledWith([
      { uuid: 'kb-1', title: 'Export Control' },
      { uuid: 'kb-2', title: 'Uniform Guidance' },
    ])
    expect(onClose).toHaveBeenCalled()
  })

  it('hides a broken bookmark, which has no KB behind it to search', async () => {
    render(
      <AttachKBModal attachedUuids={[]} maxAttached={3} onAttach={vi.fn()} onClose={vi.fn()} />,
    )

    await screen.findByRole('button', { name: /Export Control/ })
    expect(screen.queryByText('Broken bookmark')).not.toBeInTheDocument()
  })

  it('will not exceed the attachment limit', async () => {
    render(
      <AttachKBModal
        attachedUuids={['kb-9', 'kb-8']}
        maxAttached={3}
        onAttach={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    // One slot left: taking it disables the other option.
    fireEvent.click(await screen.findByRole('button', { name: /Export Control/ }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Uniform Guidance/ })).toBeDisabled(),
    )
    expect(screen.getByText(/reached the limit/i)).toBeInTheDocument()
  })

  it('marks a knowledge base already attached to the chat', async () => {
    render(
      <AttachKBModal
        attachedUuids={['kb-1']}
        maxAttached={3}
        onAttach={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    const row = await screen.findByRole('button', { name: /Export Control/ })
    expect(row).toBeDisabled()
    expect(row.textContent).toMatch(/attached/)
  })
})
