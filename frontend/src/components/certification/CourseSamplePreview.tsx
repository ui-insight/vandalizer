import { useEffect, useId, useRef, useState } from 'react'
import { getLabStatus } from '../../api/certification'
import { DocumentViewer } from '../files/DocumentViewer'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { createPortal } from '../shared/panelPortal'

export function CourseSamplePreview({ moduleId, enrollmentId, documentId, name, onClose }: {
  moduleId: string; enrollmentId?: string; documentId: string; name: string; onClose: () => void
}) {
  const heading = useId(), description = useId()
  const [state, setState] = useState<'checking' | 'ready' | 'unavailable'>('checking')
  const [revision, setRevision] = useState(0)
  const requestKey = JSON.stringify([moduleId, enrollmentId, documentId, name])
  const [verified, setVerified] = useState('')
  const checking = useRef(true)
  const close = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    let active = true
    checking.current = true
    setState('checking')
    void getLabStatus(moduleId, enrollmentId).then(value => {
      if (!active) return
      if (value.module_id !== moduleId || value.enrollment_id !== enrollmentId || value.credit_changed !== false
        || !value.folder_id || !['ready', 'processing', 'failed', 'unavailable'].includes(value.state)
        || !value.documents.some(row => row.document_id === documentId && row.name === name)) throw new Error('Sample no longer assigned')
      setVerified(requestKey)
      setState('ready')
    }).catch(() => { if (active) setState('unavailable') }).finally(() => { if (active) checking.current = false })
    return () => { active = false }
  }, [moduleId, enrollmentId, documentId, name, revision, requestKey])
  return createPortal(<FocusTrap focusTrapOptions={{ initialFocus: () => close.current!, escapeDeactivates: false,
    tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
    <div role="dialog" aria-modal="true" aria-labelledby={heading} aria-describedby={description}
      className="workspace-shell fixed inset-0 z-[9500] flex min-w-0 flex-col bg-white text-gray-900 [overflow-wrap:anywhere] [&_button]:min-h-11 [&_button]:min-w-11 [&_input]:min-h-11"
      onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); onClose() } }}>
      <header className="shrink-0 space-y-2 border-b border-gray-300 p-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 id={heading} className="min-w-0 text-base font-semibold">Assigned sample: {name}</h2>
          <button ref={close} type="button" onClick={onClose} className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2">Return to course</button>
        </div>
        <p id={description} className="text-sm text-gray-700">This is the current assigned file. Saved assessment runs keep their original captured copy. Your course and chat stay open; viewing a sample earns no credit.</p>
      </header>
      <div className="min-h-0 flex-1 overflow-auto">
        {(state === 'checking' || state === 'ready' && verified !== requestKey) && <p role="status" className="p-4 text-sm">Checking this course’s assigned sample…</p>}
        {state === 'unavailable' && <div className="space-y-3 p-4 text-sm"><p role="alert">This sample is no longer available for the selected course, or its status could not be checked. Your saved work is unchanged.</p>
          <button type="button" className="rounded-lg border border-gray-300 px-3 py-2" onClick={() => { if (!checking.current) { checking.current = true; setState('checking'); setRevision(value => value + 1) } }}>Check sample access again</button></div>}
        {state === 'ready' && verified === requestKey && <DocumentViewer docUuid={documentId} unavailableHelp="Return to your course and check sample status and file access. Saved assessment evidence is unchanged." />}
      </div>
    </div>
  </FocusTrap>, document.body)
}
