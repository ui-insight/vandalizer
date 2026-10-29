"""Delivery-time print support for saved Pages, including existing revisions."""

import secrets
from datetime import timezone

from bs4 import BeautifulSoup

from app.services.artifacts import CONTENT_CSP


PRINT_STYLE = """
#vandalizer-print-controls {
  all: initial; display: block; padding: 12px; text-align: right;
  font: 14px/1.5 system-ui, sans-serif; background: #fff; color: #111827;
}
#vandalizer-print-button {
  all: initial; display: inline-block; padding: 9px 14px; border: 1px solid #cbd5e1;
  border-radius: 6px; background: #fff; color: #111827; cursor: pointer;
  font: 600 14px/1.5 system-ui, sans-serif;
}
#vandalizer-print-button:focus-visible { outline: 3px solid #2563eb; outline-offset: 2px; }
@media print {
  @page {
    margin: 12mm 12mm 22mm;
    @bottom-center {
      content: __PAGE_FOOTER__;
      font: 9pt/1.35 system-ui, sans-serif; color: #334155;
      text-align: center; vertical-align: middle; white-space: normal;
      overflow-wrap: anywhere;
    }
  }
  *, *::before, *::after {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  #vandalizer-print-controls { display: none !important; }
  figure, tr { break-inside: avoid; }
  thead { display: table-header-group; }
}
"""
PRINT_SCRIPT = """document.getElementById('vandalizer-print-button').addEventListener('click', function () { window.print(); });"""
AUTO_PRINT_SCRIPT = """window.addEventListener('load', function () { window.print(); });"""


def render_page(revision: dict, version: int, view: str = "content") -> tuple[str, str]:
    """Return HTML and CSP without modifying immutable stored source.

    Preview/download content remains script-free. Full-page and print views
    permit only our nonce-authorized print script, in an opaque sandbox with
    no network access or same-origin privileges. Authored scripts stay blocked.
    """
    soup = BeautifulSoup(revision["html"], "html.parser")
    # Saved Pages already have a canonical head/body; tolerate old fragments.
    if not soup.html:
        wrapper = BeautifulSoup("<!doctype html><html><head></head><body></body></html>", "html.parser")
        for node in list(soup.contents):
            wrapper.body.append(node.extract())
        soup = wrapper
    if not soup.head:
        soup.html.insert(0, soup.new_tag("head"))
    if not soup.body:
        soup.html.append(soup.new_tag("body"))
    for element in soup.select("#vandalizer-print-style, #vandalizer-print-footer, #vandalizer-print-controls, #vandalizer-print-script"):
        element.decompose()
    saved = revision.get("created_at")
    if saved is not None:
        if saved.tzinfo is None:
            saved = saved.replace(tzinfo=timezone.utc)
        date = saved.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    else:
        date = "Date unavailable"
    footer_text = f'{revision["title"]} · Version {version} · Saved {date}'
    soup.head.append(soup.new_tag("meta", id="vandalizer-print-footer", attrs={"name": "page-version", "content": footer_text}))
    # A margin box reserves space on every sheet instead of overlaying content.
    # Hex-escape all text, including quotes and </style>, for the CSS context.
    footer_css = '"' + ''.join(f'\\{ord(char):x} ' for char in footer_text) + '"'
    style = soup.new_tag("style", id="vandalizer-print-style")
    style.string = PRINT_STYLE.replace("__PAGE_FOOTER__", footer_css)
    soup.head.append(style)

    csp = CONTENT_CSP
    if view in {"full", "print"}:
        nonce = secrets.token_urlsafe(24)
        csp = csp.replace("sandbox;", "sandbox allow-scripts allow-modals;").replace("script-src 'none'", f"script-src 'nonce-{nonce}'")
        controls = soup.new_tag("nav", id="vandalizer-print-controls", attrs={"aria-label": "Page printing"})
        button = soup.new_tag("button", id="vandalizer-print-button", type="button")
        button.string = "Print / Save as PDF"
        controls.append(button)
        soup.body.insert(0, controls)
        script = soup.new_tag("script", id="vandalizer-print-script", nonce=nonce)
        script.string = PRINT_SCRIPT + (AUTO_PRINT_SCRIPT if view == "print" else "")
        soup.body.append(script)
    # The meta policy must agree with the response header. It cannot loosen
    # that header, but the old script-src 'none' would block our print button.
    for meta in soup.find_all("meta"):
        if str(meta.get("http-equiv", "")).lower() == "content-security-policy":
            meta.decompose()
    soup.head.insert(0, soup.new_tag("meta", attrs={"http-equiv": "Content-Security-Policy", "content": csp}))
    return str(soup), csp
