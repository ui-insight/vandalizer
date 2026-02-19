import { useCallback, useEffect, useRef, useState } from 'react'
import type { Document, Folder } from '../types/document'
import { listContents, pollStatus } from '../api/documents'

export function useDocuments(space: string, folderId: string | null, teamUuid?: string) {
  const [documents, setDocuments] = useState<Document[]>([])
  const [folders, setFolders] = useState<Folder[]>([])
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listContents(space, folderId ?? undefined, teamUuid)
      setFolders(data.folders)
      setDocuments(data.documents)
    } finally {
      setLoading(false)
    }
  }, [space, folderId, teamUuid])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Poll processing documents
  useEffect(() => {
    const processing = documents.filter((d) => d.processing)
    if (processing.length === 0) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    pollRef.current = setInterval(async () => {
      let changed = false
      for (const doc of processing) {
        const status = await pollStatus(doc.uuid)
        if (status.complete) {
          changed = true
        }
      }
      if (changed) refresh()
    }, 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [documents, refresh])

  return { documents, folders, loading, refresh }
}
