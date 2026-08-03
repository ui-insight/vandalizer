import { useEffect, useMemo, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Folder as FolderIcon, Home, Users } from 'lucide-react'
import { listAllFolders, type FolderSummary } from '../../api/folders'

interface MoveFileDialogProps {
  fileNames: string[]
  // The folder the file(s) currently live in; null or "0" = top level.
  currentFolderId: string | null
  onSubmit: (folderId: string) => void
  onClose: () => void
}

// Files obey the same ownership boundary as folders: a personal file can only
// move within personal folders (or to the top level), a team file only within
// that team's folders — the backend rejects anything else. The file's team is
// derived from the folder it currently sits in, since documents don't carry
// team_id to the frontend.
export function MoveFileDialog({ fileNames, currentFolderId, onSubmit, onClose }: MoveFileDialogProps) {
  const [all, setAll] = useState<FolderSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fromFolderId = currentFolderId && currentFolderId !== '0' ? currentFolderId : null

  useEffect(() => {
    listAllFolders()
      .then(setAll)
      .catch(() => setError('Could not load folders.'))
  }, [])

  const movingTeamId = useMemo(() => {
    if (!fromFolderId || !all) return null
    return all.find(f => f.uuid === fromFolderId)?.team_id ?? null
  }, [all, fromFolderId])

  const destinations = useMemo(() => {
    if (!all) return []
    return all
      .filter(f => (f.team_id ?? null) === movingTeamId)
      .filter(f => f.uuid !== fromFolderId) // already there
      .sort((a, b) => a.path.localeCompare(b.path, undefined, { sensitivity: 'base' }))
  }, [all, movingTeamId, fromFolderId])

  const showTopLevel = movingTeamId === null && fromFolderId !== null

  const label = fileNames.length === 1 ? (
    <>Move <strong className="text-gray-700">{fileNames[0]}</strong> to:</>
  ) : (
    <>Move <strong className="text-gray-700">{fileNames.length} files</strong> to:</>
  )

  return (
    <div
      className="fixed inset-0 flex items-center justify-center bg-black/50"
      style={{ zIndex: 700 }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose()
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="move-file-dialog-title"
      >
        <div className="mb-1 flex items-center justify-between">
          <h3 id="move-file-dialog-title" className="text-lg font-medium text-gray-900">
            {fileNames.length === 1 ? 'Move file' : 'Move files'}
          </h3>
          <button onClick={onClose} aria-label="Close" className="text-gray-500 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 text-sm text-gray-500">{label}</p>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {!all && !error && <p className="text-sm text-gray-500">Loading folders…</p>}

        {all && !error && (
          <div className="max-h-72 overflow-y-auto rounded-md border border-gray-200">
            {!showTopLevel && destinations.length === 0 ? (
              <p className="px-3 py-4 text-sm text-gray-500">No other folders available.</p>
            ) : (
              <ul>
                {showTopLevel && (
                  <li>
                    <button
                      onClick={() => onSubmit('0')}
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
                        onClick={() => onSubmit(d.uuid)}
                        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-sm text-left text-[#111] hover:bg-black/[.04]"
                      >
                        {isTeam
                          ? <Users className="h-4 w-4 shrink-0" style={{ color: 'rgb(0,128,128)' }} />
                          : <FolderIcon className="h-4 w-4 shrink-0 text-gray-500" />}
                        <span className="truncate">{d.path}</span>
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
