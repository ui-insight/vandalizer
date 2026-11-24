import { useEffect, useState } from 'react'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { Download, Loader2, X } from 'lucide-react'
import { downloadFile, listFileVersions, type FileVersion } from '../../api/files'

/** Every stored version of a file, newest first. Older versions stay out of
 * the file list but remain here, and Pages built from them can compare. */
export function VersionHistoryDialog({ docUuid, docTitle, onClose }: { docUuid: string; docTitle: string; onClose: () => void }) {
  const [versions, setVersions] = useState<FileVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    listFileVersions(docUuid)
      .then(r => { if (!cancelled) setVersions(r.versions) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load version history') })
    return () => { cancelled = true }
  }, [docUuid])
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/50" style={{ zIndex: 700 }}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
        <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="version-history-title"
          style={{ maxHeight: '80vh', overflowY: 'auto' }}>
          <div className="mb-4 flex items-start justify-between gap-3">
            <div>
              <h3 id="version-history-title" className="text-lg font-medium text-gray-900">Version history</h3>
              <div className="text-sm text-gray-500" style={{ wordBreak: 'break-word' }}>{docTitle}</div>
            </div>
            <button onClick={onClose} aria-label="Close dialog" className="shrink-0 text-gray-500 hover:text-gray-600"><X className="h-5 w-5" /></button>
          </div>
          {error && <div role="alert" className="text-sm text-red-700">{error}</div>}
          {!versions && !error && <div role="status" className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" />Loading versions…</div>}
          {versions && <ul className="divide-y divide-gray-100">
            {versions.map(v => <li key={v.uuid} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <div style={{ minWidth: 0 }}>
                <div className="font-medium text-gray-900">Version {v.version_number}{v.current ? ' · current' : ''}{v.processing ? ' · reading…' : ''}</div>
                <div className="truncate text-gray-500" title={v.title}>{v.title}{v.created_at ? ` · ${new Date(v.created_at).toLocaleString()}` : ''}</div>
              </div>
              <button className="inline-flex shrink-0 items-center gap-1 rounded border border-gray-200 px-2 py-1 text-gray-700 hover:bg-gray-50"
                onClick={() => downloadFile(v.uuid)} aria-label={`Download version ${v.version_number}`}><Download className="h-4 w-4" />Download</button>
            </li>)}
          </ul>}
          <p className="mt-4 text-xs text-gray-500">To add a version, choose Upload new version on the file. Pages built from an earlier version show what changed and offer an update.</p>
        </div>
      </FocusTrap>
    </div>
  )
}
