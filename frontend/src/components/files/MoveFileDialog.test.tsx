import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MoveFileDialog } from './MoveFileDialog'
import { listAllFolders, type FolderSummary } from '../../api/folders'

vi.mock('../../api/folders', () => ({
  listAllFolders: vi.fn(),
}))

const FOLDERS: FolderSummary[] = [
  { uuid: 'granted', title: 'GRANTED', path: 'GRANTED', parent_id: '0', is_shared_team_root: false, team_id: null },
  { uuid: 'proposals', title: 'Proposals', path: 'Proposals', parent_id: '0', is_shared_team_root: false, team_id: null },
  { uuid: 'sub', title: 'Archive', path: 'Proposals / Archive', parent_id: 'proposals', is_shared_team_root: false, team_id: null },
  { uuid: 'team-a', title: 'Team Docs', path: 'Team Docs', parent_id: '0', is_shared_team_root: true, team_id: 't1' },
]

describe('MoveFileDialog', () => {
  beforeEach(() => {
    vi.mocked(listAllFolders).mockResolvedValue(FOLDERS)
  })

  it('lists personal destinations plus Top level for a file in a personal folder', async () => {
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId="granted"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(await screen.findByText('Top level')).toBeInTheDocument()
    expect(screen.getByText('Proposals')).toBeInTheDocument()
    expect(screen.getByText('Proposals / Archive')).toBeInTheDocument()
    // Current folder and cross-boundary team folders are not offered
    expect(screen.queryByText('GRANTED')).not.toBeInTheDocument()
    expect(screen.queryByText('Team Docs')).not.toBeInTheDocument()
  })

  it('hides Top level for a file already at the top level', async () => {
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId={null}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(await screen.findByText('GRANTED')).toBeInTheDocument()
    expect(screen.queryByText('Top level')).not.toBeInTheDocument()
  })

  it('only offers same-team folders for a file in a team folder', async () => {
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId="team-a"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    // No same-team siblings exist, and personal folders/top level are not valid
    expect(await screen.findByText('No other folders available.')).toBeInTheDocument()
    expect(screen.queryByText('Top level')).not.toBeInTheDocument()
    expect(screen.queryByText('Proposals')).not.toBeInTheDocument()
  })

  it('submits the chosen destination uuid', async () => {
    const onSubmit = vi.fn()
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId="granted"
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    )
    fireEvent.click(await screen.findByText('Proposals'))
    expect(onSubmit).toHaveBeenCalledWith('proposals')
  })

  it('submits "0" when moving to the top level', async () => {
    const onSubmit = vi.fn()
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId="granted"
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />,
    )
    fireEvent.click(await screen.findByText('Top level'))
    expect(onSubmit).toHaveBeenCalledWith('0')
  })

  it('shows a bulk heading when moving multiple files', async () => {
    render(
      <MoveFileDialog
        fileNames={['a.pdf', 'b.pdf', 'c.pdf']}
        currentFolderId="granted"
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />,
    )
    expect(await screen.findByText('Move files')).toBeInTheDocument()
    expect(screen.getByText('3 files')).toBeInTheDocument()
  })

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn()
    render(
      <MoveFileDialog
        fileNames={['proposal.pdf']}
        currentFolderId="granted"
        onSubmit={vi.fn()}
        onClose={onClose}
      />,
    )
    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })
})
