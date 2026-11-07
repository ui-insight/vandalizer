#!/usr/bin/env python3
"""Create two explicitly fictional, unpublished capstone source documents."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import reportlab

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'backend/certification-data/drafts/v5.0/documents'
SOURCES = {
    'capstone-award-notice.pdf': {
        'title': 'Research award notice', 'subtitle': 'Initial award | October 1, 2026',
        'rows': [('Award ID', 'RSP-2026-042'), ('Project Title', 'River Sensor Reliability Pilot'),
            ('Principal Investigator', 'Dr. Nia Patel'), ('Institution', 'Cascadia Research Institute'),
            ('Sponsor', 'Regional Research Fund'), ('Approved Project Ceiling', '$600,000'),
            ('Funds Obligated to Date', '$180,000'), ('Project End Date', 'September 30, 2028')],
        'sections': [('Funding boundary', 'The approved project ceiling describes the maximum planned award. Only funds expressly obligated in an issued notice are available. Future increments are not guaranteed. Do not report the project ceiling as funds obligated to date.'),
            ('Reporting boundary', 'Prepare an internal routing memo for the research office. This notice does not authorize sponsor submission, external delivery or broad workspace sharing.'),
            ('Record authority', 'This initial notice is issued for the stated award. A later issued amendment may change specific fields; retain this notice and identify the amendment used. An unissued proposal or agent summary does not supersede the record.')],
    },
    'capstone-award-amendment.pdf': {
        'title': 'Issued award amendment', 'subtitle': 'Amendment 01 | December 15, 2026',
        'rows': [('Award ID', 'RSP-2026-042'), ('Project Title', 'River Sensor Reliability Pilot'),
            ('Principal Investigator', 'Dr. Nia Patel'), ('Additional Funds Obligated', '$70,000'),
            ('Revised Funds Obligated to Date', '$250,000'), ('Approved Project Ceiling', '$600,000'),
            ('Revised Project End Date', 'March 31, 2029'), ('Status', 'Issued for this synthetic assignment')],
        'sections': [('What this amendment changes', 'The additional $70,000 raises funds obligated to date from $180,000 to $250,000. The project end date changes from September 30, 2028 to March 31, 2029. The approved project ceiling remains $600,000. The project title and Principal Investigator remain unchanged.'),
            ('Required internal review', 'The research-office owner checks this amendment and the original award before accepting an internal routing memo. The memo must distinguish available obligated funds from the planned ceiling and cite both exact source records.'),
            ('Use and access limits', 'Use these fictional documents only in the learner-owned training space. Any certification handoff is a private rehearsal visible only to the enrolled learner. Neither certification completion nor this amendment grants authority to submit to a sponsor, share with everyone, enable an automation or claim staff approval.')],
    },
}


def build():
    fonts = Path(reportlab.__file__).parent / 'fonts'
    pdfmetrics.registerFont(TTFont('CapstoneVera', str(fonts / 'Vera.ttf')))
    pdfmetrics.registerFont(TTFont('CapstoneVeraBold', str(fonts / 'VeraBd.ttf')))
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('CapTitle', fontName='CapstoneVeraBold', fontSize=21, leading=26, textColor=colors.HexColor('#22354b'), spaceAfter=8))
    styles.add(ParagraphStyle('CapBody', fontName='CapstoneVera', fontSize=10, leading=15, textColor=colors.HexColor('#243449'), spaceAfter=9))
    styles.add(ParagraphStyle('CapHeading', fontName='CapstoneVeraBold', fontSize=11, leading=15, textColor=colors.HexColor('#22354b'), spaceBefore=9, spaceAfter=5))
    styles.add(ParagraphStyle('CapCell', fontName='CapstoneVera', fontSize=9, leading=13))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, data in SOURCES.items():
        story = [Paragraph(data['title'], styles['CapTitle']), Paragraph(data['subtitle'], styles['CapBody']),
            Paragraph('FICTIONAL TRAINING RECORD - NOT A REAL AWARD', styles['CapHeading']), Spacer(1, 10)]
        table = Table([[Paragraph(label, styles['CapCell']), Paragraph(value, styles['CapCell'])] for label, value in data['rows']], colWidths=[215, 284])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#edf1f7')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor('#cdd5df')), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
        story.extend([table, Spacer(1, 12)])
        for heading, content in data['sections']:
            story.extend([Paragraph(heading, styles['CapHeading']), Paragraph(content, styles['CapBody'])])
        def footer(canvas, page):
            canvas.setFont('CapstoneVera', 8)
            canvas.setFillColor(colors.HexColor('#4b5e73'))
            canvas.drawString(48, 26, 'Synthetic capstone source | Unpublished Vandalizer 5.0 draft')
            canvas.drawRightString(A4[0] - 48, 26, f'Page {page.page}')
        target = OUTPUT / filename
        SimpleDocTemplate(str(target), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=38, bottomMargin=45,
            invariant=1, title=data['title'] + ' - synthetic training', author='Vandalizer certification').build(story, onFirstPage=footer, onLaterPages=footer)
        print(target)


if __name__ == '__main__':
    build()
