import type { KnowledgeBaseSource } from '../../types/knowledge'

/** The label a KB source goes by: the user's name for it, else its title or URL. */
export function sourceDisplayName(s: KnowledgeBaseSource): string {
  return s.custom_name
    || (s.source_type === 'url' ? (s.url_title || s.url) : s.document_title)
    || s.document_uuid
    || s.uuid
}
