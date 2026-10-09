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

    Embed bundled DejaVu Sans where it covers the text, otherwise use a CID
    font chosen by script for CJK. Text
    no candidate fully covers falls back to DejaVu, which draws the most.
    """
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
    certified_at: datetime.datetime | None,
    credential_id: str,
    *,
    course_title: str | None = None,
    course_version: str | None = None,
    module_count: int = 11,
    legacy_unknown: bool = False,
    credential_promise: str | None = None,
) -> bytes:
    """Render a one-page landscape Letter certificate and return the PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape

    buf = BytesIO()
    width, height = landscape(letter)
    c = Canvas(buf, pagesize=(width, height))
    c.setTitle(f"Vandal Workflow Architect certificate - {name}")
    c.setAuthor("Vandalizer")
    _dejavu_charmap()  # Embed Latin fonts; do not rely on a viewer's font substitution.

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
    c.setFont("DejaVuSans-Bold", 11)
    c.drawCentredString(cx, height - 1.3 * inch, "UNIVERSITY OF IDAHO  ·  VANDALIZER")

    c.setFillColor(ink)
    c.setFont("DejaVuSans-Bold", 34)
    c.drawCentredString(cx, height - 2.0 * inch, "Certificate of Completion")

    c.setFillColor(muted)
    c.setFont("DejaVuSans", 14)
    c.drawCentredString(cx, height - 2.7 * inch, "This certifies that")

    # Shrink a long name to fit between the borders rather than clip it.
    name_font = _font_for(name, bold=True)
    name_size = 30
    while name_size > 14 and c.stringWidth(name, name_font, name_size) > width - 2 * inch:
        name_size -= 1
    c.setFillColor(ink)
    if c.stringWidth(name, name_font, name_size) <= width - 2 * inch:
        c.setFont(name_font, name_size)
        c.drawCentredString(cx, height - 3.4 * inch, name)
    else:
        label = Paragraph(escape(name), ParagraphStyle('learner', fontName=name_font, fontSize=14, leading=17, alignment=1, textColor=ink))
        _label_width, label_height = label.wrap(width - 2 * inch, 54)
        if label_height > 54:
            raise ValueError('Learner name exceeds the certificate name area')
        label.drawOn(c, inch, height - 3.45 * inch)
    c.setStrokeColor(gold)
    c.setLineWidth(1)
    c.line(cx - 3.2 * inch, height - 3.55 * inch, cx + 3.2 * inch, height - 3.55 * inch)

    c.setFillColor(muted)
    c.setFont("DejaVuSans", 14)
    c.drawCentredString(cx, height - 4.1 * inch, "has a preserved certification record for" if legacy_unknown else f"has completed all {module_count} modules and earned the title")

    c.setFillColor(gold)
    c.setFont("DejaVuSans-Bold", 24)
    c.drawCentredString(cx, height - 4.7 * inch, "Vandal Workflow Architect")

    c.setFillColor(muted)
    c.setFont("DejaVuSans", 12)
    if course_title:
        caption = course_title + (f' | {course_version}' if course_version else '')
        label = Paragraph(escape(caption), ParagraphStyle('course', fontName=_font_for(caption), fontSize=11, leading=14, alignment=1, textColor=muted))
        _label_width, label_height = label.wrap(width - 2 * inch, 42)
        if label_height > 42:
            raise ValueError('Course title exceeds the certificate course area')
        label.drawOn(c, inch, height - 5.2 * inch - label_height + 14)
    else:
        c.drawCentredString(
            cx, height - 5.15 * inch,
            "for completing the course's document workflow requirements",
        )

    if credential_promise:
        label = Paragraph(escape(credential_promise), ParagraphStyle('scope',
            fontName=_font_for(credential_promise), fontSize=9, leading=12, alignment=1, textColor=ink))
        _label_width, label_height = label.wrap(width - 2 * inch, 72)
        if label_height > 72:
            raise ValueError('Credential promise exceeds the certificate scope area')
        label.drawOn(c, inch, height - 5.8 * inch - label_height)

    # Footer: date, level, credential ID
    c.setFillColor(ink)
    for x, value in (
        (cx - 3 * inch, _format_date(certified_at) if certified_at else 'Original date unavailable'),
        (cx, f"{level.title()} level"),
        (cx + 3 * inch, credential_id),
    ):
        footer_font = _font_for(value, bold=True)
        footer_size = 12
        while footer_size > 7 and c.stringWidth(value, footer_font, footer_size) > 2.5 * inch:
            footer_size -= 0.5
        c.setFont(footer_font, footer_size)
        c.drawCentredString(x, 1.35 * inch, value)
    c.setFillColor(muted)
    c.setFont("DejaVuSans", 9)
    c.drawCentredString(cx - 3 * inch, 1.1 * inch, "DATE CERTIFIED")
    c.drawCentredString(cx, 1.1 * inch, "LEVEL")
    c.drawCentredString(cx + 3 * inch, 1.1 * inch, "CREDENTIAL ID")

    c.showPage()
    c.save()
    return buf.getvalue()
