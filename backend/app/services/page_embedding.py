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
  const textOf = (el) => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 300);
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
