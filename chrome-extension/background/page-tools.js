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
    // display:contents wrappers draw no box of their own; their children do.
    if (style.display === 'contents') return true
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

  // Clear every earlier number, in frames at any depth and in shadow roots,
  // so a leftover can never be clicked in place of this read's control.
  const clearRefs = (root) => {
    root.querySelectorAll('[data-vz-ref]').forEach((e) => e.removeAttribute('data-vz-ref'))
    root.querySelectorAll('*').forEach((e) => {
      if (e.shadowRoot) clearRefs(e.shadowRoot)
      if (e.tagName === 'IFRAME' || e.tagName === 'FRAME') {
        let inner = null
        try { inner = e.contentDocument } catch { inner = null }
        if (inner) clearRefs(inner)
      }
    })
  }
  clearRefs(document)
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

/**
 * Click by number, unless the control could change something.
 *
 * Decided by what the control is, not only by its words: a link to another
 * page and a search form that sends GET only read; a form that posts, a
 * checkbox or switch, and a button whose purpose can't be read from its
 * label may write, so they need a label that clearly reads (or a filter
 * panel around them).
 */
export function clickRef(ref) {
  // Defined in here: this function is serialized into the page on its own.
  function clickVerdict(el) {
    const clean = (s) => String(s || '').replace(/\s+/g, ' ').trim()
    const doc = el.ownerDocument
    const tag = el.tagName
    const role = (el.getAttribute('role') || '').toLowerCase()
    const type = (el.getAttribute('type') || '').toLowerCase()

    // Every name the control has, not just the first: an icon button's
    // text can be "✓" while its aria-label says "Approve".
    const names = [el.innerText ?? el.textContent, el.value, el.getAttribute('aria-label'), el.title, el.getAttribute('alt')]
    if (el.id) names.push(doc.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText)
    const labelledBy = el.getAttribute('aria-labelledby')
    if (labelledBy) labelledBy.split(/\s+/).forEach((id) => names.push(doc.getElementById(id)?.innerText))
    names.push(el.closest('label')?.innerText)
    el.querySelectorAll('img[alt], [aria-label], [title]').forEach((child) => {
      names.push(child.getAttribute('alt'), child.getAttribute('aria-label'), child.getAttribute('title'))
    })
    const label = [...new Set(names.map(clean).filter(Boolean))].join(' / ').slice(0, 200)

    // Nouns that look like verbs: a "Purchase Orders" tab orders nothing.
    const NOUNS = /\b(purchase orders?|change (requests?|orders?|history|log)|orders? (history|status|numbers?|details|list)|requests? (history|status|numbers?|details|list)|payments? (history|details|status|summary|schedule)|transfers? (history|details)|post(ed|ing) dates?|sign(ed)? dates?|approv(al|ed) (status|history|dates?)|submi(tted|ssion) (dates?|status|history))\b/gi
    // Filter controls change the view, not the record.
    const FILTER_WORDS = /\b(add|apply|clear|reset|remove|update|change)\s+(a\s+|the\s+)?(filters?|criteria|columns?|sort(ing)?|search|view|date range)\b/gi
    const words = label.replace(NOUNS, ' ').replace(FILTER_WORDS, ' ')
    const DESTRUCTIVE = /\b(approve|certify|sign|e-?sign|delete|remove|pay|payment|transfer|withdraw|cancel|confirm|reject|deny|decline|accept|agree|void|reverse|finali[sz]e|draw ?down|close ?out|log ?out|sign ?out|log ?off|sign ?off|purchase|send)\b/i
    const WRITE = /\b(submit|save|update|approve|certify|sign|e-?sign|send|delete|remove|pay|payment|transfer|confirm|apply|post|upload|cancel|withdraw|reject|deny|decline|accept|agree|purchase|order|create|add|change|request|finali[sz]e|draw ?down|close ?out|log ?out|sign ?out|log ?off|sign ?off|void|reverse|archive|release|route|discard|deactivate|unlock)\b/i
    const READS = /\b(search|find|filter|view|show|display|refresh|look ?up|run report|next|previous|prev|first|last|page|sort|expand|collapse|details|more|export|print)\b/i

    const form = el.form || el.closest('form')
    const method = (el.getAttribute('formmethod') || form?.getAttribute('method') || 'get').toLowerCase()
    const getForm = Boolean(form) && method === 'get'
    const inFilterPanel = () => {
      if (getForm || el.closest('[role="search"]')) return true
      let node = el.parentElement
      for (let i = 0; node && i < 6; i++, node = node.parentElement) {
        const name = `${node.id} ${typeof node.className === 'string' ? node.className : ''} ${node.getAttribute('aria-label') || ''}`
        if (/filter|search|criteria|facet|query|toolbar/i.test(name)) return true
      }
      return false
    }

    const blocked = (error, why) => ({
      blocked: true,
      error,
      label,
      message: `${label ? `"${label.slice(0, 80)}"` : 'That control'} ${why}, so Vandalizer will not click it. Ask the person to click it themselves if it is needed.`,
    })
    const allowed = { blocked: false, label }

    if (tag === 'INPUT' && ['file', 'password', 'reset'].includes(type)) return blocked('blocked_write_action', 'is not something Vandalizer uses')

    // Checkboxes, radios and switches often save as soon as they change.
    const toggle = (tag === 'INPUT' && (type === 'checkbox' || type === 'radio'))
      || ['checkbox', 'switch', 'radio', 'menuitemcheckbox', 'menuitemradio'].includes(role)
      || el.hasAttribute('aria-pressed')
    if (toggle) {
      if (inFilterPanel() && !DESTRUCTIVE.test(words)) return allowed
      return blocked('blocked_write_action', 'is a checkbox or switch that may save a change')
    }

    // A button that sends its form.
    const submits = (tag === 'INPUT' && (type === 'submit' || type === 'image'))
      || (tag === 'BUTTON' && (type === '' || type === 'submit') && Boolean(el.form))
    if (submits) {
      // A GET form only asks for a page (a search); a posting form may write.
      if (getForm) return DESTRUCTIVE.test(words) ? blocked('blocked_write_action', 'looks like it would change something') : allowed
      if (READS.test(words) && !WRITE.test(words)) return allowed
      return blocked('blocked_write_action', 'sends a form that may change something')
    }

    // A real link to another page: judge where it goes.
    const rawHref = tag === 'A' ? (el.getAttribute('href') || '').trim() : ''
    if (rawHref && !rawHref.startsWith('#') && !/^javascript:/i.test(rawHref)) {
      let target = null
      try { target = new URL(el.href, doc.baseURI) } catch { target = null }
      let path = target ? `${target.pathname}${target.search}` : rawHref
      try { path = decodeURIComponent(path) } catch { /* keep it encoded */ }
      if (/(^|[/_\-.=?&])(delete|del|remove|destroy|logout|log-?out|log_?off|logoff|signout|sign-?out|signoff|approve|reject|certify|submit|withdraw|cancel|pay|transfer|void)([/_\-.=?&]|$)/i.test(path)) {
        return blocked('blocked_write_action', 'links to an address that looks like it would change something')
      }
      return DESTRUCTIVE.test(words) ? blocked('blocked_write_action', 'looks like it would change something') : allowed
    }

    // Tabs and tree items switch what is shown.
    if (['tab', 'treeitem', 'option'].includes(role)) {
      return DESTRUCTIVE.test(words) ? blocked('blocked_write_action', 'looks like it would change something') : allowed
    }

    // Any other button: it must say what it does.
    if (!/[a-z]{2}/i.test(label)) return blocked('unlabeled_control', 'has no readable label, so what it does is unknown')
    if (!WRITE.test(words)) return allowed
    // "Apply" or "Clear" in a filter panel narrows the list.
    if (inFilterPanel() && !DESTRUCTIVE.test(words)) return allowed
    return blocked('blocked_write_action', 'looks like it would change something')
  }

  // Same places readPage numbers: the page, same-origin frames at any depth,
  // and open shadow roots.
  const findRef = (root) => {
    const hit = root.querySelector(`[data-vz-ref="${Number(ref)}"]`)
    if (hit) return hit
    for (const e of root.querySelectorAll('*')) {
      let inner = e.shadowRoot
      if (!inner && (e.tagName === 'IFRAME' || e.tagName === 'FRAME')) {
        try { inner = e.contentDocument } catch { inner = null }
      }
      const found = inner && findRef(inner)
      if (found) return found
    }
    return null
  }
  const el = findRef(document)
  if (!el) return { error: 'stale_ref', message: `No element [${ref}] on the page now. Read the page again.` }
  const verdict = clickVerdict(el)
  if (verdict.blocked) {
    return {
      error: verdict.error,
      label: verdict.label,
      message: verdict.message,
    }
  }
  el.scrollIntoView({ block: 'center' })
  el.click()
  return { ok: true, clicked: verdict.label.slice(0, 80) }
}

/** Replace a search or filter field's text, the way a person typing would. */
export function typeRef(ref, text) {
  // Same places readPage numbers: the page, same-origin frames at any depth,
  // and open shadow roots.
  const findRef = (root) => {
    const hit = root.querySelector(`[data-vz-ref="${Number(ref)}"]`)
    if (hit) return hit
    for (const e of root.querySelectorAll('*')) {
      let inner = e.shadowRoot
      if (!inner && (e.tagName === 'IFRAME' || e.tagName === 'FRAME')) {
        try { inner = e.contentDocument } catch { inner = null }
      }
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
  // Same places readPage numbers: the page, same-origin frames at any depth,
  // and open shadow roots.
  const findRef = (root) => {
    const hit = root.querySelector(`[data-vz-ref="${Number(ref)}"]`)
    if (hit) return hit
    for (const e of root.querySelectorAll('*')) {
      let inner = e.shadowRoot
      if (!inner && (e.tagName === 'IFRAME' || e.tagName === 'FRAME')) {
        try { inner = e.contentDocument } catch { inner = null }
      }
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

