#!/usr/bin/env python3
"""Readable unpublished batch sources with all original strings preserved."""
import importlib.util
from pathlib import Path
import re

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate

from build_certification_nih_draft import NIHHandout

ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = ROOT / 'backend/certification-data/documents'
OUTPUT = ROOT / 'backend/certification-data/drafts/v5.0/documents'
NAMES = tuple(f'proposal-batch-{i}.pdf' for i in range(1, 4))


class BatchHandout(NIHHandout):
    def output(self, path):
        target = Path(path).resolve()
        if target.parent != OUTPUT.resolve() or target.name not in NAMES:
            raise ValueError('This builder writes only the three unpublished batch drafts')
        self.flush_table()
        document = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=36, rightMargin=36,
            topMargin=30, bottomMargin=36, invariant=1,
            title='Batch proposal synthetic certification source', author='Vandalizer certification')

        def footer(canvas, page):
            canvas.setFont('CourseVera', 7)
            canvas.setFillColor(colors.HexColor('#455365'))
            canvas.drawString(36, 20, 'Synthetic training document | Unpublished 5.0 draft')
            canvas.drawRightString(A4[0] - 36, 20, f'Page {page.page}')

        document.build(self.story, onFirstPage=footer, onLaterPages=footer)


def normalized(path, *, draft=False):
    with fitz.open(path) as pdf:
        text = '\n'.join(page.get_text() for page in pdf)
    if draft:
        text = re.sub(r'Synthetic training document \| Unpublished 5\.0 draft\s*Page \d+', '', text)
    return ' '.join(text.split())


def build():
    spec = importlib.util.spec_from_file_location('batch_source_content', ROOT / 'backend/certification-data/generate_pdfs.py')
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    # The original generator used Python's randomized hash for proposal numbers.
    # Bind its hash expression to the already-authored original number so a
    # reflow never silently renumbers a proposal across Python processes.
    numbers = {}
    for name in NAMES:
        text = normalized(ORIGINALS / name)
        pi = re.search(r'Principal Investigator: (.*?) Institution:', text).group(1)
        number = int(re.search(r'Proposal Number: BIO-2024-(\d+)', text).group(1))
        numbers[pi] = number - 10000
    source.hash = lambda pi: numbers[pi]
    source.DocPDF = BatchHandout
    source.OUT_DIR = OUTPUT
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source.gen_batch_proposals()
    for name in NAMES:
        if normalized(ORIGINALS / name) != normalized(OUTPUT / name, draft=True):
            raise ValueError('Original proposal content changed: ' + name)
        print(OUTPUT / name)


if __name__ == '__main__':
    build()
