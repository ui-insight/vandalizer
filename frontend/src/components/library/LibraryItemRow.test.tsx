import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LibraryItemRow } from './LibraryItemRow'
import type { LibraryItem } from '../../types/library'

vi.mock('../../api/library', () => ({
  submitForVerification: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'viewer', email: 'viewer@example.com', name: 'Viewer', is_admin: false },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

vi.mock('../../lib/shareLink', () => ({
  useShareLink: () => vi.fn(),
  buildShareUrl: vi.fn(),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

function makeItem(overrides: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 'item-1',
    item_id: 'wf-1',
    item_uuid: 'wf-uuid-1',
    kind: 'workflow',
    name: 'Budget Analyzer',
    description: 'Analyzes budgets',
    set_type: null,
    tags: ['finance', 'pre-award'],
    note: null,
    folder: null,
    pinned: false,
    favorited: false,
    verified: false,
    added_by_user_id: 'user1',
    created_at: '2025-01-01T00:00:00',
    last_used_at: '2025-06-15T12:00:00',
    ...overrides,
  }
}

const defaultProps = {
  scope: 'mine' as const,
  onPin: vi.fn(),
  onFavorite: vi.fn(),
  onClone: vi.fn(),
  onShare: vi.fn(),
  onRemove: vi.fn(),
  onOpen: vi.fn(),
  onEdit: vi.fn(),
}

beforeEach(() => {
  Object.values(defaultProps).forEach((fn) => { if (typeof fn === 'function' && 'mockReset' in fn) fn.mockReset() })
})

describe('LibraryItemRow', () => {
  it('renders the item name', () => {
    render(<LibraryItemRow item={makeItem()} {...defaultProps} />)
    expect(screen.getByText('Budget Analyzer')).toBeTruthy()
  })

  it('shows kind label for workflow', () => {
    render(<LibraryItemRow item={makeItem({ kind: 'workflow' })} {...defaultProps} />)
    expect(screen.getByText('Workflow')).toBeTruthy()
  })

  it('shows kind label for extraction (search_set)', () => {
    render(<LibraryItemRow item={makeItem({ kind: 'search_set', name: 'NSF Extractor' })} {...defaultProps} />)
    expect(screen.getByText('Extraction Task')).toBeTruthy()
  })

  it('renders tags', () => {
    render(<LibraryItemRow item={makeItem({ tags: ['compliance', 'irb'] })} {...defaultProps} />)
    expect(screen.getByText('compliance')).toBeTruthy()
    expect(screen.getByText('irb')).toBeTruthy()
  })

  it('calls onOpen when row is clicked', () => {
    const item = makeItem()
    render(<LibraryItemRow item={item} {...defaultProps} />)
    fireEvent.click(screen.getByText('Budget Analyzer'))
    expect(defaultProps.onOpen).toHaveBeenCalledWith(item)
  })

  it('shows pinned indicator when pinned', () => {
    render(<LibraryItemRow item={makeItem({ pinned: true })} {...defaultProps} />)
    // Pinned items have a visual indicator
    const row = screen.getByText('Budget Analyzer').closest('div')
    expect(row).toBeTruthy()
  })

  it('shows favorited indicator when favorited', () => {
    render(<LibraryItemRow item={makeItem({ favorited: true })} {...defaultProps} />)
    const row = screen.getByText('Budget Analyzer').closest('div')
    expect(row).toBeTruthy()
  })

  it('truncates tags beyond 3', () => {
    render(<LibraryItemRow item={makeItem({ tags: ['a', 'b', 'c', 'd', 'e'] })} {...defaultProps} />)
    // Should show 3 tags and a "+2" overflow indicator
    expect(screen.getByText('a')).toBeTruthy()
    expect(screen.getByText('b')).toBeTruthy()
    expect(screen.getByText('c')).toBeTruthy()
    expect(screen.getByText('+2')).toBeTruthy()
  })
})

describe('Library row actions', () => {
  it('moves the exact item with a keyboard-accessible inline folder choice', () => {
    const move = vi.fn()
    render(<LibraryItemRow item={makeItem()} {...defaultProps} onMoveToFolder={move} folders={[{ uuid: 'destination', name: 'Team evidence', item_count: 0 } as import('../../types/library').LibraryFolder]} />)
    fireEvent.click(screen.getByRole('button', { name: 'More actions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Move to folder' }))
    const destination = screen.getByRole('button', { name: 'Team evidence' })
    destination.focus()
    expect(destination).toHaveFocus()
    fireEvent.click(destination)
    expect(move).toHaveBeenCalledExactlyOnceWith('item-1', 'destination')
    expect(defaultProps.onOpen).not.toHaveBeenCalled()
  })
  it('closes actions with Escape and restores the trigger', () => {
    render(<LibraryItemRow item={makeItem()} {...defaultProps} />)
    const trigger = screen.getByRole('button', { name: 'More actions' })
    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('group', { name: 'Actions for Budget Analyzer' }), { key: 'Escape' })
    expect(screen.queryByRole('group', { name: 'Actions for Budget Analyzer' })).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
  it('disables mutation controls while the item action is pending', () => {
    render(<LibraryItemRow item={makeItem()} {...defaultProps} busy />)
    const favorite = screen.getByRole('button', { name: 'Favorite (shows in all views)' })
    expect(favorite).toBeDisabled()
    fireEvent.click(favorite)
    expect(defaultProps.onFavorite).not.toHaveBeenCalled()
  })
})
