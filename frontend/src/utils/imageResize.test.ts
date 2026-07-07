import { describe, it, expect } from 'vitest'
import { fileToConstrainedDataUrl } from './imageResize'

// Note: the canvas downscale path can't run under jsdom (no 2D context), so
// these cover the canvas-free branches: SVG pass-through and the
// already-small short-circuit. The resize path is exercised manually / in the
// browser.

function fileOf(content: string, type: string, name = 'img'): File {
  return new File([content], name, { type })
}

describe('fileToConstrainedDataUrl', () => {
  it('returns an SVG untouched (vector — never rasterized)', async () => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    const out = await fileToConstrainedDataUrl(fileOf(svg, 'image/svg+xml'), {
      maxBytes: 500_000,
      maxDimension: 512,
    })
    expect(out.startsWith('data:image/svg+xml')).toBe(true)
    expect(atob(out.split(',')[1])).toContain('<svg')
  })

  it('passes an oversized SVG through so the caller can reject it', async () => {
    const svg = '<svg>' + 'a'.repeat(2000) + '</svg>'
    const out = await fileToConstrainedDataUrl(fileOf(svg, 'image/svg+xml'), {
      maxBytes: 100, // far smaller than the encoded SVG
      maxDimension: 512,
    })
    // Returned unchanged and still over the cap — caller's size check handles it.
    expect(out.startsWith('data:image/svg+xml')).toBe(true)
    expect(out.length).toBeGreaterThan(100)
  })

  it('returns a raster image untouched when already under the cap', async () => {
    const out = await fileToConstrainedDataUrl(fileOf('tiny', 'image/png'), {
      maxBytes: 500_000,
      maxDimension: 512,
    })
    expect(out.startsWith('data:image/png')).toBe(true)
    expect(atob(out.split(',')[1])).toBe('tiny')
  })
})
