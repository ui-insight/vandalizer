// Functions injected into the working tab with chrome.scripting.executeScript.
// Each one is serialized on its own, so it must not use anything from outside
// its own body.

/**
 * Read the page as compact text. Each link, button and field gets a number,
 * written "[12]" in the text and kept as data-vz-ref so later actions can find
 * it. Numbers from an earlier read are cleared. Same-origin frames are read.
 */
export function readPage(query, maxChars) {
  const BLOCK = new Set(['ADDRESS', 'ARTICLE', 'ASIDE', 'BLOCKQUOTE', 'BR', 'DD', 'DIV', 'DL', 'DT', 'FIELDSET',
    'FIGCAPTION', 'FIGURE', 'FOOTER', 'FORM', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'HEADER', 'HR', 'LI', 'MAIN',
    'NAV', 'OL', 'P', 'PRE', 'SECTION', 'TABLE', 'TBODY', 'TFOOT', 'THEAD', 'TR', 'UL', 'CAPTION', 'LEGEND'])
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'SVG', 'CANVAS', 'VIDEO', 'AUDIO', 'OBJECT', 'EMBED'])
  const ROLES = new Set(['button', 'link', 'tab', 'menuitem', 'option', 'checkbox', 'radio', 'switch', 'combobox', 'treeitem'])
  const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim()
  const quote = (s, n = 80) => `"${clean(s).slice(0, n).replace(/"/g, "'")}"`
  const lines = []
  let line = ''
  let next = 1
  let loginRequired = false
  let skippedFrames = 0

  const flush = () => {
    const text = clean(line)
    if (text) lines.push(text)
    line = ''
  }
  const visible = (el) => {
    const view = el.ownerDocument.defaultView
    const style = view.getComputedStyle(el)
    if (style.display === 'none' || style.visibility === 'hidden') return false
    if (el.getAttribute('aria-hidden') === 'true') return false
    return el.getClientRects().length > 0 || el.tagName === 'OPTION'
  }
  const labelOf = (el) => {
    const doc = el.ownerDocument
    if (el.id) {
      const label = doc.querySelector(`label[for="${CSS.escape(el.id)}"]`)
      if (label) return clean(label.innerText)
    }
    const labelledBy = el.getAttribute('aria-labelledby')
    if (labelledBy) {
      const text = labelledBy.split(/\s+/).map((id) => doc.getElementById(id)?.innerText || '').join(' ')
      if (clean(text)) return clean(text)
    }
    const wrap = el.closest('label')
    if (wrap) return clean(wrap.innerText)
    return clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.title || el.name || '')
  }
  const interactive = (el) => {
    const tag = el.tagName
    if (tag === 'A') return el.hasAttribute('href')
    if (tag === 'BUTTON' || tag === 'SELECT' || tag === 'TEXTAREA') return true
    if (tag === 'INPUT') return el.type !== 'hidden'
    return ROLES.has(el.getAttribute('role') || '')
  }
  const describe = (el, ref) => {
    const tag = el.tagName
    const role = el.getAttribute('role')
    if (tag === 'SELECT') {
      const options = [...el.options].map((o) => clean(o.text)).filter(Boolean)
      const chosen = el.selectedOptions[0] ? clean(el.selectedOptions[0].text) : ''
      const shown = options.slice(0, 15).join(' | ') + (options.length > 15 ? ` | … ${options.length - 15} more` : '')
      return `[${ref}] dropdown ${quote(labelOf(el))} = ${quote(chosen)} options: ${shown}`
    }
    if (tag === 'TEXTAREA') return `[${ref}] text box ${quote(labelOf(el))} = ${quote(el.value, 120)}`
    if (tag === 'INPUT') {
      const type = (el.type || 'text').toLowerCase()
      if (type === 'password') return `[${ref}] password field (never type here)`
      if (type === 'checkbox' || type === 'radio') return `[${ref}] ${type} ${quote(labelOf(el))}${el.checked ? ' (checked)' : ''}`
      if (['submit', 'button', 'reset', 'image'].includes(type)) return `[${ref}] button ${quote(el.value || el.alt || labelOf(el))}`
      if (type === 'file') return `[${ref}] file upload (not available)`
      return `[${ref}] field ${quote(labelOf(el))} = ${quote(el.value, 120)}`
    }
    const kind = tag === 'A' ? 'link' : tag === 'BUTTON' ? 'button' : role || 'control'
    return `[${ref}] ${kind} ${quote(el.innerText || el.getAttribute('aria-label') || el.title || '')}`
  }

  const walk = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      line += ' ' + node.nodeValue
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return
    const el = node
    const tag = el.tagName.toUpperCase()
    if (SKIP.has(tag)) return
    if (!visible(el)) return
    if (tag === 'IFRAME' || tag === 'FRAME') {
      let inner = null
      try { inner = el.contentDocument } catch { inner = null }
      if (inner?.body) {
        flush()
        walk(inner.body)
        flush()
      } else {
        skippedFrames += 1
      }
      return
    }
    if (tag === 'INPUT' && (el.type || '').toLowerCase() === 'password') loginRequired = true
    if (interactive(el)) {
      const ref = next++
      el.setAttribute('data-vz-ref', String(ref))
      line += ' ' + describe(el, ref)
      return
    }
    const block = BLOCK.has(tag)
    if (block) flush()
    if (/^H[1-6]$/.test(tag)) line += '#'.repeat(Number(tag[1])) + ' '
    if (tag === 'TD' || tag === 'TH') line += ' | '
    if (el.shadowRoot) el.shadowRoot.childNodes.forEach(walk)
    el.childNodes.forEach(walk)
    if (block) flush()
  }

  document.querySelectorAll('[data-vz-ref]').forEach((e) => e.removeAttribute('data-vz-ref'))
  document.querySelectorAll('iframe, frame').forEach((f) => {
    try { f.contentDocument?.querySelectorAll('[data-vz-ref]').forEach((e) => e.removeAttribute('data-vz-ref')) } catch { /* other site */ }
  })
  if (document.body) walk(document.body)
  flush()
  if (skippedFrames) lines.push(`(${skippedFrames} embedded frame(s) from another site were not read)`)

  let kept = lines
  let matched = true
  const terms = clean(query).toLowerCase().split(' ').filter((t) => t.length > 1)
  if (terms.length) {
    const keep = new Set()
    lines.forEach((l, i) => {
      const lower = l.toLowerCase()
      if (terms.some((t) => lower.includes(t))) for (let j = Math.max(0, i - 3); j <= Math.min(lines.length - 1, i + 3); j++) keep.add(j)
    })
    if (keep.size) {
      kept = []
      let last = -2
      ;[...keep].sort((a, b) => a - b).forEach((i) => {
        if (i !== last + 1) kept.push('…')
        kept.push(lines[i])
        last = i
      })
    } else {
      matched = false
    }
  }
  let text = kept.join('\n')
  const truncated = text.length > maxChars
  if (truncated) text = text.slice(0, maxChars) + '\n… (page continues; read again with a query to see a specific part)'
  return {
    url: location.href,
    title: document.title,
    text,
    truncated,
    login_required: loginRequired,
    ...(terms.length && !matched ? { query_not_found: true } : {}),
  }
}

/** Click by number, unless the control looks like it changes something. */
export function clickRef(ref) {
  const findRef = (doc) => {
    const hit = doc.querySelector(`[data-vz-ref="${ref}"]`)
    if (hit) return hit
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      let inner = null
      try { inner = frame.contentDocument } catch { inner = null }
      const found = inner && findRef(inner)
      if (found) return found
    }
    return null
  }
  const el = findRef(document)
  if (!el) return { error: 'stale_ref', message: `No element [${ref}] on the page now. Read the page again.` }
  const label = String(el.innerText || el.value || el.getAttribute('aria-label') || el.title || el.alt || '')
    .replace(/\s+/g, ' ').trim()
  const WRITE = /\b(submit|save|update|approve|certify|sign|send|delete|remove|pay|payment|transfer|confirm|apply|post|upload|cancel|withdraw|reject|accept|agree|purchase|order|create|add|edit|change|request|finali[sz]e|draw ?down|close ?out|log ?out|sign ?out)\b/i
  if (WRITE.test(label)) {
    return {
      error: 'blocked_write_action',
      label,
      message: `"${label}" looks like it would change something, so Vandalizer will not click it. Ask the person to click it themselves if it is needed.`,
    }
  }
  el.scrollIntoView({ block: 'center' })
  el.click()
  return { ok: true, clicked: label.slice(0, 80) }
}

/** Replace a search or filter field's text, the way a person typing would. */
export function typeRef(ref, text) {
  const findRef = (doc) => {
    const hit = doc.querySelector(`[data-vz-ref="${ref}"]`)
    if (hit) return hit
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      let inner = null
      try { inner = frame.contentDocument } catch { inner = null }
      const found = inner && findRef(inner)
      if (found) return found
    }
    return null
  }
  const el = findRef(document)
  if (!el) return { error: 'stale_ref', message: `No element [${ref}] on the page now. Read the page again.` }
  const type = (el.type || '').toLowerCase()
  const typable = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && ['', 'text', 'search', 'number', 'date', 'email', 'tel', 'url', 'month', 'week'].includes(type))
  if (!typable) return { error: 'not_a_text_field', message: `[${ref}] is not a text field.` }
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
  el.focus()
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(text))
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  return { ok: true }
}

/** Choose a drop-down option by its visible text. */
export function selectRef(ref, option) {
  const findRef = (doc) => {
    const hit = doc.querySelector(`[data-vz-ref="${ref}"]`)
    if (hit) return hit
    for (const frame of doc.querySelectorAll('iframe, frame')) {
      let inner = null
      try { inner = frame.contentDocument } catch { inner = null }
      const found = inner && findRef(inner)
      if (found) return found
    }
    return null
  }
  const el = findRef(document)
  if (!el) return { error: 'stale_ref', message: `No element [${ref}] on the page now. Read the page again.` }
  if (el.tagName !== 'SELECT') return { error: 'not_a_dropdown', message: `[${ref}] is not a drop-down.` }
  const wanted = String(option).replace(/\s+/g, ' ').trim().toLowerCase()
  const options = [...el.options]
  const match = options.find((o) => o.text.replace(/\s+/g, ' ').trim().toLowerCase() === wanted)
    || options.find((o) => o.text.toLowerCase().includes(wanted))
  if (!match) return { error: 'option_not_found', options: options.map((o) => o.text.trim()).slice(0, 50) }
  el.value = match.value
  el.dispatchEvent(new Event('input', { bubbles: true }))
  el.dispatchEvent(new Event('change', { bubbles: true }))
  return { ok: true, selected: match.text.trim() }
}

