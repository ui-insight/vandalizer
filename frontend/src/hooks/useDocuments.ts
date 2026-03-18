import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Document, Folder } from '../types/document'
import { listContents } from '../api/documents'

interface ContentsResult {
  documents: Document[]
  folders: Folder[]
}

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

  const documents = data?.documents ?? []
  const folders = data?.folders ?? []

  const refresh = () => qc.invalidateQueries({ queryKey })

  return { documents, folders, loading, refresh }
}
