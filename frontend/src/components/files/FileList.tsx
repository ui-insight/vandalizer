import { useId } from 'react'
import { ChevronUp, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react'
import type { Document, Folder } from '../../types/document'
import type { SortColumn, SortState } from './FileBrowser'
import { FolderRow } from './FolderRow'
import { FileRow } from './FileRow'
import { documentIssueSummary } from '../../utils/documentReadiness'
import { DOCUMENT_FILTER_LABELS, documentFilterCounts, visibleDocumentFilters, type DocumentFilter } from '../../utils/documentFilters'
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
  onRetryDoc?: (doc: Document) => void
  retryingUuids?: Set<string>
  /** Hide the folder rows, keeping the Folders heading to bring them back. */
  foldersCollapsed?: boolean
  onToggleFoldersCollapsed?: () => void
  /** Every document the list could show, before the chip filter. `documents`
   *  is what the active chip leaves; the chips count from this. */
  allDocuments?: Document[]
  documentFilter?: DocumentFilter
  onDocumentFilterChange?: (filter: DocumentFilter) => void
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
  onRetryDoc,
  retryingUuids,
  foldersCollapsed = false,
  onToggleFoldersCollapsed,
  allDocuments = documents,
  documentFilter = 'all',
  onDocumentFilterChange,
}: FileListProps) {
  const sectionId = useId()
  if (folders.length === 0 && allDocuments.length === 0) {
    return <FileBrowserTutorial highlighted={highlighted} />
  }

  const issueSummary = documentIssueSummary(allDocuments)
  const counts = documentFilterCounts(allDocuments)
  const chips = onDocumentFilterChange ? visibleDocumentFilters(counts) : []
  const shownFolders = foldersCollapsed ? [] : folders
  // Select all covers only rows on screen: a chip or a collapsed section must
  // never leave something selected that a bulk delete would then remove.
  const allUuids = [...shownFolders.map(f => f.uuid), ...documents.map(d => d.uuid)]
  const allSelected = onToggleSelect && selectedUuids && allUuids.length > 0 && allUuids.every(u => selectedUuids.has(u))

  const headerStyle: React.CSSProperties = {
    padding: "var(--workspace-space-8) 15px",
    textAlign: 'left',
    fontSize: 'var(--workspace-font-meta)',
    fontWeight: 500,
    color: '#555e68',
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
    <>
    {issueSummary && !chips.includes('attention') && (
      <p
        className="flex items-center gap-1.5"
        style={{ margin: 0, padding: 'var(--workspace-space-8) 15px', fontSize: 'var(--workspace-font-meta)', color: '#92400e', background: '#fffbeb', borderBottom: '1px solid #fde68a' }}
      >
        <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <span><span className="font-semibold">Files with problems:</span> {issueSummary}. Hover a badge for the reason.</span>
      </p>
    )}
    <table className="file-table w-full" style={{ fontSize: 'var(--workspace-font-body)', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
      <colgroup>
        <col style={{ width: 32 }} />
        <col />
        <col className="file-size-col" style={{ width: 96 }} />
        <col style={{ width: 110 }} />
      </colgroup>
      <thead>
        <tr style={{ borderBottom: '1px solid #dddddd' }}>
          <th scope="col" style={{ padding: "var(--workspace-space-8) 0 var(--workspace-space-8) 15px", width: 32 }}>
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
            className="file-size-cell"
            aria-sort={sort?.column === 'size' ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
            style={{ ...headerStyle, textAlign: 'right' }}
          >
            {onSort ? (
              <button
                type="button"
                onClick={() => onSort('size')}
                className="hover:bg-[#a6b5c945] hover:text-[#191919] transition-colors"
                style={{ ...sortButtonStyle, justifyContent: 'flex-end', width: '100%' }}
              >
                Size
                <SortIndicator column="size" sort={sort} />
              </button>
            ) : (
              <>Size<SortIndicator column="size" sort={sort} /></>
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
      {folders.length > 0 && (
      <tbody aria-labelledby={`${sectionId}-folders`}>
        <tr className="file-section-row">
          <th scope="rowgroup" colSpan={4} id={`${sectionId}-folders`}>
            {onToggleFoldersCollapsed ? (
              <button
                type="button"
                className="file-section-toggle"
                aria-expanded={!foldersCollapsed}
                onClick={onToggleFoldersCollapsed}
              >
                {foldersCollapsed
                  ? <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                  : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
                Folders <span className="file-section-count">{folders.length}</span>
              </button>
            ) : (
              <span className="file-section-title">Folders <span className="file-section-count">{folders.length}</span></span>
            )}
          </th>
        </tr>
        {shownFolders.map((folder) => (
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
      </tbody>
      )}
      {allDocuments.length > 0 && (
      <tbody aria-labelledby={`${sectionId}-documents`}>
        <tr className="file-section-row">
          <th scope="rowgroup" colSpan={4}>
            <div className="file-section-heading">
              <span className="file-section-title" id={`${sectionId}-documents`}>
                Documents <span className="file-section-count">{allDocuments.length}</span>
              </span>
              {chips.length > 0 && (
                <div role="group" aria-label="Show documents" className="file-filter-chips">
                  {chips.map(chip => (
                    <button
                      key={chip}
                      type="button"
                      className="file-filter-chip"
                      data-tone={chip === 'attention' ? 'attention' : undefined}
                      aria-pressed={documentFilter === chip}
                      title={chip === 'attention' && issueSummary ? `Files with problems: ${issueSummary}` : undefined}
                      onClick={() => onDocumentFilterChange?.(chip)}
                    >
                      {DOCUMENT_FILTER_LABELS[chip]} <span className="file-filter-count">{counts[chip]}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {documentFilter === 'attention' && issueSummary && (
              <p className="file-section-note" role="status">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>{issueSummary}. Hover a badge for the reason.</span>
              </p>
            )}
          </th>
        </tr>
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
            onRetry={onRetryDoc}
            retrying={retryingUuids?.has(doc.uuid)}
          />
        ))}
      </tbody>
      )}
    </table>
    </>
  )
}
