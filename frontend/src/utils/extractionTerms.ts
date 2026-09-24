/**
 * Split an "add field" entry into separate extraction terms on commas.
 * Shared by the standalone Extraction editor and the workflow task's field
 * input so a pasted "PI Name, Institution, Total Budget" becomes three fields
 * in both. A comma inside brackets or quotes is part of the term, so
 * "Budget (direct, indirect)" stays one field. Blank pieces, repeats within
 * the entry, and terms already in `existing` are dropped; order is preserved.
 */
export function splitFieldTerms(text: string, existing: readonly string[] = []): string[] {
  const seen = new Set(existing)
  const out: string[] = []
  for (const piece of splitTopLevelCommas(text)) {
    const term = piece.trim()
    if (term && !seen.has(term)) {
      seen.add(term)
      out.push(term)
    }
  }
  return out
}

const OPENERS: Record<string, string> = { '(': ')', '[': ']', '{': '}' }

/** Split on commas that sit outside brackets and double quotes. */
function splitTopLevelCommas(text: string): string[] {
  const pieces: string[] = []
  const closers: string[] = []
  let inQuote = false
  let start = 0
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') inQuote = !inQuote
    else if (inQuote) continue
    else if (ch in OPENERS) closers.push(OPENERS[ch])
    else if (closers.length && ch === closers[closers.length - 1]) closers.pop()
    else if (ch === ',' && !closers.length) {
      pieces.push(text.slice(start, i))
      start = i + 1
    }
  }
  pieces.push(text.slice(start))
  return pieces
}
