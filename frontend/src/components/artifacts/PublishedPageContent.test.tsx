import { act, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { PublishedPageContent } from './PublishedPageContent'

it('grows and shrinks for sizing messages from its own isolated frame only', () => {
  render(<PublishedPageContent src="/api/pages/public/token/content?revision=r4" />)
  const frame = screen.getByTitle('Published page content') as HTMLIFrameElement
  expect(frame).toHaveAttribute('src', '/api/pages/public/token/content?revision=r4&view=embed')
  expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox')
  expect(frame.getAttribute('sandbox')).not.toContain('allow-same-origin')
  expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
  const resize = (data: unknown, source: Window | null = frame.contentWindow) => act(() => {
    window.dispatchEvent(new MessageEvent('message', { data, source, origin: 'null' }))
  })
  resize({ type: 'vandalizer:page-height', height: 3000 }, window)
  expect(frame.style.height).toBe('')
  resize({ type: 'vandalizer:page-height', height: 3000.4 })
  expect(frame.style.height).toBe('3001px')
  for (const height of [-1, 0, Infinity, NaN, '5000', 1_000_001]) resize({ type: 'vandalizer:page-height', height })
  resize(null); resize({ type: 'another-message', height: 5000 })
  expect(frame.style.height).toBe('3001px')
  resize({ type: 'vandalizer:page-height', height: 2400 })
  expect(frame.style.height).toBe('2400px')
})

it('turns on Edit text in the frame, reports the change count and collects only well-formed edits', () => {
  const counts: number[] = []
  const collected: unknown[] = []
  const { rerender } = render(<PublishedPageContent src="/api/pages/p/revisions/r6/content" editing onEditCount={n => counts.push(n)} collect={0} onEdits={e => collected.push(e)} />)
  const frame = screen.getByTitle('Published page content') as HTMLIFrameElement
  const posted: unknown[] = []
  Object.defineProperty(frame.contentWindow!, 'postMessage', { value: (m: unknown) => posted.push(m), configurable: true })
  act(() => { frame.dispatchEvent(new Event('load')) })
  expect(posted).toContainEqual({ type: 'vandalizer:edit-mode', on: true })
  const fromFrame = (data: unknown) => act(() => { window.dispatchEvent(new MessageEvent('message', { data, source: frame.contentWindow })) })
  fromFrame({ type: 'vandalizer:edit-count', count: 2 })
  fromFrame({ type: 'vandalizer:edit-count', count: -1 })
  expect(counts).toEqual([2])
  rerender(<PublishedPageContent src="/api/pages/p/revisions/r6/content" editing onEditCount={n => counts.push(n)} collect={1} onEdits={e => collected.push(e)} />)
  expect(posted).toContainEqual({ type: 'vandalizer:edit-collect' })
  fromFrame({ type: 'vandalizer:edits', edits: [
    { tag: 'h1', index: 0, original: 'Dashbord', text: 'Dashboard' },
    { tag: '<script>', index: 0, original: 'x', text: 'y' },
    { tag: 'td', index: -1, original: 'x', text: 'y' },
  ] })
  expect(collected).toEqual([[{ tag: 'h1', index: 0, original: 'Dashbord', text: 'Dashboard' }]])
})
