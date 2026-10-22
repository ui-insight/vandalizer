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
//
// Plus the markdown marks document conversion adds: bold/italic asterisks,
// heading hashes, table pipes and code backticks. Extraction quotes come from
// the stored markdown ("**FOA Number:** PA-23-152") while the PDF text layer
// has none of them, so Inspect source showed "passage not matched". Both sides
// are normalized, so a real asterisk or hash in a PDF still lines up.
const DROP_CHARS = new Set(['\u00AD', '\uFEFF', '\u200B', '\u200C', '\u200D', '*', '#', '|', '`'])

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

// Longest anchor phrase we ask the viewer to find. Chunk previews run to a few
// hundred characters, but the longer the needle the likelier it straddles a
// page break, a header, or a hyphenated line the text layer renders
// differently — and a miss costs the highlight entirely.
const ANCHOR_MAX_CHARS = 120

// Turn a retrieved chunk's preview text into a phrase worth searching for in
// the document it came from. Previews are cut to a fixed character budget
// server-side, so they routinely end mid-word; a truncated needle matches
// nothing. Returns '' when nothing usable is left.
export function citationAnchor(preview: string | null | undefined): string {
  const text = (preview ?? '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  if (text.length <= ANCHOR_MAX_CHARS) {
    // Short enough to use whole, and short enough to prove it was never cut:
    // the server truncates content_preview at 240 chars (_build_kb_segment),
    // well above this branch, so the last word is already complete. Trimming
    // it anyway costs precision on the anchors with the least to spare —
    // "Section 3 Reporting" would become "Section 3", which matches half the
    // document.
    return text
  }
  return trimPartialWord(text.slice(0, ANCHOR_MAX_CHARS))
}

// Drop everything after the last space, so the phrase ends on a whole word.
// A single unbroken run (a long URL, say) is returned as-is.
function trimPartialWord(text: string): string {
  const lastSpace = text.lastIndexOf(' ')
  return lastSpace > 0 ? text.slice(0, lastSpace) : text
}

// --- Loose matching ---------------------------------------------------------
// A PDF's text layer and a text extractor read the same page differently:
// the layer splits runs into items ("( up to 250 characters )", "time) :"),
// draws bullets ("•") where the extractor writes list marks ("- "), and an
// extractor that cannot read a ligature glyph drops it ("Staffing" read as
// "Stang"). Compared letter for letter and digit for digit, in order, the
// two agree; spacing, punctuation and bullets are not compared.

// The Latin ligatures U+FB00 to U+FB06, spelled out.
const LIGATURES: Record<string, string> = Object.fromEntries(
  ['ff', 'fi', 'fl', 'ffi', 'ffl', 'st', 'st'].map((spelled, i) => [String.fromCharCode(0xfb00 + i), spelled]),
)
const LETTER_OR_DIGIT = /[\p{L}\p{N}]/u

/** `text`'s letters and digits only, lowercased, ligatures spelled out, and
 *  the index in `text` each comes from. */
export function skeletonWithMap(text: string): { skel: string; map: number[] } {
  let skel = ''
  const map: number[] = []
  for (let i = 0; i < text.length; i++) {
    const spelled = LIGATURES[text[i]] ?? text[i]
    for (const c of spelled) {
      if (!LETTER_OR_DIGIT.test(c)) continue
      for (const lower of c.toLowerCase()) {
        skel += lower
        map.push(i)
      }
    }
  }
  return { skel, map }
}

/** Shortest needle (in letters and digits) matched loosely: shorter, and
 *  ignoring spaces could find its letters where its words do not stand
 *  together. */
export const LOOSE_MIN_CHARS = 12
/** Longest needle a dropped ligature is allowed for. */
const LIGATURE_MAX_CHARS = 800

/**
 * `[start, end)` ranges of `haystack` whose letters and digits are
 * `needle`'s, in order. When there are none, a needle missing an "ff", "fi",
 * "fl", "ffi" or "ffl" that `haystack` has between two letters still
 * matches — what an extractor that dropped a ligature glyph wrote.
 */
export function findLoose(haystack: string, needle: string): Array<[number, number]> {
  const n = skeletonWithMap(needle).skel
  if (n.length < LOOSE_MIN_CHARS) return []
  const { skel, map } = skeletonWithMap(haystack)
  const out: Array<[number, number]> = []
  for (let at = skel.indexOf(n); at !== -1; at = skel.indexOf(n, at + n.length)) {
    out.push([map[at], map[at + n.length - 1] + 1])
  }
  if (out.length > 0 || n.length > LIGATURE_MAX_CHARS) return out
  // `n` holds only letters and digits: nothing in it needs escaping.
  const pattern = Array.from(n).join('(?:ffi|ffl|ff|fi|fl)?')
  for (const m of skel.matchAll(new RegExp(pattern, 'g'))) {
    const at = m.index ?? 0
    out.push([map[at], map[at + m[0].length - 1] + 1])
  }
  return out
}

/**
 * The longest leading part of `needle` — whole words, at least `minWords` —
 * that `findLoose` finds in `haystack`, as `[start, end)`. A passage that
 * runs onto the next page is on neither page whole; its start is on the
 * page it is cited at.
 */
export function findLoosePrefix(haystack: string, needle: string, minWords = 4): [number, number] | null {
  const words = needle.split(/\s+/).filter(Boolean)
  for (let k = words.length - 1; k >= minWords; k--) {
    const [range] = findLoose(haystack, words.slice(0, k).join(' '))
    if (range) return range
  }
  return null
}
