import { Loader2, MoreHorizontal, AlertTriangle, Shield, AlertCircle } from 'lucide-react'
import type { Document } from '../../types/document'
import { formatFileDate } from '../../utils/time'
import { stageCopy, isDocReady } from '../../utils/processingStatus'

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
  // Spinner stays on through the whole upload pipeline (text extraction +
  // RAG indexing), not just the `processing` flag which flips off early.
  const stillProcessing = !isDocReady(doc)
  return (
    <tr
      className="group hover:bg-[#a6b5c945]"
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
      <td style={{ padding: 0, width: 32 }} onClick={(e) => e.stopPropagation()}>
        {onToggleSelect && (
          <label
            className="flex items-center cursor-pointer"
            style={{ padding: '12px 4px 12px 15px' }}
          >
            <input
              type="checkbox"
              checked={!!selected}
              onChange={() => onToggleSelect(doc.uuid)}
              aria-label={`Select ${doc.title}`}
              className="h-4 w-4 cursor-pointer accent-[var(--highlight-color)]"
            />
          </label>
        )}
      </td>

      {/* Name + icon */}
      <td style={{ padding: '12px 15px' }}>
        <div className="flex items-center min-w-0">
          {stillProcessing ? (
            <Loader2 className="h-4 w-4 animate-spin shrink-0 mr-2.5" style={{ color: 'var(--highlight-color)' }} />
          ) : !doc.valid ? (
            <span
              className="shrink-0 mr-2.5 inline-flex items-center"
              role="img"
              aria-label={
                doc.validation_feedback
                  ? `Failed validation: ${doc.validation_feedback}`
                  : 'This document did not pass automated upload validation.'
              }
              title={
                doc.validation_feedback
                  ? `Failed validation: ${doc.validation_feedback}`
                  : 'This document did not pass automated upload validation.'
              }
            >
              <AlertTriangle className="h-4 w-4 text-red-500" />
            </span>
          ) : doc.ingest_error ? (
            <span
              className="shrink-0 mr-2.5 inline-flex items-center"
              role="img"
              aria-label={`Could not index this document for search: ${doc.ingest_error}. Chat and Knowledge Base retrieval will not work.`}
              title={`Could not index this document for search: ${doc.ingest_error}. Chat and Knowledge Base retrieval will not work.`}
            >
              <AlertCircle className="h-4 w-4 text-amber-500" />
            </span>
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

      {/* Modified — right-aligned, with hover-revealed action overlay */}
      <td
        style={{
          padding: '12px 15px',
          color: '#17181a6e',
          fontSize: '0.8em',
          fontWeight: 300,
          whiteSpace: 'nowrap',
          textAlign: 'right',
          position: 'relative',
        }}
        title={doc.updated_at || doc.created_at || undefined}
      >
        <span className="group-hover:opacity-0 transition-opacity">
          {stillProcessing ? (
            <span style={{ color: 'var(--highlight-color)' }}>{stageCopy(doc.task_status).short}</span>
          ) : (
            (doc.updated_at || doc.created_at) && formatFileDate(doc.updated_at || doc.created_at)
          )}
        </span>
        <div
          onClick={(e) => e.stopPropagation()}
          className="opacity-0 group-hover:opacity-100 transition-opacity"
          style={{
            position: 'absolute',
            right: 8,
            top: '50%',
            transform: 'translateY(-50%)',
            display: 'flex',
            alignItems: 'center',
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 999,
            padding: '2px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          }}
        >
          <button
            onClick={(e) => {
              e.stopPropagation()
              onContextMenu(e)
            }}
            className="bg-transparent border-0 cursor-pointer text-[#191919] hover:bg-black/5"
            style={{
              width: 28,
              height: 28,
              borderRadius: 14,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            aria-label="More options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  )
}
