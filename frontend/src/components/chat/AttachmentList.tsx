import { X, FileText, ExternalLink, FolderOpen } from 'lucide-react'
import type { FileAttachment, UrlAttachment } from '../../types/chat'

interface Props {
  fileAttachments?: FileAttachment[]
  urlAttachments?: UrlAttachment[]
  selectedDocUuids?: string[]
  selectedDocNames?: Record<string, string>
  onRemoveFile?: (id: string) => void
  onRemoveUrl?: (id: string) => void
  onDeselectDoc?: (uuid: string) => void
}

export function AttachmentList({ fileAttachments, urlAttachments, selectedDocUuids, selectedDocNames, onRemoveFile, onRemoveUrl, onDeselectDoc }: Props) {
  const hasFileAttachments = !!fileAttachments?.length
  const hasUrlAttachments = !!urlAttachments?.length
  const hasSelectedDocs = !!selectedDocUuids?.length

  if (!hasFileAttachments && !hasUrlAttachments && !hasSelectedDocs) return null

  return (
    <div className="flex flex-wrap gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
      {/* File browser selections */}
      {selectedDocUuids?.map((uuid) => (
        <div
          key={`doc-${uuid}`}
          className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs text-gray-700 shadow-sm border"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
            borderColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 30%, #e5e7eb)',
          }}
        >
          <FolderOpen className="h-3 w-3 shrink-0" style={{ color: 'var(--highlight-color, #eab308)' }} />
          <span className="max-w-[120px] truncate">{selectedDocNames?.[uuid] || 'Document'}</span>
          {onDeselectDoc && (
            <button
              onClick={() => onDeselectDoc(uuid)}
              className="ml-1 text-gray-400 hover:text-red-500"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}
      {/* Chat file attachments */}
      {fileAttachments?.map((att) => (
        <div
          key={att.id}
          className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-gray-700 shadow-sm border border-gray-200"
        >
          <FileText className="h-3 w-3 text-gray-400" />
          <span className="max-w-[120px] truncate">{att.filename}</span>
          {onRemoveFile && (
            <button
              onClick={() => onRemoveFile(att.id)}
              className="ml-1 text-gray-400 hover:text-red-500"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}
      {/* URL attachments */}
      {urlAttachments?.map((att) => (
        <div
          key={att.id}
          className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-gray-700 shadow-sm border border-gray-200"
        >
          <a
            href={att.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-gray-700 hover:text-gray-900"
          >
            <ExternalLink className="h-3 w-3 text-gray-400" />
            <span className="max-w-[120px] truncate">{att.title || att.url}</span>
          </a>
          {onRemoveUrl && (
            <button
              onClick={() => onRemoveUrl(att.id)}
              className="ml-1 text-gray-400 hover:text-red-500"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
