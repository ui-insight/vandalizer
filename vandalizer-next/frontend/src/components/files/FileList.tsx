import { FolderOpen } from 'lucide-react'
import type { Document, Folder } from '../../types/document'
import { FolderRow } from './FolderRow'
import { FileRow } from './FileRow'

interface FileListProps {
  folders: Folder[]
  documents: Document[]
  onFolderClick: (folderId: string) => void
  onFolderContextMenu: (folder: Folder, e: React.MouseEvent) => void
  onDocContextMenu: (doc: Document, e: React.MouseEvent) => void
  onDocClick?: (doc: Document) => void
  selectedUuids?: Set<string>
  onToggleSelect?: (uuid: string) => void
  onToggleAll?: () => void
  snippets?: Map<string, string>
}

export function FileList({
  folders,
  documents,
  onFolderClick,
  onFolderContextMenu,
  onDocContextMenu,
  onDocClick,
  selectedUuids,
  onToggleSelect,
  onToggleAll,
  snippets,
}: FileListProps) {
  if (folders.length === 0 && documents.length === 0) {
    return (
      <div style={{ padding: '40px 20px', textAlign: 'center', color: '#5d5f63' }}>
        <div className="flex flex-col items-center gap-3">
          <FolderOpen className="h-7 w-7" style={{ color: '#b0b3b8' }} />
          <div style={{ fontWeight: 600, color: '#2d2f33' }}>No files yet</div>
          <div style={{ fontSize: 13, maxWidth: 320 }}>
            Use the + Add button above or drag files in to get started. You can also
            create folders to keep things organized.
          </div>
        </div>
      </div>
    )
  }

  const allUuids = [...folders.map(f => f.uuid), ...documents.map(d => d.uuid)]
  const allSelected = onToggleSelect && selectedUuids && allUuids.length > 0 && allUuids.every(u => selectedUuids.has(u))

  return (
    <table className="w-full" style={{ fontSize: '1.05em', borderCollapse: 'collapse' }}>
      {onToggleSelect && allUuids.length > 0 && (
        <thead>
          <tr style={{ borderBottom: '1px solid #dddddd' }}>
            <th style={{ padding: '8px 0 8px 15px', width: 32 }}>
              <input
                type="checkbox"
                checked={!!allSelected}
                onChange={onToggleAll}
                className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
              />
            </th>
            <th style={{ padding: '8px 15px', textAlign: 'left', fontSize: '0.8em', fontWeight: 500, color: '#6b7280' }}>
              {selectedUuids && selectedUuids.size > 0 ? `${selectedUuids.size} selected` : 'Select all'}
            </th>
          </tr>
        </thead>
      )}
      <tbody>
        {folders.map((folder) => (
          <FolderRow
            key={folder.uuid}
            folder={folder}
            onClick={() => onFolderClick(folder.uuid)}
            onContextMenu={(e) => {
              e.preventDefault()
              onFolderContextMenu(folder, e)
            }}
            selected={selectedUuids?.has(folder.uuid)}
            onToggleSelect={onToggleSelect}
          />
        ))}
        {documents.map((doc) => (
          <FileRow
            key={doc.uuid}
            doc={doc}
            onClick={() => onDocClick?.(doc)}
            onContextMenu={(e) => {
              e.preventDefault()
              onDocContextMenu(doc, e)
            }}
            selected={selectedUuids?.has(doc.uuid)}
            onToggleSelect={onToggleSelect}
            snippet={snippets?.get(doc.uuid)}
          />
        ))}
      </tbody>
    </table>
  )
}
