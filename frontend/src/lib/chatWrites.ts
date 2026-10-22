import { useCallback, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { ToolResultInfo } from '../types/chat'

/** Workspace lists a chat tool can change behind a panel's back. */
export type ChatWriteTarget = 'knowledgeBases' | 'library' | 'automations' | 'projects' | 'documents'

const EVENT = 'vandalizer:chat-write'

/** React Query roots each target owns. Panels on local state listen for EVENT instead. */
const QUERY_ROOTS: Record<ChatWriteTarget, string[]> = {
  knowledgeBases: ['knowledgeBases'],
  library: ['workflows', 'searchSets'],
  automations: [],
  projects: ['projects', 'project'],
  documents: ['documents'],
}

/**
 * The lists a completed chat write changed. Previews (needs_confirmation),
 * errors and malformed results change nothing, so they map to none.
 */
export function chatWriteTargets(result: ToolResultInfo): ChatWriteTarget[] {
  const data = result.content
  if (!data || typeof data !== 'object' || Array.isArray(data)) return []
  const value = data as Record<string, unknown>
  if (value.error || value.needs_confirmation) return []
  const has = (key: string) => typeof value[key] === 'string' && value[key] !== ''
  switch (result.tool_name) {
    case 'create_knowledge_base': return has('uuid') ? ['knowledgeBases'] : []
    case 'add_documents_to_kb':
    case 'add_url_to_kb': return has('kb_uuid') ? ['knowledgeBases'] : []
    // A project brings its own knowledge base and root folder.
    case 'create_project': return has('project_uuid') ? ['projects', 'knowledgeBases', 'documents'] : []
    case 'pin_to_project':
    case 'unpin_from_project':
    case 'set_project_status': return value.ok === true ? ['projects'] : []
    case 'create_extraction_from_document': return has('extraction_set_uuid') ? ['library'] : []
    case 'create_workflow': return has('workflow_id') ? ['library'] : []
    case 'create_automation': return has('id') ? ['automations'] : []
    case 'save_to_folder': return has('document_uuid') ? ['documents'] : []
    default: return []
  }
}

/** Returns a tool-result handler that refreshes every list the write touched. */
export function useChatWriteAnnouncer() {
  const qc = useQueryClient()
  return useCallback((result: ToolResultInfo) => {
    const targets = chatWriteTargets(result)
    if (!targets.length) return
    for (const target of targets) {
      for (const root of QUERY_ROOTS[target]) void qc.invalidateQueries({ queryKey: [root] })
    }
    window.dispatchEvent(new CustomEvent<ChatWriteTarget[]>(EVENT, { detail: targets }))
  }, [qc])
}

/** Re-runs *refresh* when a chat write touches *target* (for panels outside React Query). */
export function useRefreshOnChatWrite(target: ChatWriteTarget, refresh: () => unknown) {
  const latest = useRef(refresh)
  latest.current = refresh
  useEffect(() => {
    const onWrite = (event: Event) => {
      if ((event as CustomEvent<ChatWriteTarget[]>).detail?.includes(target)) void latest.current()
    }
    window.addEventListener(EVENT, onWrite)
    return () => window.removeEventListener(EVENT, onWrite)
  }, [target])
}
