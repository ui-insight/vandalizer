import type { Citation } from '../types/chat'

// A KB answer cites the snippets it used by number — "[S3]", "[S1, S3]" —
// because a filename can't say which of one document's several snippets was
// meant. The numbers mean nothing to a reader, so they are shown as the
// citation they stand for. Mirrors expand_snippet_refs in
// backend/app/services/kb_answer_grounding.py, which does the same to the
// stored answer.
const SNIPPET_REF_RE = /\[\s*S\d+(?:\s*[,;]\s*S?\d+)*\s*\]/g

export function expandSnippetRefs(text: string, citations: Citation[]): string {
  if (!citations.length) return text
  const byRef = new Map<number, Citation>()
  for (const c of citations) if (typeof c.ref === 'number') byRef.set(c.ref, c)
  if (!byRef.size) return text
  return text.replace(SNIPPET_REF_RE, (match) => {
    const labels: string[] = []
    for (const n of (match.match(/\d+/g) ?? []).map(Number)) {
      const c = byRef.get(n)
      // A number no snippet carries is left as written, not erased.
      if (!c) return match
      labels.push(c.cite_label || c.document_title)
    }
    return `[Source: ${[...new Set(labels)].join('; ')}]`
  })
}

// Mark which snippets the finished answer cited. A citation without `used`
// predates the distinction and stays a source.
export function markUsed(citations: Citation[], usedRefs: number[]): Citation[] {
  const used = new Set(usedRefs)
  return citations.map(c => ({ ...c, used: typeof c.ref === 'number' ? used.has(c.ref) : true }))
}

export function isUsedCitation(c: Citation): boolean {
  return c.used !== false
}
