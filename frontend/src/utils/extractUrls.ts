/**
 * Pull web addresses out of arbitrary text — an email, a document, an HTML
 * page, a CSV or a plain list (feature request: "smart paste" and URL files).
 *
 * Finds http(s):// links anywhere in the text, plus bare addresses
 * (`www.example.gov/page`, or `example.gov/page` alone on a line, which Add
 * URLs has always accepted) given https://. Sentence punctuation and an
 * unmatched closing bracket after a link are not part of it. Order is kept and
 * repeats are dropped.
 */

const SCHEME_URL = /https?:\/\/[^\s<>"'`{}|\\^]+/gi
const WWW_URL = /(?<![\w./@-])www\.[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:[/?#][^\s<>"'`{}|\\^]*)?/gi
// A whole line that is just a host with a dot-separated TLD, optionally a path.
const BARE_LINE = /^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?$/i

const TRAILING = /[.,;:!?'"*_>]+$/

function trimLink(raw: string): string {
  let url = raw.replace(/&amp;/gi, '&')
  for (;;) {
    const before = url
    url = url.replace(TRAILING, '')
    for (const [open, close] of [['(', ')'], ['[', ']']]) {
      // "(see https://a.gov/x)" — the ")" closes the sentence, not the link;
      // "https://en.wikipedia.org/wiki/A_(b)" keeps its own.
      while (url.endsWith(close) && url.split(close).length > url.split(open).length) url = url.slice(0, -1)
    }
    if (url === before) return url
  }
}

function isWebUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname.includes('.')
  } catch {
    return false
  }
}

export function extractUrls(text: string): string[] {
  const found: { index: number; url: string }[] = []
  const covered: [number, number][] = []

  for (const match of text.matchAll(SCHEME_URL)) {
    const url = trimLink(match[0])
    found.push({ index: match.index ?? 0, url })
    covered.push([match.index ?? 0, (match.index ?? 0) + match[0].length])
  }
  for (const match of text.matchAll(WWW_URL)) {
    const start = match.index ?? 0
    if (covered.some(([a, b]) => start >= a && start < b)) continue // inside an http(s) link
    found.push({ index: start, url: `https://${trimLink(match[0])}` })
  }
  let offset = 0
  for (const line of text.split('\n')) {
    const value = line.trim()
    if (BARE_LINE.test(value) && !/^www\./i.test(value)) {
      found.push({ index: offset + line.indexOf(value), url: `https://${trimLink(value)}` })
    }
    offset += line.length + 1
  }

  found.sort((a, b) => a.index - b.index)
  const seen = new Set<string>()
  const urls: string[] = []
  for (const { url } of found) {
    if (!isWebUrl(url) || seen.has(url)) continue
    seen.add(url)
    urls.push(url)
  }
  return urls
}
