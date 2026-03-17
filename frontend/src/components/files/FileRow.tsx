import { Loader2, MoreVertical, AlertTriangle, Shield } from 'lucide-react'
import type { Document } from '../../types/document'
import { formatFileDate } from '../../utils/time'

const CLASSIFICATION_STYLES: Record<string, { bg: string; text: string }> = {
  unrestricted: { bg: '#dcfce7', text: '#166534' },
  internal: { bg: '#dbeafe', text: '#1e40af' },
  ferpa: { bg: '#fef3c7', text: '#92400e' },
  cui: { bg: '#ffedd5', text: '#9a3412' },
  itar: { bg: '#fee2e2', text: '#991b1b' },
}

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
      tabIndex={0}
      role="row"
      aria-label={`Document: ${doc.title}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
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
            aria-label={`Select ${doc.title}`}
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
            <span className="flex items-center gap-1.5">
              <span
                style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  color: '#17181abb',
                }}
              >
                {doc.title}
              </span>
              {doc.classification && doc.classification !== 'unrestricted' && (
                <span
                  className="inline-flex items-center gap-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                  style={{
                    backgroundColor: CLASSIFICATION_STYLES[doc.classification]?.bg || '#f3f4f6',
                    color: CLASSIFICATION_STYLES[doc.classification]?.text || '#374151',
                  }}
                  title={`Classification: ${doc.classification}`}
                >
                  <Shield className="h-2.5 w-2.5" />
                  {doc.classification}
                </span>
              )}
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
          aria-label="More options"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </td>
    </tr>
  )
}
