import { describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { chatWriteTargets, useChatWriteAnnouncer, useRefreshOnChatWrite } from './chatWrites'
import type { ToolResultInfo } from '../types/chat'

const result = (tool_name: string, content: unknown): ToolResultInfo =>
  ({ tool_name, tool_call_id: 'call-1', content, quality: null }) as ToolResultInfo

describe('chatWriteTargets', () => {
  it('maps a created knowledge base to the KB list', () => {
    expect(chatWriteTargets(result('create_knowledge_base', { uuid: 'kb-1', title: 'QA Smoke' }))).toEqual(['knowledgeBases'])
  })

  it('ignores previews, errors and malformed content', () => {
    const preview = { action: 'create_knowledge_base', preview: 'Create…', needs_confirmation: true }
    expect(chatWriteTargets(result('create_knowledge_base', preview))).toEqual([])
    expect(chatWriteTargets(result('create_knowledge_base', { error: 'nope' }))).toEqual([])
    expect(chatWriteTargets(result('create_knowledge_base', 'Created'))).toEqual([])
    expect(chatWriteTargets(result('search_documents', { uuid: 'x' }))).toEqual([])
  })

  it('covers the other creating tools', () => {
    expect(chatWriteTargets(result('create_workflow', { workflow_id: 'w' }))).toEqual(['library'])
    expect(chatWriteTargets(result('create_extraction_from_document', { extraction_set_uuid: 's' }))).toEqual(['library'])
    expect(chatWriteTargets(result('create_automation', { id: 'a' }))).toEqual(['automations'])
    expect(chatWriteTargets(result('create_project', { project_uuid: 'p' }))).toEqual(['projects', 'knowledgeBases', 'documents'])
    expect(chatWriteTargets(result('save_to_folder', { document_uuid: 'd' }))).toEqual(['documents'])
  })
})

describe('useChatWriteAnnouncer', () => {
  it('refetches the KB list and notifies local-state panels', () => {
    const qc = new QueryClient()
    const invalidate = vi.spyOn(qc, 'invalidateQueries')
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    const libraryRefresh = vi.fn()
    const automationsRefresh = vi.fn()
    renderHook(() => useRefreshOnChatWrite('library', libraryRefresh))
    renderHook(() => useRefreshOnChatWrite('automations', automationsRefresh))
    const { result: announce } = renderHook(() => useChatWriteAnnouncer(), { wrapper })

    announce.current(result('create_knowledge_base', { needs_confirmation: true }))
    expect(invalidate).not.toHaveBeenCalled()

    announce.current(result('create_knowledge_base', { uuid: 'kb-1' }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['knowledgeBases'] })
    expect(libraryRefresh).not.toHaveBeenCalled()

    announce.current(result('create_workflow', { workflow_id: 'w' }))
    expect(libraryRefresh).toHaveBeenCalledTimes(1)
    expect(automationsRefresh).not.toHaveBeenCalled()
  })
})
