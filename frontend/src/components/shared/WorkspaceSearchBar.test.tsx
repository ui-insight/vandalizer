import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { WorkspaceSearchBar } from './WorkspaceSearchBar'

describe('WorkspaceSearchBar', () => {
  it('is a labelled search box that reports what is typed', () => {
    const onChange = vi.fn()
    render(<WorkspaceSearchBar value="" onChange={onChange} label="Search library" placeholder="Search library…" />)
    const box = screen.getByRole('searchbox', { name: 'Search library' })
    expect(box).toHaveAttribute('placeholder', 'Search library…')
    fireEvent.change(box, { target: { value: 'budget' } })
    expect(onChange).toHaveBeenCalledWith('budget')
    // Nothing to clear yet.
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
  })

  it('clears with the button or Escape once something is typed', () => {
    const onChange = vi.fn()
    render(<WorkspaceSearchBar value="budget" onChange={onChange} label="Search files and content" placeholder="Search files and content…" />)
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Escape' })
    expect(onChange.mock.calls).toEqual([[''], ['']])
  })

  it('leaves Escape alone when the box is empty', () => {
    const onChange = vi.fn()
    const onKeyDown = vi.fn()
    render(<div onKeyDown={onKeyDown}><WorkspaceSearchBar value="" onChange={onChange} label="Search library" placeholder="…" /></div>)
    fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Escape' })
    expect(onChange).not.toHaveBeenCalled()
    expect(onKeyDown).toHaveBeenCalled()
  })
})
