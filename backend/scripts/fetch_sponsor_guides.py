"""Fetch the NSF PAPPG and NIH Grants Policy Statement as bundled KB text (#1006).

The catalog's "NSF PAPPG Reference" and "NIH Grants Policy Statement" knowledge
bases held only landing pages: three NSF navigation pages, and an NIH
JavaScript redirect stored under the title "Redirector". Questions about the
two guides RAs consult most were answered from the model's memory. This
module builds plain-text copies from the official publications so the KBs
ship like the bundled eCFR regulations: offline-capable, and unable to
silently capture a landing page instead of the document.

* **NSF PAPPG**: one file per chapter of the current edition, from its HTML
  chapter pages (headings and numbering intact), plus the edition's
  supplements, which amend it.
* **NIH GPS**: the official PDF, split into one file per top-level chapter
  using the PDF's own table of contents. Running headers are dropped and
  each page ends with its printed page label, e.g. "(GPS page IIA-76)", so a
  passage can be found in the PDF.

Every file stays under the 500,000-character ``KnowledgeBaseSource.content``
cap. Re-run when NSF issues a new PAPPG or NIH a new GPS revision, update
``PAPPG_EDITION`` / ``GPS_EDITION``, then bump ``seeds/VERSION``::

    cd backend
    python -m scripts.fetch_sponsor_guides            # both guides
    python -m scripts.fetch_sponsor_guides --only gps
"""

import argparse
import html
import json
import pathlib
import re
from html.parser import HTMLParser

import httpx

SEEDS_KB = pathlib.Path(__file__).resolve().parents[1] / "seeds" / "knowledge_bases"
CONTENT = SEEDS_KB / "content"
CONTENT_CAP = 500_000
USER_AGENT = "Vandalizer catalog build (+https://github.com/ui-insight/vandalizer)"

PAPPG_EDITION = "24-1"
PAPPG_LABEL = "NSF 24-1"
PAPPG_BASE = "https://www.nsf.gov/policies/pappg/24-1"
PAPPG_PAGES = [
    ("summary-changes", "Summary of Changes"),
    ("ch-1-pre-submission", "Chapter I: Pre-Submission Information"),
    ("ch-2-proposal-preparation", "Chapter II: Proposal Preparation Instructions"),
    ("ch-3-proposal-processing-review", "Chapter III: NSF Proposal Processing and Review"),
    ("ch-4-non-award-decisions-transactions", "Chapter IV: Non-Award Decisions and Transactions"),
    ("ch-5-renewal-proposals", "Chapter V: Renewal Proposals"),
    ("ch-6-nsf-awards", "Chapter VI: NSF Awards"),
    ("ch-7-award-administration", "Chapter VII: Award Administration"),
    ("ch-8-financial-requirements-payments", "Chapter VIII: Financial Requirements and Payments"),
    ("ch-9-recipient-standards", "Chapter IX: Recipient Standards"),
    ("ch-10-allowability-of-costs", "Chapter X: Allowability of Costs"),
    ("ch-11-other-post-award-requirements", "Chapter XI: Other Post-Award Requirements and Considerations"),
    ("ch-12-disputes-misconduct", "Chapter XII: Recipient Disputes and Misconduct"),
]
PAPPG_SUPPLEMENTS = [
    ("https://www.nsf.gov/policies/document/pappg24-1-supplement-1", "Supplement 1 (NSF 26-200)"),
    ("https://www.nsf.gov/policies/document/pappg24-1-supplement-2", "Supplement 2 (NSF 26-202)"),
]

GPS_EDITION = "FY 2026"
GPS_PDF = "https://grants.nih.gov/grants/policy/nihgps/nihgps.pdf"
GPS_URL = "https://grants.nih.gov/policy-and-compliance/nihgps"

_BLOCK = {"p", "div", "section", "article", "tr", "table", "ul", "ol", "dl", "dd", "dt", "blockquote"}
_SKIP = {"script", "style", "nav", "button", "svg", "noscript", "form", "header", "footer"}


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _MainText(HTMLParser):
    """Text of a page's <main>, with headings as Markdown and list items as bullets.

    Navigation, buttons and the collapsible table of contents are skipped,
    tracked by nesting depth so the skip ends with the element that began it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.depth = 0
        self.main_depth: int | None = None
        self.skip_depth: int | None = None

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag == "br" and self.main_depth is not None and self.skip_depth is None:
                self.out.append("\n")
            return
        self.depth += 1
        if tag == "main" and self.main_depth is None:
            self.main_depth = self.depth
            return
        if self.main_depth is None or self.skip_depth is not None:
            return
        classes = dict(attrs).get("class") or ""
        if tag in _SKIP or "usa-accordion" in classes:
            self.skip_depth = self.depth
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.out.append("\n\n" + "#" * min(int(tag[1]) + 1, 4) + " ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self.skip_depth is not None and self.depth == self.skip_depth:
            self.skip_depth = None
        elif self.main_depth is not None and self.depth == self.main_depth:
            self.main_depth = None
        elif self.main_depth is not None and self.skip_depth is None and (re.fullmatch(r"h[1-6]", tag) or tag in _BLOCK):
            self.out.append("\n")
        self.depth -= 1

    def handle_data(self, data):
        if self.main_depth is not None and self.skip_depth is None:
            self.out.append(data)


def html_main_text(page: str) -> str:
    parser = _MainText()
    parser.feed(page)
    text = html.unescape("".join(parser.out))
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _write(name: str, header: str, body: str) -> int:
    text = f"{header}\n\n{body.strip()}\n"
    if len(text) > CONTENT_CAP:
        raise SystemExit(f"{name}: {len(text):,} chars exceeds the {CONTENT_CAP:,}-char content cap; split it")
    (CONTENT / name).write_text(text, encoding="utf-8")
    return len(text)


def build_pappg(client: httpx.Client) -> list[dict]:
    sources = []
    pages = [(f"{PAPPG_BASE}/{slug}", label, f"nsf-pappg-{PAPPG_EDITION}-{slug}.txt") for slug, label in PAPPG_PAGES]
    pages += [(url, label, f"nsf-pappg-{PAPPG_EDITION}-{url.rsplit('-', 2)[-2]}-{url.rsplit('-', 1)[-1]}.txt")
              for url, label in PAPPG_SUPPLEMENTS]
    for url, label, name in pages:
        r = client.get(url)
        r.raise_for_status()
        body = html_main_text(r.text)
        if len(body) < 2000:
            raise SystemExit(f"{url}: only {len(body)} chars of content; the page layout may have changed")
        title = f"NSF PAPPG ({PAPPG_LABEL}) — {label}"
        size = _write(name, f"{title}\nSource: {url}", body)
        sources.append({"source_type": "url", "url": url, "content_file": f"content/{name}", "url_title": title})
        print(f"  {name}: {size:,} chars")
    return sources


_GPS_HEADER = re.compile(r"^(Part [IVX]+:.*|NIH Grants Policy Statement)$")
_GPS_PAGE_LABEL = re.compile(r"^(?:[IVX]+[AB]?|[ivx]+)-\d+$")


def _gps_page_text(page, chapter_title: str) -> str:
    lines = [ln.rstrip() for ln in page.get_text().splitlines()]
    while lines and (_GPS_HEADER.match(lines[0].strip()) or lines[0].strip() == chapter_title):
        lines.pop(0)
    label = ""
    if lines and _GPS_PAGE_LABEL.match(lines[-1].strip()):
        label = lines.pop().strip()
    text = "\n".join(lines).strip()
    # Words split across a line break by the PDF layout: "applic-\nable".
    text = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", text)
    return f"{text}\n(GPS page {label})" if label else text


def build_gps(client: httpx.Client, pdf_path: pathlib.Path | None) -> list[dict]:
    import fitz  # PyMuPDF, already a backend dependency

    if pdf_path is None:
        r = client.get(GPS_PDF)
        r.raise_for_status()
        doc = fitz.open(stream=r.content, filetype="pdf")
    else:
        doc = fitz.open(pdf_path)
    chapters = [(title, page) for level, title, page in doc.get_toc() if level == 1]
    if len(chapters) < 15:
        raise SystemExit(f"GPS PDF has {len(chapters)} top-level chapters; expected about 20")
    # The introduction (before the table of contents) states what the GPS is
    # and which revision this is.
    toc_start = next(i for i in range(len(doc)) if "TABLE OF CONTENTS" in doc[i].get_text())
    spans = [("Introduction", 1, toc_start)]
    for i, (title, page) in enumerate(chapters):
        end = chapters[i + 1][1] - 1 if i + 1 < len(chapters) else len(doc)
        spans.append((title, page, end))
    sources = []
    for title, first, last in spans:
        number = title.split(" ", 1)[0] if title[0].isdigit() else "0"
        heading = re.sub(r"^\d+\s+", "", title)
        body = "\n\n".join(_gps_page_text(doc[p - 1], title) for p in range(first, last + 1))
        label = f"Chapter {number}: {heading}" if number != "0" else heading
        name = f"nih-gps-{GPS_EDITION.lower().replace(' ', '')}-{int(number):02d}.txt"
        full_title = f"NIH Grants Policy Statement ({GPS_EDITION} revision) — {label}"
        if len(body) > CONTENT_CAP - 1000:
            # Split an oversized chapter at a page boundary near the middle.
            pages = body.split("\n\n")
            half = len(pages) // 2
            for part, chunk in ((1, pages[:half]), (2, pages[half:])):
                part_name = name.replace(".txt", f"-part{part}.txt")
                part_title = f"{full_title} (part {part} of 2)"
                size = _write(part_name, f"{part_title}\nSource: {GPS_URL}", "\n\n".join(chunk))
                sources.append({"source_type": "url", "url": f"{GPS_URL}#ch{number}-part{part}",
                                "content_file": f"content/{part_name}", "url_title": part_title})
                print(f"  {part_name}: {size:,} chars")
            continue
        size = _write(name, f"{full_title}\nSource: {GPS_URL}", body)
        sources.append({"source_type": "url", "url": f"{GPS_URL}#ch{number}",
                        "content_file": f"content/{name}", "url_title": full_title})
        print(f"  {name}: {size:,} chars")
    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", choices=["pappg", "gps"])
    parser.add_argument("--gps-pdf", type=pathlib.Path, help="use a downloaded nihgps.pdf instead of fetching it")
    parser.add_argument("--print-sources", action="store_true", help="print the seed source entries as JSON")
    args = parser.parse_args()
    built: dict[str, list[dict]] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        if args.only in (None, "pappg"):
            print(f"NSF PAPPG {PAPPG_LABEL}:")
            built["pappg"] = build_pappg(client)
        if args.only in (None, "gps"):
            print(f"NIH GPS {GPS_EDITION}:")
            built["gps"] = build_gps(client, args.gps_pdf)
    if args.print_sources:
        print(json.dumps(built, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
