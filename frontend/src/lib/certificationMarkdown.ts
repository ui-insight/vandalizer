import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** Authored teaching content has Markdown formatting, not executable actions. */
export function renderCertificationMarkdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false, breaks: true, gfm: true }), {
    FORBID_TAGS: ['style', 'form', 'input', 'button'],
  })
}
