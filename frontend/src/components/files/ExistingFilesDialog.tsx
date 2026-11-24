import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { X, FileText } from 'lucide-react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { searchDocuments, type SearchResult } from '../../api/documents'
import { moveFile } from '../../api/files'
import { announceWorkspaceWrite } from '../../lib/chatWrites'

export type ExistingFile = Pick<SearchResult, 'uuid' | 'title'>

interface Props {
  attachedUuids?: string[]
  destination?: { uuid: string; title: string }
  onAttach?: (files: ExistingFile[]) => void
  onClose: () => void
}

/** Reuse existing documents: chat attaches references; a folder receives a move. */
export function ExistingFilesDialog({ attachedUuids = [], destination, onAttach, onClose }: Props) {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [items, setItems] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(true)
  const [searchError, setSearchError] = useState('')
  const [picked, setPicked] = useState<Record<string, ExistingFile>>({})
  const [moved, setMoved] = useState<string[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setSearchError('')
    const timer = setTimeout(() => {
      searchDocuments(search.trim(), 100).then(result => {
        if (!cancelled) setItems(result.items)
      }).catch(() => {
        if (!cancelled) setSearchError('Could not load your files.')
      }).finally(() => { if (!cancelled) setLoading(false) })
    }, search ? 250 : 0)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [search, attempt])

  const selected = Object.values(picked).filter(file => !attachedUuids.includes(file.uuid) && !moved.includes(file.uuid))
  const submit = async () => {
    if (pending.current || !selected.length) return
    if (!destination) { onAttach?.(selected); onClose(); return }
    pending.current = true
    setBusy(true)
    setErrors([])
    try {
      const results = await Promise.allSettled(selected.map(async file => {
        const result = await moveFile(file.uuid, destination.uuid)
        if (!result.ok) throw new Error('The file could not be moved.')
      }))
      const succeeded = selected.filter((_, index) => results[index].status === 'fulfilled').map(file => file.uuid)
      const failures = selected.flatMap((file, index) => {
        const result = results[index]
        return result.status === 'rejected' ? [`${file.title}: ${result.reason instanceof Error ? result.reason.message : 'Could not move this file.'}`] : []
      })
      if (succeeded.length) {
        setMoved(previous => [...previous, ...succeeded])
        setPicked(previous => Object.fromEntries(Object.entries(previous).filter(([uuid]) => !succeeded.includes(uuid))))
        void qc.invalidateQueries({ queryKey: ['documents'] })
        void qc.invalidateQueries({ queryKey: ['project'] })
        void qc.invalidateQueries({ queryKey: ['projects'] })
        announceWorkspaceWrite('documents', 'projects', 'knowledgeBases')
      }
      if (failures.length) setErrors(failures)
      else onClose()
    } finally { pending.current = false; setBusy(false) }
  }

  return <div className="fixed inset-0 flex items-center justify-center bg-black/50 p-4" style={{ zIndex: 1100 }} onKeyDown={event => { if (event.key === 'Escape' && !pending.current) onClose() }}>
    <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div role="dialog" aria-modal="true" aria-labelledby="existing-files-title" className="flex max-h-[90dvh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-3">
          <h3 id="existing-files-title" className="font-medium">From my files</h3>
          <button type="button" disabled={busy} onClick={onClose} aria-label="Close file picker" className="rounded p-1 disabled:opacity-50"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-3 overflow-y-auto p-5 text-sm">
          <p>{destination ? <>Move existing files into <strong>{destination.title}</strong>. They leave their current folder and become available to people who can access this project. No duplicate is created.</> : 'Attach existing Vandalizer files to this chat. Their location and sharing stay the same.'}</p>
          <label className="block">Search my files<input type="search" value={search} disabled={busy} onChange={event => setSearch(event.target.value)} className="mt-1 w-full rounded border border-gray-300 p-2" placeholder="Search titles or content" /></label>
          {!!moved.length && <p role="status">{moved.length} file{moved.length === 1 ? '' : 's'} moved. Only the remaining selections will be retried.</p>}
          {!!errors.length && <div role="alert" className="text-red-700"><p>Some files could not be moved:</p><ul>{errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
          {loading ? <p role="status">Loading files…</p> : searchError ? <p role="alert">{searchError} <button type="button" onClick={() => setAttempt(value => value + 1)} className="underline">Retry files</button></p> : <>
            {!items.length && <p>No files found. Try another search.</p>}
            <ul className="space-y-2">{items.map(file => {
              const already = attachedUuids.includes(file.uuid) || moved.includes(file.uuid) || (!!destination && file.folder === destination.uuid)
              return <li key={file.uuid}><label className="flex items-start gap-2 rounded border border-gray-200 p-3">
                <input type="checkbox" checked={already || !!picked[file.uuid]} disabled={already || busy} onChange={event => {
                  const checked = event.target.checked
                  setPicked(previous => {
                    const next = { ...previous }
                    if (checked) next[file.uuid] = { uuid: file.uuid, title: file.title }
                    else delete next[file.uuid]
                    return next
                  })
                }} />
                <FileText className="h-4 w-4 shrink-0" />
                <span className="min-w-0 break-words">{file.title}{already && <span className="ml-2 text-xs text-gray-500">{destination ? 'Already in this folder' : 'Already attached'}</span>}</span>
              </label></li>
            })}</ul>
            {items.length >= 100 && <p>Showing up to 100 files. Search by name to narrow the results.</p>}
          </>}
          {!!selected.length && <p className="break-words">Selected: {selected.map(file => file.title).join(', ')}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <button type="button" disabled={busy} onClick={onClose} className="rounded px-3 py-2">Cancel</button>
          <button type="button" disabled={busy || !selected.length} onClick={() => void submit()} className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50">{busy ? 'Moving files…' : destination ? `Move ${selected.length || ''} file${selected.length === 1 ? '' : 's'} here` : `Attach ${selected.length || ''} file${selected.length === 1 ? '' : 's'}`}</button>
        </div>
      </div>
    </FocusTrap>
  </div>
}
