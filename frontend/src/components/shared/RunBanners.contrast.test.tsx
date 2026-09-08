/**
 * These banners are dropped into whatever container a caller has, so their
 * text has to be legible against the surface they paint themselves — not
 * against a dark ancestor that may or may not be there. Written for a dark
 * theme, they rendered near-white text on a tint that washed out to pale pink
 * on the light Validate tabs, and the failure message was unreadable (support
 * ticket). Every text colour is checked against the nearest painted
 * background at the WCAG AA ratio for normal text.
 */
import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { CancelledBanner, ErrorBanner, FailedBanner, PastRunBanner } from './RunBanners'

const AA_NORMAL_TEXT = 4.5

function channel(value: number): number {
  const c = value / 255
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function contrast(fg: [number, number, number], bg: [number, number, number]): number {
  const [light, dark] = [luminance(fg), luminance(bg)].sort((a, b) => b - a)
  return (light + 0.05) / (dark + 0.05)
}

/** jsdom reports inline colours as "rgb(r, g, b)"; "" when unset. */
function parseColor(value: string): [number, number, number] | null {
  const m = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(value)
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

/** The background actually behind an element: the nearest painted ancestor,
 * falling back to the page, which is white. */
function backgroundBehind(el: HTMLElement): [number, number, number] {
  for (let node: HTMLElement | null = el; node; node = node.parentElement) {
    const bg = parseColor(node.style.backgroundColor || node.style.background || '')
    if (bg) return bg
  }
  return [255, 255, 255]
}

/** The colour the text is painted in: the nearest inline `color` up the tree,
 * since text mostly inherits it from the banner's own wrapper. */
function colorOf(el: HTMLElement): [number, number, number] | null {
  for (let node: HTMLElement | null = el; node; node = node.parentElement) {
    const color = parseColor(node.style.color || '')
    if (color) return color
  }
  return null
}

function faintText(container: HTMLElement): string[] {
  const failures: string[] = []
  for (const el of Array.from(container.querySelectorAll<HTMLElement>('*'))) {
    const color = colorOf(el)
    // Only elements that render their own text — a wrapper is judged on the
    // child that actually shows under it.
    const ownText = Array.from(el.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent?.trim() ?? '')
      .join('')
    if (!color || !ownText) continue
    const ratio = contrast(color, backgroundBehind(el))
    if (ratio < AA_NORMAL_TEXT) {
      failures.push(`"${ownText.slice(0, 40)}" at ${ratio.toFixed(2)}:1`)
    }
  }
  return failures
}

describe('RunBanners contrast', () => {
  it('FailedBanner is readable — title, message and retry button', () => {
    const { container } = render(
      <FailedBanner message="No extraction fields defined" onRunAgain={() => {}} />,
    )
    expect(faintText(container)).toEqual([])
  })

  it('FailedBanner is readable in its remediation form', () => {
    const { container } = render(
      <FailedBanner
        message="raw backend error"
        errorCode="kb_empty"
        onRunAgain={() => {}}
      />,
    )
    expect(faintText(container)).toEqual([])
  })

  it('ErrorBanner is readable', () => {
    const { container } = render(<ErrorBanner message="Something went wrong" />)
    expect(faintText(container)).toEqual([])
  })

  it('CancelledBanner is readable', () => {
    const { container } = render(
      <CancelledBanner completedTrials={3} onRunAgain={() => {}} />,
    )
    expect(faintText(container)).toEqual([])
  })

  it('PastRunBanner is readable', () => {
    const { container } = render(
      <PastRunBanner startedAt="2026-08-31T10:00:00Z" onExit={() => {}} />,
    )
    expect(faintText(container)).toEqual([])
  })

  it('the check itself catches faint text', () => {
    const { container } = render(
      <div style={{ backgroundColor: '#fef2f2' }}>
        <span style={{ color: '#fca5a5' }}>the colour this ticket was about</span>
      </div>,
    )
    expect(faintText(container)).toHaveLength(1)
  })
})
