import { useState } from 'react'
import { X, FileText, ExternalLink, FolderOpen, BookOpen, Link2, Loader2, Check, Share2 } from 'lucide-react'
import type { FileAttachment, UrlAttachment } from '../../types/chat'
import type { AttachedKB } from '../../contexts/WorkspaceContext'

// Documents, folders and knowledge bases all answer the same question — what is
// this conversation looking at — so they share one chip row. Type is carried by
// icon *and* tag *and* tint together, never tint alone: --highlight-color is
// deploy-customizable, so a second semantic colour wouldn't survive theming,
// and colour alone is invisible to a colourblind reader either way.

const CHIP = 'flex max-w-full min-w-0 flex-wrap items-center gap-1.5 rounded-xl px-3 py-1 text-xs text-gray-700 shadow-sm border'
const TAG = 'shrink-0 text-xs font-semibold uppercase tracking-wide'
const ICON_BTN = 'ml-1 shrink-0 rounded p-1 text-gray-600 hover:text-red-700'

// Knowledge bases (capped at three) and folders set the conversation's scope, so
// they always render. Documents are unbounded — a heavy library selection would
// otherwise wrap far enough down to push the scope chips out of view.
const DOCS_SHOWN_COLLAPSED = 6

interface Props {
  fileAttachments?: FileAttachment[]
  urlAttachments?: UrlAttachment[]
  selectedDocUuids?: string[]
  selectedDocNames?: Record<string, string>
  /** uuid → true while a selected doc is still extracting text (OCR/indexing). */
  processingByUuid?: Record<string, boolean>
  documentErrors?: Record<string, string>
  selectedFolderUuids?: string[]
  selectedFolderNames?: Record<string, string>
  knowledgeBases?: AttachedKB[]
  knowledgeHealth?: Record<string, string>
  onRemoveFile?: (id: string) => void
  onRemoveUrl?: (id: string) => void
  onDeselectDoc?: (uuid: string) => void
  onDeselectFolder?: (uuid: string) => void
  onDetachKB?: (uuid: string) => void
  onShareKB?: (kb: AttachedKB) => void
  /** Copy a link that opens a chat with these knowledge bases, documents and folders attached. */
  onShareSetup?: () => void
}

export function AttachmentList({
  fileAttachments, urlAttachments, selectedDocUuids, selectedDocNames, processingByUuid, documentErrors,
  selectedFolderUuids, selectedFolderNames, knowledgeBases, knowledgeHealth,
  onRemoveFile, onRemoveUrl, onDeselectDoc, onDeselectFolder, onDetachKB, onShareKB, onShareSetup,
}: Props) {
  const [expanded, setExpanded] = useState(false)

  // Scope chips: bounded, always visible.
  const scopeChips = [
    ...(knowledgeBases ?? []).map(kb => (
      <div
        key={`kb-${kb.uuid}`}
        className={`${CHIP} font-semibold`}
        style={{
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 16%, white)',
          borderColor: "color-mix(in srgb, var(--highlight-color, #eab308) 45%, var(--workspace-border))",
          color: '#424a55',
        }}
      >
        <BookOpen className="h-3 w-3 shrink-0" />
        <span className={TAG}>KB</span>
        <span className="break-words">{kb.title}</span>
        <span className="text-xs font-normal">
          {knowledgeHealth?.[kb.uuid] ?? 'Source status unavailable'}
        </span>
        {onShareKB && (
          <button
            type="button"
            aria-label={`Copy share link for knowledge base: ${kb.title}`}
            title="Copy share link"
            onClick={() => onShareKB(kb)}
            className="ml-1 opacity-70 hover:opacity-100"
          >
            <Link2 className="h-3 w-3" />
          </button>
        )}
        {onDetachKB && (
          <button
            type="button"
            aria-label={`Detach knowledge base: ${kb.title}`}
            onClick={() => onDetachKB(kb.uuid)}
            className={ICON_BTN}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    )),
    ...(selectedFolderUuids ?? []).map(uuid => {
      const name = selectedFolderNames?.[uuid] || 'Untitled folder'
      return (
        <div key={`folder-${uuid}`} className={`${CHIP} border-gray-200 bg-white`}>
          <FolderOpen className="h-3 w-3 shrink-0 text-gray-500" />
          <span className={TAG}>Folder</span>
          <span className="max-w-full break-words">{name}</span>
          {onDeselectFolder && (
            <button
              type="button"
              aria-label={`Deselect folder: ${name}`}
              onClick={() => onDeselectFolder(uuid)}
              className={ICON_BTN}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      )
    }),
  ]

  // Document chips: unbounded, collapsed past DOCS_SHOWN_COLLAPSED.
  const docChips = [
    // File browser selections
    ...(selectedDocUuids ?? []).map(uuid => {
      const name = selectedDocNames?.[uuid] || 'Document'
      const processing = processingByUuid?.[uuid]
      return (
        <div
          key={`doc-${uuid}`}
          className={CHIP}
          style={{
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
            borderColor: "color-mix(in srgb, var(--highlight-color, #eab308) 30%, var(--workspace-border))",
          }}
        >
          {processing
            ? <Loader2 className="h-3 w-3 shrink-0 animate-spin" style={{ color: 'var(--highlight-color, #eab308)' }} />
            : <FileText className="h-3 w-3 shrink-0" style={{ color: 'var(--highlight-color, #eab308)' }} />}
          <span className="max-w-full break-words">{name}</span>
          {documentErrors?.[uuid] ? <span className="text-xs text-red-700" title={documentErrors[uuid]}>Processing failed · open Files to retry</span> : processing
            ? <span className="text-xs italic text-gray-500">processing…</span>
            : processingByUuid && <span className="inline-flex items-center gap-1 text-xs text-green-700"><Check className="h-3 w-3 shrink-0" />Ready</span>}
          {onDeselectDoc && (
            <button
              type="button"
              aria-label={`Deselect ${name}`}
              onClick={() => onDeselectDoc(uuid)}
              className={ICON_BTN}
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      )
    }),
    // Chat file attachments
    ...(fileAttachments ?? []).map(att => (
      <div key={att.id} className={`${CHIP} border-gray-200 bg-white`}>
        <FileText className="h-3 w-3 shrink-0 text-gray-500" />
        <span className="max-w-full break-words">{att.filename}</span>
        {onRemoveFile && (
          <button
            type="button"
            aria-label={`Remove ${att.filename}`}
            onClick={() => onRemoveFile(att.id)}
            className={ICON_BTN}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    )),
    // URL attachments
    ...(urlAttachments ?? []).map(att => (
      <div key={att.id} className={`${CHIP} border-gray-200 bg-white`}>
        <a
          href={att.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-gray-700 hover:text-gray-900"
        >
          <ExternalLink className="h-3 w-3 shrink-0 text-gray-500" />
          <span className="max-w-full break-words">{att.title || att.url}</span>
        </a>
        {onRemoveUrl && (
          <button
            type="button"
            aria-label={`Remove ${att.title || att.url}`}
            onClick={() => onRemoveUrl(att.id)}
            className={ICON_BTN}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    )),
  ]

  if (!scopeChips.length && !docChips.length) return null

  const hidden = expanded ? 0 : Math.max(0, docChips.length - DOCS_SHOWN_COLLAPSED)

  return (
    <div role="region" aria-label="Conversation sources" tabIndex={0} className="chat-attachment-list flex flex-wrap gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
      {scopeChips}
      {hidden ? docChips.slice(0, DOCS_SHOWN_COLLAPSED) : docChips}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className={`${CHIP} border-gray-300 bg-white hover:bg-gray-100`}
        >
          +{hidden} more
        </button>
      )}
      {expanded && docChips.length > DOCS_SHOWN_COLLAPSED && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className={`${CHIP} border-gray-300 bg-white hover:bg-gray-100`}
        >
          Show fewer
        </button>
      )}
      {onShareSetup && (
        <button
          type="button"
          onClick={onShareSetup}
          title="Copy a link that opens a new chat with these knowledge bases, documents and folders attached"
          className={`${CHIP} ml-auto border-gray-300 bg-white font-semibold hover:bg-gray-100`}
        >
          <Share2 className="h-3 w-3 shrink-0" />
          Share chat setup
        </button>
      )}
    </div>
  )
}
