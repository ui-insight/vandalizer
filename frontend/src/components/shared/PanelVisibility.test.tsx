import { useEffect, useState } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RetainedPanel } from './PanelVisibility'
import { FocusTrap } from './PanelFocusTrap'
import { createPortal } from './panelPortal'

describe('retained workspace panels', () => {
  it('mounts on first visit and preserves drafts and pending results while hidden', async () => {
    const unmounted = vi.fn()
    let finish!: (value: string) => void
    const pending = new Promise<string>(resolve => { finish = resolve })
    function Content() {
      const [draft, setDraft] = useState('')
      const [result, setResult] = useState('Waiting')
      useEffect(() => { pending.then(setResult); return unmounted }, [])
      return <><input aria-label="Draft" value={draft} onChange={e => setDraft(e.target.value)} /><p>{result}</p></>
    }
    const view = (active: boolean) => <RetainedPanel active={active}><Content /></RetainedPanel>
    const { rerender, unmount } = render(view(false))
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    rerender(view(true))
    const field = screen.getByRole('textbox', { name: 'Draft' })
    fireEvent.change(field, { target: { value: 'Keep this draft' } })
    rerender(view(false))
    expect(field).not.toBeVisible()
    expect(unmounted).not.toHaveBeenCalled()
    await act(async () => { finish('Completed while away'); await pending })
    rerender(view(true))
    expect(screen.getByRole('textbox', { name: 'Draft' })).toBe(field)
    expect(field).toHaveValue('Keep this draft')
    expect(screen.getByText('Completed while away')).toBeVisible()
    unmount(); expect(unmounted).toHaveBeenCalledOnce()
  })

  it('hides portals and releases modal focus when its panel is hidden', async () => {
    const view = (active: boolean) => <><button>Outside</button><RetainedPanel active={active}>
      {createPortal(<FocusTrap focusTrapOptions={{ tabbableOptions: { displayCheck: 'none' } }}><div role="dialog" aria-label="Retained dialog"><input aria-label="Dialog draft" /><button>Close</button></div></FocusTrap>, document.body)}
    </RetainedPanel></>
    const { rerender } = render(view(true))
    const draft = screen.getByRole('textbox', { name: 'Dialog draft' })
    await waitFor(() => expect(draft).toHaveFocus())
    fireEvent.change(draft, { target: { value: 'Unsaved modal content' } })
    rerender(view(false))
    screen.getByRole('button', { name: 'Outside' }).focus()
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Outside' })).toHaveFocus()
    rerender(view(true))
    expect(screen.getByRole('textbox', { name: 'Dialog draft' })).toHaveValue('Unsaved modal content')
    await waitFor(() => expect(draft).toHaveFocus())
  })
})
