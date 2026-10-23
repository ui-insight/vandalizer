#!/usr/bin/env python3
"""Render the existing synthetic NIH content as a separate, unpublished handout.

Only the NIH generator is invoked. The legacy inputs and course registry are
never written. Embedded fonts and fixed table columns make the source readable
without relying on a PDF viewer's substitute fonts.
"""
import importlib.util
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'backend/certification-data/drafts/v5.0/documents/nih-r01-neuroscience.pdf'


class NIHHandout:
    """Layout adapter for the original generator, preserving its source strings."""

    def __init__(self):
        fonts = Path(reportlab.__file__).parent / 'fonts'
        pdfmetrics.registerFont(TTFont('CourseVera', str(fonts / 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('CourseVeraBold', str(fonts / 'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('CourseVera', normal='CourseVera', bold='CourseVeraBold')
        self.body_style = ParagraphStyle('body', fontName='CourseVera', fontSize=9, leading=13)
        self.heading_style = ParagraphStyle('heading', parent=self.body_style, fontName='CourseVeraBold',
                                            fontSize=12, leading=16, spaceBefore=10, spaceAfter=6,
                                            keepWithNext=True)
        self.cell_style = ParagraphStyle('cell', parent=self.body_style, fontSize=8, leading=11)
        self.story = []
        self.rows = []

    def add_page(self):
        if self.story:
            self.story.append(PageBreak())

    def header_block(self, title, subtitle=''):
        style = ParagraphStyle('title', parent=self.heading_style, fontSize=17, leading=22)
        self.story.extend([Paragraph(escape(title), style), Paragraph(escape(subtitle), self.body_style), Spacer(1, 12)])

    def field(self, label, value):
        self.story.append(Paragraph(f'<b>{escape(label)}:</b> {escape(value)}', self.body_style))

    def section(self, title):
        self.flush_table()
        if title == 'Budget Justification':
            self.story.append(PageBreak())
        self.story.append(Paragraph(escape(title), self.heading_style))

    def body(self, text):
        for paragraph in text.split('\n\n'):
            self.story.extend([Paragraph(escape(paragraph), self.body_style), Spacer(1, 7)])

    def ln(self, height=3):
        self.flush_table()
        self.story.append(Spacer(1, height))

    def table_row(self, cells, bold=False):
        self.rows.append([Paragraph(f'<b>{escape(cell)}</b>' if bold else escape(cell), self.cell_style)
                          for cell in cells])

    def flush_table(self):
        if not self.rows:
            return
        width = A4[0] - 72
        columns = [135, 138, 50, width - 323] if len(self.rows[0]) == 4 else [105] + [(width - 105) / 6] * 6
        table = Table(self.rows, colWidths=columns, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#bcc5d0')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf0f6')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        self.story.append(table)
        self.rows = []

    def output(self, path):
        self.flush_table()
        if Path(path).resolve() != OUTPUT.resolve():
            raise ValueError('This builder only writes the unpublished NIH draft')
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=36, rightMargin=36,
                                topMargin=30, bottomMargin=36, invariant=1,
                                title='NIH R01 synthetic certification source', author='Vandalizer certification')

        def footer(canvas, document):
            canvas.setFont('CourseVera', 7)
            canvas.setFillColor(colors.HexColor('#455365'))
            canvas.drawString(36, 20, 'Synthetic training document | Unpublished 5.0 draft')
            canvas.drawRightString(A4[0] - 36, 20, f'Page {document.page}')

        doc.build(self.story, onFirstPage=footer, onLaterPages=footer)


def build():
    spec = importlib.util.spec_from_file_location('certification_source_content', ROOT / 'backend/certification-data/generate_pdfs.py')
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    source.DocPDF = NIHHandout
    source.OUT_DIR = OUTPUT.parent
    source.gen_nih_r01()
    print(OUTPUT)


if __name__ == '__main__':
    build()
