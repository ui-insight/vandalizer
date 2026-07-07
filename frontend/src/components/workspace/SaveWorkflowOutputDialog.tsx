import { useEffect, useMemo, useState } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { X, Folder } from 'lucide-react'
import { listAllFolders, type FolderSummary } from '../../api/folders'
import { saveResultToFolder, type SaveOutputFormat } from '../../api/workflows'
import { useWorkspace } from '../../contexts/WorkspaceContext'

interface Props {
  sessionId: string
  workflowName?: string
  outputPreview?: unknown
  onClose: () => void
  onSaved: (folderUuid: string) => void
}

const FORMAT_OPTIONS: { value: SaveOutputFormat; label: string; ext: string }[] = [
  { value: 'pdf', label: 'PDF', ext: 'pdf' },
  { value: 'markdown', label: 'Markdown', ext: 'md' },
  { value: 'text', label: 'Plain text', ext: 'txt' },
  { value: 'csv', label: 'CSV (tables)', ext: 'csv' },
  { value: 'json', label: 'JSON', ext: 'json' },
]

export function SaveWorkflowOutputDialog({ sessionId, workflowName, outputPreview, onClose, onSaved }: Props) {
  const { activeProjectRootFolder } = useWorkspace()
  const [folders, setFolders] = useState<FolderSummary[]>([])
  const [folderUuid, setFolderUuid] = useState('')
  const [format, setFormat] = useState<SaveOutputFormat>('pdf')
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAllFolders()
      .then(list => {
        const sorted = [...list].sort((a, b) => a.path.localeCompare(b.path))
        setFolders(sorted)
        // In a project, default to its folder so results land back in the
        // project (and get re-indexed for chat) — the enrich flywheel.
        const projectMatch = activeProjectRootFolder
          && sorted.some(f => f.uuid === activeProjectRootFolder)
        setFolderUuid(projectMatch ? activeProjectRootFolder : (sorted[0]?.uuid ?? ''))
      })
      .catch(() => setFolders([]))
      .finally(() => setLoading(false))
  }, [activeProjectRootFolder])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (fileName) return
    const date = new Date().toISOString().slice(0, 10)
    const slug = (workflowName || 'workflow').trim().replace(/\s+/g, '_')
    setFileName(`${date}_${slug}_results`)
  }, [workflowName, fileName])

  const handleSubmit = async () => {
    if (!folderUuid) return
    setSaving(true)
    setError(null)
    try {
      await saveResultToFolder(sessionId, {
        folder_uuid: folderUuid,
        format,
        file_name: fileName.trim() || undefined,
      })
      onSaved(folderUuid)
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
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="save-output-dialog-title"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 id="save-output-dialog-title" className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <Folder size={18} className="text-gray-500" />
            Save output to folder
          </h3>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1 text-gray-400 hover:text-gray-600 rounded">
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
          <label htmlFor="save-output-folder" className="block text-sm font-medium text-gray-700 mb-1">Folder</label>
          <select
            id="save-output-folder"
            value={folderUuid}
            onChange={e => setFolderUuid(e.target.value)}
            disabled={loading || folders.length === 0}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          >
            {loading && <option value="">Loading folders…</option>}
            {!loading && folders.length === 0 && <option value="">No folders available</option>}
            {folders.map(f => (
              <option key={f.uuid} value={f.uuid}>
                {f.path}
              </option>
            ))}
          </select>
        </div>

        <div className="mb-4">
          <label htmlFor="save-output-format" className="block text-sm font-medium text-gray-700 mb-1">Format</label>
          <select
            id="save-output-format"
            value={format}
            onChange={e => setFormat(e.target.value as SaveOutputFormat)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          >
            {FORMAT_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>
                {opt.label} (.{opt.ext})
              </option>
            ))}
          </select>
        </div>

        <div className="mb-2">
          <label htmlFor="save-output-filename" className="block text-sm font-medium text-gray-700 mb-1">File name</label>
          <input
            id="save-output-filename"
            type="text"
            value={fileName}
            onChange={e => setFileName(e.target.value)}
            placeholder="2026-05-12_my_workflow_results"
            aria-invalid={!!error}
            aria-describedby={error ? 'save-output-error' : undefined}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-highlight"
          />
          <div className="text-xs text-gray-500 mt-1">Extension is added automatically.</div>
        </div>

        {error && <div id="save-output-error" role="alert" className="text-xs text-red-600 mb-2">{error}</div>}

        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving || !folderUuid}
            className="px-4 py-2 text-sm font-bold text-highlight-text bg-highlight hover:brightness-90 rounded-lg disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}
