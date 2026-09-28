import { useEffect, useRef, useState } from 'react'
import { uploadFile } from '../api/files'
import { readUploadPolicy, uploadFileError } from '../utils/uploadPolicy'

export interface ChatUpload {
  id: string
  file: File
  status: 'uploading' | 'failed' | 'canceled'
  error?: string
}

function readFile(file: File, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    const abort = () => { reader.abort(); reject(new DOMException('Upload canceled', 'AbortError')) }
    const cleanup = () => signal.removeEventListener('abort', abort)
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    reader.onload = () => { cleanup(); resolve(String(reader.result).split(',')[1]) }
    reader.onerror = () => { cleanup(); reject(reader.error ?? new Error('Could not read this file')) }
    reader.onabort = cleanup
    reader.readAsDataURL(file)
  })
}

/** Each transfer owns its cancellation and retry; successful siblings stay attached. */
export function useChatUploads(onUploaded: (uuid: string, file: File) => void) {
  const [uploads, setUploads] = useState<ChatUpload[]>([])
  const controllers = useRef(new Map<string, AbortController>())
  const callback = useRef(onUploaded)
  callback.current = onUploaded
  useEffect(() => {
    const active = controllers.current
    return () => { active.forEach(controller => controller.abort()); active.clear() }
  }, [])

  const run = async (entry: ChatUpload) => {
    if (controllers.current.has(entry.id)) return
    const controller = new AbortController()
    controllers.current.set(entry.id, controller)
    setUploads(prev => [...prev.filter(item => item.id !== entry.id), { ...entry, status: 'uploading', error: undefined }])
    try {
      const error = uploadFileError(entry.file, await readUploadPolicy())
      if (controller.signal.aborted) return
      if (error) throw new Error(error)
      const content = await readFile(entry.file, controller.signal)
      const result = await uploadFile({ contentAsBase64String: content, fileName: entry.file.name, extension: entry.file.name.split('.').pop() || '' }, controller.signal)
      if (controller.signal.aborted) return
      if (!result.uuid) throw new Error('The server did not return a document. Try uploading again.')
      callback.current(result.uuid, entry.file)
      setUploads(prev => prev.filter(item => item.id !== entry.id))
    } catch (error) {
      if (!controller.signal.aborted) {
        setUploads(prev => prev.map(item => item.id === entry.id ? { ...item, status: 'failed', error: error instanceof Error ? error.message : 'Upload failed. Try again.' } : item))
      }
    } finally {
      if (controllers.current.get(entry.id) === controller) controllers.current.delete(entry.id)
    }
  }
  return {
    uploads,
    uploading: uploads.some(item => item.status === 'uploading'),
    add: (files: File[]) => files.forEach(file => { void run({ id: crypto.randomUUID(), file, status: 'uploading' }) }),
    retry: (entry: ChatUpload) => { void run(entry) },
    cancel: (id: string) => {
      controllers.current.get(id)?.abort()
      controllers.current.delete(id)
      setUploads(prev => prev.map(item => item.id === id ? { ...item, status: 'canceled' } : item))
    },
    dismiss: (id: string) => setUploads(prev => prev.filter(item => item.id !== id)),
  }
}
