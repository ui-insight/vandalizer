import DOMPurify from 'dompurify'
import { marked } from 'marked'

/** Add keyboard-scrollable frames to already-sanitized course HTML. */
export function wrapCertificationTables(html: string): string {
  if (!html.includes('<table')) return html
  const template = document.createElement('template')
  template.innerHTML = html
  for (const [index, table] of [...template.content.querySelectorAll('table')].entries()) {
    if (table.parentElement?.classList.contains('cert-table-region')) continue
    const region = document.createElement('div')
    region.className = 'cert-table-region'
    region.setAttribute('role', 'region')
    region.setAttribute('aria-label', `Course table ${index + 1}`)
    region.tabIndex = 0
    table.before(region)
    region.append(table)
  }
  return template.innerHTML
}

/** Authored teaching content has Markdown formatting, not executable actions. */
export function renderCertificationMarkdown(text: string): string {
  return wrapCertificationTables(DOMPurify.sanitize(marked.parse(text, { async: false, breaks: true, gfm: true }), {
    FORBID_TAGS: ['style', 'form', 'input', 'button'],
  }))
}
