import type { KBSourceReprocessMode } from '../../api/knowledge'
import type { KnowledgeBaseSource } from '../../types/knowledge'

/** A source the user asked to reprocess, followed until it settles. */
export interface TrackedReprocess {
  mode: KBSourceReprocessMode
  name: string
}

export interface SettledReprocess {
  uuid: string
  name: string
  ok: boolean
  chunkCount: number
  error: string | null
  /** A failed re-fetch leaves the source ready on its previous text. */
  keptPrevious: boolean
  /** The re-fetched page matched what was indexed, so nothing was rebuilt. */
  unchanged: boolean
}

const inFlight = (s: KnowledgeBaseSource) => s.status === 'pending' || s.status === 'processing'

/** Split tracked reprocesses into those still running and those that
 *  finished (ready or error) in ``sources``. A source no longer listed was
 *  removed; it is dropped without a result. */
export function settleReprocesses(
  tracked: Record<string, TrackedReprocess>,
  sources: KnowledgeBaseSource[],
): { remaining: Record<string, TrackedReprocess>; settled: SettledReprocess[] } {
  const byUuid = new Map(sources.map(s => [s.uuid, s]))
  const remaining: Record<string, TrackedReprocess> = {}
  const settled: SettledReprocess[] = []
  for (const [uuid, t] of Object.entries(tracked)) {
    const s = byUuid.get(uuid)
    if (!s) continue
    if (inFlight(s)) { remaining[uuid] = t; continue }
    // A web re-fetch that fails keeps serving the previous text, so the
    // source settles "ready"; only its currency outcome says it failed.
    const outcome = t.mode === 'refetch' ? s.currency?.last_refresh_outcome : null
    const refetchFailed = s.status === 'ready'
      && (outcome === 'retrieval_failed' || outcome === 'ingestion_failed')
    const ok = s.status === 'ready' && !refetchFailed
    settled.push({
      uuid,
      name: t.name,
      ok,
      chunkCount: s.chunk_count,
      // Trailing period trimmed: the toast adds its own sentence after it.
      error: ok ? null : (
        refetchFailed ? (s.currency?.last_refresh_error || 'The page could not be re-fetched')
        : (s.error_message || 'Processing failed')
      ).replace(/[.\s]+$/, ''),
      keptPrevious: refetchFailed,
      unchanged: ok && outcome === 'unchanged',
    })
  }
  return { remaining, settled }
}

/** The live line under an in-flight source. ``mode`` is known only for a
 *  reprocess started in this session; otherwise the status alone speaks. */
export function inFlightText(status: KnowledgeBaseSource['status'], mode?: KBSourceReprocessMode): string {
  if (status === 'processing') return 'Indexing… large documents can take a few minutes'
  if (mode === 'reextract') return 'Reprocessing — re-reading the document’s text first…'
  if (mode === 'reindex' || mode === 'refetch') return 'Reprocessing — queued…'
  return 'Waiting for document text to finish extracting…'
}

/** What the start toast says a reprocess will do. */
export function startMessage(mode: KBSourceReprocessMode, name: string): string {
  switch (mode) {
    case 'refetch': return `Reprocessing “${name}” — re-fetching the page. The previous text is kept if the fetch fails.`
    case 'reextract': return `Reprocessing “${name}” — its document had no readable text, so it is being read again first.`
    case 'waiting': return `“${name}” will be indexed as soon as its document finishes extracting.`
    default: return `Reprocessing “${name}” — re-chunking and re-embedding its text.`
  }
}
