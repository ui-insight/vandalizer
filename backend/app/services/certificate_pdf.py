"""Printable certificate for the Vandal Workflow Architect certification."""

import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Bundled DejaVu Sans (~1.4 MB for both weights) covers Latin Extended,
# Vietnamese, Greek, Cyrillic and more. CJK uses ReportLab's built-in CID
# fonts, which need no font file (the viewer supplies the glyphs), instead of
# a 15-20 MB Noto CJK bundle. CID fonts have no bold weight.
_DEJAVU = {False: "DejaVuSans", True: "DejaVuSans-Bold"}
_CID_KOREAN = "HYGothic-Medium"
_CID_JAPANESE = "HeiseiKakuGo-W5"
_CID_CHINESE = "STSong-Light"


def _is_hangul(cp: int) -> bool:
    return 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F or 0xAC00 <= cp <= 0xD7AF


def _is_kana(cp: int) -> bool:
    return 0x3040 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF or 0xFF66 <= cp <= 0xFF9F


def _is_cjk(cp: int) -> bool:
    return (
        0x2E80 <= cp <= 0x9FFF  # radicals, CJK punctuation, kana, unified ideographs
        or 0xAC00 <= cp <= 0xD7AF
        or 0x1100 <= cp <= 0x11FF
        or 0xF900 <= cp <= 0xFAFF
        or 0xFF00 <= cp <= 0xFFEF  # full/half-width forms
        or 0x20000 <= cp <= 0x3FFFF
    )


@lru_cache(maxsize=1)
def _dejavu_charmap() -> frozenset[int]:
    """Register the bundled DejaVu fonts and return the code points they cover."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    covered: frozenset[int] = frozenset()
    for bold, font_name in _DEJAVU.items():
        font = TTFont(font_name, str(_FONT_DIR / f"{font_name}.ttf"))
        pdfmetrics.registerFont(font)
        if not bold:
            covered = frozenset(font.face.charToGlyph)
    return covered


def _register_cid(font_name: str) -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    return font_name


def _font_for(text: str, bold: bool = False) -> str:
    """Pick a font that can draw every character of ``text``.

    Helvetica for anything its WinAnsi encoding covers (the original look),
    else bundled DejaVu Sans, else a CID font chosen by script for CJK. Text
    no candidate fully covers falls back to DejaVu, which draws the most.
    """
    try:
        text.encode("cp1252")
        return "Helvetica-Bold" if bold else "Helvetica"
    except UnicodeEncodeError:
        pass
    dejavu = _dejavu_charmap()
    cps = [ord(ch) for ch in text]
    if all(cp in dejavu for cp in cps):
        return _DEJAVU[bold]
    if any(_is_cjk(cp) for cp in cps):
        if any(_is_hangul(cp) for cp in cps):
            return _register_cid(_CID_KOREAN)
        if any(_is_kana(cp) for cp in cps):
            return _register_cid(_CID_JAPANESE)
        return _register_cid(_CID_CHINESE)
    return _DEJAVU[bold]


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
    name_font = _font_for(name, bold=True)
    name_size = 30
    while name_size > 14 and c.stringWidth(name, name_font, name_size) > width - 2 * inch:
        name_size -= 1
    c.setFillColor(ink)
    c.setFont(name_font, name_size)
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
    for x, value in (
        (cx - 3 * inch, _format_date(certified_at)),
        (cx, f"{level.title()} level"),
        (cx + 3 * inch, credential_id),
    ):
        c.setFont(_font_for(value, bold=True), 12)
        c.drawCentredString(x, 1.35 * inch, value)
    c.setFillColor(muted)
    c.setFont("Helvetica", 9)
    c.drawCentredString(cx - 3 * inch, 1.1 * inch, "DATE CERTIFIED")
    c.drawCentredString(cx, 1.1 * inch, "LEVEL")
    c.drawCentredString(cx + 3 * inch, 1.1 * inch, "CREDENTIAL ID")

    c.showPage()
    c.save()
    return buf.getvalue()
