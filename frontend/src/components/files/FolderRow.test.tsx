import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FolderRow } from './FolderRow'
import type { Folder } from '../../types/document'

function renderRow(overrides: Partial<Folder> = {}) {
  const folder: Folder = { id: 'id-1', title: 'Proposals', uuid: 'f1', parent_id: '0', is_shared_team_root: false, ...overrides }
  return render(
    <table><tbody><FolderRow folder={folder} onClick={vi.fn()} onContextMenu={vi.fn()} /></tbody></table>,
  )
}

describe('FolderRow', () => {
  it('shows how many items the folder holds and when it last changed', () => {
    renderRow({ item_count: 12, updated_at: '2021-03-02T14:30:00' })
    expect(screen.getByText('12 items')).toBeTruthy()
    expect(screen.getByText('Mar 2, 2021')).toBeTruthy()
  })

  it('says Empty for a folder with nothing in it', () => {
    renderRow({ item_count: 0, updated_at: '2021-03-02T14:30:00' })
    expect(screen.getByText('Empty')).toBeTruthy()
  })
})
