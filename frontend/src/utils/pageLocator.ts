/**
 * Render the page part of a citation.
 *
 * Page numbers reach the UI from two different backend paths. Text PDFs have
 * their page boundaries measured directly from the file; scanned PDFs go
 * through OCR, which returns no page structure, so the backend estimates the
 * boundaries by spreading the known page count evenly across the text. Both
 * arrive as a plain `page` number, and only `page_approximate` distinguishes
 * them — without the marker, an estimate reads as a precise location.
 *
 * Citations created before the flag existed carry no value for it and render
 * as measured, which is the behaviour they have today.
 *
 * See #603.
 */
export function formatPageLocator(
  page: unknown,
  approximate?: boolean,
): string | null {
  if (typeof page !== 'number' || !Number.isInteger(page)) return null
  return approximate ? `p. ~${page}` : `p. ${page}`
}
