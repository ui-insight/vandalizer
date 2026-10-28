import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ActivityActions } from './ActivityActions'

describe('activity actions menu', () => {
  it('supports keyboard navigation and Escape restores trigger focus', () => {
    render(<ActivityActions title="Budget review" disabled={false} onRename={vi.fn()} onDelete={vi.fn()} />)
    const trigger = screen.getByRole('button', { name: 'Actions for Budget review' })
    fireEvent.click(trigger)
    fireEvent.scroll(window)
    expect(screen.getByRole('menu')).toBeInTheDocument()
    const rename = screen.getByRole('menuitem', { name: 'Rename chat: Budget review' })
    expect(rename).toHaveFocus()
    fireEvent.keyDown(rename, { key: 'ArrowDown' })
    const remove = screen.getByRole('menuitem', { name: 'Delete activity: Budget review' })
    expect(remove).toHaveFocus()
    fireEvent.keyDown(remove, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('dismisses on an outside pointer and invokes delete only from the explicit action', () => {
    const remove = vi.fn()
    render(<ActivityActions title="Run" disabled={false} onDelete={remove} />)
    const trigger = screen.getByRole('button', { name: 'Actions for Run' })
    fireEvent.click(trigger)
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(remove).not.toHaveBeenCalled()
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete activity: Run' }))
    expect(remove).toHaveBeenCalledOnce()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
