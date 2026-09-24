"""Printable certificate for the Vandal Workflow Architect certification."""

import datetime
from io import BytesIO


def _format_date(when: datetime.datetime) -> str:
    return f"{when:%B} {when.day}, {when:%Y}"


def render_certificate_pdf(
    name: str,
    level: str,
    certified_at: datetime.datetime,
    credential_id: str,
) -> bytes:
    """Render a one-page landscape Letter certificate and return the PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    width, height = landscape(letter)
    c = Canvas(buf, pagesize=(width, height))
    c.setTitle(f"Vandal Workflow Architect certificate - {name}")
    c.setAuthor("Vandalizer")

    gold = colors.HexColor("#b8860b")
    ink = colors.HexColor("#191919")
    muted = colors.HexColor("#6b7280")
    cx = width / 2

    # Double border
    c.setStrokeColor(gold)
    c.setLineWidth(3)
    c.rect(0.4 * inch, 0.4 * inch, width - 0.8 * inch, height - 0.8 * inch)
    c.setLineWidth(0.75)
    c.rect(0.55 * inch, 0.55 * inch, width - 1.1 * inch, height - 1.1 * inch)

    c.setFillColor(muted)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(cx, height - 1.3 * inch, "UNIVERSITY OF IDAHO  ·  VANDALIZER")

    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(cx, height - 2.0 * inch, "Certificate of Completion")

    c.setFillColor(muted)
    c.setFont("Helvetica", 14)
    c.drawCentredString(cx, height - 2.7 * inch, "This certifies that")

    # Shrink a long name to fit between the borders rather than clip it.
    name_size = 30
    while name_size > 14 and c.stringWidth(name, "Helvetica-Bold", name_size) > width - 2 * inch:
        name_size -= 1
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", name_size)
    c.drawCentredString(cx, height - 3.4 * inch, name)
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    c.line(cx - 3.2 * inch, height - 3.55 * inch, cx + 3.2 * inch, height - 3.55 * inch)

    c.setFillColor(muted)
    c.setFont("Helvetica", 14)
    c.drawCentredString(cx, height - 4.1 * inch, "has completed all 11 modules and earned the title")

    c.setFillColor(gold)
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(cx, height - 4.7 * inch, "Vandal Workflow Architect")

    c.setFillColor(muted)
    c.setFont("Helvetica", 12)
    c.drawCentredString(
        cx, height - 5.15 * inch,
        "for mastery in AI-powered document workflow design for research administration",
    )

    # Footer: date, level, credential ID
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(cx - 3 * inch, 1.35 * inch, _format_date(certified_at))
    c.drawCentredString(cx, 1.35 * inch, f"{level.title()} level")
    c.drawCentredString(cx + 3 * inch, 1.35 * inch, credential_id)
    c.setFillColor(muted)
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx - 3 * inch, 1.1 * inch, "DATE CERTIFIED")
    c.drawCentredString(cx, 1.1 * inch, "LEVEL")
    c.drawCentredString(cx + 3 * inch, 1.1 * inch, "CREDENTIAL ID")

    c.showPage()
    c.save()
    return buf.getvalue()
