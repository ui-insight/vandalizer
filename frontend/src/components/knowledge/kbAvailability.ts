import type { KnowledgeBase } from '../../types/knowledge'

/** Retrieval availability is separate from the quality measured by Validation. */
export function describeKBAvailability(kb: KnowledgeBase): string {
  if (kb.status === 'unavailable') return 'The original is no longer accessible. Remove this bookmark or find another knowledge base.'
  if (kb.total_sources === 0) return 'Add files or web sources to start building this knowledge base.'
  if (kb.status === 'building') return 'Sources are being indexed. This view updates as processing finishes.'
  if (kb.sources_failed >= kb.total_sources) return 'No sources are ready. Open the source errors and retry ingestion.'
  if (kb.sources_failed > 0 && kb.sources_ready > 0) return 'Some sources need attention. Chat uses only the content indexed successfully.'
  if (kb.status === 'ready' && kb.total_chunks > 0) return 'Indexed content is available for chat.'
  return 'No indexed content is available for chat yet. Open the sources to check their status.'
}
