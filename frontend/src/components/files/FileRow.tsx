import { Loader2, MoreVertical, AlertTriangle } from 'lucide-react'
import type { Document } from '../../types/document'
import { formatFileDate } from '../../utils/time'

interface FileRowProps {
  doc: Document
  onClick?: () => void
  onContextMenu: (e: React.MouseEvent) => void
  selected?: boolean
  onToggleSelect?: (uuid: string) => void
  snippet?: string
}

export function FileRow({ doc, onClick, onContextMenu, selected, onToggleSelect, snippet }: FileRowProps) {
  return (
    <tr
      className="hover:bg-[#a6b5c945]"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', doc.uuid)
      }}
      onClick={(e) => {
        if (e.button === 0) onClick?.()
      }}
      onContextMenu={(e) => {
        e.preventDefault()
        onContextMenu(e)
      }}
      style={{ borderBottom: '1px solid #dddddd', cursor: 'pointer' }}
    >
      {/* Checkbox */}
      <td style={{ padding: '12px 0 12px 15px', width: 32 }}>
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect(doc.uuid)}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
          />
        )}
      </td>

      {/* Name + icon */}
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center min-w-0">
          {doc.processing ? (
            <Loader2 className="h-4 w-4 animate-spin shrink-0 mr-2.5" style={{ color: 'var(--highlight-color)' }} />
          ) : !doc.valid ? (
            <AlertTriangle className="h-4 w-4 shrink-0 mr-2.5 text-red-500" />
          ) : null}
          <div style={{ minWidth: 0, flex: 1 }}>
            <span
              style={{
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                color: '#17181abb',
              }}
            >
              {doc.title}
            </span>
            {snippet && (
              <span
                style={{
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  fontSize: '0.78em',
                  color: '#6b7280',
                  lineHeight: 1.4,
                  marginTop: 2,
                }}
              >
                {snippet}
              </span>
            )}
          </div>
        </div>
      </td>

      {/* Modified */}
      <td
        style={{
          padding: '12px 15px',
          color: '#17181a6e',
          fontSize: '0.8em',
          fontWeight: 300,
          whiteSpace: 'nowrap',
        }}
        title={doc.updated_at || doc.created_at || undefined}
      >
        {doc.processing ? (
          <span style={{ color: 'var(--highlight-color)' }}>{doc.task_status || 'Processing...'}</span>
        ) : (
          (doc.updated_at || doc.created_at) && formatFileDate(doc.updated_at || doc.created_at)
        )}
      </td>

      {/* Menu */}
      <td style={{ padding: '12px 4px', width: 40 }}>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onContextMenu(e)
          }}
          className="bg-transparent border-0 cursor-pointer p-1 text-[#191919] hover:bg-black/5 rounded"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </td>
    </tr>
  )
}
