import type { ChatMessage } from '../../types/chat'
import { formatPageLocator } from '../../utils/pageLocator'

/** "Budget.xlsx, Award.pdf and 1 other": the names known for ``ids``, the rest counted. */
function namedList(ids: string[], names: Record<string, string>): string {
  const known = ids.map((id) => names[id]).filter((name): name is string => Boolean(name))
  const others = ids.length - known.length
  if (others === 0) return known.join(', ')
  if (known.length === 0) return `${others} not named in this export`
  return `${known.join(', ')} and ${others} other${others === 1 ? '' : 's'}`
}

/**
 * Export recorded provenance, never the selection that happens to be active later.
 *
 * ``names`` maps a document, folder, knowledge base or project ID to its title.
 * The selection used to print on every message as raw IDs, with "None
 * selected" for each kind even when nothing was selected (support ticket).
 */
export function conversationEvidence(message: ChatMessage, names: Record<string, string> = {}): string {
  const lines: string[] = []
  const scope = message.request_scope
  if (scope) {
    const recorded = { ...names }
    for (const doc of message.source_documents ?? []) if (doc.uuid && doc.title) recorded[doc.uuid] = doc.title
    const selected = [
      ['Documents', scope.documents],
      ['Folders', scope.folders],
      ['Knowledge bases', scope.knowledgeBases],
      ['Project', scope.project ? [scope.project] : []],
    ] as const
    const parts = selected.filter(([, ids]) => ids.length > 0).map(([label, ids]) => `${label}: ${namedList([...ids], recorded)}`)
    if (parts.length) lines.push('Selected when sent:', ...parts)
  }
  if (message.source_documents?.length) {
    lines.push('Recorded input documents:')
    for (const doc of message.source_documents) lines.push(doc.truncated ? `${doc.truncated} additional documents were not recorded.` : doc.title || (doc.uuid ? `Document ID: ${doc.uuid}` : 'Document'))
  }
  if (message.interruption) lines.push(message.interruption === 'stopped' ? 'Response stopped; this is partial output. Server work may continue.' : 'Connection interrupted; this is partial output. Server work may continue.')
  if (message.unsupported_figures?.length) lines.push(`Unconfirmed figures: ${message.unsupported_figures.join(', ')}. Check these against the source.`)
  if (message.citations?.length) {
    lines.push('Source references (inspect the originals before relying on the answer):')
    message.citations.forEach((source, index) => {
      const locator = formatPageLocator(source.page, source.page_approximate, source.page_end)
      lines.push(`[${index + 1}] ${source.document_title || 'Untitled source'}${locator ? ` · ${locator}` : ''}${source.sheet ? ` · Sheet: ${source.sheet}` : ''}`)
      if (source.kb_title || source.kb_uuid) lines.push(`Knowledge base: ${source.kb_title || source.kb_uuid}`)
      if (!source.document_title && (source.document_uuid || source.document_id)) lines.push(`Document ID: ${source.document_uuid || source.document_id}`)
      if (source.url) lines.push(`URL: ${source.url}`)
      if (source.source_reference) lines.push(`Reference: ${source.source_reference}`)
      if (source.content_preview) lines.push(`Saved passage: ${source.content_preview}`)
      else lines.push('No passage preview was recorded.')
    })
  } else if (message.role === 'assistant') lines.push('No source references were recorded for this answer.')
  return lines.join('\n')
}
