import { describe, expect, it } from 'vitest'
import type { ContextMeterInfo } from '../types/chat'
import { conversationNearMemoryLimit } from './contextNudge'

const meter = (extra: Partial<ContextMeterInfo>): ContextMeterInfo => ({
  estimated_tokens: 100_000, context_window: 128_000, effective_window: 120_000, warn_threshold: 90_000,
  compact_threshold: 105_000, block_threshold: 117_000, state: 'warning', percent_until_compact: 5,
  estimate_source: 'token_count', ...extra,
})

// Support ticket: a first question with a large .xlsx attached said
// "This conversation is getting long".
describe('conversation memory nudge', () => {
  it('stays hidden when attached files, not the conversation, fill the window', () => {
    expect(conversationNearMemoryLimit(meter({ history_tokens: 0 }), 0, 0)).toBe(false)
  })

  it('shows when the conversation is most of what fills it', () => {
    expect(conversationNearMemoryLimit(meter({ history_tokens: 70_000 }), 0, 0)).toBe(true)
  })

  it('keeps the old behaviour for servers that do not report the split', () => {
    expect(conversationNearMemoryLimit(meter({}), 0, 0)).toBe(true)
    expect(conversationNearMemoryLimit(meter({ state: 'ok', history_tokens: 90_000 }), 0, 0)).toBe(false)
    expect(conversationNearMemoryLimit(null, 95, 100)).toBe(true)
  })
})
