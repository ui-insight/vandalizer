import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { RailResizer } from './RailResizer'

it('resizes the Activity panel from the keyboard within its limits, and resets on double-click', () => {
  const onChange = vi.fn()
  const onReset = vi.fn()
  render(<RailResizer value={320} min={260} max={560} onChange={onChange} onReset={onReset} />)
  const control = screen.getByRole('separator', { name: 'Resize Activity panel' })
  expect(control).toHaveAttribute('aria-valuenow', '320')
  // The panel sits on the right, so Left widens it.
  fireEvent.keyDown(control, { key: 'ArrowLeft' }); expect(onChange).toHaveBeenLastCalledWith(340, true)
  fireEvent.keyDown(control, { key: 'ArrowRight' }); expect(onChange).toHaveBeenLastCalledWith(300, true)
  fireEvent.keyDown(control, { key: 'Home' }); expect(onChange).toHaveBeenLastCalledWith(260, true)
  fireEvent.keyDown(control, { key: 'End' }); expect(onChange).toHaveBeenLastCalledWith(560, true)
  fireEvent.doubleClick(control); expect(onReset).toHaveBeenCalled()
})

it('drags to the distance from the right edge, and only remembers the width on release', () => {
  vi.stubGlobal('PointerEvent', MouseEvent)
  const onChange = vi.fn()
  render(<RailResizer value={320} min={260} max={560} onChange={onChange} onReset={vi.fn()} />)
  const control = screen.getByRole('separator')
  control.setPointerCapture = vi.fn(); control.releasePointerCapture = vi.fn()
  fireEvent.pointerDown(control, { button: 0 })
  fireEvent.pointerMove(control, { clientX: window.innerWidth - 400 })
  expect(onChange).toHaveBeenLastCalledWith(400, false)
  fireEvent.pointerUp(control, { clientX: window.innerWidth - 2000 })
  expect(onChange).toHaveBeenLastCalledWith(560, true)
  expect(document.body.style.cursor).toBe('')
  vi.unstubAllGlobals()
})
