import { X, FileText, ExternalLink } from 'lucide-react'
import type { FileAttachment, UrlAttachment } from '../../types/chat'

interface Props {
  fileAttachments?: FileAttachment[]
  urlAttachments?: UrlAttachment[]
  onRemoveFile?: (id: string) => void
}

export function AttachmentList({ fileAttachments, urlAttachments, onRemoveFile }: Props) {
  if (!fileAttachments?.length && !urlAttachments?.length) return null

  return (
    <div className="flex flex-wrap gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
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
      {urlAttachments?.map((att) => (
        <div
          key={att.id}
          className="flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-xs text-gray-700 shadow-sm border border-gray-200"
        >
          <ExternalLink className="h-3 w-3 text-gray-400" />
          <span className="max-w-[120px] truncate">{att.title || att.url}</span>
        </div>
      ))}
    </div>
  )
}
