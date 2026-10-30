import type { ContextMeterInfo } from '../types/chat'

/**
 * Whether to show "This conversation is getting long … Manage memory".
 *
 * Only when the conversation is what fills the model's window. On a first
 * question with a large spreadsheet attached, the file fills it; the
 * "Only part of a large file was sent" notice covers that, and trimming
 * messages can't help.
 */
export function conversationNearMemoryLimit(
  meter: ContextMeterInfo | null | undefined, tokens: number, window: number,
): boolean {
  if (!meter) return tokens > 0 && window > 0 && tokens / window >= 0.9
  if (meter.state === 'ok') return false
  return meter.history_tokens == null || meter.history_tokens * 2 >= meter.estimated_tokens
}
