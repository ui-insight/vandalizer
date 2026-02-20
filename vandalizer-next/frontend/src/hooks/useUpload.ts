import { useCallback, useState } from 'react'
import { uploadFile } from '../api/files'

export interface UploadProgress {
  fileName: string
  progress: number // 0–100
  done: boolean
  error?: string
  uuid?: string
}

export function useUpload(space: string, folderId: string | null, onComplete: () => void) {
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const [lastUploadedUuid, setLastUploadedUuid] = useState<string | null>(null)

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files)
      const initial: UploadProgress[] = fileArray.map((f) => ({
        fileName: f.name,
        progress: 0,
        done: false,
      }))
      setUploads(initial)
      let firstUuid: string | null = null

      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i]
        try {
          const ext = file.name.split('.').pop() || ''
          const base64 = await fileToBase64(file)

          setUploads((prev) =>
            prev.map((u, idx) => (idx === i ? { ...u, progress: 50 } : u)),
          )

          const result = await uploadFile({
            contentAsBase64String: base64,
            fileName: file.name,
            extension: ext,
            space,
            folder: folderId ?? undefined,
          })

          const uuid = result.uuid
          if (uuid && !firstUuid) firstUuid = uuid

          setUploads((prev) =>
            prev.map((u, idx) => (idx === i ? { ...u, progress: 100, done: true, uuid } : u)),
          )
        } catch (err) {
          setUploads((prev) =>
            prev.map((u, idx) =>
              idx === i
                ? { ...u, done: true, error: err instanceof Error ? err.message : 'Upload failed' }
                : u,
            ),
          )
        }
      }

      if (firstUuid) setLastUploadedUuid(firstUuid)
      onComplete()
      setTimeout(() => setUploads([]), 3000)
    },
    [space, folderId, onComplete],
  )

  const clearLastUploaded = useCallback(() => setLastUploadedUuid(null), [])

  return { uploads, upload, lastUploadedUuid, clearLastUploaded }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      // Strip data URL prefix
      const base64 = result.split(',')[1]
      resolve(base64)
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}
