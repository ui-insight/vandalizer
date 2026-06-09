import { useMemo } from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { cn } from '../../lib/cn'

/** Render trusted (authored) markdown to sanitized HTML. Same pipeline as ChatMessage. */
export function renderMarkdown(md: string): string {
  return DOMPurify.sanitize(marked.parse(md, { breaks: true, gfm: true }) as string)
}

/** Inline markdown block. `className` styles the wrapper; content is always sanitized. */
export function Markdown({ source, className }: { source: string; className?: string }) {
  const html = useMemo(() => renderMarkdown(source), [source])
  return <div className={cn(className)} dangerouslySetInnerHTML={{ __html: html }} />
}
