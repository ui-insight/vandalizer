import { ChevronUp, ChevronDown } from 'lucide-react'
import type { Document, Folder } from '../../types/document'
import type { SortColumn, SortState } from './FileBrowser'
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
  sort?: SortState
  onSort?: (column: SortColumn) => void
  watchedFolderUuids?: Set<string>
}

function SortIndicator({ column, sort }: { column: SortColumn; sort?: SortState }) {
  if (!sort || sort.column !== column) return null
  return sort.direction === 'asc'
    ? <ChevronUp className="inline h-3.5 w-3.5 ml-0.5" />
    : <ChevronDown className="inline h-3.5 w-3.5 ml-0.5" />
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
  sort,
  onSort,
  watchedFolderUuids,
}: FileListProps) {
  if (folders.length === 0 && documents.length === 0) {
    return <FileBrowserTutorial highlighted={highlighted} />
  }

  const allUuids = [...folders.map(f => f.uuid), ...documents.map(d => d.uuid)]
  const allSelected = onToggleSelect && selectedUuids && allUuids.length > 0 && allUuids.every(u => selectedUuids.has(u))

  const headerStyle: React.CSSProperties = {
    padding: '8px 15px',
    textAlign: 'left',
    fontSize: '0.8em',
    fontWeight: 500,
    color: '#6b7280',
    cursor: onSort ? 'pointer' : undefined,
    userSelect: 'none',
    whiteSpace: 'nowrap',
  }

  return (
    <table className="w-full" style={{ fontSize: '1.05em', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <colgroup>
        <col style={{ width: 32 }} />
        <col />
        <col style={{ width: 140 }} />
        <col style={{ width: 40 }} />
      </colgroup>
      <thead>
        <tr style={{ borderBottom: '1px solid #dddddd' }}>
          <th style={{ padding: '8px 0 8px 15px', width: 32 }}>
            {onToggleSelect && allUuids.length > 0 && (
              <input
                type="checkbox"
                checked={!!allSelected}
                onChange={onToggleAll}
                className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
              />
            )}
          </th>
          <th
            style={headerStyle}
            onClick={() => onSort?.('name')}
          >
            Name
            <SortIndicator column="name" sort={sort} />
          </th>
          <th
            style={headerStyle}
            onClick={() => onSort?.('modified')}
          >
            Modified
            <SortIndicator column="modified" sort={sort} />
          </th>
          <th style={{ width: 40 }} />
        </tr>
      </thead>
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
            isWatched={watchedFolderUuids?.has(folder.uuid)}
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
