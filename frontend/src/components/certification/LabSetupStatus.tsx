import { CourseSamplePreview } from './CourseSamplePreview'
import { useEffect, useRef, useState } from 'react'
import { getLabStatus } from '../../api/certification'
import type { CertificationLabStatus } from '../../types/certification'

const labels = { not_required: 'No sample files required', not_setup: 'Set up your lab',
  processing: 'Sample text is not ready yet', ready: 'Sample text is ready', failed: 'Sample processing failed',
  unavailable: 'Sample status needs attention' }
const documentLabels = { processing: 'Processing', ready: 'Text ready', failed: 'Processing failed', unavailable: 'Unavailable' }
const button = 'min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-900 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2'

export function LabSetupStatus({ moduleId, enrollmentId, filenames, assignmentKey, onProvision, provisioning, onOpenWorkspace }: {
  moduleId: string; enrollmentId?: string; filenames: string[]; assignmentKey?: string; onProvision: () => void; provisioning: boolean; onOpenWorkspace?: () => Promise<void>
}) {
  const [preview, setPreview] = useState<{ documentId: string; name: string } | null>(null)
  const [status, setStatus] = useState<CertificationLabStatus | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  const pending = useRef(false)
  const checking = useRef(true)
  const checkButton = useRef<HTMLButtonElement>(null)
  const navigating = useRef(false)
  const [openingWorkspace, setOpeningWorkspace] = useState(false)
  const [navigationError, setNavigationError] = useState(false)
  const signature = JSON.stringify(filenames)
  useEffect(() => {
    let active = true
    checking.current = true
    setStatus(null); setError(false); setLoading(true)
    if (provisioning) return () => { active = false }
    getLabStatus(moduleId, enrollmentId).then(value => {
      if (!active) return
      const expected: string[] = JSON.parse(signature)
      if (!value || value.module_id !== moduleId || value.enrollment_id !== enrollmentId
        || !Object.hasOwn(labels, value.state) || value.credit_changed !== false || !Array.isArray(value.documents)
        || (value.folder_name !== null && typeof value.folder_name !== 'string')
        || (value.folder_id !== null && typeof value.folder_id !== 'string')
        || (value.state === 'not_required' && expected.length > 0)
        || (['not_setup', 'not_required'].includes(value.state) ? value.documents.length !== 0
          : value.documents.length !== expected.length || value.documents.some((row, index) => !row || row.name !== expected[index]
            || !Object.hasOwn(documentLabels, row.state) || (row.document_id !== null && typeof row.document_id !== 'string')))
        || (value.state === 'ready' && (!value.folder_id || value.documents.some(row => row.state !== 'ready' || !row.document_id)))) {
        throw new Error('The lab status does not match this course')
      }
      setStatus(value)
    }).catch(() => { if (active) setError(true) }).finally(() => { if (active) { checking.current = false; setLoading(false) } })
    return () => { active = false }
  }, [moduleId, enrollmentId, signature, assignmentKey, revision, provisioning])
  useEffect(() => {
    if (!provisioning && pending.current) {
      pending.current = false
      checkButton.current?.focus()
    }
  }, [provisioning])
  const prepare = () => {
    if (pending.current || provisioning) return
    pending.current = true
    onProvision()
  }
  return <section aria-label="Course sample files" className={`min-w-0 space-y-3 rounded-xl border p-4 [overflow-wrap:anywhere] ${error || status?.state === 'failed' ? 'border-red-300 bg-red-50' : status?.state === 'ready' ? 'border-green-300 bg-green-50' : 'border-gray-300 bg-gray-50'}`}>
    <h4 className="font-semibold text-gray-900"><span role="status">{provisioning ? 'Preparing sample files…' : loading ? 'Checking sample files…' : error ? 'Sample status could not be loaded' : status ? labels[status.state] : 'Sample status unavailable'}</span></h4>
    {error && <p role="alert" className="text-sm text-red-800">Your saved work is unchanged. Retry the status check before starting more setup.</p>}
    {status?.folder_name && <p className="text-sm text-gray-700">Folder: {status.folder_name}</p>}
    {status && status.documents.length > 0 && <ul className="space-y-1 text-sm text-gray-800">{status.documents.map(row => <li key={row.name}><p>{row.name} — {documentLabels[row.state]}</p>{row.document_id && !loading && !error && !provisioning && <button type="button" className={button} onClick={() => setPreview({ documentId: row.document_id!, name: row.name })}>View assigned {row.name}</button>}</li>)}</ul>}
    {status?.state === 'not_setup' && <p className="text-sm text-gray-700">Add the assigned samples: {filenames.join(', ')}. Setup does not complete the module.</p>}
    {status?.state === 'processing' && <p className="text-sm text-gray-700">Text processing has not finished. You can keep reading and check again. Closing the panel does not cancel processing.</p>}
    {status?.state === 'ready' && <p className="text-sm text-gray-700">Text processing is complete. Follow the challenge instructions to do the assessed work; setup earns no credit.</p>}
    {status?.state === 'failed' && <p className="text-sm text-gray-700">Open Files to inspect the failed sample and retry its processing. Check status again afterward; repeating lab setup does not repair processing.</p>}
    {status?.state === 'unavailable' && <p className="text-sm text-gray-700">An assigned sample is missing, inaccessible or has an unknown processing state. Review Files and your access, then check again. Setup can restore missing samples you are allowed to create.</p>}
    <div className="flex flex-wrap gap-2">
      {status && ['not_setup', 'unavailable'].includes(status.state) && <button className={button} disabled={provisioning || loading} onClick={prepare}>{status.state === 'not_setup' ? 'Set Up Lab' : 'Set up missing samples'}</button>}
      <button ref={checkButton} className={button} disabled={provisioning} aria-disabled={loading || provisioning} onClick={() => {
        if (checking.current || provisioning) return
        checking.current = true
        setLoading(true)
        setRevision(value => value + 1)
      }}>Check sample status</button>
      {onOpenWorkspace && <button className={button} disabled={openingWorkspace} onClick={async () => {
        if (navigating.current) return
        navigating.current = true
        setOpeningWorkspace(true); setNavigationError(false)
        try { await onOpenWorkspace() } catch { setNavigationError(true) }
        finally { navigating.current = false; setOpeningWorkspace(false) }
      }}>{openingWorkspace ? 'Opening Files…' : 'Open Files in workspace'}</button>}
    </div>
    {navigationError && <p role="alert" className="text-sm text-red-800">Files could not be opened. Your lab is still here; try opening Files again.</p>}
    {preview && <CourseSamplePreview key={`${moduleId}:${enrollmentId}:${preview.documentId}`} moduleId={moduleId} enrollmentId={enrollmentId} documentId={preview.documentId} name={preview.name} onClose={() => setPreview(null)} />}
  </section>
}
