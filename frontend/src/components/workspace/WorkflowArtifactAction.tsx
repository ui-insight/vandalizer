import { useRef, useState } from 'react'
import { saveWorkflowArtifact } from '../../api/artifacts'

export function WorkflowArtifactAction({ sessionId }: { sessionId: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [uuid, setUuid] = useState('')
  const pending = useRef(false)
  return <div className="flex flex-wrap items-center gap-2">
    <button type="button" disabled={busy} className="rounded border bg-white px-3 py-2 text-sm disabled:opacity-50" onClick={async () => {
      if (pending.current) return
      pending.current = true; setBusy(true); setError('')
      try { setUuid((await saveWorkflowArtifact(sessionId)).uuid) }
      catch (e) { setError(e instanceof Error ? e.message : 'Could not save artifact.') }
      finally { pending.current = false; setBusy(false) }
    }}>{busy ? 'Saving artifact…' : 'Save as Artifact'}</button>
    {uuid && <a className="text-sm underline" href={`/artifacts/${uuid}`} target="_blank" rel="noreferrer">Open private artifact</a>}
    {error && <p role="alert" className="w-full text-sm text-red-700">{error}</p>}
  </div>
}
