"""Fit published HTML into the reader's normal scroll without granting app access."""
import re
import secrets

from bs4 import BeautifulSoup


EMBED_STYLE = """
html, body { height: auto !important; min-height: 0 !important; max-height: none !important; overflow-y: visible !important; }
.vandalizer-table-scroll { max-width: 100%; overflow-x: auto; overscroll-behavior-x: contain; }
.vandalizer-table-scroll:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
html.vandalizer-picking :is(td, th, li, p, h1, h2, h3, h4, h5, h6, dt, dd, figcaption, caption, blockquote, pre):hover { outline: 2px dashed #b45309; outline-offset: 2px; cursor: crosshair; }
.vandalizer-feedback-spot { outline: 3px solid #f1b300 !important; outline-offset: 2px; background: #fffbeb !important; }
html.vandalizer-editing .vandalizer-editable { outline: 1px dashed #93c5fd; outline-offset: 2px; cursor: text; }
html.vandalizer-editing .vandalizer-editable:hover { outline: 2px solid #3b82f6; }
html.vandalizer-editing .vandalizer-editable:focus { outline: 2px solid #1d4ed8; background: #eff6ff; }
html.vandalizer-editing .vandalizer-edited { background: #fef9c3; }
"""
EMBED_SCRIPT = """(() => {
  // Page-authored JavaScript remains blocked by CSP. Only this nonce-bearing
  // handler runs, in an opaque origin with no network or parent DOM access.
  document.querySelectorAll('table').forEach(table => {
    if (table.parentElement.classList.contains('vandalizer-table-scroll')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'vandalizer-table-scroll';
    wrapper.tabIndex = 0;
    wrapper.setAttribute('role', 'region');
    wrapper.setAttribute('aria-label', (table.caption?.textContent.trim() || 'Table') + ' (scroll horizontally)');
    table.replaceWith(wrapper);
    wrapper.append(table);
  });
  let previous = 0;
  let scheduled = false;
  const measure = () => {
    scheduled = false;
    const body = document.body;
    const top = body.getBoundingClientRect().top + window.scrollY;
    const height = Math.ceil(top + Math.max(body.scrollHeight, body.getBoundingClientRect().height)
      + (parseFloat(getComputedStyle(body).marginBottom) || 0));
    if (height > 0 && height !== previous) {
      previous = height;
      window.parent.postMessage({ type: 'vandalizer:page-height', height }, '*');
    }
  };
  const schedule = () => { if (!scheduled) { scheduled = true; requestAnimationFrame(measure); } };
  new ResizeObserver(schedule).observe(document.body);
  window.addEventListener('resize', schedule);
  window.addEventListener('load', schedule);
  document.addEventListener('load', schedule, true);
  document.addEventListener('toggle', schedule, true);
  document.fonts?.ready.then(schedule);
  schedule();

  // Questions from viewers (page feedback): the app turns on picking, a click
  // reports the element's path from <body> and its text, and the app can ask
  // for a reported spot to be shown again. Only the parent may ask; nothing
  // here reads or sends anything beyond the clicked element's own text.
  const BLOCKS = 'td, th, li, p, h1, h2, h3, h4, h5, h6, dt, dd, figcaption, caption, blockquote, pre';
  const pathOf = (el) => {
    const parts = [];
    while (el && el !== document.body && el.parentElement) {
      parts.unshift(Array.prototype.indexOf.call(el.parentElement.children, el));
      el = el.parentElement;
    }
    return el === document.body ? parts.join('/') : '';
  };
  const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300);
  const resolve = (path, text) => {
    let el = document.body;
    for (const i of (path || '').split('/').filter(Boolean)) { el = el && el.children[Number(i)]; }
    if (el && el !== document.body && (!text || textOf(el) === text)) return el;
    if (!text) return null;
    return Array.from(document.querySelectorAll(BLOCKS)).find(c => textOf(c) === text)
      || Array.from(document.querySelectorAll(BLOCKS)).find(c => textOf(c).includes(text.slice(0, 80))) || null;
  };
  let picking = false;
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || !event.data || typeof event.data !== 'object') return;
    const data = event.data;
    if (data.type === 'vandalizer:pick-mode') {
      picking = data.on === true;
      document.documentElement.classList.toggle('vandalizer-picking', picking);
    } else if (data.type === 'vandalizer:show-spot') {
      document.querySelectorAll('.vandalizer-feedback-spot').forEach(e => e.classList.remove('vandalizer-feedback-spot'));
      const el = resolve(typeof data.path === 'string' ? data.path : '', typeof data.text === 'string' ? data.text : '');
      if (el) {
        el.classList.add('vandalizer-feedback-spot');
        const top = el.getBoundingClientRect().top + window.scrollY;
        window.parent.postMessage({ type: 'vandalizer:spot-shown', found: true, top }, '*');
      } else {
        window.parent.postMessage({ type: 'vandalizer:spot-shown', found: false }, '*');
      }
    }
  });
  // Edit text (owner only; the app asks for it). Each innermost text block
  // becomes editable as plain text. On collect, the changed blocks are sent
  // back as {tag, index, original, text}: index counts earlier blocks with
  // the same tag and original text, which is how the server finds the block
  // in the saved HTML (positions differ: tables are wrapped here, and the
  // browser adds <tbody>). Nothing is saved from here.
  const EDITABLE = 'td, th, li, p, h1, h2, h3, h4, h5, h6, dt, dd, figcaption, caption, blockquote, pre';
  const editState = new Map();
  const editedCount = () => Array.from(editState.entries()).filter(([el, s]) => el.textContent !== s.original).length;
  const startEditing = () => {
    if (editState.size) return;
    const seen = new Map();
    Array.from(document.querySelectorAll(EDITABLE)).forEach(el => {
      const original = el.textContent || '';
      const key = el.tagName.toLowerCase() + '\\u0000' + original;
      const index = seen.get(key) || 0;
      seen.set(key, index + 1);
      if (el.querySelector(EDITABLE) || !original.trim()) return;
      editState.set(el, { tag: el.tagName.toLowerCase(), index, original });
      try { el.contentEditable = 'plaintext-only'; } catch (e) { el.contentEditable = 'true'; }
      if (el.contentEditable !== 'plaintext-only') el.contentEditable = 'true';
      el.classList.add('vandalizer-editable');
      el.spellcheck = true;
    });
    document.documentElement.classList.add('vandalizer-editing');
  };
  const stopEditing = () => {
    editState.forEach((_s, el) => { el.removeAttribute('contenteditable'); el.classList.remove('vandalizer-editable', 'vandalizer-edited'); });
    editState.clear();
    document.documentElement.classList.remove('vandalizer-editing');
  };
  document.addEventListener('keydown', (event) => {
    if (!editState.size || event.key !== 'Enter') return;
    const el = event.target instanceof Element ? event.target.closest('.vandalizer-editable') : null;
    if (el && el.tagName !== 'PRE') event.preventDefault();
  }, true);
  document.addEventListener('paste', (event) => {
    const el = event.target instanceof Element ? event.target.closest('.vandalizer-editable') : null;
    if (!el || el.contentEditable === 'plaintext-only') return;
    event.preventDefault();
    document.execCommand('insertText', false, (event.clipboardData && event.clipboardData.getData('text/plain')) || '');
  }, true);
  document.addEventListener('input', (event) => {
    const el = event.target instanceof Element ? event.target.closest('.vandalizer-editable') : null;
    if (!el) return;
    const state = editState.get(el);
    el.classList.toggle('vandalizer-edited', !!state && el.textContent !== state.original);
    window.parent.postMessage({ type: 'vandalizer:edit-count', count: editedCount() }, '*');
    schedule();
  }, true);
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || !event.data || typeof event.data !== 'object') return;
    if (event.data.type === 'vandalizer:edit-mode') {
      if (event.data.on === true) startEditing(); else stopEditing();
    } else if (event.data.type === 'vandalizer:edit-collect') {
      const edits = [];
      editState.forEach((s, el) => {
        const text = el.textContent || '';
        if (text !== s.original) edits.push({ tag: s.tag, index: s.index, original: s.original, text });
      });
      window.parent.postMessage({ type: 'vandalizer:edits', edits }, '*');
    }
  });
  document.addEventListener('click', (event) => {
    if (!picking) return;
    const target = event.target instanceof Element ? event.target : null;
    const el = (target && target.closest(BLOCKS)) || target;
    if (!el || el === document.body || el === document.documentElement) return;
    event.preventDefault();
    event.stopPropagation();
    window.parent.postMessage({ type: 'vandalizer:page-pick', path: pathOf(el), text: textOf(el) }, '*');
  }, true);
})();"""


def prepare_page_embed(html: str, csp: str) -> tuple[str, str]:
    """Inject trusted sizing only at delivery; saved HTML and downloads stay static."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select('#vandalizer-embed-style, #vandalizer-embed-script'):
        element.decompose()
    nonce = secrets.token_urlsafe(24)
    csp = re.sub(r'\bsandbox\b', 'sandbox allow-scripts', csp, count=1)
    csp = csp.replace("script-src 'none'", f"script-src 'nonce-{nonce}'")
    head, body = soup.head, soup.body
    if head is None or body is None:
        raise ValueError('Saved Page is missing its document structure')
    style = soup.new_tag('style', id='vandalizer-embed-style')
    style.string = EMBED_STYLE
    head.append(style)
    script = soup.new_tag('script', id='vandalizer-embed-script', nonce=nonce)
    script.string = EMBED_SCRIPT
    body.append(script)
    for meta in soup.find_all('meta'):
        if str(meta.get('http-equiv', '')).lower() == 'content-security-policy':
            meta['content'] = csp
    return str(soup), csp
