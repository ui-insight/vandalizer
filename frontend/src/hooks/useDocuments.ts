import { useCallback, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Document, Folder } from '../types/document'
import { listContents } from '../api/documents'
import { isDocReady } from '../utils/processingStatus'

interface ContentsResult {
  documents: Document[]
  folders: Folder[]
}

const EMPTY_DOCUMENTS: Document[] = []
const EMPTY_FOLDERS: Folder[] = []

export function useDocuments(folderId: string | null, teamUuid?: string) {
  const qc = useQueryClient()
  const queryKey = ['documents', folderId, teamUuid] as const

  const { data, isLoading: loading } = useQuery<ContentsResult>({
    queryKey,
    queryFn: () => listContents(folderId ?? undefined, teamUuid),
    // Auto-poll every 3s while any document is still moving through the
    // pipeline. We can't just check `processing` here — that flag flips off
    // after text extraction, but the doc continues through RAG indexing
    // (task_status="readying") before it's truly done. Without this the list
    // would freeze on a stale state and the chat banner would never update.
    refetchInterval: (query) => {
      const docs = query.state.data?.documents
      if (docs?.some((d) => !isDocReady(d))) return 3000
      return false
    },
  })

  // Stable fallbacks: avoid new array references on every render when data is
  // undefined (loading), which would cause downstream useEffects to re-fire.
  const documents = data?.documents ?? EMPTY_DOCUMENTS
  const folders = data?.folders ?? EMPTY_FOLDERS

  // Stable refresh function
  const queryKeyRef = useRef(queryKey)
  queryKeyRef.current = queryKey
  const refresh = useCallback(
    () => qc.invalidateQueries({ queryKey: queryKeyRef.current }),
    [qc],
  )

  return { documents, folders, loading, refresh }
}
