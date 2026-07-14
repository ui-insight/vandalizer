import DOMPurify from 'dompurify'
import { marked } from 'marked'

// Matches [ACTION:type]Label[/ACTION] (correct) plus tolerated LLM variants:
// backslash-escaped brackets (\[ACTION:...\] — marked would otherwise unescape
// them and show the raw markup), backtick-wrapped tags, stray whitespace, and
// lowercase "action". Also [Label][ACTION:type] / [Label](ACTION:type)
// (common LLM mistakes), and leftover open/close fragments, so raw ACTION
// markup never reaches the user.
const ACTION_RE = /`?\\?\[\s*ACTION:\s*([\w-]+)\s*\\?\](.*?)\\?\[\s*\/\s*ACTION\s*\\?\]`?/gi
const ACTION_RE_ALT = /\[([^\]]+)\]\\?\[\s*ACTION:\s*([\w-]+)\s*\\?\]/gi
const ACTION_RE_ALT2 = /\[([^\]]+)\]\(\s*ACTION:\s*([\w-]+)\s*\)/gi
const ACTION_OPEN_REMNANT_RE = /\\?\[\s*ACTION:\s*([\w-]+)\s*\\?\]/gi
const ACTION_CLOSE_REMNANT_RE = /\\?\[\s*\/\s*ACTION\s*\\?\]/gi
export const THINK_BLOCK_RE = /<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>\n?/g
export const THINK_TRAILING_RE = /<think(?:ing)?>[\s\S]*$/

marked.setOptions({ breaks: true, gfm: true })

// Display labels for a bare [ACTION:type] the model emitted without label
// text. Unknown types fall back to the humanized type — actionRoute sends the
// label as a chat message, so it must read like a request.
const ACTION_FALLBACK_LABELS: Record<string, string> = {
  'start-cert': 'Start the Certification Program',
  'upload-docs': 'Upload your documents',
}

function actionButton(type: string, label: string): string {
  const clean = label.trim()
    || ACTION_FALLBACK_LABELS[type.toLowerCase()]
    || type.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase())
  return `<button data-action="${type}" class="chat-action-btn">${clean}</button>`
}

/** Render a markdown string to sanitized HTML. */
export function renderMarkdown(text: string): string {
  let cleaned = text.replace(THINK_BLOCK_RE, '').replace(THINK_TRAILING_RE, '')
  // Canonical (and escaped/backticked/spaced variants): [ACTION:type]Label[/ACTION]
  cleaned = cleaned.replace(ACTION_RE, (_match, type: string, label: string) =>
    actionButton(type, label)
  )
  // LLM mistake: [Label][ACTION:type]
  cleaned = cleaned.replace(ACTION_RE_ALT, (_match, label: string, type: string) =>
    actionButton(type, label)
  )
  // LLM mistake: [Label](ACTION:type)
  cleaned = cleaned.replace(ACTION_RE_ALT2, (_match, label: string, type: string) =>
    actionButton(type, label)
  )
  // Last resort: unpaired fragments — a bare open tag still becomes a button,
  // a dangling close tag disappears.
  cleaned = cleaned.replace(ACTION_OPEN_REMNANT_RE, (_match, type: string) =>
    actionButton(type, '')
  )
  cleaned = cleaned.replace(ACTION_CLOSE_REMNANT_RE, '')
  return DOMPurify.sanitize(marked.parse(cleaned) as string, {
    ADD_TAGS: ['button'],
    ADD_ATTR: ['data-action'],
  })
}
