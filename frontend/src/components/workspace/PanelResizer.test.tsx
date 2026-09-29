import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { PanelResizer } from './PanelResizer'
const setPanelSplit=vi.fn()
vi.mock('../../contexts/WorkspaceContext',()=>({useWorkspace:()=>({setPanelSplit})}))
beforeEach(()=>vi.clearAllMocks())
it('supports keyboard sizing within the current viewport limits',()=>{
  render(<PanelResizer containerRef={{current:document.createElement('div')}} value={50} min={40} max={65} />)
  const control=screen.getByRole('separator',{name:'Resize workspace panels'})
  expect(control).toHaveAttribute('aria-valuenow','50')
  fireEvent.keyDown(control,{key:'ArrowRight'});expect(setPanelSplit).toHaveBeenLastCalledWith(55)
  fireEvent.keyDown(control,{key:'Home'});expect(setPanelSplit).toHaveBeenLastCalledWith(40)
  fireEvent.keyDown(control,{key:'End'});expect(setPanelSplit).toHaveBeenLastCalledWith(65)
  fireEvent.doubleClick(control);expect(setPanelSplit).toHaveBeenLastCalledWith(60)
})
it('restores document interaction if the viewport removes a resizer during a drag',()=>{
  vi.stubGlobal('PointerEvent',MouseEvent)
  const view=render(<PanelResizer containerRef={{current:document.createElement('div')}} value={50} min={40} max={65} />)
  const control=screen.getByRole('separator')
  control.setPointerCapture=vi.fn()
  document.body.style.cursor='default'
  fireEvent.pointerDown(control,{button:0})
  expect(document.body.style.cursor).toBe('col-resize')
  view.unmount()
  expect(document.body.style.cursor).toBe('default')
  expect(document.body.style.userSelect).toBe('')
  document.body.style.cursor=''
})
