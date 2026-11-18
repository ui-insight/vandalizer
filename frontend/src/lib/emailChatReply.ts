// Hand a chat reply to the person's own email app (support ticket #1200: chat
// wrote an email summary of an award and there was no way to send it on but
// copy and paste). Vandalizer sends nothing: this builds a mailto: link.

// Chat-only markup that means nothing in an email: the buttons a reply
// offers, and links to items inside Vandalizer.
const ACTION_RE = /\[ACTION:[^\]]*\][\s\S]*?\[\/ACTION\]/g
const INTERNAL_LINK_RE = /!?\[([^\]]+)\]\((?:doc|kb|page|workflow|extraction|project):[^)]*\)/g

function proseToPlain(text: string): string {
  return text
    .replace(ACTION_RE, '')
    .replace(INTERNAL_LINK_RE, '$1')
    .replace(/!?\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, '$1 ($2)')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    // Emphasis hugs its words: "**Amount:**" is bold, "a ** b ** c" and
    // "2 * 3 * 4" are arithmetic, and "__init__.py" is a file name.
    .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g, '$1')
    .replace(/(^|[\s(])__(?=\S)(.+?)(?<=\S)__(?=[\s),;:!?]|\.(?:\s|$)|$)/gm, '$1$2')
    .replace(/(^|[\s(])([*_])(?=\S)([^*_\n]+?)(?<=\S)\2(?=[\s).,;:!?]|$)/gm, '$1$3')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/^(\s*)[*+]\s+/gm, '$1- ')
    .replace(/^\s*([-*_])(\s*\1){2,}\s*$/gm, '')
}

/** Markdown reads as clutter in a plain-text email; keep the words. What is
 * inside a code fence is kept exactly as written. */
export function markdownToPlain(text: string): string {
  return text
    .split(/^\s{0,3}```[^\n]*$/m)
    .map((part, i) => (i % 2 === 0 ? proseToPlain(part) : part))
    .join('')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

const SUBJECT_RE = /^\s*subject\s*:\s*\S/i
const OTHER_HEADER_RE = /^\s*(to|from|date|cc|bcc|re)\s*:/i

/** Subject and body for a reply. When the reply is itself a drafted email
 * with a "Subject:" line near the top, that line becomes the subject and the
 * email starts after it; otherwise the subject is left for the person.
 *
 * A "Subject:" line that sits among To/From/Date lines may be a memo the
 * reply is quoting, where those lines are content. Its subject is still
 * used, and the whole reply is kept as the body so nothing is dropped. */
export function emailDraftFromReply(text: string): { subject: string; body: string } {
  const plain = markdownToPlain(text)
  const lines = plain.split('\n')
  const at = lines.slice(0, 12).findIndex(line => SUBJECT_RE.test(line))
  if (at === -1) return { subject: '', body: plain }
  const subject = lines[at].replace(/^\s*subject\s*:\s*/i, '').trim()
  const headerBlock = lines.slice(0, at).some(l => OTHER_HEADER_RE.test(l)) || OTHER_HEADER_RE.test(lines[at + 1] ?? '')
  if (headerBlock) return { subject, body: plain }
  return { subject, body: lines.slice(at + 1).join('\n').trim() }
}

// Email apps differ in how long a mailto: link they accept. Past this the
// body can arrive cut short, so the caller copies it instead.
export const MAILTO_SAFE_LENGTH = 1900

// Half of a surrogate pair (a cut-off emoji) makes encodeURIComponent throw,
// which left the button doing nothing.
const LONE_SURROGATE_RE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g
const encode = (text: string) => encodeURIComponent(text.replace(LONE_SURROGATE_RE, '\uFFFD'))

export function mailtoUrl(subject: string, body = ''): string {
  const params = [
    subject ? `subject=${encode(subject)}` : '',
    body ? `body=${encode(body.replace(/\r?\n/g, '\r\n'))}` : '',
  ].filter(Boolean).join('&')
  return `mailto:${params ? `?${params}` : ''}`
}

export function openMailto(url: string): void {
  const link = document.createElement('a')
  link.href = url
  link.click()
}
