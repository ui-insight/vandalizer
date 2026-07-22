"""Unit tests for the eCFR API text pipeline and bundled seed content."""

import json
import pathlib
import xml.etree.ElementTree as ET

import pytest

from scripts.fetch_ecfr_text import (
    DEFAULT_OUT_DIR,
    MANIFEST_NAME,
    SEED_ECFR_SOURCES,
    extract_text,
    parse_ecfr_url,
    xml_to_text,
)

SEEDS_KB_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "seeds" / "knowledge_bases"
)

PART_XML = """
<DIV5 N="200" TYPE="PART">
  <HEAD>PART 200—UNIFORM REQUIREMENTS</HEAD>
  <AUTH><HED>Authority:</HED><P>31 U.S.C. 503</P></AUTH>
  <DIV6 N="A" TYPE="SUBPART">
    <HEAD>Subpart A—Definitions</HEAD>
    <DIV8 N="200.1" TYPE="SECTION">
      <HEAD>§ 200.1 Definitions.</HEAD>
      <P>Award means <I>financial assistance</I> received.</P>
    </DIV8>
  </DIV6>
  <DIV6 N="B" TYPE="SUBPART">
    <HEAD>Subpart B—General</HEAD>
    <DIV8 N="200.100" TYPE="SECTION">
      <HEAD>§ 200.100 Purpose.</HEAD>
      <P>This part establishes uniform requirements.</P>
      <DIV><TR><TD>Cell one</TD><TD>Cell two</TD></TR></DIV>
    </DIV8>
  </DIV6>
  <DIV9 N="Appendix I" TYPE="APPENDIX">
    <HEAD>Appendix I to Part 200—Funding Notice</HEAD>
    <P>Appendix body text.</P>
  </DIV9>
</DIV5>
"""


@pytest.fixture()
def part_root():
    return ET.fromstring(PART_XML)


# --- parse_ecfr_url ---

def test_parse_part_url():
    assert parse_ecfr_url(
        "https://www.ecfr.gov/current/title-42/chapter-I/subchapter-D/part-93"
    ) == {"title": 42, "part": 93}


def test_parse_subpart_url():
    assert parse_ecfr_url(
        "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200/subpart-E"
    ) == {"title": 2, "part": 200, "subpart": "E"}


def test_parse_rejects_non_part_url():
    assert parse_ecfr_url("https://www.ecfr.gov/search?query=costs") is None


def test_parse_rejects_non_ecfr_url():
    assert parse_ecfr_url("https://www.acquisition.gov/far/part-31") is None


# --- xml_to_text / extract_text ---

def test_xml_to_text_flattens_inline_markup(part_root):
    text = xml_to_text(part_root)
    assert "Award means financial assistance received." in text
    assert "<I>" not in text


def test_xml_to_text_renders_table_rows(part_root):
    assert "Cell one | Cell two" in xml_to_text(part_root)


def test_extract_subpart(part_root):
    text = extract_text(part_root, "subpart-B")
    assert "Subpart B—General" in text
    assert "uniform requirements" in text
    assert "Subpart A—Definitions" not in text
    assert "Appendix I" not in text


def test_extract_appendices(part_root):
    text = extract_text(part_root, "appendices")
    assert "Appendix body text." in text
    assert "Subpart A—Definitions" not in text


def test_extract_missing_subpart_raises(part_root):
    with pytest.raises(ValueError):
        extract_text(part_root, "subpart-Z")


def test_extract_unknown_selection_raises(part_root):
    with pytest.raises(ValueError):
        extract_text(part_root, "chapter-1")


# --- bundled seed content consistency ---

def test_seed_json_content_files_exist():
    """Every content_file referenced by a seed JSON must ship in the repo."""
    referenced = []
    for seed_path in SEEDS_KB_DIR.glob("*.json"):
        data = json.loads(seed_path.read_text())
        for item in data.get("items", []):
            for src in item.get("sources", []):
                if src.get("content_file"):
                    referenced.append((seed_path.name, src["content_file"]))
    assert referenced, "expected at least one bundled seed source"
    for seed_name, rel in referenced:
        path = SEEDS_KB_DIR / rel
        assert path.exists(), f"{seed_name} references missing file {rel}"
        assert len(path.read_text().strip()) > 1000, f"{rel} looks empty"


def test_manifest_covers_all_seeded_ecfr_urls():
    """The repair manifest and SEED_ECFR_SOURCES must cover every ecfr.gov
    URL that appears in the seed files, so poisoned prod sources can always
    be rebuilt from bundled text."""
    manifest = json.loads((DEFAULT_OUT_DIR / MANIFEST_NAME).read_text())
    module_urls = {s["url"] for s in SEED_ECFR_SOURCES}
    for seed_path in SEEDS_KB_DIR.glob("*.json"):
        data = json.loads(seed_path.read_text())
        for item in data.get("items", []):
            for src in item.get("sources", []):
                url = src.get("url") or ""
                if "ecfr.gov" in url:
                    assert url in manifest, f"{url} missing from manifest"
                    assert url in module_urls, f"{url} missing from SEED_ECFR_SOURCES"
                    assert src.get("content_file"), f"{url} has no content_file"
