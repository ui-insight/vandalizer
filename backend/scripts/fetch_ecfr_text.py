"""Fetch CFR text through the official eCFR developer API.

eCFR.gov and FederalRegister.gov block HTML scraping ("Request Access"
interstitial) and direct programmatic users to their developer APIs. This
module is the sanctioned replacement for scraping ecfr.gov pages: it downloads
a part's XML from the versioner API and converts it to plain text suitable for
KB ingestion.

Used two ways:

* CLI — regenerate the bundled seed content files::

      cd backend
      python -m scripts.fetch_ecfr_text                 # fetch live, write seeds/knowledge_bases/content/
      python -m scripts.fetch_ecfr_text --xml-dir DIR   # convert pre-downloaded title-N.xml?part=P dumps

* Library — ``scripts.repair_gov_kb_sources`` imports the URL parser and
  converter to rebuild poisoned ``KnowledgeBaseSource`` rows.

API reference: https://www.ecfr.gov/developers/documentation/api/v1
"""

import argparse
import json
import pathlib
import re
import time
import xml.etree.ElementTree as ET

import httpx

API_BASE = "https://www.ecfr.gov/api/versioner/v1"

# Every ecfr.gov URL that ships in backend/seeds/knowledge_bases/*.json, mapped
# to the API selection that reproduces its content. The whole-part-200 URL maps
# to the appendices: subparts A-F are separate sources, so appendices + subparts
# cover the entire part with no duplicated text (and each stays well under the
# 500k-char KnowledgeBaseSource.content cap).
SEED_ECFR_SOURCES: list[dict] = [
    {
        "url": "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200",
        "title": 2, "part": 200, "select": "appendices",
        "file": "ecfr-title2-part200-appendices.txt",
        "label": "2 CFR Part 200 — Appendices I–XII",
    },
    *[
        {
            "url": f"https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-{letter}",
            "title": 2, "part": 200, "select": f"subpart-{letter}",
            "file": f"ecfr-title2-part200-subpart-{letter.lower()}.txt",
        }
        for letter in "ABCDEF"
    ],
    {
        "url": "https://www.ecfr.gov/current/title-2/subtitle-B/chapter-XI/subchapter-D/part-1104",
        "title": 2, "part": 1104, "select": "part",
        "file": "ecfr-title2-part1104.txt",
    },
    {
        "url": "https://www.ecfr.gov/current/title-2/subtitle-B/chapter-IX/part-910",
        "title": 2, "part": 910, "select": "part",
        "file": "ecfr-title2-part910.txt",
    },
    {
        "url": "https://www.ecfr.gov/current/title-42/chapter-I/subchapter-D/part-93",
        "title": 42, "part": 93, "select": "part",
        "file": "ecfr-title42-part93.txt",
    },
]

DEFAULT_OUT_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "seeds" / "knowledge_bases" / "content"
)
MANIFEST_NAME = "manifest.json"

# Block-level elements in eCFR XML whose text becomes a paragraph.
_BLOCK_TAGS = {
    "HEAD", "P", "FP", "FP-1", "FP-2", "FP-DASH", "HD1", "HD2", "HD3",
    "HED", "CITA", "AUTH", "SOURCE", "PSPACE", "NOTE", "EXTRACT",
}


def parse_ecfr_url(url: str) -> dict | None:
    """Extract {title, part, subpart?} from an ecfr.gov content URL.

    Returns None for URLs that don't name a part (search pages, the API
    itself, etc.).
    """
    if "ecfr.gov" not in url:
        return None
    title_m = re.search(r"/title-(\d+)(?:/|$)", url)
    part_m = re.search(r"/part-(\d+)(?:/|$)", url)
    if not title_m or not part_m:
        return None
    out = {"title": int(title_m.group(1)), "part": int(part_m.group(1))}
    subpart_m = re.search(r"/subpart-([A-Za-z]+)(?:/|$)", url)
    if subpart_m:
        out["subpart"] = subpart_m.group(1).upper()
    return out


def parse_ecfr_chapter_url(url: str) -> dict | None:
    """Extract {title, chapter} from a chapter-level ecfr.gov URL (no part).

    A whole chapter can't be fetched in one API call — the full-XML endpoint
    silently ignores its ``chapter`` param and returns the entire title — so
    callers expand these URLs part-by-part via ``fetch_parts_for_chapter_url``.
    """
    if "ecfr.gov" not in url:
        return None
    if re.search(r"/part-(\d+)(?:/|$)", url):
        return None
    title_m = re.search(r"/title-(\d+)(?:/|$)", url)
    chapter_m = re.search(r"/chapter-([0-9A-Za-z]+)(?:/|$)", url)
    if not title_m or not chapter_m:
        return None
    return {"title": int(title_m.group(1)), "chapter": chapter_m.group(1).upper()}


def _el_text(el: ET.Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _render(el: ET.Element, out: list[str]) -> None:
    tag = el.tag
    if tag == "TR":
        cells = [_el_text(c) for c in el if c.tag in ("TD", "TH")]
        row = " | ".join(c for c in cells if c)
        if row:
            out.append(row)
        return
    if tag == "HEAD" or tag.startswith("HD") or tag == "HED":
        text = _el_text(el)
        if text:
            out.extend(["", text, ""])
        return
    if tag in _BLOCK_TAGS:
        text = _el_text(el)
        if text:
            out.append(text)
        return
    for child in el:
        _render(child, out)


def xml_to_text(el: ET.Element) -> str:
    """Convert an eCFR XML division to readable plain text."""
    out: list[str] = []
    _render(el, out)
    lines: list[str] = []
    prev_blank = False
    for line in out:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        lines.append(line)
        prev_blank = blank
    return "\n".join(lines).strip()


def division_heading(el: ET.Element) -> str:
    head = el.find("HEAD")
    return _el_text(head) if head is not None else ""


def extract_text(root: ET.Element, select: str) -> str:
    """Pull text for a selection out of a part's XML.

    ``select`` is "part" (everything), "appendices" (DIV9 nodes only), or
    "subpart-X".
    """
    if select == "part":
        return xml_to_text(root)
    if select == "appendices":
        parts = [xml_to_text(div) for div in root.iter("DIV9")]
        parts = [p for p in parts if p]
        if not parts:
            raise ValueError("part has no appendices")
        heading = division_heading(root)
        return "\n\n\n".join(([heading] if heading else []) + parts)
    if select.startswith("subpart-"):
        letter = select.split("-", 1)[1].upper()
        for div in root.iter("DIV6"):
            if div.attrib.get("N", "").upper() == letter:
                return xml_to_text(div)
        raise ValueError(f"subpart {letter} not found")
    raise ValueError(f"unknown selection: {select}")


def latest_issue_dates(client: httpx.Client) -> dict[int, str]:
    resp = client.get(f"{API_BASE}/titles.json")
    resp.raise_for_status()
    return {
        t["number"]: t["latest_issue_date"]
        for t in resp.json()["titles"]
        if t.get("latest_issue_date")
    }


def fetch_part_xml(
    client: httpx.Client, title: int, part: int, issue_date: str,
) -> ET.Element:
    resp = client.get(
        f"{API_BASE}/full/{issue_date}/title-{title}.xml", params={"part": part},
    )
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def fetch_text_for_url(url: str, client: httpx.Client | None = None) -> tuple[str, str] | None:
    """Fetch (label, text) for an arbitrary ecfr.gov content URL via the API.

    Whole-part URLs return the full part text; the seed-specific
    appendices-vs-subparts split only applies to the bundled seed files.
    Returns None when the URL doesn't map to a part.
    """
    parsed = parse_ecfr_url(url)
    if not parsed:
        return None
    own_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        dates = latest_issue_dates(client)
        issue_date = dates.get(parsed["title"])
        if not issue_date:
            raise ValueError(f"no issue date for title {parsed['title']}")
        root = fetch_part_xml(client, parsed["title"], parsed["part"], issue_date)
        select = f"subpart-{parsed['subpart']}" if "subpart" in parsed else "part"
        text = extract_text(root, select)
        label = division_heading(root)
        if "subpart" in parsed:
            for div in root.iter("DIV6"):
                if div.attrib.get("N", "").upper() == parsed["subpart"]:
                    label = division_heading(div) or label
                    break
        return (label or url, text)
    finally:
        if own_client:
            client.close()


def list_chapter_parts(
    client: httpx.Client, title: int, chapter: str, issue_date: str,
) -> tuple[str, list[dict]]:
    """Enumerate a chapter's non-reserved parts via the structure API.

    Returns (chapter_label, parts) where each part is {"part", "label", "url"}
    and ``url`` is the part's canonical ecfr.gov URL, rebuilt from its ancestor
    path (e.g. /current/title-48/chapter-99/subchapter-B/part-9904).
    """
    resp = client.get(f"{API_BASE}/structure/{issue_date}/title-{title}.json")
    resp.raise_for_status()

    chapter_label = f"{title} CFR Chapter {chapter}"
    parts: list[dict] = []

    def walk(node: dict, path: list[str], in_chapter: bool) -> None:
        nonlocal chapter_label
        ntype = node.get("type")
        ident = str(node.get("identifier", ""))
        if ntype == "chapter" and ident.upper() == chapter:
            in_chapter = True
            chapter_label = (node.get("label") or chapter_label).strip()
        if ntype == "part" and in_chapter:
            if not node.get("reserved") and ident.isdigit():
                parts.append({
                    "part": int(ident),
                    "label": (node.get("label") or "").strip() or f"{title} CFR Part {ident}",
                    "url": "https://www.ecfr.gov/current/" + "/".join([*path, f"part-{ident}"]),
                })
            return
        seg = f"{ntype}-{ident}" if ntype in ("title", "subtitle", "chapter", "subchapter") else None
        for child in node.get("children") or []:
            walk(child, [*path, seg] if seg else path, in_chapter)

    walk(resp.json(), [], False)
    if not parts:
        raise ValueError(f"no non-reserved parts found for title {title} chapter {chapter}")
    return chapter_label, parts


def fetch_parts_for_chapter_url(
    url: str, client: httpx.Client | None = None, delay_seconds: float = 2.0,
) -> tuple[str, list[dict]] | None:
    """Fetch every part of a chapter-level ecfr.gov URL via the API.

    Returns (chapter_label, parts) with each part as {"part", "label", "url",
    "text"}, or None when the URL isn't chapter-shaped. One API call per part,
    spaced ``delay_seconds`` apart to stay polite.
    """
    parsed = parse_ecfr_chapter_url(url)
    if not parsed:
        return None
    own_client = client is None
    client = client or httpx.Client(timeout=60)
    try:
        dates = latest_issue_dates(client)
        issue_date = dates.get(parsed["title"])
        if not issue_date:
            raise ValueError(f"no issue date for title {parsed['title']}")
        chapter_label, listed = list_chapter_parts(
            client, parsed["title"], parsed["chapter"], issue_date,
        )
        out: list[dict] = []
        for entry in listed:
            time.sleep(delay_seconds)
            root = fetch_part_xml(client, parsed["title"], entry["part"], issue_date)
            text = xml_to_text(root)
            if not text.strip():
                continue
            out.append({**entry, "label": division_heading(root) or entry["label"], "text": text})
        return chapter_label, out
    finally:
        if own_client:
            client.close()


def build_seed_content(out_dir: pathlib.Path, xml_dir: pathlib.Path | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    roots: dict[tuple[int, int], ET.Element] = {}

    needed = sorted({(s["title"], s["part"]) for s in SEED_ECFR_SOURCES})
    if xml_dir:
        for title, part in needed:
            path = xml_dir / f"title-{title}-part-{part}.xml"
            roots[(title, part)] = ET.parse(path).getroot()
    else:
        with httpx.Client(timeout=60) as client:
            dates = latest_issue_dates(client)
            for title, part in needed:
                print(f"fetching title {title} part {part} ({dates[title]})…")
                roots[(title, part)] = fetch_part_xml(client, title, part, dates[title])
                time.sleep(2)  # stay polite: the whole point is not getting banned again

    manifest: dict[str, dict] = {}
    for src in SEED_ECFR_SOURCES:
        root = roots[(src["title"], src["part"])]
        text = extract_text(root, src["select"])
        label = src.get("label")
        if not label:
            if src["select"].startswith("subpart-"):
                letter = src["select"].split("-", 1)[1]
                for div in root.iter("DIV6"):
                    if div.attrib.get("N", "").upper() == letter:
                        label = division_heading(div)
                        break
            label = label or division_heading(root)
        (out_dir / src["file"]).write_text(text + "\n")
        manifest[src["url"]] = {"file": src["file"], "title": label}
        print(f"  {src['file']}: {len(text):,} chars — {label}")

    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(manifest)} sources + {MANIFEST_NAME} to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--xml-dir", type=pathlib.Path, default=None,
        help="Convert pre-downloaded title-<T>-part-<P>.xml files instead of fetching",
    )
    args = parser.parse_args()
    build_seed_content(args.out_dir, args.xml_dir)


if __name__ == "__main__":
    main()
