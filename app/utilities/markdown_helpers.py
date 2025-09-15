import io
import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from xhtml2pdf import pisa


def convert_inline_markdown_to_tags(text):
    """Converts inline Markdown to ReportLab's supported XML tags."""
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.*?)__", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    text = re.sub(r"~~(.*?)~~", r"<strike>\1</strike>", text)
    text = re.sub(r"`(.*?)`", r'<font face="Courier">\1</font>', text)
    return text


def sanitize_for_reportlab(html: str) -> str:
    """
    Convert <span style="color:…">…</span> into <font color="…">…</font>,
    and drop any other <span> tags entirely.
    """
    soup = BeautifulSoup(html, "html.parser")
    for span in soup.find_all("span"):
        style = span.get("style", "")
        # look for a color declaration
        m = re.search(r"color\s*:\s*([^;]+)", style)
        if m:
            color = m.group(1).strip()
            new_tag = soup.new_tag("font", color=color)
            new_tag.string = span.get_text()
            span.replace_with(new_tag)
        else:
            span.unwrap()
    return str(soup)


DEFAULT_PDF_CSS = """
@page {
  size: Letter;
  margin: 0.75in;
}
body {
  font-family: Helvetica, Arial, sans-serif;
  color: #222;
  line-height: 1.5;
  font-size: 11pt;
}
h1, h2, h3 { font-weight: 700; margin: 0.6em 0 0.3em; }
h1 { font-size: 24pt; } h2 { font-size: 18pt; } h3 { font-size: 14pt; }
p, li { font-size: 11pt; }
ul, ol { margin: 0.2em 0 0.8em 1.2em; }
table { width: 100%; border-collapse: collapse; margin: 0.6em 0 1em; }
th, td { border: 1px solid #ddd; padding: 6px 8px; }
th { background: #f6f7f9; font-weight: 600; }
code, pre {
  font-family: Courier, monospace;
  font-size: 10pt;
}
pre { background: #f6f7f9; padding: 8px; border-radius: 6px; }
hr { border: 0; border-top: 1px solid #eee; margin: 16px 0; }
img { max-width: 100%; height: auto; }
"""


def _ensure_full_html(html: str) -> str:
    """Wrap fragments in <html><head>… so xhtml2pdf is happy."""
    html = html or ""
    soup = BeautifulSoup(html, "html.parser")

    # If it's already a full HTML doc, just ensure there's a <style> with defaults.
    if soup.find("html"):
        head = soup.find("head") or soup.html.insert(0, soup.new_tag("head"))
        # prepend default CSS (keep user CSS last so it can override defaults)
        style_tag = soup.new_tag("style")
        style_tag.string = DEFAULT_PDF_CSS
        head.insert(0, style_tag)
        return str(soup)

    # Otherwise, wrap it.
    doc = BeautifulSoup("", "html.parser")
    html_tag = doc.new_tag("html")
    head_tag = doc.new_tag("head")
    style_tag = doc.new_tag("style")
    style_tag.string = DEFAULT_PDF_CSS
    head_tag.append(style_tag)
    body_tag = doc.new_tag("body")

    body_fragment = BeautifulSoup(html, "html.parser")
    body_tag.append(body_fragment)

    html_tag.append(head_tag)
    html_tag.append(body_tag)
    doc.append(html_tag)
    return str(doc)


def _link_callback_factory(base_path: str):
    """
    Resolve relative images/stylesheets to filesystem paths for xhtml2pdf.
    base_path: typically your Flask `static` folder or app root.
    """

    def _link_callback(uri, rel):
        parsed = urlparse(uri)
        # Already a file path
        if os.path.isabs(uri) and os.path.exists(uri):
            return uri
        # Data URIs and http(s) are passed through (xhtml2pdf supports data:; http(s) limited)
        if parsed.scheme in ("http", "https", "data"):
            return uri
        # Otherwise resolve relative to base_path
        candidate = os.path.join(base_path, uri.lstrip("/"))
        return candidate

    return _link_callback


def generate_pdf_from_html(html: str) -> io.BytesIO:
    """
    Pure-Python HTML→PDF using xhtml2pdf (ReportLab under the hood).
    - html: the HTML string (fragment or full document)
    - base_path: filesystem base for resolving relative assets (e.g. Flask app.root_path or static_folder)
    Returns BytesIO positioned at 0.
    """
    full_html = _ensure_full_html(html)

    print(full_html)

    buf = io.BytesIO()
    link_cb = _link_callback_factory(None)
    # pisa.CreatePDF accepts file-like for src & dest; css within <style> is supported.
    result = pisa.CreatePDF(
        src=io.StringIO(full_html),
        dest=buf,
        link_callback=link_cb,
        encoding="utf-8",
    )
    if result.err:
        # You can log result.log if needed
        # Fall back to a very simple plaintext PDF via ReportLab if you want,
        # but usually fixing the HTML/CSS is better.
        raise RuntimeError("xhtml2pdf failed to render HTML to PDF")
    buf.seek(0)
    return buf


def generate_pdf_from_markdown(formatted_markdown: str):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )
    styles = getSampleStyleSheet()
    # … your style tweaks here …

    story = []
    lines = formatted_markdown.strip().split("\n")
    in_ul = in_ol = False
    list_items = []

    for line in lines:
        line = line.strip()
        # detect list items
        is_ul_item = line.startswith(("* ", "- "))
        is_ol_item = re.match(r"^\d+\.\s", line)

        # close lists when they end
        if (in_ul and not is_ul_item) or (in_ol and not is_ol_item):
            story.append(
                ListFlowable(list_items, bulletType="bullet" if in_ul else "1")
            )
            story.append(Spacer(1, 0.1 * inch))
            list_items = []
            in_ul = in_ol = False

        # headings
        if line.startswith("# "):
            raw = line[2:]
            tag = "h1"
        elif line.startswith("## "):
            raw = line[3:]
            tag = "h2"
        elif line.startswith("### "):
            raw = line[4:]
            tag = "h3"
        else:
            raw = line
            tag = None

        if tag:
            html = convert_inline_markdown_to_tags(raw)
            clean = sanitize_for_reportlab(html)
            story.append(Paragraph(clean, styles[tag]))
            continue

        # unordered list
        if is_ul_item:
            in_ul = True
            html = convert_inline_markdown_to_tags(line[2:])
            clean = sanitize_for_reportlab(html)
            list_items.append(ListItem(Paragraph(clean, styles["Bullet"])))
            continue

        # ordered list
        if is_ol_item:
            in_ol = True
            text = re.sub(r"^\d+\.\s", "", line)
            html = convert_inline_markdown_to_tags(text)
            clean = sanitize_for_reportlab(html)
            list_items.append(ListItem(Paragraph(clean, styles["Bullet"])))
            continue

        # normal paragraph
        if line:
            html = convert_inline_markdown_to_tags(line)
            clean = sanitize_for_reportlab(html)
            story.append(Paragraph(clean, styles["Normal"]))
            story.append(Spacer(1, 0.1 * inch))

    # if the file ended with a list still open
    if in_ul or in_ol:
        story.append(ListFlowable(list_items, bulletType="bullet" if in_ul else "1"))

    doc.build(story)
    buf.seek(0)
    return buf
