import { beforeEach, expect, it } from 'vitest'
import { fitPanelSplit, panelSplitBounds, readCompactPanelChoices, validPanelSplit } from './workspaceLayout'
beforeEach(()=>sessionStorage.clear())
it('rejects invalid sizes and clamps remembered positions to useful pane widths',()=>{
  expect(validPanelSplit(Infinity)).toBe(60)
  expect(validPanelSplit(NaN)).toBe(60)
  expect(validPanelSplit(100)).toBe(80)
  expect(validPanelSplit(-10)).toBe(20)
  const fitted=fitPanelSplit(80,650)
  expect(650*(1-fitted/100)).toBeCloseTo(320)
  expect(fitPanelSplit(20,650)*650/100).toBeCloseTo(280)
  expect(fitPanelSplit(70,1400)).toBe(70)
  expect(panelSplitBounds(0)).toEqual({min:20,max:80})
})
it('restores only recognized section and pane choices from session storage',()=>{
  sessionStorage.setItem('workspace:compactPanels',JSON.stringify({files:'tools',knowledge:'source',admin:'tools',projects:'invalid'}))
  expect(readCompactPanelChoices()).toEqual({files:'tools',knowledge:'source'})
  sessionStorage.setItem('workspace:compactPanels','broken')
  expect(readCompactPanelChoices()).toEqual({})
})
