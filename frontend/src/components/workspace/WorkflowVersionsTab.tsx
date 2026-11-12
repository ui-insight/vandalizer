import { useCallback, useEffect, useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { listWorkflowVersions, restoreWorkflowVersion, saveWorkflowVersion, type WorkflowVersionEntry, type WorkflowVersionHistory } from '../../api/workflows'
import { relativeTime } from '../../utils/time'
import { useConfirm } from '../shared/useConfirm'

const SOURCE_LABELS: Record<string, string> = {
  original: 'Original',
  chat: 'Chat edit',
  editor: 'Editor changes',
  restore: 'Restored',
}

function sourceLabel(version: WorkflowVersionEntry) {
  if (version.source === 'restore' && version.restored_from) return `Restored from version ${version.restored_from}`
  return SOURCE_LABELS[version.source] ?? 'Saved'
}

/**
 * A workflow's version history. Chat edits, restores and saved editor changes
 * each record a version; restoring one applies it as a new version, so the
 * history only grows and every state stays reachable.
 */
export function WorkflowVersionsTab({ workflowId, onRestored }: { workflowId: string; onRestored: () => unknown }) {
  const confirm = useConfirm()
  const [history, setHistory] = useState<WorkflowVersionHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [status, setStatus] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setHistory(await listWorkflowVersions(workflowId))
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the version history.')
    }
  }, [workflowId])

  useEffect(() => { void load() }, [load])

  const restore = async (version: WorkflowVersionEntry) => {
    const ok = await confirm({
      title: `Restore version ${version.number}?`,
      message: <>The workflow's steps and settings go back to version {version.number}{version.note ? <> (“{version.note}”)</> : null}. The current version stays in this history, so you can return to it.</>,
      confirmLabel: `Restore version ${version.number}`,
    })
    if (!ok) return
    setBusy(version.id); setStatus(null)
    try {
      const result = await restoreWorkflowVersion(workflowId, version.id)
      setStatus(`Restored version ${version.number} as version ${result.number}.${result.name_note ? ` ${result.name_note}` : ''}`)
      await onRestored()
      await load()
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : 'The version could not be restored.')
    } finally {
      setBusy(null)
    }
  }

  const save = async () => {
    setBusy('save'); setStatus(null)
    try {
      const result = await saveWorkflowVersion(workflowId, note.trim())
      setNote('')
      setStatus(`Saved as version ${result.number}.`)
      await load()
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : 'The version could not be saved.')
    } finally {
      setBusy(null)
    }
  }

  if (error) {
    return <div className="p-6 text-sm text-red-800" role="alert">{error} <button type="button" className="underline" onClick={() => void load()}>Try again</button></div>
  }
  if (!history) {
    return <div className="flex items-center gap-2 p-6 text-sm text-gray-700" role="status"><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Loading versions…</div>
  }

  const { versions, unsaved_changes: unsaved, can_manage: canManage } = history
  return (
    <div className="space-y-4 p-6 text-sm text-gray-900">
      <p className="text-gray-700">
        Changes made through chat are saved here as versions, labeled with what changed. Restore any version to make it current again; the version you leave stays in this list.
      </p>

      {canManage && unsaved && (
        <form className="space-y-2 rounded-lg border border-gray-300 p-3" onSubmit={event => { event.preventDefault(); void save() }}>
          <p className="font-medium">
            {versions.length ? 'This workflow has changes made in the editor since the last version.' : 'No versions saved yet.'}
          </p>
          <label className="block text-gray-700" htmlFor="workflow-version-note">What changed (optional)</label>
          <div className="flex flex-wrap gap-2">
            <input id="workflow-version-note" value={note} onChange={event => setNote(event.target.value)} maxLength={500}
              placeholder={versions.length ? 'Edited in the workflow editor' : 'Original'}
              className="min-h-10 min-w-0 flex-1 rounded-md border border-gray-300 px-3" />
            <button type="submit" disabled={busy !== null} className="min-h-10 rounded-md border border-gray-900 px-3 font-semibold disabled:opacity-50">
              {busy === 'save' ? 'Saving…' : 'Save version'}
            </button>
          </div>
        </form>
      )}

      {status && <p role="status" className="text-gray-800">{status}</p>}

      {versions.length === 0 ? (
        <p className="text-gray-700">When chat changes this workflow, or you save a version, it will appear here.</p>
      ) : (
        <ol className="divide-y divide-gray-200 rounded-lg border border-gray-300" aria-label="Workflow versions">
          {versions.map(version => (
            <li key={version.id} className="flex flex-wrap items-start gap-3 p-3">
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">Version {version.number}</span>
                  {version.is_current && <span className="rounded-full border border-green-700 px-2 text-xs font-semibold text-green-800">Current</span>}
                  <span className="text-xs text-gray-700">{sourceLabel(version)}</span>
                </div>
                <p className="[overflow-wrap:anywhere]">{version.note}</p>
                <p className="text-xs text-gray-700">
                  {version.created_at ? relativeTime(version.created_at) : ''}
                  {version.created_by_name ? ` · ${version.created_by_name}` : ''}
                  {version.step_names.length ? ` · ${version.step_names.length} step${version.step_names.length === 1 ? '' : 's'}: ${version.step_names.join(', ')}` : ''}
                </p>
              </div>
              {canManage && !version.is_current && (
                <button type="button" disabled={busy !== null} onClick={() => void restore(version)}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-md border border-gray-300 px-3 font-medium disabled:opacity-50"
                  aria-label={`Restore version ${version.number}`}>
                  {busy === version.id ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <RotateCcw className="h-4 w-4" aria-hidden />}
                  Restore
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
