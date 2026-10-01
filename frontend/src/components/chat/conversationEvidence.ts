import type { ChatMessage } from '../../types/chat'
import { formatPageLocator } from '../../utils/pageLocator'

/** Export recorded provenance, never the selection that happens to be active later. */
export function conversationEvidence(message: ChatMessage): string {
  const lines: string[] = []
  if (message.request_scope) {
    const scope = message.request_scope
    lines.push('Scope when sent:', `Document IDs: ${scope.documents.join(', ') || 'None selected'}`, `Folder IDs: ${scope.folders.join(', ') || 'None selected'}`, `Knowledge base IDs: ${scope.knowledgeBases.join(', ') || 'None selected'}`, `Project ID: ${scope.project || 'None selected'}`)
  }
  if (message.source_documents?.length) {
    lines.push('Recorded input documents:')
    for (const doc of message.source_documents) lines.push(doc.truncated ? `${doc.truncated} additional documents were not recorded.` : `${doc.title || 'Document'}${doc.uuid ? ` (ID: ${doc.uuid})` : ''}`)
  }
  if (message.role === 'user' && !message.request_scope) lines.push('Full request scope was not recorded for this turn; the current selection is not used to infer it.')
  if (message.interruption) lines.push(message.interruption === 'stopped' ? 'Response stopped; this is partial output. Server work may continue.' : 'Connection interrupted; this is partial output. Server work may continue.')
  if (message.unsupported_figures?.length) lines.push(`Unconfirmed figures: ${message.unsupported_figures.join(', ')}. Check these against the source.`)
  if (message.citations?.length) {
    lines.push('Source references (inspect the originals before relying on the answer):')
    message.citations.forEach((source, index) => {
      const locator = formatPageLocator(source.page, source.page_approximate, source.page_end)
      lines.push(`[${index + 1}] ${source.document_title || 'Untitled source'}${locator ? ` · ${locator}` : ''}${source.sheet ? ` · Sheet: ${source.sheet}` : ''}`)
      if (source.kb_title || source.kb_uuid) lines.push(`Knowledge base: ${source.kb_title || source.kb_uuid}${source.kb_title && source.kb_uuid ? ` (ID: ${source.kb_uuid})` : ''}`)
      if (source.document_uuid || source.document_id) lines.push(`Document ID: ${source.document_uuid || source.document_id}`)
      if (source.url) lines.push(`URL: ${source.url}`)
      if (source.source_reference) lines.push(`Reference: ${source.source_reference}`)
      if (source.content_preview) lines.push(`Saved passage: ${source.content_preview}`)
      else lines.push('No passage preview was recorded.')
    })
  } else if (message.role === 'assistant') lines.push('No source references were recorded for this answer.')
  return lines.join('\n')
}
