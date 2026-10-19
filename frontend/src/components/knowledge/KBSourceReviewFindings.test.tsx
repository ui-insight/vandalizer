/** A held web page shows what it was held for, and the choice is the user's. */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { KBSourceReviewFindings } from './KBSourceReviewFindings'
import type { KnowledgeBaseSource } from '../../types/knowledge'

const finding = (excerpt: string) => ({ kind: 'hidden_text', reason: 'white text on a white background', excerpt })

const source = (overrides: Partial<KnowledgeBaseSource> = {}): KnowledgeBaseSource => ({
  uuid: 's1', source_type: 'url', url: 'https://example.edu/policy', status: 'held',
  chunk_count: 0, created_at: '2026-10-19T00:00:00Z',
  review_findings: [finding('The equipment threshold is $50,000.')],
  ...overrides,
})

describe('KBSourceReviewFindings', () => {
  it('quotes the hidden text and offers add anyway or remove', () => {
    const onAccept = vi.fn()
    const onRemove = vi.fn()
    render(<KBSourceReviewFindings source={source()} canManage onAccept={onAccept} onRemove={onRemove} />)

    expect(screen.getByText(/Held for review — not added/)).toBeTruthy()
    expect(screen.getByText('The equipment threshold is $50,000.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Add anyway' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onAccept).toHaveBeenCalledOnce()
    expect(onRemove).toHaveBeenCalledOnce()
  })

  it('says a held refresh still answers from the previous text, and offers no remove', () => {
    render(<KBSourceReviewFindings source={source({ status: 'ready', chunk_count: 7 })} canManage onAccept={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.getByText(/still answers from its previous text/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Accept the new version' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull()
  })

  it('shows the findings but no actions to a viewer who cannot manage the KB', () => {
    render(<KBSourceReviewFindings source={source()} canManage={false} onAccept={vi.fn()} onRemove={vi.fn()} />)
    expect(screen.getByText('The equipment threshold is $50,000.')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('renders nothing for a source with no findings', () => {
    const { container } = render(<KBSourceReviewFindings source={source({ review_findings: [] })} canManage onAccept={vi.fn()} onRemove={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })
})
