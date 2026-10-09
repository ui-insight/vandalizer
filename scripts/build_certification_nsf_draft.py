#!/usr/bin/env python3
"""Reflow original NSF training content into a separate unpublished source."""
import importlib.util
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from build_certification_nih_draft import NIHHandout

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'backend/certification-data/drafts/v5.0/documents/nsf-proposal-alpine-ecology.pdf'


class NSFHandout(NIHHandout):
    def section(self, title):
        self.flush_table()
        self.story.append(Paragraph(escape(title), self.heading_style))

    def flush_table(self):
        if not self.rows:
            return
        if any(len(row) != 5 for row in self.rows):
            raise ValueError('The original NSF budget requires five aligned columns')
        width = A4[0] - 72
        table = Table(self.rows, colWidths=[135] + [(width - 135) / 4] * 4, repeatRows=1, hAlign='LEFT')
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
            raise ValueError('This builder only writes the unpublished NSF draft')
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=36, rightMargin=36,
            topMargin=30, bottomMargin=36, invariant=1,
            title='NSF proposal synthetic certification source', author='Vandalizer certification')

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
    source.DocPDF = NSFHandout
    source.OUT_DIR = OUTPUT.parent
    source.gen_nsf_proposal()
    print(OUTPUT)


if __name__ == '__main__':
    build()
