import { useEffect, useMemo, useRef, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Folder as FolderIcon, Home, Users } from 'lucide-react'
import { listAllFolders, type FolderSummary } from '../../api/folders'
import type { Folder } from '../../types/document'

interface MoveFolderDialogProps {
  folder: Folder
  onSubmit: (parentId: string) => void | Promise<void>
  onClose: () => void
}

// A folder can only move within its own ownership boundary (personal stays
// personal, team stays in the same team) — crossing that line is what
// "Convert to team folder" is for, and the backend rejects it. Top level
// ("0") is personal, so it's only a valid destination for personal folders.
export function MoveFolderDialog({ folder, onSubmit, onClose }: MoveFolderDialogProps) {
  const [all, setAll] = useState<FolderSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [pending, setPending] = useState(false)
  const [moveError, setMoveError] = useState<string | null>(null)
  const submitting = useRef(false)
  const submit = async (destination: string) => {
    if (submitting.current) return
    submitting.current = true; setPending(true); setMoveError(null)
    try { await onSubmit(destination) }
    catch (error) { setMoveError(error instanceof Error ? error.message : 'Could not move. Choose a destination to retry.') }
    finally { submitting.current = false; setPending(false) }
  }
  const movingTeamId = folder.team_id ?? null

  useEffect(() => {
    let cancelled = false
    setError(null)
    listAllFolders()
      .then(data => { if (!cancelled) setAll(data) })
      .catch(() => { if (!cancelled) setError('Could not load folders.') })
    return () => { cancelled = true }
  }, [attempt])

  // Folders that are the moving folder itself or one of its descendants can't
  // be destinations — that would create a cycle.
  const excluded = useMemo(() => {
    const blocked = new Set<string>([folder.uuid])
    if (!all) return blocked
    let added = true
    while (added) {
      added = false
      for (const f of all) {
        if (!blocked.has(f.uuid) && blocked.has(f.parent_id)) {
          blocked.add(f.uuid)
          added = true
        }
      }
    }
    return blocked
  }, [all, folder.uuid])

  const destinations = useMemo(() => {
    if (!all) return []
    return all
      .filter(f => (f.team_id ?? null) === movingTeamId)
      .filter(f => !excluded.has(f.uuid))
      .filter(f => f.uuid !== folder.parent_id) // already there
      .sort((a, b) => a.path.localeCompare(b.path, undefined, { sensitivity: 'base' }))
  }, [all, excluded, movingTeamId, folder.parent_id])

  const showTopLevel = movingTeamId === null && folder.parent_id !== '0'

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !submitting.current) onClose()
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="flex w-full max-w-sm flex-col rounded-lg bg-white p-6 shadow-xl"
        style={{ maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="move-folder-dialog-title"
      >
        <div className="mb-1 flex items-center justify-between">
          <h3 id="move-folder-dialog-title" className="text-lg font-medium text-gray-900">Move folder</h3>
          <button disabled={pending} onClick={onClose} aria-label="Close" className="text-gray-500 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 break-words text-sm text-gray-500">
          Move <strong className="text-gray-700">{folder.title}</strong> to:
        </p>

        {error && <div role="alert" className="text-sm text-red-700">{error} <button onClick={() => setAttempt(value => value + 1)} className="rounded border px-2 py-1 underline">Retry folders</button></div>}
        {moveError && <p role="alert" className="mb-3 break-words text-sm text-red-700">{moveError}</p>}
        {pending && <p role="status" className="mb-2 text-sm text-gray-600">Moving…</p>}
        {!all && !error && <p className="text-sm text-gray-500">Loading folders…</p>}

        {all && !error && (
          <div className="min-h-0 max-h-72 overflow-y-auto rounded-md border border-gray-200">
            {!showTopLevel && destinations.length === 0 ? (
              <p className="px-3 py-4 text-sm text-gray-500">No other folders available.</p>
            ) : (
              <ul>
                {showTopLevel && (
                  <li>
                    <button
                      disabled={pending}
                      onClick={() => submit('0')}
                      className="flex w-full items-center gap-2.5 px-3 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04]"
                    >
                      <Home className="h-4 w-4 shrink-0 text-gray-500" />
                      Top level
                    </button>
                  </li>
                )}
                {destinations.map(d => {
                  const isTeam = !!d.team_id || d.is_shared_team_root
                  return (
                    <li key={d.uuid}>
                      <button
                        disabled={pending}
                        onClick={() => submit(d.uuid)}
                        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04]"
                      >
                        {isTeam
                          ? <Users className="h-4 w-4 shrink-0" style={{ color: 'rgb(0,128,128)' }} />
                          : <FolderIcon className="h-4 w-4 shrink-0 text-gray-500" />}
                        <span className="min-w-0 break-words">{d.path}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            disabled={pending}
            onClick={onClose}
            className="rounded-md px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
          >
            Cancel
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
