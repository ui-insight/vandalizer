import { describe, it, expect } from 'vitest'
import { shouldAutoContinueAfterAttach } from './autoContinue'

describe('shouldAutoContinueAfterAttach', () => {
  it('continues when the assistant spoke last and the chat is idle', () => {
    expect(shouldAutoContinueAfterAttach({
      lastMessageRole: 'assistant', isStreaming: false, hasHeldMessage: false,
    })).toBe(true)
  })

  it('does not continue on a fresh chat with no messages', () => {
    expect(shouldAutoContinueAfterAttach({
      lastMessageRole: undefined, isStreaming: false, hasHeldMessage: false,
    })).toBe(false)
  })

  it('does not continue when the user spoke last', () => {
    expect(shouldAutoContinueAfterAttach({
      lastMessageRole: 'user', isStreaming: false, hasHeldMessage: false,
    })).toBe(false)
  })

  it('does not hijack an active stream', () => {
    expect(shouldAutoContinueAfterAttach({
      lastMessageRole: 'assistant', isStreaming: true, hasHeldMessage: false,
    })).toBe(false)
  })

  it('yields to a message the user already queued', () => {
    expect(shouldAutoContinueAfterAttach({
      lastMessageRole: 'assistant', isStreaming: false, hasHeldMessage: true,
    })).toBe(false)
  })
})
