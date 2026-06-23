import DOMPurify from 'dompurify'
import { marked } from 'marked'

// Matches [ACTION:type]Label[/ACTION] (correct) and also
// [Label][ACTION:type] or [Label](ACTION:type) (common LLM mistakes)
const ACTION_RE = /\[ACTION:([\w-]+)\](.*?)\[\/ACTION\]/g
const ACTION_RE_ALT = /\[([^\]]+)\]\[ACTION:([\w-]+)\]/g
const ACTION_RE_ALT2 = /\[([^\]]+)\]\(ACTION:([\w-]+)\)/g
export const THINK_BLOCK_RE = /<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g
export const THINK_TRAILING_RE = /<think(?:ing)?>[\s\S]*$/

marked.setOptions({ breaks: true, gfm: true })

/** Render a markdown string to sanitized HTML. */
export function renderMarkdown(text: string): string {
  let cleaned = text.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '')
  // Canonical: [ACTION:type]Label[/ACTION]
  cleaned = cleaned.replace(ACTION_RE, (_match, type: string, label: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  // LLM mistake: [Label][ACTION:type]
  cleaned = cleaned.replace(ACTION_RE_ALT, (_match, label: string, type: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  // LLM mistake: [Label](ACTION:type)
  cleaned = cleaned.replace(ACTION_RE_ALT2, (_match, label: string, type: string) =>
    `<button data-action="${type}" class="chat-action-btn">${label}</button>`
  )
  return DOMPurify.sanitize(marked.parse(cleaned) as string, {
    ADD_TAGS: ['button'],
    ADD_ATTR: ['data-action'],
  })
}
