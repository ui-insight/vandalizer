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
}

export function FileList({
  folders,
  documents,
  onFolderClick,
  onFolderContextMenu,
  onDocContextMenu,
  onDocClick,
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

  return (
    <table className="w-full" style={{ fontSize: '1.05em', borderCollapse: 'collapse' }}>
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
          />
        ))}
      </tbody>
    </table>
  )
}
