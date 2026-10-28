import { expect, it, vi } from 'vitest'
import { streamChat, exportChat } from './chat'
import { rawFetch } from './client'
vi.mock('./client', () => ({ rawFetch: vi.fn(), apiFetch: vi.fn() }))
it('marks a retry for the server so reopening does not restore duplicate user messages', async () => {
  vi.mocked(rawFetch).mockResolvedValueOnce(new Response(''))
  await streamChat('Make a page', ['workbook'], 'activity', undefined, 'kimi-k3', undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, null, undefined, true)
  expect(JSON.parse(vi.mocked(rawFetch).mock.lastCall![1]!.body as string)).toMatchObject({
    message: 'Make a page', activity_id: 'activity', document_uuids: ['workbook'], retry: true,
  })
})
it('downloads a real export through the authenticated fetch wrapper', async () => {
  vi.mocked(rawFetch).mockResolvedValueOnce(new Response('office bytes', { headers: { 'Content-Type': 'application/octet-stream' } }))
  const messages = [{ role: 'assistant' as const, content: 'Answer', tools: [], evidence: 'Source.pdf' }]
  const blob = await exportChat('docx', messages)
  expect(blob.size).toBe(12)
  expect(rawFetch).toHaveBeenLastCalledWith('/api/chat/export', expect.objectContaining({ method: 'POST', body: JSON.stringify({ format: 'docx', messages }), signal: expect.any(AbortSignal) }))
})

it('surfaces renderer errors instead of downloading an error response', async () => {
  vi.mocked(rawFetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'A table cell is too long for Excel.' }), { status: 422 }))
  await expect(exportChat('xlsx', [])).rejects.toThrow('A table cell is too long for Excel.')
})
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

it('sends only the selected Skill identity and reviewed version, never client instructions', async () => {
  vi.mocked(rawFetch).mockResolvedValue(new Response(''))
  await streamChat('Review', [], null, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, 'skill-1', 'version-1')
  const body = JSON.parse(vi.mocked(rawFetch).mock.lastCall![1]!.body as string)
  expect(body.skill_uuid).toBe('skill-1')
  expect(body.skill_version).toBe('version-1')
  expect(body.instructions).toBeUndefined()
})

it('distinguishes removing a Skill from a legacy request that omits selection', async () => {
  vi.mocked(rawFetch).mockImplementation(async () => new Response(''))
  await streamChat('Continue', [])
  expect(JSON.parse(vi.mocked(rawFetch).mock.lastCall![1]!.body as string)).not.toHaveProperty('skill_uuid')
  await streamChat('Continue', [], null, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, undefined, null)
  expect(JSON.parse(vi.mocked(rawFetch).mock.lastCall![1]!.body as string).skill_uuid).toBeNull()
})

it('keeps a long page generation alive on heartbeats and delivers the eventual preview', async () => {
  vi.useFakeTimers()
  try {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({ start(c) { controller = c } })
    vi.mocked(rawFetch).mockResolvedValue(new Response(stream))
    const chunks = vi.fn()
    const pending = streamChat('Build a page', [], null, chunks)
    await vi.advanceTimersByTimeAsync(0)
    controller.enqueue(encoder.encode(JSON.stringify({ kind: 'activity', content: '', activity: { phase: 'tool_preparing', tool_name: 'create_html_artifact' } }) + '\n'))
    for (let i = 0; i < 8; i++) {
      await vi.advanceTimersByTimeAsync(15_000)
      controller.enqueue(encoder.encode('{"kind":"heartbeat","content":""}\n'))
      await vi.advanceTimersByTimeAsync(0)
    }
    controller.enqueue(encoder.encode('{"kind":"tool_result","tool_name":"create_html_artifact","tool_call_id":"page","content":{"needs_confirmation":true,"artifact_preview_html":"<h1>Review</h1>"}}\n'))
    controller.close()
    await expect(pending).resolves.toBeTruthy()
    expect(chunks).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'tool_result', content: expect.objectContaining({ needs_confirmation: true }) }))
  } finally { vi.useRealTimers() }
})

it('still detects a genuinely silent connection and cancels its reader', async () => {
  vi.useFakeTimers()
  try {
    const cancel = vi.fn()
    vi.mocked(rawFetch).mockResolvedValue(new Response(new ReadableStream({ cancel })))
    const pending = streamChat('Build a page', [])
    const failure = expect(pending).rejects.toThrow('The response stalled')
    await vi.advanceTimersByTimeAsync(90_001)
    await failure
    expect(cancel).toHaveBeenCalledOnce()
  } finally { vi.useRealTimers() }
})
