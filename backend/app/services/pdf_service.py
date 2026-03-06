"""PDF generation service — fallback report when no fillable template is attached."""

import datetime
from io import BytesIO


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
    story.append(Paragraph(title, title_style))

    # Meta row
    date_str = datetime.date.today().strftime("%B %d, %Y")
    doc_part = f"Documents: {', '.join(document_names)}" if document_names else ""
    meta_parts = [date_str] + ([doc_part] if doc_part else [])
    story.append(Paragraph(" · ".join(meta_parts), meta_style))

    # Build table data
    table_data = [["Field", "Value"]]
    for item in items:
        label = item.title if item.title else item.searchphrase
        value = results.get(item.searchphrase, "")
        table_data.append([
            Paragraph(label, cell_style),
            Paragraph(str(value), cell_style),
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
