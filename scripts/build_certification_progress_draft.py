#!/usr/bin/env python3
"""Reflow the unchanged synthetic progress report into a separate unpublished source.

Keep every amount, period, publication status and milestone unchanged. Only the
progress-report generator runs; legacy sources and enrollment are untouched.
"""
import importlib.util
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from build_certification_nih_draft import NIHHandout

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'backend/certification-data/drafts/v5.0/documents/progress-report-year2.pdf'


class ProgressHandout(NIHHandout):
    def body(self, text):
        self.flush_table()
        for line in text.splitlines():
            self.story.append(Paragraph(escape(line), self.body_style) if line.strip() else Spacer(1, 7))
        self.story.append(Spacer(1, 7))

    def section(self, title):
        self.flush_table()
        if title == '3. Students and Training':
            self.story.append(PageBreak())
        self.story.append(Paragraph(escape(title), self.heading_style))

    def flush_table(self):
        if not self.rows:
            return
        count = len(self.rows[0])
        if count != 4 or any(len(row) != count for row in self.rows):
            raise ValueError('The progress-report budget table requires four consistent columns')
        width = A4[0] - 72
        columns = [width - 345, 105, 105, 135]
        table = Table(self.rows, colWidths=columns, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), .5, colors.HexColor('#bcc5d0')),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf0f6')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        self.story.extend([table, Spacer(1, 7)])
        self.rows = []

    def output(self, path):
        self.flush_table()
        if Path(path).resolve() != OUTPUT.resolve():
            raise ValueError('This builder only writes the unpublished progress-report draft')
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=36, rightMargin=36,
                                     topMargin=30, bottomMargin=36, invariant=1,
                                     title='Annual progress report synthetic certification source', author='Vandalizer certification')

        def footer(canvas, page):
            canvas.setFont('CourseVera', 7)
            canvas.setFillColor(colors.HexColor('#455365'))
            canvas.drawString(36, 20, 'Synthetic training document | Unpublished 5.0 draft')
            canvas.drawRightString(A4[0] - 36, 20, f'Page {page.page}')

        document.build(self.story, onFirstPage=footer, onLaterPages=footer)


def build():
    spec = importlib.util.spec_from_file_location('certification_source_content', ROOT / 'backend/certification-data/generate_pdfs.py')
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    source.DocPDF = ProgressHandout
    source.OUT_DIR = OUTPUT.parent
    source.gen_progress_report()
    print(OUTPUT)


if __name__ == '__main__':
    build()
