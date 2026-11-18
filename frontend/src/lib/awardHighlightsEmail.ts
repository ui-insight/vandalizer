// The email a research administrator sends a PI with an award's highlights.
// Written from the extracted facts by a fixed template, so the same document
// gives the same email every time (support ticket #1200: a chat prompt gave
// different facts depending on its wording).

import type { AwardHighlightFact, AwardHighlightPI, AwardHighlights } from '../api/files'

export const NOT_FOUND = 'Not found'

function line(fact: AwardHighlightFact): string {
  if (!fact.value) return `${fact.label}: ${NOT_FOUND} in the document`
  const page = fact.page ? ` (p. ${fact.page_approximate ? '~' : ''}${fact.page})` : ''
  return `${fact.label}: ${fact.value}${page}`
}

export function composeHighlightsEmail(
  highlights: AwardHighlights,
  pi: AwardHighlightPI | null,
): { subject: string; body: string } {
  const title = highlights.document.title
  const parts = [
    pi?.name.value ? `Hello ${pi.name.value},` : 'Hello,',
    '',
    `Here are the highlights from ${title}. Page numbers refer to that document.`,
    '',
    ...highlights.facts.map(line),
    '',
    'Contacts',
    ...highlights.contacts.map(line),
    '',
    'Please check these against the agreement itself before relying on them.',
  ]
  if (highlights.sender_name) parts.push('', highlights.sender_name)
  return { subject: `Award highlights: ${title}`, body: parts.join('\n') }
}

// Mail programs differ in how long a mailto: link they accept; past this the
// body can arrive cut short, so the dialog points to Copy draft as well.
export const MAILTO_SAFE_LENGTH = 1900

export function mailtoUrl(to: string, subject: string, body: string): string {
  const crlf = body.replace(/\r?\n/g, '\r\n')
  return `mailto:${encodeURIComponent(to.trim())}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(crlf)}`
}
