import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ItemPickerModal } from './ItemPickerModal'
import type { LibraryItem } from '../../types/library'
import React from 'react'

vi.mock('focus-trap-react', () => ({
  FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: '1', user_id: 'viewer', email: 'viewer@example.com', name: 'Viewer', is_admin: false, current_team: null },
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  }),
}))

const makeItem = (overrides: Partial<LibraryItem>): LibraryItem => ({
  id: 'li-1',
  item_id: 'wf-1',
  item_uuid: null,
  kind: 'workflow',
  name: 'Workflow',
  description: null,
  set_type: null,
  tags: [],
  note: null,
  folder: null,
  pinned: false,
  favorited: false,
  verified: false,
  added_by_user_id: 'viewer',
  created_at: null,
  last_used_at: null,
  ...overrides,
})

const listItems = vi.fn()

vi.mock('../../api/library', () => ({
  listLibraries: () => Promise.resolve([
    { id: 'lib-1', scope: 'personal', title: 'My Library', description: null, owner_user_id: 'viewer', team_id: null, item_count: 3, created_at: null, updated_at: null },
  ]),
  listItems: (...args: unknown[]) => listItems(...args),
  listVerifiedItems: vi.fn().mockResolvedValue({ items: [] }),
}))

describe('ItemPickerModal pin/favorite ordering', () => {
  beforeEach(() => {
    listItems.mockReset()
  })

  it('sorts pinned first, then favorited, then the rest, with icons', async () => {
    listItems.mockResolvedValue([
      makeItem({ id: 'li-plain', item_id: 'wf-plain', name: 'Plain Workflow' }),
      makeItem({ id: 'li-fav', item_id: 'wf-fav', name: 'Favorited Workflow', favorited: true }),
      makeItem({ id: 'li-pin', item_id: 'wf-pin', name: 'Pinned Workflow', pinned: true }),
    ])

    render(<ItemPickerModal kind="workflow" onSelect={vi.fn()} onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Pinned Workflow')).toBeTruthy())

    const dialog = screen.getByRole('dialog')
    const names = Array.from(dialog.querySelectorAll('button'))
      .map(b => b.textContent ?? '')
      .filter(t => t.includes('Workflow') && !t.includes('Search'))
    expect(names[0]).toContain('Pinned Workflow')
    expect(names[1]).toContain('Favorited Workflow')
    expect(names[2]).toContain('Plain Workflow')

    expect(screen.getByLabelText('Pinned')).toBeTruthy()
    expect(screen.getByLabelText('Favorited')).toBeTruthy()
  })

  it('keeps original order among unpinned, unfavorited items', async () => {
    listItems.mockResolvedValue([
      makeItem({ id: 'li-a', item_id: 'wf-a', name: 'Alpha Workflow' }),
      makeItem({ id: 'li-b', item_id: 'wf-b', name: 'Beta Workflow' }),
      makeItem({ id: 'li-p', item_id: 'wf-p', name: 'Pinned Workflow', pinned: true }),
    ])

    render(<ItemPickerModal kind="workflow" onSelect={vi.fn()} onClose={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('Pinned Workflow')).toBeTruthy())

    const dialog = screen.getByRole('dialog')
    const names = Array.from(dialog.querySelectorAll('button'))
      .map(b => b.textContent ?? '')
      .filter(t => t.includes('Workflow') && !t.includes('Search'))
    expect(names).toEqual([
      expect.stringContaining('Pinned Workflow'),
      expect.stringContaining('Alpha Workflow'),
      expect.stringContaining('Beta Workflow'),
    ])
  })
})
