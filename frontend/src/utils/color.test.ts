import { describe, it, expect } from 'vitest'
import { contrastRatio, getContrastTextColor, getAccessibleOnLight } from './color'

describe('contrastRatio', () => {
  it('is 21:1 for black on white', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 0)
  })
  it('is 1:1 for identical colors', () => {
    expect(contrastRatio('#123456', '#123456')).toBeCloseTo(1, 5)
  })
  it('is symmetric', () => {
    expect(contrastRatio('#eab308', '#ffffff')).toBeCloseTo(contrastRatio('#ffffff', '#eab308'), 5)
  })
})

describe('getContrastTextColor', () => {
  it('picks black text on a light brand color', () => {
    expect(getContrastTextColor('#eab308')).toBe('#000000')
  })
  it('picks white text on a dark brand color', () => {
    expect(getContrastTextColor('#154cf7')).toBe('#ffffff')
  })
})

describe('getAccessibleOnLight', () => {
  it('darkens a low-contrast brand color until it passes 4.5:1 on white', () => {
    // #eab308 on white is ~1.7:1 — must be darkened.
    const out = getAccessibleOnLight('#eab308')
    expect(out).not.toBe('#eab308')
    expect(contrastRatio(out, '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })
  it('leaves an already-accessible color unchanged', () => {
    const dark = '#154cf7' // already >4.5:1 on white
    expect(getAccessibleOnLight(dark)).toBe(dark)
  })
  it('always returns a color meeting the target for a range of hues', () => {
    for (const hex of ['#eab308', '#f1b300', '#22c55e', '#38bdf8', '#a3e635']) {
      expect(contrastRatio(getAccessibleOnLight(hex), '#ffffff')).toBeGreaterThanOrEqual(4.5)
    }
  })
})
