import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatExportActions } from './ChatExportActions'
import { exportChat } from '../../api/chat'
import { saveChatArtifact } from '../../api/artifacts'
import type { ChatMessage } from '../../types/chat'

vi.mock('../../api/chat', () => ({ exportChat: vi.fn() }))
vi.mock('../../api/artifacts', () => ({ saveChatArtifact: vi.fn() }))
const messages: ChatMessage[] = [
  { role: 'user', content: 'Review the award' },
  { role: 'assistant', content: 'Stale text', segments: [{ kind: 'text', content: 'The award is $10.' }], interruption: 'stopped', unsupported_figures: ['$10'] },
]

beforeEach(() => {
  vi.mocked(exportChat).mockReset().mockResolvedValue(new Blob(['file']))
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } })
})

describe('shared chat export actions', () => {
  it('saves only the selected bubble as a private artifact and reuses the retry identity', async () => {
    vi.mocked(saveChatArtifact).mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce({ uuid: 'artifact1' } as Awaited<ReturnType<typeof saveChatArtifact>>)
    render(<ChatExportActions messages={[messages[1]]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export message' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Save transcript as page' }))
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Export message' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Save transcript as page' }))
    expect(await screen.findByRole('link', { name: 'Open saved page' })).toHaveAttribute('href', '/artifacts/artifact1')
    const calls = vi.mocked(saveChatArtifact).mock.calls
    expect(calls[0][0]).toHaveLength(1)
    expect(calls[0][0][0].content).toBe('The award is $10.')
    expect(calls[0][1]).toBe(calls[1][1])
  })
  it.each([['HTML transcript', 'html'], ['Word (.docx)', 'docx'], ['Excel (.xlsx)', 'xlsx']])('downloads %s for only the selected bubble', async (label, format) => {
    render(<ChatExportActions messages={[messages[1]]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export message' }))
    fireEvent.click(screen.getByRole('menuitem', { name: label }))
    await waitFor(() => expect(exportChat).toHaveBeenCalledOnce())
    expect(exportChat).toHaveBeenCalledWith(format, [{ role: 'assistant', content: 'The award is $10.', tools: [], evidence: expect.stringContaining('partial output') }])
    expect(vi.mocked(exportChat).mock.calls[0][1][0].evidence).toContain('Unconfirmed figures: $10')
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })

  it('exports and copies the full conversation in order', async () => {
    render(<ChatExportActions messages={messages} scope="conversation" />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy conversation' }))
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringMatching(/User:\nReview the award[\s\S]*Assistant:\nThe award is \$10\./)))
    fireEvent.click(screen.getByRole('button', { name: 'Export conversation' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Excel (.xlsx)' }))
    await waitFor(() => expect(exportChat).toHaveBeenCalledWith('xlsx', [expect.objectContaining({ content: 'Review the award' }), expect.objectContaining({ content: 'The award is $10.' })]))
  })

  it('supports keyboard navigation and Escape restores focus', () => {
    render(<ChatExportActions messages={messages} />)
    const trigger = screen.getByRole('button', { name: 'Export message' })
    fireEvent.click(trigger)
    expect(screen.getByRole('menuitem', { name: 'HTML transcript' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' })
    expect(screen.getByRole('menuitem', { name: 'Word (.docx)' })).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('prevents duplicate requests while busy and permits retry after an error', async () => {
    let reject!: (reason: Error) => void
    vi.mocked(exportChat).mockReturnValueOnce(new Promise((_, fail) => { reject = fail }))
    render(<ChatExportActions messages={messages} />)
    fireEvent.click(screen.getByRole('button', { name: 'Export message' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'HTML transcript' }))
    expect(screen.getByRole('button', { name: 'Export message' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Preparing export')
    await act(async () => reject(new Error('Export is too large.')))
    expect(screen.getByRole('alert')).toHaveTextContent('Export is too large.')
    expect(screen.getByRole('button', { name: 'Export message' })).toBeEnabled()
  })

  it('disables copy and export while a conversation is streaming', () => {
    render(<ChatExportActions messages={messages} scope="conversation" disabled />)
    expect(screen.getByRole('button', { name: 'Copy conversation' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Export conversation' })).toBeDisabled()
  })
})
