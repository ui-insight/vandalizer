"""Structure-aware chunking of knowledge-base sources (app.services.kb_chunking)
and what DocumentManager.add_to_kb stores from it: plain text as the document,
section metadata beside it, and a vector of the heading path with the text."""

import re
from unittest.mock import MagicMock, patch

from app.services import kb_chunking as kc
from app.services.document_manager import DocumentManager, count_chunks


def _para(label: str, n: int, words: str = "") -> str:
    out, i = [], 0
    while len(" ".join(out)) < n:
        out.append(f"{label}w{i}")
        i += 1
    return f"({label}) {words} " + " ".join(out) + "."


SUBPART_E = (
    "Subpart E—Cost Principles\n\nGeneral Provisions\n\n"
    "§ 200.420 Considerations for selected items of cost.\n\n"
    + "\n".join(_para(c, 400, "selected items") for c in "ab")
    + "\n\nSelected Items of Cost\n\n"
    "§ 200.421 Advertising and public relations.\n\n"
    + "\n".join(_para(c, 300, "advertising media") for c in "abcdefgh")
    + "\n\n§ 200.423 Alcoholic beverages.\n\nThe cost of alcoholic beverages is unallowable.\n\n"
    "§ 200.424 Alumni activities.\n\nCosts incurred by IHEs for, or in support of, alumni activities are unallowable.\n"
)
POLICY = (
    "45.10 - Facilities and Administrative (Indirect) Rate\nOwner: Office of Sponsored Programs\n"
    "A. Purpose. This policy sets out how the indirect rate is determined.\n"
    "B. Scope. All sponsored funding.\n"
    "C. Definitions\n"
    "C-1. Indirect rate. " + _para("r", 700, "facilities and administrative costs are real costs") + "\n"
    "C-2. Project types. " + _para("t", 700, "instruction organized research other sponsored") + "\n"
)


def _chunks(text: str, name: str = "Subpart E—Cost Principles", **kw) -> list[kc.Chunk]:
    return kc.chunk_source(text, name, **kw)


def _by_key(chunks, key):
    return [c for c in chunks if c.section_key == key]


class TestSections:
    def test_no_chunk_spans_two_sections(self):
        for c in _chunks(SUBPART_E):
            assert {m.group("num") for m in kc.SECTION_RE.finditer(c.text)} <= {c.section_key}

    def test_a_one_sentence_section_is_a_chunk_of_its_own(self):
        """Cut every 1,000 characters, § 200.423 shared its chunk with its
        neighbours; neither the embedding nor the reranker read it alone."""
        [beer] = _by_key(_chunks(SUBPART_E), "200.423")
        assert beer.text == "§ 200.423 Alcoholic beverages.\n\nThe cost of alcoholic beverages is unallowable."
        assert (beer.section_title, beer.heading_path) == ("Alcoholic beverages", "§ 200.423 Alcoholic beverages.")
        assert (beer.section_part, beer.section_parts) == (1, 1)

    def test_a_long_section_is_packed_evenly_at_line_ends(self):
        parts = _by_key(_chunks(SUBPART_E), "200.421")
        assert len(parts) >= 3
        assert [p.section_part for p in parts] == list(range(1, len(parts) + 1))
        assert all(p.section_parts == len(parts) for p in parts)
        assert all(len(p.text) <= kc.MAX_CHARS for p in parts)
        # Cut evenly, not three full chunks and a stub.
        assert min(len(p.text) for p in parts) >= 0.5 * max(len(p.text) for p in parts)
        for p in parts:
            end = p.offset + len(p.text)
            assert end == len(SUBPART_E) or SUBPART_E[end] == "\n"

    def test_every_character_is_in_a_chunk_at_its_offset(self):
        chunks = _chunks(SUBPART_E)
        covered = set()
        for c in chunks:
            assert SUBPART_E[c.offset:c.offset + len(c.text)] == c.text
            covered.update(range(c.offset, c.offset + len(c.text)))
        assert all(i in covered for i, ch in enumerate(SUBPART_E) if not ch.isspace())

    def test_a_subpart_title_opens_the_first_section_and_a_centre_heading_the_next(self):
        chunks = _chunks(SUBPART_E)
        assert chunks[0].text.startswith("Subpart E—Cost Principles\n\nGeneral Provisions\n\n§ 200.420")
        assert chunks[0].section_key == "200.420"
        first_421 = _by_key(chunks, "200.421")[0]
        assert first_421.text.startswith("Selected Items of Cost\n\n§ 200.421 Advertising")
        assert not any(c.text.endswith("Selected Items of Cost") for c in _by_key(chunks, "200.420"))

    def test_a_contents_list_is_not_the_sections(self):
        text = (
            "Contents\n§ 200.501 Audit requirements.\n§ 200.506 Audit costs.\n\n"
            "§ 200.501 Audit requirements.\n\n" + _para("a", 600, "single audit threshold") + "\n\n"
            "§ 200.506 Audit costs.\n\nSee § 200.425.\n"
        )
        chunks = _chunks(text, "Subpart F")
        [costs] = _by_key(chunks, "200.506")
        assert costs.text == "§ 200.506 Audit costs.\n\nSee § 200.425."
        assert _by_key(chunks, "200.501")[0].text.startswith("Contents\n§ 200.501")

    def test_a_title_opening_on_a_quoted_term_is_a_section(self):
        """15 CFR's § 734.8 opens on “Technology”. Unread as a heading, its
        fundamental-research rule was stored, and cited, as § 734.7."""
        text = (
            "§ 734.7 Published.\n\n" + "\n".join(_para(c, 400, "published information") for c in "abc")
            + "\n\n§ 734.8 “Technology” or “software” that arises during, or results from, fundamental research.\n\n"
            + "\n".join(_para(c, 400, "fundamental research") for c in "abc")
            + "\n\n§ 734.9 Foreign-Direct Product (FDP) Rules.\n\n" + _para("a", 300, "foreign-produced items") + "\n"
        )
        chunks = _chunks(text, "PART 734—SCOPE OF THE EXPORT ADMINISTRATION REGULATIONS")
        assert list(dict.fromkeys(c.section_key for c in chunks)) == ["734.7", "734.8", "734.9"]
        assert not any("fundamental research" in c.text for c in _by_key(chunks, "734.7"))
        first = _by_key(chunks, "734.8")[0]
        assert first.text.startswith("§ 734.8 “Technology” or “software”")
        assert first.section_title == (
            "“Technology” or “software” that arises during, or results from, fundamental research"
        )

    def test_a_title_opens_on_a_capital_or_a_quoted_term(self):
        for heading in ("§ 734.8 “Technology” or “software” that arises …", '§ 734.8 "Technology" or "software" …',
                        "734.8 ‘Technology’ …", "§ 200.2 [Reserved]", "§ 200.414 Indirect (F&A) costs."):
            assert kc.SECTION_RE.fullmatch(heading), heading
        # A sentence opening on a section number, and a cross-reference.
        for line in ("§ 734.8 of this part sets out …", "734.8 “fundamental research” is defined …",
                     "See § 734.8 “Technology” or “software” …"):
            assert not kc.SECTION_RE.search(line), line

    def test_a_line_opening_on_a_section_number_and_a_lower_case_word_stays_in_its_section(self):
        text = (
            "§ 734.3 Items subject to the EAR.\n\n" + _para("a", 300, "items subject")
            + "\n§ 734.8 of this part sets out when research results are not subject to the EAR.\n"
            "734.8 “fundamental research” is defined in paragraph (c) of that section.\n"
            + _para("b", 300, "items subject") + "\n"
        )
        assert {c.section_key for c in _chunks(text, "PART 734")} == {"734.3"}

    def test_text_under_no_heading_is_named_by_its_source(self):
        [c] = _chunks("A short page about parking permits for visitors.", "Parking.html")
        assert (c.section_key, c.section_title, c.heading_path) == ("source:Parking.html", "Parking.html", "Parking.html")


class TestHeadingPaths:
    def test_a_chunk_is_named_by_the_sub_heading_holding_most_of_it(self):
        """Stubs ("B. Scope.") fold into the next sub-section; the path names
        the sub-section that is most of the chunk, under its parent."""
        chunks = _chunks(POLICY, "APM 45.10 - Facilities and Administrative (Indirect) Rate | University of Idaho")
        assert {c.section_key for c in chunks} == {"45.10"}
        holding = next(c for c in chunks if "C-1. Indirect rate" in c.text)
        assert holding.heading_path == "45.10 - Facilities and Administrative (Indirect) Rate — Definitions — Indirect rate"
        assert any(c.text.startswith("C-2. Project types") and c.heading_path.endswith("Definitions — Project types")
                   for c in chunks)

    def test_markdown_headings_form_the_path_of_a_document_without_sections(self):
        text = (
            "# Travel Policy\n\n## Meals\n\n" + _para("m", 900, "per diem meals") + "\n\n"
            "## Lodging\n\n### Conference hotels\n\n" + _para("l", 600, "hotel rate") + "\n"
        )
        chunks = _chunks(text, "Travel.docx")
        lodging = next(c for c in chunks if "hotel rate" in c.text)
        assert lodging.heading_path == "Travel.docx — Travel Policy — Lodging — Conference hotels"
        assert lodging.text.startswith("## Lodging")
        assert {c.section_key for c in chunks} == {"source:Travel.docx"}

    def test_a_definitions_section_names_the_terms_a_chunk_defines(self):
        text = (
            "§ 200.1 Definitions.\n\nAcquisition cost means the cost of the asset.\n"
            "Advance payment means a payment made before disbursements.\n"
        )
        [c] = _chunks(text, "Subpart A")
        assert c.heading_path == "§ 200.1 Definitions. — Acquisition cost; Advance payment"
        assert c.section_title == "Definitions"


class TestTables:
    def test_a_chunk_inside_a_table_repeats_its_header(self):
        rows = "\n".join(f"| Item {i} | {i * 100} | travel and lodging for site visit {i} |" for i in range(60))
        text = "Budget\n\n| Item | Amount | Notes |\n|---|---|---|\n" + rows + "\n"
        chunks = _chunks(text, "Budget.xlsx")
        assert len(chunks) > 2
        header = "| Item | Amount | Notes |\n|---|---|---|"
        for c in chunks[1:]:
            assert c.text.startswith(header)
            assert len(c.text) <= kc.MAX_CHARS
            # The offset is where the chunk's own rows start.
            assert text[c.offset:].startswith(c.text[len(header) + 1:][:40])
        assert all(re.fullmatch(r"(\|[^\n]*\|\n?)+", c.text.split("\n", 2)[-1]) for c in chunks[1:])


class TestAddToKb:
    def _manager(self, embed=True):
        dm = object.__new__(DocumentManager)
        dm.chunk_size, dm.chunk_overlap = 1000, 200
        dm.client = MagicMock(get_max_batch_size=MagicMock(return_value=5000))
        self.embedded: list[str] = []
        if embed:
            dm.embedding_function = lambda texts: self.embedded.extend(texts) or [[0.1, 0.2] for _ in texts]
        return dm

    def test_stores_the_text_and_its_section_and_embeds_the_heading_with_it(self):
        dm, collection = self._manager(), MagicMock()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            n = dm.add_to_kb("kb", "src", "Subpart E—Cost Principles", SUBPART_E)
        chunks = _chunks(SUBPART_E)
        assert n == len(chunks) == count_chunks(SUBPART_E)
        [call] = collection.add.call_args_list
        docs, metas = call.kwargs["documents"], call.kwargs["metadatas"]
        assert call.kwargs["ids"] == [f"src_chunk_{i}" for i in range(n)]
        assert docs == [c.text for c in chunks]
        beer = metas[docs.index(_by_key(chunks, "200.423")[0].text)]
        assert beer["section_key"] == "200.423" and beer["section_title"] == "Alcoholic beverages"
        assert beer["heading_path"] == "§ 200.423 Alcoholic beverages."
        assert (beer["section_part"], beer["section_parts"]) == (1, 1)
        assert beer["chunker_version"] == kc.CHUNKER_VERSION
        assert self.embedded == [f"{c.heading_path}\n{c.text}" for c in chunks]
        assert len(call.kwargs["embeddings"]) == n

    def test_page_metadata_follows_each_chunks_offset(self):
        dm, collection = self._manager(), MagicMock()
        markers = [{"char_offset": 0, "kind": "page", "value": 1},
                   {"char_offset": SUBPART_E.index("§ 200.423"), "kind": "page", "value": 9}]
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            dm.add_to_kb("kb", "src", "UG.pdf", SUBPART_E, markers)
        metas = collection.add.call_args.kwargs["metadatas"]
        by_key = {m["section_key"]: m for m in metas}
        assert by_key["200.420"]["page"] == 1 and by_key["200.423"]["page"] == 9

    def test_without_an_embedding_function_the_collection_embeds_the_text(self):
        dm, collection = self._manager(embed=False), MagicMock()
        with patch.object(DocumentManager, "get_kb_collection", return_value=collection):
            dm.add_to_kb("kb", "src", "Subpart E", SUBPART_E)
        assert "embeddings" not in collection.add.call_args.kwargs
