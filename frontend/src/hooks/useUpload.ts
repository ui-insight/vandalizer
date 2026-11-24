import { useCallback, useState } from 'react'
import { uploadFile } from '../api/files'
import { IDENTICAL_UPLOAD_NOTE, isUnappliedUpload, unappliedUploadMessage } from '../lib/duplicateUpload'
import { readUploadPolicy, uploadFileError } from '../utils/uploadPolicy'

export interface UploadProgress {
  id: number
  fileName: string
  progress: number // 0–100
  done: boolean
  error?: string
  /** Shown under a finished upload that changed nothing. */
  note?: string
  uuid?: string
}

// Re-exported for the existing import sites; `utils/fileTypes` is the source.
export { SUPPORTED_EXTENSIONS } from '../utils/fileTypes'

let nextUploadId = 0

export function useUpload(folderId: string | null, onComplete: () => void) {
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const [lastUploadedUuid, setLastUploadedUuid] = useState<string | null>(null)

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files)
      const policy = await readUploadPolicy()
      const batch = fileArray.map((file) => {
        const error = uploadFileError(file, policy)
        const supported = !error
        const item: UploadProgress = supported
          ? { id: nextUploadId++, fileName: file.name, progress: 0, done: false }
          : {
              id: nextUploadId++,
              fileName: file.name,
              progress: 0,
              done: true,
              error: error!,
            }
        return { file, item, supported }
      })

      // Keep failed and still-uploading entries from earlier batches visible.
      setUploads((prev) => [
        ...prev.filter((u) => u.error || !u.done),
        ...batch.map((b) => b.item),
      ])
      let firstUuid: string | null = null

      const updateItem = (id: number, patch: Partial<UploadProgress>) =>
        setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)))

      for (const { file, item, supported } of batch) {
        if (!supported) continue
        try {
          const ext = file.name.split('.').pop() || ''
          const base64 = await fileToBase64(file)

          updateItem(item.id, { progress: 50 })

          const result = await uploadFile({
            contentAsBase64String: base64,
            fileName: file.name,
            extension: ext,
            folder: folderId ?? undefined,
          })

          // A same-name file was already here and the server kept it. Unless
          // the two are known to be identical, that is not a successful
          // upload: say so, and don't open the old file as if it were new.
          if (isUnappliedUpload(result)) {
            updateItem(item.id, { done: true, error: unappliedUploadMessage(file.name, result) })
            continue
          }

          const uuid = result.uuid
          if (uuid && !firstUuid) firstUuid = uuid

          updateItem(item.id, { progress: 100, done: true, uuid, note: result.exists ? IDENTICAL_UPLOAD_NOTE : undefined })
        } catch (err) {
          updateItem(item.id, {
            done: true,
            error: err instanceof Error ? err.message : 'Upload failed',
          })
        }
      }

      if (firstUuid) setLastUploadedUuid(firstUuid)
      onComplete()
      // Auto-clear successes only; failures stay until the user dismisses them.
      setTimeout(() => setUploads((prev) => prev.filter((u) => u.error || !u.done)), 3000)
    },
    [folderId, onComplete],
  )

  const dismissUpload = useCallback(
    (id: number) => setUploads((prev) => prev.filter((u) => u.id !== id)),
    [],
  )

  const clearLastUploaded = useCallback(() => setLastUploadedUuid(null), [])

  return { uploads, upload, dismissUpload, lastUploadedUuid, clearLastUploaded }
}

export function fileToBase64(file: File): Promise<string> {
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
