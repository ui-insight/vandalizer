// Text normalization for matching LLM-quoted passages against document text
// (PDF text layers, rendered DOCX). The two routinely disagree on smart
// quotes, dash variants, NBSP, soft hyphens, and ligatures, so both sides are
// folded before matching, keeping a map back to source offsets.

const FOLD_MAP: Record<string, string> = {
  // curly quotes -> straight
  '\u2018': "'", '\u2019': "'", '\u201A': "'", '\u201B': "'",
  '\u201C': '"', '\u201D': '"', '\u201E': '"',
  // hyphen/dash variants -> '-'
  '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-',
  '\u2014': '-', '\u2015': '-', '\u2212': '-',
  // NBSP / figure / thin / narrow no-break space -> ' '
  '\u00A0': ' ', '\u2007': ' ', '\u2009': ' ', '\u202F': ' ',
  // ligatures
  '\uFB01': 'fi', '\uFB02': 'fl',
}
// soft hyphen, BOM, zero-width space / non-joiner / joiner
const DROP_CHARS = new Set(['\u00AD', '\uFEFF', '\u200B', '\u200C', '\u200D'])

// Lowercase + fold + collapse whitespace, keeping a map from each normalized
// char back to its source index so matches project onto real text offsets.
export function normalizeWithMap(text: string): { norm: string; map: number[] } {
  let norm = ''
  const map: number[] = []
  let lastWasSpace = true // trims leading whitespace
  for (let i = 0; i < text.length; i++) {
    const raw = text[i]
    if (DROP_CHARS.has(raw)) continue
    const folded = FOLD_MAP[raw] ?? raw
    for (const c of folded) {
      if (/\s/.test(c)) {
        if (lastWasSpace) continue
        norm += ' '
        map.push(i)
        lastWasSpace = true
      } else {
        norm += c.toLowerCase()
        map.push(i)
        lastWasSpace = false
      }
    }
  }
  if (norm.endsWith(' ')) {
    norm = norm.slice(0, -1)
    map.pop()
  }
  return { norm, map }
}
