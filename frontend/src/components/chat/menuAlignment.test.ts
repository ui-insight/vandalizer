import { describe, it, expect } from 'vitest'
import { menuAlignmentFor } from './ChatMessage'

// The citation menu is absolutely positioned inside the chat scroller. A
// container with overflow-y: auto computes overflow-x to auto as well, and
// `hide-scrollbar` removes the scrollbar that would let a reader reach what
// spilled out — so a menu running past the right edge is simply unreachable.
// In files mode the panel is roughly half width, which is when it bites.

const MENU = 150

describe('menuAlignmentFor', () => {
  it('left-aligns a pill with room to spare', () => {
    // container 0..800, pill at 100 — 150px menu ends at 250, well inside.
    expect(menuAlignmentFor(100, 160, MENU, 0, 800)).toBe('left')
  })

  it('flips a pill near the right edge', () => {
    // pill at 700..760 in an 800-wide panel: left-aligned the menu would end
    // at 850, past the edge and unreachable.
    expect(menuAlignmentFor(700, 760, MENU, 0, 800)).toBe('right')
  })

  it('treats exactly fitting as fitting', () => {
    expect(menuAlignmentFor(650, 710, MENU, 0, 800)).toBe('left')
  })

  it('stays left when neither side fits, keeping the first item reachable', () => {
    // A container narrower than the menu: flipping would clip the other edge
    // instead, which is no better and hides the first item rather than the last.
    expect(menuAlignmentFor(10, 60, MENU, 0, 100)).toBe('left')
  })

  it('respects a container that does not start at zero', () => {
    // The panel is offset from the viewport in files mode.
    expect(menuAlignmentFor(900, 960, MENU, 500, 1000)).toBe('right')
    expect(menuAlignmentFor(520, 580, MENU, 500, 1000)).toBe('left')
  })

  it('still flips a pill sitting past the container edge', () => {
    // Degenerate — pills cannot actually escape a vertically-scrolling
    // container — but the answer should not get worse: right-aligning puts the
    // menu at 1110..1260 rather than 1200..1350, i.e. nearer the container,
    // not further out.
    expect(menuAlignmentFor(1200, 1260, MENU, 0, 800)).toBe('right')
  })
})
