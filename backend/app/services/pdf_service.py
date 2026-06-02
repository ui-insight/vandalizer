"""PDF generation service — fallback report when no fillable template is attached."""

import datetime
import json
import logging
import re
from io import BytesIO

logger = logging.getLogger(__name__)


def generate_fillable_template(title: str, items: list) -> tuple[bytes, list[str]]:
    """Generate an AcroForm fillable PDF with one text field per extraction item.

    Returns (pdf_bytes, field_names) where field_names[i] is the AcroForm field
    name for items[i]. Field names are stable indexed strings: field_0, field_1, …
    """
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors

    buf = BytesIO()
    page_width, page_height = letter
    left_margin = inch
    right_margin = inch
    field_width = page_width - left_margin - right_margin
    field_height = 28

    c = Canvas(buf, pagesize=letter)
    y = page_height - inch  # start below top margin

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left_margin, y, title or "Extraction Template")
    y -= 32

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(left_margin, y, "Fill in the fields below with the extracted values.")
    c.setFillColor(colors.black)
    y -= 24

    field_names: list[str] = []
    for i, item in enumerate(items):
        label = (item.title if item.title else item.searchphrase) or f"Field {i + 1}"
        field_name = f"field_{i}"
        field_names.append(field_name)

        # Page break if needed
        if y < inch + field_height + 30:
            c.showPage()
            y = page_height - inch

        # Label
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#111827"))
        c.drawString(left_margin, y, label)
        y -= 18

        # Text field
        c.acroForm.textfield(
            name=field_name,
            tooltip=label,
            x=left_margin,
            y=y - field_height,
            width=field_width,
            height=field_height,
            fontSize=10,
            fillColor=colors.HexColor("#f9fafb"),
            borderColor=colors.HexColor("#d1d5db"),
            borderWidth=1,
            textColor=colors.black,
        )
        y -= field_height + 20

    c.save()
    return buf.getvalue(), field_names


def generate_extraction_pdf(
    title: str,
    items: list,
    results: dict[str, str],
    document_names: list[str],
) -> bytes:
    """Generate a clean report PDF from extraction results using reportlab.

    Args:
        title: The extraction set title (used as document header).
        items: SearchSetItem objects (uses item.title if set, else item.searchphrase).
        results: Mapping of searchphrase → extracted value.
        document_names: Names of source documents (shown in meta row).

    Returns:
        Raw PDF bytes.
    """
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ExtrTitle",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ExtrMeta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=16,
    )
    cell_style = ParagraphStyle(
        "ExtrCell",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )

    story = []

    # Header
    story.append(Paragraph(_xml_escape(title), title_style))

    # Meta row
    date_str = datetime.date.today().strftime("%B %d, %Y")
    doc_part = f"Documents: {', '.join(document_names)}" if document_names else ""
    meta_parts = [date_str] + ([doc_part] if doc_part else [])
    story.append(Paragraph(_xml_escape(" · ".join(meta_parts)), meta_style))

    # Build table data
    table_data = [["Field", "Value"]]
    for item in items:
        label = item.title if item.title else item.searchphrase
        value = results.get(item.searchphrase, "")
        table_data.append([
            Paragraph(_xml_escape(label), cell_style),
            Paragraph(_xml_escape(str(value)), cell_style),
        ])

    col_widths = [2.5 * inch, 4.5 * inch]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    row_count = len(table_data)
    table_style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, row_count - 1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(table_style_cmds))

    story.append(table)
    story.append(Spacer(1, 0.3 * inch))

    doc.build(story)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Markdown / workflow-output PDF renderer
# --------------------------------------------------------------------------- #

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
# Triple-marker (bold-italic) must come *before* the bold pattern; otherwise
# `\*\*(.+?)\*\*` pulls a leading `*` into the bold body and the leftover stray
# `*`s pair with the closing `*` across the `</b>`, producing mis-nested tags
# like `<b><i>x</b></i>` that crash reportlab's paraparser.
_MD_BOLD_ITALIC_RE = re.compile(r"\*\*\*(.+?)\*\*\*")
_MD_UNDERSCORE_BOLD_ITALIC_RE = re.compile(r"___(.+?)___")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_UNDERSCORE_BOLD_RE = re.compile(r"__(.+?)__")
_MD_UNDERSCORE_ITALIC_RE = re.compile(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)")
_MD_CODE_RE = re.compile(r"`([^`]+?)`")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_MD_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_MD_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
_MD_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)$")
_MD_HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_MD_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)\s*([\w+-]*)\s*$")
# One-or-more dashes per column matches the GFM spec (and remark-gfm, which the
# UI renders with), so a model emitting ``|--|--|`` still yields a real table.
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


# Unicode characters outside Helvetica's WinAnsi encoding render as ■ boxes.
# LLM/Word output frequently uses U+2011 (non-breaking hyphen) inside compound
# words like "non‑expert" / "cross‑functional"; replace these with safe ASCII.
_PDF_CHAR_REPLACEMENTS = {
    "‐": "-",   # HYPHEN
    "‑": "-",   # NON-BREAKING HYPHEN
    "‒": "-",   # FIGURE DASH
    "−": "-",   # MINUS SIGN
    "⁃": "-",   # HYPHEN BULLET
    "‧": "-",   # HYPHENATION POINT
    "­": "",    # SOFT HYPHEN
    "​": "",    # ZERO WIDTH SPACE
    "‌": "",    # ZERO WIDTH NON-JOINER
    "‍": "",    # ZERO WIDTH JOINER
    "⁠": "",    # WORD JOINER
    "﻿": "",    # ZERO WIDTH NO-BREAK SPACE
}


def _normalize_for_pdf(text: str) -> str:
    for src, dst in _PDF_CHAR_REPLACEMENTS.items():
        if src in text:
            text = text.replace(src, dst)
    return text


def _xml_escape(text: str) -> str:
    return (
        _normalize_for_pdf(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_inline(text: str) -> str:
    """Convert inline markdown into reportlab Paragraph mini-HTML markup.

    Order matters: escape XML first, then apply markdown patterns so the
    replacement tags survive the escape step.
    """
    # Strip markdown link syntax; keep the visible text only. LLM-generated URLs
    # are frequently hallucinated — matches the docx renderer's behavior.
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _xml_escape(text)
    # Inline code first so its contents aren't reinterpreted as bold/italic.
    text = _MD_CODE_RE.sub(
        r'<font face="Courier" backColor="#f3f4f6">\1</font>', text
    )
    # Triple markers before double, so `***x***` becomes properly nested
    # `<b><i>x</i></b>` instead of malformed `<b><i>x</b></i>`.
    text = _MD_BOLD_ITALIC_RE.sub(r"<b><i>\1</i></b>", text)
    text = _MD_UNDERSCORE_BOLD_ITALIC_RE.sub(r"<b><i>\1</i></b>", text)
    text = _MD_BOLD_RE.sub(r"<b>\1</b>", text)
    text = _MD_UNDERSCORE_BOLD_RE.sub(r"<b>\1</b>", text)
    text = _MD_ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _MD_UNDERSCORE_ITALIC_RE.sub(r"<i>\1</i>", text)
    return text


def _safe_paragraph(raw: str, style, **kwargs):
    """Build a Paragraph from a markdown string, falling back to escaped text.

    Reportlab's paraparser raises ValueError on malformed mini-HTML (e.g. tags
    closed in the wrong order). When that happens we'd rather lose the
    formatting on one line than 500 the entire PDF download.
    """
    from reportlab.platypus import Paragraph

    try:
        return Paragraph(_format_inline(raw), style, **kwargs)
    except ValueError:
        logger.warning("PDF inline-markdown parse failed; falling back to plain text", exc_info=True)
        return Paragraph(_xml_escape(raw), style, **kwargs)


def _styles() -> dict:
    """Build the named ParagraphStyle dictionary used by the renderer."""
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    base = getSampleStyleSheet()
    body_font = "Helvetica"
    body_size = 10.5
    body_leading = 15

    s = {
        "title": ParagraphStyle(
            "WfTitle",
            parent=base["Title"],
            fontSize=22,
            leading=26,
            spaceAfter=4,
            textColor=colors.HexColor("#191919"),
            alignment=0,
        ),
        "meta": ParagraphStyle(
            "WfMeta",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "WfH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            spaceBefore=14,
            spaceAfter=6,
            textColor=colors.HexColor("#191919"),
        ),
        "h2": ParagraphStyle(
            "WfH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            spaceBefore=12,
            spaceAfter=5,
            textColor=colors.HexColor("#191919"),
        ),
        "h3": ParagraphStyle(
            "WfH3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            spaceBefore=10,
            spaceAfter=4,
            textColor=colors.HexColor("#1f2937"),
        ),
        "h4": ParagraphStyle(
            "WfH4",
            parent=base["Heading4"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            spaceBefore=8,
            spaceAfter=3,
            textColor=colors.HexColor("#1f2937"),
        ),
        "h5": ParagraphStyle(
            "WfH5",
            parent=base["Heading5"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=6,
            spaceAfter=2,
            textColor=colors.HexColor("#374151"),
        ),
        "h6": ParagraphStyle(
            "WfH6",
            parent=base["Heading6"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            spaceBefore=6,
            spaceAfter=2,
            textColor=colors.HexColor("#374151"),
        ),
        "body": ParagraphStyle(
            "WfBody",
            parent=base["Normal"],
            fontName=body_font,
            fontSize=body_size,
            leading=body_leading,
            textColor=colors.HexColor("#111827"),
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "WfBullet",
            parent=base["Normal"],
            fontName=body_font,
            fontSize=body_size,
            leading=body_leading,
            leftIndent=18,
            bulletIndent=6,
            spaceAfter=2,
            textColor=colors.HexColor("#111827"),
        ),
        "bullet_nested": ParagraphStyle(
            "WfBulletNested",
            parent=base["Normal"],
            fontName=body_font,
            fontSize=body_size,
            leading=body_leading,
            leftIndent=38,
            bulletIndent=26,
            spaceAfter=2,
            textColor=colors.HexColor("#111827"),
        ),
        "blockquote": ParagraphStyle(
            "WfQuote",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=body_size,
            leading=body_leading,
            leftIndent=16,
            textColor=colors.HexColor("#374151"),
            borderColor=colors.HexColor("#d1d5db"),
            borderPadding=(4, 8, 4, 8),
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "WfCode",
            parent=base["Code"],
            fontName="Courier",
            fontSize=9,
            leading=12,
            leftIndent=8,
            rightIndent=8,
            textColor=colors.HexColor("#111827"),
            backColor=colors.HexColor("#f3f4f6"),
            borderColor=colors.HexColor("#e5e7eb"),
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=10,
        ),
        "table_cell": ParagraphStyle(
            "WfTableCell",
            parent=base["Normal"],
            fontName=body_font,
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#111827"),
        ),
        "table_header": ParagraphStyle(
            "WfTableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=12,
            # Black text on the gold (#eab308) header — see _build_table_flowable.
            textColor=colors.HexColor("#111827"),
        ),
    }
    return s


def _heading_style(level: int, styles: dict):
    return styles[f"h{min(max(level, 1), 6)}"]


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cell strings."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # Honor backslash-escaped pipes by using a placeholder.
    line = line.replace(r"\|", "\x00")
    cells = [c.strip().replace("\x00", "|") for c in line.split("|")]
    return cells


def _build_table_flowable(headers: list[str], rows: list[list[str]], styles: dict, usable_width: float):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    col_count = max(len(headers), max((len(r) for r in rows), default=0)) or 1
    # Pad short rows to col_count.
    headers = headers + [""] * (col_count - len(headers))
    rows = [r + [""] * (col_count - len(r)) for r in rows]

    # Allocate widths proportionally to max content length, with a floor.
    max_lens = []
    for col in range(col_count):
        col_max = len(headers[col])
        for row in rows:
            col_max = max(col_max, len(row[col]))
        max_lens.append(min(col_max or 1, 60))
    total = sum(max_lens) or 1
    min_col_width = 0.6 * 72  # 0.6 inch floor
    col_widths = [max(usable_width * (ml / total), min_col_width) for ml in max_lens]
    # Scale down if the floor pushed us over the page width.
    width_sum = sum(col_widths)
    if width_sum > usable_width:
        scale = usable_width / width_sum
        col_widths = [w * scale for w in col_widths]

    data = [[_safe_paragraph(h, styles["table_header"]) for h in headers]]
    for row in rows:
        data.append([_safe_paragraph(cell, styles["table_cell"]) for cell in row])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    row_count = len(data)
    table.setStyle(TableStyle([
        # Vandalizer brand gold header (#eab308) with black text.
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eab308")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Faint gold-tinted zebra striping on body rows.
        ("ROWBACKGROUNDS", (0, 1), (-1, row_count - 1), [colors.white, colors.HexColor("#fdf9eb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]))
    return table


def _markdown_to_story(text: str, styles: dict, usable_width: float) -> list:
    """Convert a markdown string into a list of reportlab Flowables."""
    from reportlab.platypus import Paragraph, Spacer, Preformatted

    story: list = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        # Fenced code block
        fence = _MD_FENCE_RE.match(line)
        if fence:
            fence_marker = fence.group(1)
            i += 1
            code_lines: list[str] = []
            while i < len(lines):
                next_line = lines[i]
                close = _MD_FENCE_RE.match(next_line.rstrip())
                if close and close.group(1)[0] == fence_marker[0]:
                    i += 1
                    break
                code_lines.append(next_line)
                i += 1
            story.append(Preformatted(_normalize_for_pdf("\n".join(code_lines)), styles["code"]))
            continue

        # Markdown table — header row followed by a separator row of dashes.
        if "|" in line and i + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[i + 1].rstrip()):
            headers = _split_table_row(line)
            i += 2  # skip header + separator
            rows: list[list[str]] = []
            while i < len(lines):
                body = lines[i].rstrip()
                if not body.strip() or "|" not in body:
                    break
                rows.append(_split_table_row(body))
                i += 1
            story.append(_build_table_flowable(headers, rows, styles, usable_width))
            story.append(Spacer(1, 8))
            continue

        # Blank line → soft paragraph break (Spacer is implicit via spaceAfter).
        if not line.strip():
            i += 1
            continue

        # Horizontal rule
        if _MD_HR_RE.match(line):
            from reportlab.platypus import HRFlowable
            from reportlab.lib import colors

            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#d1d5db")))
            story.append(Spacer(1, 6))
            i += 1
            continue

        # Heading
        heading = _MD_HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            story.append(_safe_paragraph(heading.group(2).strip(), _heading_style(level, styles)))
            i += 1
            continue

        # Blockquote — accumulate consecutive lines.
        if _MD_BLOCKQUOTE_RE.match(line):
            quote_lines: list[str] = []
            while i < len(lines):
                m = _MD_BLOCKQUOTE_RE.match(lines[i].rstrip())
                if not m:
                    break
                quote_lines.append(m.group(1))
                i += 1
            try:
                quote_html = "<br/>".join(_format_inline(q) for q in quote_lines)
                story.append(Paragraph(quote_html, styles["blockquote"]))
            except ValueError:
                logger.warning("PDF blockquote inline parse failed; falling back to plain text", exc_info=True)
                quote_html = "<br/>".join(_xml_escape(q) for q in quote_lines)
                story.append(Paragraph(quote_html, styles["blockquote"]))
            continue

        # Bullet list
        bullet = _MD_BULLET_RE.match(line)
        if bullet:
            indent = len(bullet.group(1).expandtabs(4))
            nested = indent >= 2
            style = styles["bullet_nested"] if nested else styles["bullet"]
            story.append(_safe_paragraph(bullet.group(2).strip(), style, bulletText="•"))
            i += 1
            continue

        # Numbered list
        numbered = _MD_NUMBERED_RE.match(line)
        if numbered:
            indent = len(numbered.group(1).expandtabs(4))
            nested = indent >= 2
            style = styles["bullet_nested"] if nested else styles["bullet"]
            bullet_text = f"{numbered.group(2)}."
            story.append(_safe_paragraph(numbered.group(3).strip(), style, bulletText=bullet_text))
            i += 1
            continue

        # Paragraph — gather consecutive non-block lines into one paragraph.
        para_lines = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i].rstrip()
            if not nxt.strip():
                break
            if (
                _MD_HEADING_RE.match(nxt)
                or _MD_BULLET_RE.match(nxt)
                or _MD_NUMBERED_RE.match(nxt)
                or _MD_BLOCKQUOTE_RE.match(nxt)
                or _MD_HR_RE.match(nxt)
                or _MD_FENCE_RE.match(nxt)
            ):
                break
            if "|" in nxt and i + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[i + 1].rstrip()):
                break
            para_lines.append(nxt)
            i += 1
        joined = " ".join(para_lines)
        story.append(_safe_paragraph(joined, styles["body"]))

    return story


def _doc_template(buf: BytesIO):
    """Build the default SimpleDocTemplate with letter pagesize and 1-inch margins."""
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch

    return SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title="Workflow Results",
    )


def _usable_width(doc) -> float:
    return doc.width  # SimpleDocTemplate exposes width = pagesize - margins


def _header_flowables(title: str, subtitle: str | None, styles: dict) -> list:
    from reportlab.platypus import Paragraph

    flow = [Paragraph(_xml_escape(title), styles["title"])]
    if subtitle:
        flow.append(Paragraph(_xml_escape(subtitle), styles["meta"]))
    return flow


def _kv_table_flowable(data: dict, styles: dict, usable_width: float):
    """Render a flat dict as a two-column Field/Value table."""
    headers = ["Field", "Value"]
    rows = []
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v_text = json.dumps(v, default=str, indent=2)
        else:
            v_text = "" if v is None else str(v)
        rows.append([str(k), v_text])
    # Use fixed proportional widths for a more report-like look (30% / 70%).
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    data_rows = [
        [_safe_paragraph(h, styles["table_header"]) for h in headers]
    ]
    for k, v_text in rows:
        data_rows.append([
            _safe_paragraph(str(k), styles["table_cell"]),
            _safe_paragraph(v_text, styles["table_cell"]),
        ])

    col_widths = [usable_width * 0.3, usable_width * 0.7]
    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    row_count = len(data_rows)
    table.setStyle(TableStyle([
        # Vandalizer brand gold header (#eab308) with black text.
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eab308")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Faint gold-tinted zebra striping on body rows.
        ("ROWBACKGROUNDS", (0, 1), (-1, row_count - 1), [colors.white, colors.HexColor("#fdf9eb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]))
    return table


def render_workflow_pdf(data, title: str = "Workflow Results", subtitle: str | None = None) -> bytes:
    """Render workflow output (markdown string / dict / list-of-dicts) to PDF bytes.

    Dispatches on the runtime type of ``data``:
    - str: parsed as markdown (headings, lists, tables, bold/italic/code, etc.)
    - list[dict]: rendered as a wide table using union of keys
    - dict: rendered as a two-column Field/Value table
    - other: rendered as plain text under the title
    """
    buf = BytesIO()
    doc = _doc_template(buf)
    styles = _styles()
    usable = _usable_width(doc)

    if subtitle is None:
        subtitle = datetime.date.today().strftime("%B %d, %Y")

    story: list = []
    story.extend(_header_flowables(title, subtitle, styles))

    # JSON-encoded structured payload: parse so we render as a real table.
    parsed_data = data
    if isinstance(data, str):
        stripped = data.strip()
        if stripped and stripped[0] in "[{":
            try:
                parsed_data = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                parsed_data = data

    if isinstance(parsed_data, list) and parsed_data and all(isinstance(r, dict) for r in parsed_data):
        headers = list(dict.fromkeys(k for row in parsed_data for k in row.keys()))
        rows = []
        for row in parsed_data:
            cells = []
            for h in headers:
                val = row.get(h, "")
                if isinstance(val, (dict, list)):
                    cells.append(json.dumps(val, default=str))
                else:
                    cells.append("" if val is None else str(val))
            rows.append(cells)
        story.append(_build_table_flowable(headers, rows, styles, usable))
    elif isinstance(parsed_data, dict):
        story.append(_kv_table_flowable(parsed_data, styles, usable))
    elif isinstance(parsed_data, str):
        story.extend(_markdown_to_story(parsed_data, styles, usable))
    else:
        from reportlab.platypus import Paragraph

        story.append(Paragraph(_xml_escape(str(parsed_data) if parsed_data is not None else ""), styles["body"]))

    doc.build(story)
    return buf.getvalue()
