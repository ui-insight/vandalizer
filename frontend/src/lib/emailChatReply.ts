// Hand a chat reply to the person's own email app (support ticket #1200: chat
// wrote an email summary of an award and there was no way to send it on but
// copy and paste). Vandalizer sends nothing: this builds a mailto: link.

/** Markdown reads as clutter in a plain-text email; keep the words. */
export function markdownToPlain(text: string): string {
  return text
    .replace(/```[^\n]*\n?/g, '')
    .replace(/!?\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, '$1 ($2)')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/(\*\*|__)(.+?)\1/g, '$2')
    .replace(/(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s).,;:!?]|$)/g, '$1$2')
    .replace(/`([^`\n]+)`/g, '$1')
    .replace(/^(\s*)[*+]\s+/gm, '$1- ')
    .replace(/^\s*([-*_])(\s*\1){2,}\s*$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** Subject and body for a reply. When the reply is itself a drafted email
 * with a "Subject:" line near the top, that line becomes the subject and the
 * email starts after it; otherwise the subject is left for the person. */
export function emailDraftFromReply(text: string): { subject: string; body: string } {
  const plain = markdownToPlain(text)
  const lines = plain.split('\n')
  const at = lines.slice(0, 12).findIndex(line => /^\s*subject\s*:\s*\S/i.test(line))
  if (at === -1) return { subject: '', body: plain }
  return {
    subject: lines[at].replace(/^\s*subject\s*:\s*/i, '').trim(),
    body: lines.slice(at + 1).join('\n').trim(),
  }
}

// Email apps differ in how long a mailto: link they accept. Past this the
// body can arrive cut short, so the caller copies it instead.
export const MAILTO_SAFE_LENGTH = 1900

export function mailtoUrl(subject: string, body = ''): string {
  const params = [
    subject ? `subject=${encodeURIComponent(subject)}` : '',
    body ? `body=${encodeURIComponent(body.replace(/\r?\n/g, '\r\n'))}` : '',
  ].filter(Boolean).join('&')
  return `mailto:${params ? `?${params}` : ''}`
}

export function openMailto(url: string): void {
  const link = document.createElement('a')
  link.href = url
  link.click()
}
