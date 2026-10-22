import { expect, it, vi } from 'vitest'
import { streamChat } from './chat'
import { rawFetch } from './client'
vi.mock('./client', () => ({ rawFetch: vi.fn(), apiFetch: vi.fn() }))
it('reports the accepted identity before the streaming body finishes', async () => {
  let finish!: () => void
  const stream = new ReadableStream({ start(controller) { finish = () => controller.close() } })
  vi.mocked(rawFetch).mockResolvedValue(new Response(stream, { headers: { 'X-Conversation-UUID': 'conversation', 'X-Activity-ID': 'activity' } }))
  const started = vi.fn()
  const pending = streamChat('Hello', [], undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, started)
  await vi.waitFor(() => expect(started).toHaveBeenCalledWith({ conversationUuid: 'conversation', activityId: 'activity' }))
  finish()
  await expect(pending).resolves.toEqual({ conversationUuid: 'conversation', activityId: 'activity' })
})
