import { useRef, useState } from 'react'
import { Check, FileText } from 'lucide-react'
import { saveWorkflowArtifact, type Artifact } from '../../api/artifacts'
import { PageActions } from '../artifacts/PagePrimitives'
import { announceWorkspaceWrite } from '../../lib/chatWrites'

export function WorkflowArtifactAction({ sessionId }: { sessionId: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [page, setPage] = useState<Artifact | null>(null)
  const pending = useRef(false)
  return <div className="mt-3 rounded-xl border border-slate-200 bg-white p-4">
    {page ? <><p className="mb-3 flex items-center gap-2 text-sm font-medium"><Check size={16} className="text-emerald-700" />{page.title} · saved to Pages</p><PageActions uuid={page.uuid} revision={page.latest_revision} title={page.title} /></> : <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold">Keep this result as a page</p><p className="mt-1 text-xs text-slate-500">A private, shareable copy you can find in Files → Pages.</p></div><button type="button" disabled={busy} className="page-button" onClick={async () => {
      if (pending.current) return
      pending.current = true; setBusy(true); setError('')
      try { setPage(await saveWorkflowArtifact(sessionId)); announceWorkspaceWrite('pages') }
      catch (e) { setError(e instanceof Error ? e.message : 'Could not save page.') }
      finally { pending.current = false; setBusy(false) }
    }}><FileText size={16} />{busy ? 'Saving page…' : 'Save as page'}</button></div>}
    {error && <p role="alert" className="page-alert mt-3">{error}</p>}
  </div>
}
