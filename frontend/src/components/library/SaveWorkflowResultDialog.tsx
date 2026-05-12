import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import type { Library, LibraryFolder } from '../../types/library'
import { listFolders, listLibraries } from '../../api/library'
import { saveResultToLibrary } from '../../api/workflows'

interface Props {
  sessionId: string
  teamId?: string | null
  outputPreview?: unknown
  onClose: () => void
  onSaved: () => void
}

export function SaveWorkflowResultDialog({ sessionId, teamId, outputPreview, onClose, onSaved }: Props) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [selectedLibraryId, setSelectedLibraryId] = useState('')
  const [folders, setFolders] = useState<LibraryFolder[]>([])
  const [folderUuid, setFolderUuid] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listLibraries(teamId ?? undefined)
      .then(libs => {
        const writable = libs.filter(l => l.scope !== 'verified')
        setLibraries(writable)
        setSelectedLibraryId(writable[0]?.id ?? '')
      })
      .catch(() => setLibraries([]))
  }, [teamId])

  const selectedLibrary = useMemo(
    () => libraries.find(l => l.id === selectedLibraryId) ?? null,
    [libraries, selectedLibraryId],
  )

  useEffect(() => {
    setFolderUuid('')
    if (!selectedLibrary) {
      setFolders([])
      return
    }
    listFolders(selectedLibrary.scope, selectedLibrary.team_id ?? undefined)
      .then(setFolders)
      .catch(() => setFolders([]))
  }, [selectedLibrary])

  const handleSubmit = async () => {
    if (!selectedLibraryId) return
    setSaving(true)
    setError(null)
    try {
      await saveResultToLibrary(sessionId, {
        library_id: selectedLibraryId,
        folder: folderUuid || null,
        note: note.trim() || undefined,
      })
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const previewText = useMemo(() => {
    if (outputPreview === null || outputPreview === undefined) return ''
    if (typeof outputPreview === 'string') return outputPreview
    try {
      return JSON.stringify(outputPreview, null, 2)
    } catch {
      return String(outputPreview)
    }
  }, [outputPreview])

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40" style={{ zIndex: 700 }}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Save result to library</h3>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded">
            <X size={18} />
          </button>
        </div>

        {previewText && (
          <div className="mb-4">
            <div className="text-xs font-medium text-gray-500 mb-1">Output preview</div>
            <pre className="bg-gray-50 border border-gray-200 rounded-md p-2 text-xs text-gray-700 max-h-32 overflow-auto whitespace-pre-wrap break-words">
              {previewText.length > 600 ? previewText.slice(0, 600) + '…' : previewText}
            </pre>
          </div>
        )}

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Library</label>
          <select
            value={selectedLibraryId}
            onChange={e => setSelectedLibraryId(e.target.value)}
            disabled={libraries.length === 0}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          >
            {libraries.length === 0 && <option value="">No libraries available</option>}
            {libraries.map(lib => (
              <option key={lib.id} value={lib.id}>
                {lib.title} ({lib.scope})
              </option>
            ))}
          </select>
        </div>

        {selectedLibrary && (
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Folder</label>
            <select
              value={folderUuid}
              onChange={e => setFolderUuid(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
            >
              <option value="">(none — top level)</option>
              {folders.map(f => (
                <option key={f.uuid} value={f.uuid}>{f.name}</option>
              ))}
            </select>
          </div>
        )}

        <div className="mb-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Note (optional)</label>
          <textarea
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
            placeholder="Add a note for future you…"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight resize-y"
          />
        </div>

        {error && <div className="text-xs text-red-600 mb-2">{error}</div>}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !selectedLibraryId}
            className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight hover:brightness-90 rounded-lg disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
