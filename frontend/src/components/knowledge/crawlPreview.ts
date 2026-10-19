import type { CrawlPreviewPage } from '../../api/knowledge'

/** A page the user can tick: it was fetched and the KB doesn't hold it yet. */
export const isSelectable = (p: CrawlPreviewPage) => p.kind !== 'failed' && !p.in_kb

/** Ticked to start: what a crawl would have added on its own. Navigation
 *  pages are listed but start unticked, as the crawl would have skipped them. */
export function defaultSelection(pages: CrawlPreviewPage[]): Set<string> {
  return new Set(pages.filter(p => isSelectable(p) && (p.kind === 'start' || p.kind === 'content')).map(p => p.url))
}

/** Pages grouped under the start URL they were found from, in crawl order. */
export function groupByStart(startUrls: string[], pages: CrawlPreviewPage[]): { start: string; pages: CrawlPreviewPage[] }[] {
  return startUrls
    .map(start => ({ start, pages: pages.filter(p => p.start_url === start) }))
    .filter(g => g.pages.length > 0)
}

export function pageLabel(p: CrawlPreviewPage): string {
  if (p.in_kb) return 'Already in this knowledge base'
  if (p.kind === 'failed') return p.note ? `Could not be fetched — ${p.note}` : 'Could not be fetched'
  if (p.kind === 'navigation') return 'Looks like a navigation page — a crawl would skip it'
  if (p.kind === 'start') return 'The page you entered'
  return ''
}

export function formatChars(n: number): string {
  if (n >= 1000) return `${Math.round(n / 100) / 10}k characters`
  return `${n} characters`
}
