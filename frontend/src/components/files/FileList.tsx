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

  const sortButtonStyle: React.CSSProperties = {
    font: 'inherit',
    color: 'inherit',
    background: 'none',
    border: 'none',
    padding: 0,
    margin: 0,
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    whiteSpace: 'nowrap',
  }

  return (
    <table className="w-full" style={{ fontSize: '1.05em', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <colgroup>
        <col style={{ width: 32 }} />
        <col />
        <col style={{ width: 110 }} />
      </colgroup>
      <thead>
        <tr style={{ borderBottom: '1px solid #dddddd' }}>
          <th scope="col" style={{ padding: '8px 0 8px 15px', width: 32 }}>
            {onToggleSelect && allUuids.length > 0 && (
              <input
                type="checkbox"
                checked={!!allSelected}
                onChange={onToggleAll}
                aria-label="Select all"
                className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
              />
            )}
          </th>
          <th
            scope="col"
            aria-sort={sort?.column === 'name' ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
            style={headerStyle}
          >
            {onSort ? (
              <button
                type="button"
                onClick={() => onSort('name')}
                className="hover:bg-[#a6b5c945] hover:text-[#191919] transition-colors"
                style={sortButtonStyle}
              >
                Name
                <SortIndicator column="name" sort={sort} />
              </button>
            ) : (
              <>Name<SortIndicator column="name" sort={sort} /></>
            )}
          </th>
          <th
            scope="col"
            aria-sort={sort?.column === 'modified' ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
            style={{ ...headerStyle, textAlign: 'right', paddingRight: 15 }}
          >
            {onSort ? (
              <button
                type="button"
                onClick={() => onSort('modified')}
                className="hover:bg-[#a6b5c945] hover:text-[#191919] transition-colors"
                style={{ ...sortButtonStyle, justifyContent: 'flex-end', width: '100%' }}
              >
                Modified
                <SortIndicator column="modified" sort={sort} />
              </button>
            ) : (
              <>Modified<SortIndicator column="modified" sort={sort} /></>
            )}
          </th>
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
