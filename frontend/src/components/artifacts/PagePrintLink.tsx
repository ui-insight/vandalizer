import { Printer } from 'lucide-react'

export function pageViewUrl(contentUrl: string, view: 'full' | 'print'): string {
  return `${contentUrl}${contentUrl.includes('?') ? '&' : '?'}view=${view}`
}

/** A separate tab keeps the app responsive while its print dialog is open. */
export function PagePrintLink({ contentUrl }: { contentUrl: string }) {
  return <a className="page-button" href={pageViewUrl(contentUrl, 'print')} target="_blank" rel="noopener noreferrer">
    <Printer size={16} aria-hidden="true" />Print / Save as PDF
  </a>
}
