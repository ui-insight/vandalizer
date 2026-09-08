import { describe, it, expect } from 'vitest'
import { contrastRatio, getContrastTextColor, getAccessibleOnLight, getAccessibleOnDark, getPanelDark, hexToRgb, rgbToHsl } from './color'

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
  it('picks white text on the #1D3C34 dark green brand color (regression: hardcoded black gave 1.75:1, a WCAG AA failure)', () => {
    expect(getContrastTextColor('#1D3C34')).toBe('#ffffff')
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

function lightnessOf(hex: string): number {
  const { r, g, b } = hexToRgb(hex)
  return rgbToHsl(r, g, b).l
}

describe('getAccessibleOnDark', () => {
  const DARK = '#0a0a0a' // AuthLayout / Footer surface

  it('leaves the default gold unchanged (already ~10:1 on #0a0a0a)', () => {
    expect(getAccessibleOnDark('#f1b300')).toBe('#f1b300')
  })

  it('lightens a dark navy brand color until it passes 4.5:1 on #0a0a0a', () => {
    // #163A64 on #0a0a0a is ~1.6:1 — illegible as text.
    const out = getAccessibleOnDark('#163A64')
    expect(out).not.toBe('#163A64')
    expect(contrastRatio(out, DARK)).toBeGreaterThanOrEqual(4.5)
    expect(lightnessOf(out)).toBeGreaterThan(lightnessOf('#163A64'))
  })

  it('preserves hue (a navy input must not come back yellow)', () => {
    for (const hex of ['#163A64', '#1D3C34', '#4a1030']) {
      const { r, g, b } = hexToRgb(hex)
      const before = rgbToHsl(r, g, b)
      const out = hexToRgb(getAccessibleOnDark(hex))
      const after = rgbToHsl(out.r, out.g, out.b)
      expect(after.h).toBeCloseTo(before.h, 0)
    }
  })

  it('always returns a color meeting the target for a range of hues', () => {
    for (const hex of ['#163A64', '#1a1a2e', '#154cf7', '#1D3C34', '#22c55e']) {
      expect(contrastRatio(getAccessibleOnDark(hex), DARK)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('returns the terminal light value instead of looping when the target is unreachable', () => {
    // 25:1 exceeds the 21:1 maximum, so no lightness step can ever pass.
    expect(getAccessibleOnDark('#163A64', DARK, 25)).toBe('#f5f5f5')
  })

  it('moves a mid-tone in the opposite direction from getAccessibleOnLight', () => {
    // A shared 7:1 target so the same mid-tone fails on both backgrounds:
    // at 4.5:1 only a sliver of mid-tones fails against white AND #0a0a0a.
    const mid = '#808080'
    expect(lightnessOf(getAccessibleOnLight(mid, '#ffffff', 7))).toBeLessThan(lightnessOf(mid))
    expect(lightnessOf(getAccessibleOnDark(mid, '#0a0a0a', 7))).toBeGreaterThan(lightnessOf(mid))
  })
})

describe('getPanelDark', () => {
  const NEUTRAL = '#191919' // the chrome color before it followed the brand

  function saturationOf(hex: string): number {
    const { r, g, b } = hexToRgb(hex)
    return rgbToHsl(r, g, b).s
  }
  function hueOf(hex: string): number {
    const { r, g, b } = hexToRgb(hex)
    return rgbToHsl(r, g, b).h
  }

  it('tints the navy brand without meaningfully moving contrast against white', () => {
    const out = getPanelDark('#163A64')
    expect(out).not.toBe(NEUTRAL)
    // Pinning lightness is the whole point: the chrome changes hue, not legibility.
    // #163A64 -> #0f1d2e is 16.997:1 on white vs 17.582:1 for #191919.
    expect(
      Math.abs(contrastRatio(out, '#ffffff') - contrastRatio(NEUTRAL, '#ffffff')),
    ).toBeLessThan(1.5)
  })

  it('preserves the brand hue', () => {
    for (const hex of ['#163A64', '#1D3C34', '#eab308', '#4a1030']) {
      expect(Math.abs(hueOf(getPanelDark(hex)) - hueOf(hex))).toBeLessThan(3)
    }
  })

  it('returns an effectively neutral chrome for a greyscale brand', () => {
    expect(saturationOf(getPanelDark('#808080'))).toBeLessThan(0.02)
  })

  it('caps a fully saturated brand instead of returning a muddy stain', () => {
    for (const hex of ['#ff0000', '#00ff00', '#0000ff']) {
      expect(saturationOf(getPanelDark(hex))).toBeLessThanOrEqual(0.52)
    }
  })

  it('pins lightness across wildly different brand colors', () => {
    const navy = lightnessOf(getPanelDark('#163A64'))
    const gold = lightnessOf(getPanelDark('#eab308'))
    expect(navy).toBeCloseTo(gold, 2)
    expect(navy).toBeCloseTo(0.12, 2)
  })

  it('honors an explicit lightness argument', () => {
    expect(lightnessOf(getPanelDark('#163A64', 0.3))).toBeCloseTo(0.3, 2)
  })
})
