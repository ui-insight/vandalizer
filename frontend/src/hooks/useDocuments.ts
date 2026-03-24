import { useCallback, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Document, Folder } from '../types/document'
import { listContents } from '../api/documents'

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
    // Auto-poll every 3s when any document is still processing
    refetchInterval: (query) => {
      const docs = query.state.data?.documents
      if (docs?.some((d) => d.processing)) return 3000
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
