import io
import re

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
