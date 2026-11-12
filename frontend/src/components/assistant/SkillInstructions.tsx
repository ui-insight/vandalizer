import DOMPurify from 'dompurify'
import { marked } from 'marked'

export function SkillInstructions({ instructions, label = 'Skill instructions' }: { instructions: string; label?: string }) {
  // Instructions are a document to review, not chat action buttons or embedded resources.
  const html = DOMPurify.sanitize(marked.parse(instructions, { async: false, gfm: true, breaks: true }), {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'del', 's', 'code', 'pre', 'blockquote', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ALLOWED_ATTR: ['href', 'title', 'colspan', 'rowspan', 'start'],
    ALLOW_DATA_ATTR: false,
  })
  return <div>
    <div tabIndex={0} role="region" aria-label={label}
      className="chat-markdown max-h-80 overflow-y-auto break-words rounded-md border border-gray-200 bg-white p-3 text-sm text-gray-800 [&_ol]:list-decimal [&_ul]:list-disc"
      dangerouslySetInnerHTML={{ __html: html }} />
    <details className="mt-2 text-sm text-gray-600">
      <summary className="cursor-pointer underline">View original text</summary>
      <pre tabIndex={0} aria-label={`${label}, original text`} className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-md border border-gray-200 bg-white p-3 font-sans text-sm text-gray-800">{instructions}</pre>
    </details>
  </div>
}
