import { documentIssue } from '../../utils/documentReadiness'
import { Loader2, MoreHorizontal, AlertTriangle, Shield, AlertCircle, CircleStop, RotateCw } from 'lucide-react'
import { FileTypeIcon } from './FileTypeIcon'
import { formatFileSize } from '../../utils/fileDisplay'
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
  /** Re-run the upload pipeline; offered only for an issue a retry can clear. */
  onRetry?: (doc: Document) => void
  retrying?: boolean
}

export function FileRow({ doc, onClick, onContextMenu, selected, onToggleSelect, snippet, onRetry, retrying }: FileRowProps) {
  // Spinner stays on through the whole upload pipeline (text extraction +
  // RAG indexing), not just the `processing` flag which flips off early.
  const stillProcessing = !isDocReady(doc)
  const issue = documentIssue(doc)
  return (
    <tr
      className="group hover:bg-[#a6b5c945]"
      tabIndex={0}
      role="row"
      aria-label={`Document: ${doc.title}`}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
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
            style={{ padding: "var(--workspace-space-12) var(--workspace-space-4) var(--workspace-space-12) 15px" }}
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
      <td style={{ padding: "var(--workspace-space-12) 15px" }}>
        <div className="flex items-center min-w-0">
          {stillProcessing ? (
            <Loader2 className="h-4 w-4 animate-spin shrink-0 mr-2.5" style={{ color: 'var(--highlight-on-light, #806600)' }} />
          ) : issue ? (
            // Decorative: the badge beside the name carries the words.
            issue.tone === 'error'
              ? <AlertTriangle className="h-4 w-4 shrink-0 mr-2.5 text-red-500" aria-hidden="true" />
              : issue.tone === 'neutral'
                ? <CircleStop className="h-4 w-4 shrink-0 mr-2.5 text-gray-500" aria-hidden="true" />
                : <AlertCircle className="h-4 w-4 shrink-0 mr-2.5 text-amber-500" aria-hidden="true" />
          ) : <FileTypeIcon extension={doc.extension} />}
          <div style={{ minWidth: 0, flex: 1 }}>
            <span className="flex items-center gap-1.5">
              <span className="file-name" title={doc.title}
                style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  color: '#17181abb',
                }}
              >
                {doc.title}
              </span>
              {issue && (
                // Short type on the row; the full reason on hover and for
                // screen readers, so a column of failures stays scannable.
                <span
                  className="shrink-0 rounded-full px-1.5 py-0.5 text-xs font-semibold"
                  style={issue.tone === 'error'
                    ? { backgroundColor: '#fee2e2', color: '#991b1b' }
                    : issue.tone === 'neutral'
                      ? { backgroundColor: '#e5e7eb', color: '#374151' }
                      : { backgroundColor: '#fef3c7', color: '#92400e' }}
                  title={issue.detail}
                >
                  {issue.label}
                  <span className="sr-only">. {issue.detail}</span>
                </span>
              )}
              {issue?.retryable && onRetry && (
                <button
                  type="button"
                  disabled={retrying}
                  onClick={(e) => { e.stopPropagation(); onRetry(doc) }}
                  onKeyDown={(e) => e.stopPropagation()}
                  aria-label={`Retry ${doc.title}`}
                  title="Read this file again and rebuild its search index"
                  className="shrink-0 inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-1.5 py-0.5 text-xs font-medium text-[#191919] hover:bg-black/5 disabled:opacity-50 cursor-pointer disabled:cursor-default"
                >
                  <RotateCw className={`h-3 w-3${retrying ? ' animate-spin' : ''}`} aria-hidden="true" />
                  {retrying ? 'Retrying…' : 'Retry'}
                </button>
              )}
              {(doc.version_number ?? 1) > 1 && (
                <span
                  className="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-600"
                  title={`Version ${doc.version_number}. Earlier versions are in Version history.`}
                >
                  v{doc.version_number}
                </span>
              )}
              {doc.classification && doc.classification !== 'unrestricted' && (
                <span
                  className="inline-flex items-center gap-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-xs font-semibold uppercase"
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
                  fontSize: 'var(--workspace-font-meta)',
                  color: '#6b7280',
                  lineHeight: 1.4,
                  marginTop: 'var(--workspace-space-2)',
                }}
              >
                {snippet}
              </span>
            )}
          </div>
        </div>
      </td>

      {/* Size */}
      <td
        className="file-size-cell"
        style={{
          padding: "var(--workspace-space-12) 15px",
          color: '#59616b',
          fontSize: 'var(--workspace-font-meta)',
          fontWeight: 300,
          whiteSpace: 'nowrap',
          textAlign: 'right',
        }}
      >
        {formatFileSize(doc.size_bytes)}
      </td>

      {/* Modified — right-aligned, with hover-revealed action overlay */}
      <td
        style={{
          padding: "var(--workspace-space-12) 15px",
          color: '#59616b',
          fontSize: 'var(--workspace-font-meta)',
          fontWeight: 300,
          whiteSpace: 'nowrap',
          textAlign: 'right',
          position: 'relative',
        }}
        title={doc.updated_at || doc.created_at || undefined}
      >
        <span className="file-modified-label">
          {stillProcessing ? (
            <span style={{ color: 'var(--highlight-on-light, #806600)' }}>{stageCopy(doc.task_status).short}</span>
          ) : (
            (doc.updated_at || doc.created_at) && formatFileDate(doc.updated_at || doc.created_at)
          )}
        </span>
        <div
          onClick={(e) => e.stopPropagation()}
          className="file-row-actions"
          style={{
            position: 'absolute',
            right: 4,
            top: '50%',
            transform: 'translateY(-50%)',
            display: 'flex',
            alignItems: 'center',
            background: '#fff',
            border: "1px solid var(--workspace-border)",
            borderRadius: 999,
            padding: "var(--workspace-space-2)",
            boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
          }}
        >
          <button
            type="button"
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
