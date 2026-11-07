import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ActivityActions } from './ActivityActions'

describe('activity actions menu', () => {
  it.each(['Rename chat', 'Delete activity'])('allows %s after a pointer blur without a new focus target', (action) => {
    const rename = vi.fn()
    const remove = vi.fn()
    render(<ActivityActions title="Budget review" disabled={false} onRename={rename} onDelete={remove} />)
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Budget review' }))
    const item = screen.getByRole('menuitem', { name: `${action}: Budget review` })
    fireEvent.pointerDown(item)
    fireEvent.mouseDown(item)
    // Safari does not focus buttons on pointer activation. The currently
    // focused item blurs to the document before the selected item's click.
    fireEvent.blur(document.activeElement!, { relatedTarget: null })
    fireEvent.mouseUp(item)
    fireEvent.click(screen.getByRole('menuitem', { name: `${action}: Budget review` }))
    expect(action === 'Rename chat' ? rename : remove).toHaveBeenCalledOnce()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('dismisses when keyboard focus moves outside the actions', () => {
    render(<><ActivityActions title="Run" disabled={false} onDelete={vi.fn()} /><button>Next</button></>)
    fireEvent.click(screen.getByRole('button', { name: 'Actions for Run' }))
    fireEvent.blur(document.activeElement!, { relatedTarget: screen.getByRole('button', { name: 'Next' }) })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

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
