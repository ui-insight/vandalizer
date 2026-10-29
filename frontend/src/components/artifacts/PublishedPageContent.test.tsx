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
