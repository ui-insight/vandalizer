import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useChat } from './useChat'
import { streamChat, stopChatTurn } from '../api/chat'
import { MissingDocumentsError } from '../api/chatErrors'

// Support ticket: a deleted file still attached to chat answered "Document
// not found: <id>" with a Retry that sent the same file again.
vi.mock('../api/chat', () => ({ streamChat: vi.fn(), getHistory: vi.fn(), queueChatMessage: vi.fn(), stopChatTurn: vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(stopChatTurn).mockResolvedValue({ success: true })
})

it('reports which attached files are missing and resends without them', async () => {
  vi.mocked(streamChat).mockRejectedValueOnce(
    new MissingDocumentsError('A file attached to this chat was deleted.', ['gone'], 'deleted'),
  )
  const { result } = renderHook(() => useChat())

  await act(async () => { await result.current.send('When is the dataset due?', ['gone', 'kept']) })

  expect(result.current.errorDetails).toMatchObject({
    code: 'document_missing', missingDocuments: ['gone'], missingReason: 'deleted',
  })
  expect(result.current.error).toBe('A file attached to this chat was deleted.')

  vi.mocked(streamChat).mockResolvedValueOnce({ conversationUuid: 'c', activityId: 'a' } as never)
  await act(async () => { result.current.retryWithoutDocuments(['gone']) })

  await waitFor(() => expect(streamChat).toHaveBeenCalledTimes(2))
  const resent = vi.mocked(streamChat).mock.calls[1]
  expect(resent[0]).toBe('When is the dataset due?')
  expect(resent[1]).toEqual(['kept'])
  // The question appears once: the resend reuses the message already shown.
  expect(result.current.messages.filter(m => m.role === 'user')).toHaveLength(1)
})
