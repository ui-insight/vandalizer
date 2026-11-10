import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FullViewButton, useFullView } from './viewerFullView'

// Support ticket: expand opened PDFs in a new tab and downloaded .md, .docx
// and .xlsx files. It now shows the file full screen in the same tab.
function Viewer() {
  const fullView = useFullView()
  const [page, setPage] = useState(1)
  return (
    <div {...fullView.rootProps} data-testid="viewer" style={{ height: '100%', ...fullView.style }}>
      <FullViewButton expanded={fullView.expanded} onOpen={fullView.open} onClose={fullView.close} style={{}} />
      <button type="button" onClick={() => setPage(p => p + 1)}>Next page</button>
      <span>Page {page}</span>
      <input aria-label="Find in document" />
    </div>
  )
}

function Workspace() {
  return <div>
    <nav data-testid="nav"><button>Files</button></nav>
    <main><aside data-testid="chat">Chat</aside><section><Viewer /></section></main>
  </div>
}

describe('viewer full view', () => {
  it('fills the window in the same tab and returns to the same place', () => {
    render(<Workspace />)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    const expand = screen.getByRole('button', { name: 'Full view' })
    expand.focus()
    fireEvent.click(expand)

    const dialog = screen.getByRole('dialog', { name: 'Full view of the document' })
    expect(dialog.style.position).toBe('fixed')
    expect(screen.getByTestId('nav').inert).toBe(true)
    expect(screen.getByTestId('chat').inert).toBe(true)
    // The same button, now labelled, keeps focus.
    const exit = screen.getByRole('button', { name: 'Exit full view' })
    expect(exit).toBe(expand)
    expect(exit).toHaveFocus()

    fireEvent.click(exit)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByTestId('viewer').style.position).toBe('')
    expect(screen.getByTestId('nav').inert).not.toBe(true)
    expect(screen.getByTestId('chat').inert).not.toBe(true)
    expect(screen.getByText('Page 2')).toBeTruthy()
  })

  it('closes with Escape, but not while typing in the find field', () => {
    render(<Workspace />)
    fireEvent.click(screen.getByRole('button', { name: 'Full view' }))
    fireEvent.keyDown(screen.getByLabelText('Find in document'), { key: 'Escape' })
    expect(screen.getByRole('dialog')).toBeTruthy()
    fireEvent.keyDown(screen.getByRole('button', { name: 'Next page' }), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
