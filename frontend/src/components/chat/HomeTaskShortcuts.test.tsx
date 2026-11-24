import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { HomeTaskShortcuts } from './HomeTaskShortcuts'

const document = { uuid: 'doc-budget', title: 'Budget FY27.xlsx' }

describe('home task preparation', () => {
  it('requires an explicit source and prepares a request without running it', () => {
    const prepare = vi.fn()
    render(<HomeTaskShortcuts documents={[document]} onPrepare={prepare} />)
    fireEvent.click(screen.getByRole('button', { name: 'Check a budget' }))
    expect(screen.getByRole('button', { name: 'Prepare request' })).toBeDisabled()
    expect(prepare).not.toHaveBeenCalled()
    fireEvent.change(screen.getByRole('combobox', { name: 'Recent readable documents' }), { target: { value: document.uuid } })
    fireEvent.click(screen.getByRole('button', { name: 'Prepare request' }))
    expect(prepare).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('Show the arithmetic'), document)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps a task available when there are no recent readable documents', () => {
    const prepare = vi.fn(), choose = vi.fn()
    render(<HomeTaskShortcuts documents={[]} onPrepare={prepare} onChooseDocuments={choose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Review a solicitation' }))
    expect(screen.getByText(/No recent readable documents/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Choose a source in Files' }))
    expect(prepare).toHaveBeenCalledWith(expect.stringContaining('eligibility'), undefined)
    expect(choose).toHaveBeenCalledOnce()
  })

  it('cancels without changing the request or sources', () => {
    const prepare = vi.fn()
    render(<HomeTaskShortcuts documents={[document]} onPrepare={prepare} />)
    fireEvent.click(screen.getByRole('button', { name: 'Summarize an award' }))
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(prepare).not.toHaveBeenCalled()
  })
})

describe('keyboard (#1014 item 53)', () => {
  it('returns focus to the task button when its dialog closes with Escape', async () => {
    render(<HomeTaskShortcuts documents={[{ uuid: 'd1', title: 'Award notice.pdf' }]} onPrepare={vi.fn()} />)
    const opener = screen.getByRole('button', { name: 'Check a budget' })
    opener.focus()
    fireEvent.click(opener)
    const dialog = await screen.findByRole('dialog', { name: 'Check a budget' })
    fireEvent.keyDown(dialog, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(opener).toHaveFocus())
  })
})
