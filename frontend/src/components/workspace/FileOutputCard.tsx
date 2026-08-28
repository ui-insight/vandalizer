import { Download, FileText } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { formatBytes, isMarkdownType, type FileOutputSummary } from './outputFilePayload'

/**
 * A file-producing step's result, shown as a file: name, type and size, a
 * download action, and — for text files — the content itself. Replaces the
 * pretty-printed `{type, filename, data_b64}` object that every result
 * surface used to show for these (support ticket: "internal code instead of
 * the output file"). The base64 never reaches the screen.
 */
export function FileOutputCard({ summary, downloadHref, onDownload, maxHeight = '60vh' }: {
  summary: FileOutputSummary
  /** Server download URL (run / batch results). */
  downloadHref?: string
  /** Client-side download (Test Step has no server-side result). */
  onDownload?: () => void
  maxHeight?: string | number
}) {
  const size = formatBytes(summary.sizeBytes)
  const meta = [summary.fileType.toUpperCase(), size].filter(Boolean).join(' · ')
  const hasDownload = Boolean(downloadHref || onDownload)

  const actionStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px',
    fontSize: 12, fontWeight: 600, fontFamily: 'inherit', textDecoration: 'none',
    border: '1px solid #d1d5db', borderRadius: 6, backgroundColor: '#fff',
    color: '#374151', cursor: 'pointer', flexShrink: 0,
  }

  return (
    <div data-testid="file-output-card">
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        border: '1px solid #e5e7eb', borderRadius: 6, backgroundColor: '#f9fafb',
        padding: '10px 12px',
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 6, backgroundColor: '#eef2ff',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <FileText style={{ width: 18, height: 18, color: '#4f46e5' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#202124', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={summary.filename}>
            {summary.filename}
          </div>
          <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
            {meta}{summary.text === null ? ' · download to open' : ''}
          </div>
        </div>
        {hasDownload && (downloadHref ? (
          <a href={downloadHref} download={summary.filename} style={actionStyle} aria-label={`Download ${summary.filename}`}>
            <Download style={{ width: 14, height: 14 }} />
            Download
          </a>
        ) : (
          <button type="button" onClick={onDownload} style={actionStyle} aria-label={`Download ${summary.filename}`}>
            <Download style={{ width: 14, height: 14 }} />
            Download
          </button>
        ))}
      </div>
      {summary.text !== null && (
        isMarkdownType(summary.fileType) ? (
          <div
            className="chat-markdown"
            style={{
              marginTop: 8, backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
              padding: 12, fontSize: 13, lineHeight: 1.6,
              maxHeight, overflowY: 'auto', overflowX: 'auto',
              color: '#374151', wordBreak: 'break-word',
            }}
            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(summary.text) as string) }}
          />
        ) : (
          <pre style={{
            marginTop: 8, backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: 6,
            padding: 12, fontSize: 12, lineHeight: 1.5, fontFamily: 'monospace',
            maxHeight, overflow: 'auto', color: '#374151', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          }}>
            {summary.text}
          </pre>
        )
      )}
      {summary.textTruncated && (
        <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
          Preview cut at {Math.round(summary.text!.length / 1000)}k characters — download the file for the rest.
        </div>
      )}
    </div>
  )
}
