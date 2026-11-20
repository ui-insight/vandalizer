import { createRef, useLayoutEffect, type RefObject } from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChatScrollRegion } from './ChatScrollRegion'

// jsdom has no layout. Model a browser clamping the viewport while React
// replaces streamed content; a child layout effect precedes componentDidUpdate.
function ReplacedContent({ scrollRef, revision }: { scrollRef: RefObject<HTMLDivElement | null>; revision: number }) {
  useLayoutEffect(() => {
    if (revision && scrollRef.current) scrollRef.current.scrollTop = 0
  }, [revision, scrollRef])
  return <p>Response {revision}</p>
}

function setup() {
  const scrollRef = createRef<HTMLDivElement>()
  const view = (revision: number, isStreaming = true, conversationUuid = 'chat-1') => (
    <ChatScrollRegion scrollRef={scrollRef} isStreaming={isStreaming} conversationUuid={conversationUuid} aria-label="Conversation" role="region">
      <ReplacedContent scrollRef={scrollRef} revision={revision} />
    </ChatScrollRegion>
  )
  const result = render(view(0))
  const scroller = screen.getByRole('region', { name: 'Conversation' })
  Object.defineProperty(scroller, 'offsetParent', { configurable: true, value: document.body })
  return { scroller, update: (revision: number, streaming = true, conversation = 'chat-1') => result.rerender(view(revision, streaming, conversation)) }
}

describe('streaming reading position', () => {
  it('preserves the latest native position even before a scroll event is delivered', () => {
    const { scroller, update } = setup()
    scroller.scrollTop = 420
    update(1)
    expect(scroller.scrollTop).toBe(420)
    // The reader can move both down and up between chunks.
    scroller.scrollTop = 780
    update(2)
    expect(scroller.scrollTop).toBe(780)
    scroller.scrollTop = 160
    update(3)
    expect(scroller.scrollTop).toBe(160)
    expect(scroller).toHaveStyle({ overflowAnchor: 'none' })
  })

  it('also preserves position when the completed message replaces the stream', () => {
    const { scroller, update } = setup()
    scroller.scrollTop = 600
    update(1, false)
    expect(scroller.scrollTop).toBe(600)
    // Subsequent non-streaming updates do not restore an old reading position.
    update(2, false)
    expect(scroller.scrollTop).toBe(0)
  })

  it('does not carry the previous position into a different conversation', () => {
    const { scroller, update } = setup()
    scroller.scrollTop = 600
    update(1, false, 'chat-2')
    expect(scroller.scrollTop).toBe(0)
  })

  it('leaves hidden-panel restoration to the workspace', () => {
    const { scroller, update } = setup()
    Object.defineProperty(scroller, 'offsetParent', { value: null })
    scroller.scrollTop = 600
    update(1)
    expect(scroller.scrollTop).toBe(0)
  })
})
