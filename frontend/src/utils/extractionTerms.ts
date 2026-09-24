/**
 * Split an "add field" entry into separate extraction terms on commas.
 * Shared by the standalone Extraction editor and the workflow task's field
 * input so a pasted "PI Name, Institution, Total Budget" becomes three fields
 * in both. Blank pieces, repeats within the entry, and terms already in
 * `existing` are dropped; order is preserved.
 */
export function splitFieldTerms(text: string, existing: readonly string[] = []): string[] {
  const seen = new Set(existing)
  const out: string[] = []
  for (const piece of text.split(',')) {
    const term = piece.trim()
    if (term && !seen.has(term)) {
      seen.add(term)
      out.push(term)
    }
  }
  return out
}
