import { FolderOpen } from 'lucide-react'
import type { Document, Folder } from '../../types/document'
import { FolderRow } from './FolderRow'
import { FileRow } from './FileRow'
import { FileBrowserTutorial } from '../workspace/FileBrowserTutorial'

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
  onDropFile?: (fileUuid: string, folderUuid: string) => void
  highlighted?: boolean
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
  onDropFile,
  highlighted,
}: FileListProps) {
  if (folders.length === 0 && documents.length === 0) {
    return <FileBrowserTutorial highlighted={highlighted} />
  }

  const allUuids = [...folders.map(f => f.uuid), ...documents.map(d => d.uuid)]
  const allSelected = onToggleSelect && selectedUuids && allUuids.length > 0 && allUuids.every(u => selectedUuids.has(u))

  return (
    <table className="w-full" style={{ fontSize: '1.05em', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
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
            onDropFile={onDropFile}
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
