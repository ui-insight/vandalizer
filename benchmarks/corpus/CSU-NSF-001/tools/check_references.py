"""Cross-check References Cited against in-text citations.

Handles the citation forms an NSF narrative actually uses:

    [7]         single
    [13,14,15]  explicit list
    [13-15]     inclusive range      <-- an earlier version of this script read
    [13–15]     en-dash range            only the endpoints and reported the
                                         middle references as uncited. That was
                                         a bug in the checker; the document was
                                         correct. Ranges are expanded here.

Run: cd backend && uv run python \\
       ../benchmarks/corpus/CSU-NSF-001/tools/check_references.py --binaries DIR
"""
import argparse
import re
import sys
from pathlib import Path

import pymupdf

# A citation group: digits separated by commas and/or range dashes.
_GROUP = re.compile(r"\[((?:\d{1,3})(?:\s*[,–-]\s*\d{1,3})*)\]")
_RANGE = re.compile(r"(\d{1,3})\s*[–-]\s*(\d{1,3})")
_ENTRY = re.compile(r"\[(\d{1,3})\]\s+[A-Z]")


def text(pdf_dir: Path, name: str) -> str:
    with pymupdf.open(pdf_dir / name) as d:
        return "\n".join(p.get_text("text") for p in d)


def cited_numbers(body: str) -> set[int]:
    found: set[int] = set()
    for group in _GROUP.findall(body):
        rest = group
        for lo, hi in _RANGE.findall(group):
            lo_i, hi_i = int(lo), int(hi)
            if lo_i <= hi_i <= lo_i + 50:  # a real range, not two odd numbers
                found.update(range(lo_i, hi_i + 1))
            rest = rest.replace(f"{lo}-{hi}", " ").replace(f"{lo}–{hi}", " ")
        found.update(int(n) for n in re.findall(r"\d{1,3}", rest))
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binaries", type=Path, required=True,
                        help="directory holding the unpacked release assets (pdf/, source/)")
    args = parser.parse_args()
    pdf_dir = args.binaries / "pdf"

    refs = text(pdf_dir, "07_References_Cited.pdf")
    desc = text(pdf_dir, "04_Project_Description.pdf")
    listed = {int(m) for m in _ENTRY.findall(refs)}
    cited = cited_numbers(desc)

    orphaned = sorted(listed - cited)
    dangling = sorted(cited - listed)

    print(f"listed in References Cited : {len(listed)}")
    print(f"cited in the narrative     : {len(cited)}")
    print(f"listed but never cited     : {orphaned or 'NONE'}")
    print(f"cited but not listed       : {dangling or 'NONE'}")
    return 1 if (orphaned or dangling) else 0


if __name__ == "__main__":
    sys.exit(main())
