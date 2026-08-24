"""Verify the scanned variants carry no residual text layer.

The scanned set exists to exercise OCR. If a rasterization left a text layer
behind, the pipeline reads it directly and the OCR measurement is a fiction —
which is invisible in the results, because the answers get *better*. So the
gate is zero extracted characters, plus the shape of the set: sixteen documents
and forty-two pages at every degradation level.

Run: cd backend && uv run python \\
       ../benchmarks/corpus/CSU-NSF-001/tools/check_scans.py --binaries DIR
"""
import argparse
import sys
from pathlib import Path

import pymupdf

LEVELS = ("light", "medium", "heavy")
EXPECTED_PDFS = 16
EXPECTED_PAGES = 42


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binaries", type=Path, required=True,
                        help="directory holding the unpacked release assets (scanned/)")
    args = parser.parse_args()

    failures = []
    for level in LEVELS:
        pdfs = sorted((args.binaries / "scanned" / level).glob("*.pdf"))
        pages = chars = 0
        for path in pdfs:
            with pymupdf.open(path) as doc:
                pages += doc.page_count
                chars += sum(len(page.get_text() or "") for page in doc)
        print(f"{level:7} {len(pdfs):3} pdfs  {pages:3} pages  {chars:6} extracted chars")
        if len(pdfs) != EXPECTED_PDFS:
            failures.append(f"{level}: expected {EXPECTED_PDFS} PDFs, found {len(pdfs)}")
        if pages != EXPECTED_PAGES:
            failures.append(f"{level}: expected {EXPECTED_PAGES} pages, found {pages}")
        if chars:
            failures.append(f"{level}: residual text layer, {chars} extracted chars")

    if failures:
        print("SCAN CHECK: FAIL")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("SCAN CHECK: PASS (no residual text in any level)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
