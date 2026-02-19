import { FileText, Loader2, MoreVertical, AlertTriangle } from 'lucide-react'
import type { Document } from '../../types/document'

interface FileRowProps {
  doc: Document
  onClick?: () => void
  onContextMenu: (e: React.MouseEvent) => void
}

export function FileRow({ doc, onClick, onContextMenu }: FileRowProps) {
  return (
    <tr
      className="hover:bg-[#a6b5c945]"
      onClick={onClick}
      onContextMenu={onContextMenu}
      style={{ borderBottom: '1px solid #dddddd', cursor: 'pointer' }}
    >
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center min-w-0">
          {/* Icon */}
          {doc.processing ? (
            <Loader2 className="h-4 w-4 animate-spin shrink-0" style={{ color: 'var(--highlight-color)' }} />
          ) : !doc.valid ? (
            <AlertTriangle className="h-4 w-4 shrink-0 text-red-500" />
          ) : (
            <FileText className="h-4 w-4 shrink-0" style={{ color: 'rgb(206, 206, 206)' }} />
          )}

          {/* File name */}
          <span
            style={{
              maxWidth: 300,
              paddingLeft: 10,
              paddingRight: 10,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              color: '#17181abb',
            }}
          >
            {doc.title}
          </span>

          {/* Date / status */}
          <span
            className="ml-2.5 shrink-0"
            style={{
              paddingLeft: 30,
              paddingRight: 30,
              color: '#17181a6e',
              fontSize: '0.8em',
              fontWeight: 300,
            }}
          >
            {doc.processing ? (
              <span style={{ color: 'var(--highlight-color)' }}>{doc.task_status || 'Processing...'}</span>
            ) : (
              doc.num_pages > 0 && `${doc.num_pages} pages`
            )}
          </span>

          {/* Ellipsis menu */}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onContextMenu(e)
            }}
            className="ml-auto bg-transparent border-0 cursor-pointer p-1 text-[#191919] hover:bg-black/5 rounded shrink-0"
          >
            <MoreVertical className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}
