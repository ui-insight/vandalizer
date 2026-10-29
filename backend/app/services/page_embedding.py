"""Fit published HTML into the reader's normal scroll without granting app access."""
import re
import secrets

from bs4 import BeautifulSoup


EMBED_STYLE = """
html, body { height: auto !important; min-height: 0 !important; max-height: none !important; overflow-y: visible !important; }
.vandalizer-table-scroll { max-width: 100%; overflow-x: auto; overscroll-behavior-x: contain; }
.vandalizer-table-scroll:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
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
})();"""


def prepare_page_embed(html: str, csp: str) -> tuple[str, str]:
    """Inject trusted sizing only at delivery; saved HTML and downloads stay static."""
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select('#vandalizer-embed-style, #vandalizer-embed-script'):
        element.decompose()
    nonce = secrets.token_urlsafe(24)
    csp = re.sub(r'\bsandbox\b', 'sandbox allow-scripts', csp, count=1)
    csp = csp.replace("script-src 'none'", f"script-src 'nonce-{nonce}'")
    style = soup.new_tag('style', id='vandalizer-embed-style')
    style.string = EMBED_STYLE
    soup.head.append(style)
    script = soup.new_tag('script', id='vandalizer-embed-script', nonce=nonce)
    script.string = EMBED_SCRIPT
    soup.body.append(script)
    for meta in soup.find_all('meta'):
        if str(meta.get('http-equiv', '')).lower() == 'content-security-policy':
            meta['content'] = csp
    return str(soup), csp
