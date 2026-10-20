"""Per-task knowledge-base grounding (app.services.kb_grounding).

Retrieval is exercised against a fake DocumentManager; nothing here touches
Chroma, Mongo, or a model.
"""

import json
from unittest.mock import MagicMock

import pytest

from app.services import kb_grounding as kg
from app.services.kb_grounding import (
    GroundingConfig,
    GroundingConfigError,
    KnowledgeBaseTarget,
    cites_any,
    condense_query,
    dedupe_passages,
    grounding_targets,
    has_grounding,
    looks_like_citation,
    merge_pools,
    merge_sources,
    parse_grounding_config,
    render_queries,
    resolve_passage_tags,
    retrieve_grounding,
    trim_to_budget,
    unmatched_citations,
)


def _chunk(cid, content, *, source="UG.pdf", page=None, similarity=0.9, source_id=None):
    meta = {"source_name": source, "source_id": source_id or source}
    if page is not None:
        meta["page"] = page
    return {
        "content": content, "metadata": meta, "chunk_id": cid,
        "score": 1 - similarity, "similarity": similarity,
    }


class FakeDM:
    """query_kb answers from a per-(kb, query-substring) table; lexical
    lookups from a per-(kb, term) table. Records every call."""

    def __init__(self, vector=None, lexical=None):
        self.vector = vector or {}
        self.lexical = lexical or {}
        self.calls: list[tuple] = []

    def query_kb(self, kb_uuid, query, k=8, min_similarity=0.0, **kw):
        self.calls.append((kb_uuid, query, k, min_similarity))
        for (kb, needle), chunks in self.vector.items():
            if kb == kb_uuid and needle in query:
                return [dict(c) for c in chunks][:k]
        return []

    def get_kb_chunks_containing(self, kb_uuid, substring, limit=20):
        return [dict(c) for c in self.lexical.get((kb_uuid, substring), [])][:limit]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestGroundingTargets:
    def test_per_base_entries_keep_their_own_queries(self):
        targets = grounding_targets({
            "knowledge_bases": [
                {"kb_uuid": "ug", "queries": ["cost sharing", "indirect costs"]},
                {"kb_uuid": "osp", "queries": "approval routing\n\nF&A waiver\n"},
            ],
        })
        assert [(t.kb_uuid, t.queries) for t in targets] == [
            ("ug", ["cost sharing", "indirect costs"]),
            ("osp", ["approval routing", "F&A waiver"]),
        ]

    def test_flat_form_gives_every_base_the_shared_queries(self):
        targets = grounding_targets({"knowledge_bases": ["ug", "osp"], "queries": ["cost sharing"]})
        assert [(t.kb_uuid, t.queries) for t in targets] == [
            ("ug", ["cost sharing"]), ("osp", ["cost sharing"]),
        ]

    def test_shared_queries_fill_in_for_an_entry_without_its_own(self):
        targets = grounding_targets({
            "knowledge_bases": [{"kb_uuid": "ug"}, {"kb_uuid": "osp", "queries": ["routing"]}],
            "queries": ["shared"],
        })
        assert [(t.kb_uuid, t.queries) for t in targets] == [("ug", ["shared"]), ("osp", ["routing"])]

    def test_legacy_single_fields_and_duplicates(self):
        assert [(t.kb_uuid, t.queries) for t in grounding_targets({"kb_uuid": "ug", "query": "one"})] == [("ug", ["one"])]
        merged = grounding_targets({"knowledge_bases": [
            {"kb_uuid": "ug", "queries": ["a"]}, {"kb_uuid": "ug", "queries": ["b", "a"]},
        ]})
        assert [(t.kb_uuid, t.queries) for t in merged] == [("ug", ["a", "b"])]

    def test_has_grounding(self):
        assert has_grounding({"knowledge_bases": [{"kb_uuid": "ug", "queries": ["q"]}]})
        assert has_grounding({"knowledge_bases": ["ug"]})
        assert not has_grounding({"knowledge_bases": []})
        assert not has_grounding({"queries": ["q"]})
        assert not has_grounding(None)
        assert not has_grounding("ug")


class TestParseGroundingConfig:
    def test_requires_a_knowledge_base(self):
        with pytest.raises(GroundingConfigError, match="no knowledge base selected"):
            parse_grounding_config({"queries": ["cost sharing"]})

    def test_requires_a_query_somewhere(self):
        with pytest.raises(GroundingConfigError, match="query is empty"):
            parse_grounding_config({"knowledge_bases": [{"kb_uuid": "kb-1"}], "queries": []})

    def test_a_base_without_queries_passes_parse_for_the_retriever_to_name(self):
        cfg = parse_grounding_config({"knowledge_bases": [
            {"kb_uuid": "ug", "queries": ["a"]}, {"kb_uuid": "osp"},
        ]})
        assert [t.queries for t in cfg.targets] == [["a"], []]

    def test_unconfigured_block_names_both(self):
        with pytest.raises(GroundingConfigError, match="not configured"):
            parse_grounding_config(None)

    def test_defaults_apply(self):
        cfg = parse_grounding_config({"knowledge_bases": ["kb-1"], "queries": "cost sharing\n"})
        assert cfg.knowledge_bases == ["kb-1"]
        assert cfg.queries == ["cost sharing"]
        assert cfg.k == kg.DEFAULT_K
        assert cfg.max_passages == kg.DEFAULT_MAX_PASSAGES
        assert cfg.min_similarity == 0.0

    def test_numbers_are_clamped_and_tolerant(self):
        cfg = parse_grounding_config({
            "knowledge_bases": "kb-1", "queries": ["q"],
            "k": "999", "max_passages": "abc", "min_similarity": "-1",
        })
        assert cfg.k == kg.MAX_K
        assert cfg.max_passages == kg.DEFAULT_MAX_PASSAGES
        assert cfg.min_similarity == 0.0

    def test_queries_property_is_the_distinct_union(self):
        cfg = parse_grounding_config({"knowledge_bases": [
            {"kb_uuid": "ug", "queries": ["a", "b"]}, {"kb_uuid": "osp", "queries": ["b", "c"]},
        ]})
        assert cfg.queries == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

class TestRenderQueries:
    def test_templates_read_the_step_input(self):
        queries, warnings = render_queries(
            ["policies for {{ inputs.output.sponsor }}", "cost share"],
            {"output": {"sponsor": "NSF"}},
        )
        assert queries == ["policies for NSF", "cost share"]
        assert warnings == []

    def test_empty_render_is_dropped_with_a_warning(self):
        queries, warnings = render_queries(["{{ inputs.output }}"], {"output": ""})
        assert queries == []
        assert warnings and "empty" in warnings[0]

    def test_unresolvable_placeholder_is_a_config_error(self):
        with pytest.raises(GroundingConfigError):
            render_queries(["{{ inputs.output.missing }}"], {"output": {"a": 1}})


class TestCondenseQuery:
    def test_short_query_is_untouched(self):
        assert condense_query("cost sharing", model=None, system_config_doc=None) == ("cost sharing", None)

    def test_long_query_without_a_model_is_cut_with_a_warning(self):
        long = " ".join(f"w{i}" for i in range(200))
        query, warning = condense_query(long, model=None, system_config_doc=None)
        assert len(query.split()) == kg.CONDENSE_WORD_LIMIT
        assert warning and "cut" in warning

    def test_long_query_is_condensed_by_the_rewriter(self, monkeypatch):
        long = " ".join(f"w{i}" for i in range(200))
        agent = MagicMock()
        agent.run_sync.return_value = MagicMock(output="indirect cost rate waiver")
        monkeypatch.setattr(
            "app.services.llm_service.create_chat_agent", lambda *a, **k: agent,
        )
        query, warning = condense_query(long, model="m", system_config_doc={})
        assert query == "indirect cost rate waiver"
        assert warning is None


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_dedupes_by_id_and_by_content(self):
        same_text = "Cost sharing means the portion of project costs not paid by Federal funds."
        passages = [
            _chunk("a", same_text),
            _chunk("a", "repeat id"),
            _chunk("b", same_text.upper()),  # subpart page re-ingesting the part
            _chunk("c", "different"),
        ]
        assert [p["chunk_id"] for p in dedupe_passages(passages)] == ["a", "c"]

    def test_round_robins_queries_then_knowledge_bases(self):
        kb1 = [[_chunk("1a", "1a"), _chunk("1b", "1b")], [_chunk("1c", "1c")]]
        kb2 = [[_chunk("2a", "2a")], [_chunk("2b", "2b"), _chunk("2c", "2c")]]
        merged = merge_pools([kb1, kb2], max_passages=10)
        assert [p["chunk_id"] for p in merged] == ["1a", "2a", "1c", "2b", "1b", "2c"]

    def test_cap_applies_after_merge(self):
        kb1 = [[_chunk("1a", "1a"), _chunk("1b", "1b"), _chunk("1c", "1c")]]
        kb2 = [[_chunk("2a", "2a"), _chunk("2b", "2b"), _chunk("2c", "2c")]]
        merged = merge_pools([kb1, kb2], max_passages=3)
        assert [p["chunk_id"] for p in merged] == ["1a", "2a", "1b"]


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def _targets(**per_kb: list[str]) -> list[KnowledgeBaseTarget]:
    return [KnowledgeBaseTarget(kb_uuid=uuid, queries=list(qs)) for uuid, qs in per_kb.items()]


class TestRetrieveGrounding:
    def _cfg(self, targets=None, **kw):
        base = dict(
            targets=targets if targets is not None else _targets(
                ug=["cost sharing", "F&A rate"], osp=["cost sharing", "F&A rate"],
            ),
            k=2, max_passages=8,
        )
        base.update(kw)
        return GroundingConfig(**base)

    def test_each_base_is_searched_with_its_queries_and_labelled(self):
        dm = FakeDM(vector={
            ("ug", "cost sharing"): [_chunk("u1", "UG on cost share", source="Subpart C", page=12)],
            ("ug", "F&A"): [_chunk("u2", "UG on F&A", source="Subpart E", page=40)],
            ("osp", "cost sharing"): [_chunk("o1", "OSP cost share approval", source="APM 45.05")],
            ("osp", "F&A"): [],
        })
        meta = {
            "ug": {"title": "OMB Uniform Guidance", "exists": True},
            "osp": {"title": "UI OSP", "exists": True},
        }
        result = retrieve_grounding(self._cfg(), {"output": "prev"}, kb_meta=meta, dm=dm)

        assert not result.empty
        assert {c[0] for c in dm.calls} == {"ug", "osp"}
        assert len(dm.calls) == 4
        # Over-fetch and the (unset) floor reach the store.
        assert dm.calls[0][2] == 2 * kg.OVERFETCH_MULTIPLIER
        assert "OMB Uniform Guidance — Subpart C · p. 12" in result.text
        assert "UI OSP — APM 45.05" in result.text
        assert kg.KB_GROUNDING_HEADER in result.text
        assert "Retrieval queries: 'cost sharing'; 'F&A rate'" in result.text
        titles = {s["kb_title"] for s in result.sources}
        assert titles == {"OMB Uniform Guidance", "UI OSP"}
        assert all(s["kb_uuid"] in ("ug", "osp") for s in result.sources)

    def test_different_queries_per_base_go_only_to_that_base(self):
        """The RFA budget task: Uniform Guidance searched for the regulation,
        the institution's base for its approval process — never crossed."""
        dm = FakeDM(vector={
            ("ug", "200.306"): [_chunk("u1", "§ 200.306 Cost sharing", source="Subpart C")],
            ("osp", "approval"): [_chunk("o1", "Cost share approval routes through OSP", source="APM 45.05")],
        })
        meta = {"ug": {"title": "OMB Uniform Guidance", "exists": True}, "osp": {"title": "UI OSP", "exists": True}}
        cfg = self._cfg(targets=_targets(
            ug=["cost sharing 200.306 requirements"],
            osp=["cost share commitment approval routing"],
        ))
        result = retrieve_grounding(cfg, {}, kb_meta=meta, dm=dm)

        assert [(c[0], c[1]) for c in dm.calls] == [
            ("ug", "cost sharing 200.306 requirements"),
            ("osp", "cost share commitment approval routing"),
        ]
        assert [p["chunk_id"] for p in result.passages] == ["u1", "o1"]
        # The model is told which base each query was aimed at.
        assert "Retrieval queries — OMB Uniform Guidance: 'cost sharing 200.306 requirements' | UI OSP: 'cost share commitment approval routing'" in result.text
        assert result.queries == ["cost sharing 200.306 requirements", "cost share commitment approval routing"]

    def test_a_base_without_queries_is_a_config_error_naming_it(self):
        meta = {"ug": {"title": "OMB Uniform Guidance", "exists": True}, "osp": {"title": "UI OSP", "exists": True}}
        cfg = self._cfg(targets=_targets(ug=["cost sharing"], osp=[]))
        with pytest.raises(GroundingConfigError, match="no retrieval query for UI OSP"):
            retrieve_grounding(cfg, {}, kb_meta=meta, dm=FakeDM())

    def test_every_base_is_represented_before_any_repeats(self):
        dm = FakeDM(vector={
            ("ug", "cost"): [_chunk(f"u{i}", f"ug {i}") for i in range(6)],
            ("osp", "cost"): [_chunk(f"o{i}", f"osp {i}", source="APM") for i in range(6)],
        })
        cfg = self._cfg(targets=_targets(ug=["cost"], osp=["cost"]), k=4, max_passages=4)
        result = retrieve_grounding(cfg, {}, dm=dm)
        ids = [p["chunk_id"] for p in result.passages]
        assert ids == ["u0", "o0", "u1", "o1"]

    def test_tuned_floor_applies_when_the_task_sets_none(self):
        dm = FakeDM(vector={
            ("ug", "cost"): [
                _chunk("hi", "relevant", similarity=0.8),
                _chunk("lo", "junk", similarity=0.1),
            ],
        })
        meta = {"ug": {"title": "UG", "exists": True, "rag_config_override": {"min_similarity": 0.5}}}
        cfg = self._cfg(targets=_targets(ug=["cost"]))
        result = retrieve_grounding(cfg, {}, kb_meta=meta, dm=dm)
        assert [p["chunk_id"] for p in result.passages] == ["hi"]
        assert dm.calls[0][3] == 0.5

    def test_task_floor_overrides_the_tuned_one(self):
        dm = FakeDM(vector={("ug", "cost"): [_chunk("x", "x", similarity=0.3)]})
        meta = {"ug": {"title": "UG", "exists": True, "rag_config_override": {"min_similarity": 0.5}}}
        cfg = self._cfg(targets=_targets(ug=["cost"]), min_similarity=0.2)
        result = retrieve_grounding(cfg, {}, kb_meta=meta, dm=dm)
        assert [p["chunk_id"] for p in result.passages] == ["x"]

    def test_cited_section_is_pinned_lexically(self):
        dm = FakeDM(
            vector={("ug", "200.414"): [_chunk("v1", "vaguely about rates")]},
            lexical={("ug", "200.414"): [_chunk("lex", "§ 200.414 Indirect (F&A) costs.")]},
        )
        cfg = self._cfg(targets=_targets(ug=["§ 200.414 indirect costs"]), k=2)
        result = retrieve_grounding(cfg, {}, dm=dm)
        assert [p["chunk_id"] for p in result.passages][0] == "lex"

    def test_a_section_pin_is_exact_not_a_prefix(self):
        """The store's substring lookup for "200.1" also returns 200.10; only
        the exact section may take a pinned slot."""
        dm = FakeDM(lexical={("ug", "200.1"): [
            _chunk("s10", "§ 200.10 U.S. Federal awarding agency."),
            _chunk("s1", "§ 200.1 Definitions."),
        ]})
        cfg = self._cfg(targets=_targets(ug=["§ 200.1 definitions"]), k=2)
        result = retrieve_grounding(cfg, {}, dm=dm)
        assert [p["chunk_id"] for p in result.passages] == ["s1"]

    def test_missing_knowledge_base_is_a_config_error(self):
        meta = {"ug": {"title": "UG", "exists": True}, "osp": {"title": None, "exists": False}}
        with pytest.raises(GroundingConfigError, match="Knowledge base not found"):
            retrieve_grounding(self._cfg(), {}, kb_meta=meta, dm=FakeDM())

    def test_no_matches_is_a_warning_not_an_error(self):
        result = retrieve_grounding(self._cfg(), {}, dm=FakeDM())
        assert result.empty
        assert result.text == ""
        assert result.warnings and "No knowledge-base passages matched" in result.warnings[0]

    def test_single_lookup_keeps_the_classic_no_match_wording(self):
        cfg = self._cfg(targets=_targets(ug=["obscure"]))
        result = retrieve_grounding(cfg, {}, dm=FakeDM())
        assert "no matching passages for the query: 'obscure'" in result.warnings[0]

    def test_every_query_rendering_empty_skips_retrieval(self):
        dm = FakeDM()
        cfg = self._cfg(targets=_targets(ug=["{{ inputs.output }}"], osp=["{{ inputs.output }}"]))
        result = retrieve_grounding(cfg, {"output": ""}, dm=dm)
        assert result.empty and not result.queries
        assert dm.calls == []

    def test_one_base_rendering_empty_is_skipped_and_named(self):
        dm = FakeDM(vector={("osp", "routing"): [_chunk("o1", "routing", source="APM")]})
        meta = {"ug": {"title": "OMB UG", "exists": True}, "osp": {"title": "UI OSP", "exists": True}}
        cfg = self._cfg(targets=_targets(ug=["{{ inputs.output }}"], osp=["routing"]))
        result = retrieve_grounding(cfg, {"output": ""}, kb_meta=meta, dm=dm)
        assert [p["chunk_id"] for p in result.passages] == ["o1"]
        assert any("OMB UG was skipped" in w for w in result.warnings)

    def test_store_failure_propagates(self):
        dm = MagicMock()
        dm.query_kb.side_effect = RuntimeError("chroma down")
        with pytest.raises(RuntimeError, match="chroma down"):
            retrieve_grounding(self._cfg(), {}, dm=dm)

    def test_single_base_without_title_reads_as_before(self):
        dm = FakeDM(vector={("ug", "cost"): [_chunk("u1", "text", source="PAPPG.pdf", page=234)]})
        cfg = self._cfg(targets=_targets(ug=["cost"]))
        result = retrieve_grounding(cfg, {}, dm=dm, header="HDR", show_queries=False)
        assert result.text.startswith("HDR\n\n[KB1] PAPPG.pdf · p. 234\n")
        # Untagged (a Knowledge Base Query step): each passage under its
        # source line, which a later step copies as its citation.
        untagged = retrieve_grounding(cfg, {}, dm=dm, header="HDR", show_queries=False, tagged=False)
        assert untagged.text.startswith("HDR\n\n[PAPPG.pdf · p. 234]\n")


class TestTrimToBudget:
    def test_drops_lowest_ranked_first_and_says_so(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.context_budget.count_tokens", lambda text, *a, **k: 100,
        )
        passages = [_chunk("a", "a"), _chunk("b", "b"), _chunk("c", "c")]
        kept, warning = trim_to_budget(passages, 250, model="m", system_config_doc={})
        assert [p["chunk_id"] for p in kept] == ["a", "b"]
        assert warning and "1 lower-ranked" in warning

    def test_nothing_fits_is_explained(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.context_budget.count_tokens", lambda text, *a, **k: 100,
        )
        kept, warning = trim_to_budget([_chunk("a", "a")], 50, model="m", system_config_doc={})
        assert kept == []
        assert warning and "left out" in warning

    def test_no_budget_means_no_trim(self):
        passages = [_chunk("a", "a")]
        assert trim_to_budget(passages, None, model="m", system_config_doc={}) == (passages, None)


class TestCitationPayload:
    def test_sources_carry_the_label_the_model_cites_and_the_passage(self):
        """The run UI links a bracketed citation in the output to a passage by
        this exact label, and shows this text on click."""
        dm = FakeDM(vector={("ug", "cost"): [
            _chunk("u1", "Cost sharing means the portion of project costs not paid by Federal funds.", source="Subpart C", page=12),
        ]})
        meta = {"ug": {"title": "OMB Uniform Guidance", "exists": True}}
        cfg = GroundingConfig(targets=_targets(ug=["cost"]), k=2, max_passages=8)
        result = retrieve_grounding(cfg, {}, kb_meta=meta, dm=dm)
        src = result.sources[0]
        assert src["label"] == "OMB Uniform Guidance — Subpart C · p. 12"
        assert src["content"].startswith("Cost sharing means")
        # The model cites the tag; the engine swaps in this exact line.
        assert "[KB1] " + src["label"] in result.text

    def test_a_pageless_passage_is_told_apart_by_its_part(self):
        """A web page or eCFR subpart has no pages: without its position every
        passage from it would share one source line."""
        dm = FakeDM(vector={("ug", "cost"): [
            _chunk("src_chunk_44", "first", source="Subpart E—Cost Principles"),
            _chunk("src_chunk_8", "second", source="Subpart E—Cost Principles"),
        ]})
        meta = {"ug": {"title": "OMB UG", "exists": True}}
        result = retrieve_grounding(GroundingConfig(targets=_targets(ug=["cost"])), {}, kb_meta=meta, dm=dm)
        assert [s["label"] for s in result.sources] == [
            "OMB UG — Subpart E—Cost Principles · part 45",
            "OMB UG — Subpart E—Cost Principles · part 9",
        ]

    def test_a_source_line_is_safe_inside_brackets_and_json(self):
        dm = FakeDM(vector={("ug", "cost"): [
            _chunk("c1", "x", source='APM 45.05 [Cost "Share"]; notes\\draft', page=3),
        ]})
        result = retrieve_grounding(GroundingConfig(targets=_targets(ug=["cost"])), {}, dm=dm)
        assert result.sources[0]["label"] == "APM 45.05 (Cost 'Share'), notes/draft · p. 3"


class TestCitationHelpers:
    SOURCES = [
        {"document_title": "2 CFR Part 200 Subpart F -- Audit Requirements", "page": 12,
         "kb_title": "OMB Uniform Guidance (2 CFR 200)",
         "label": "OMB Uniform Guidance (2 CFR 200) — 2 CFR Part 200 Subpart F -- Audit Requirements · p. 12",
         "chunk_id": "a"},
        {"document_title": "APM 45.05 Cost Share", "page": 3, "label": "APM 45.05 Cost Share · p. 3", "chunk_id": "b"},
    ]

    def test_merge_sources_keeps_the_first_copy_of_a_passage(self):
        a = {"chunk_id": "a", "document_title": "A"}
        b = {"chunk_id": "b", "document_title": "B"}
        again = {"chunk_id": "a", "document_title": "A (again)"}
        no_id = {"document_id": "d", "page": 1, "content_preview": "same text"}
        assert merge_sources([a, b], None, [again, no_id], [dict(no_id)]) == [a, b, no_id]

    def test_exact_and_loosely_written_citations_match(self):
        text = (
            "Audits [OMB Uniform Guidance (2 CFR 200) — 2 CFR Part 200 Subpart F -- Audit Requirements · p. 12] "
            "and cost share [APM 45.05 Cost Share, page 3] and [2 CFR Part 200 Subpart F -- Audit Requirements - p. 12]."
        )
        assert unmatched_citations(text, self.SOURCES) == []

    def test_an_invented_source_is_reported_once(self):
        text = "x [NIH GPS — Section 7 · p. 3] y [NIH GPS — Section 7 · p. 3]"
        assert unmatched_citations(text, self.SOURCES) == ["NIH GPS — Section 7 · p. 3"]

    def test_passage_tags_resolve_to_their_source_lines(self):
        a, b = self.SOURCES[0]["label"], self.SOURCES[1]["label"]
        assert resolve_passage_tags("Audits apply [KB1].", self.SOURCES) == f"Audits apply [{a}]."
        assert resolve_passage_tags("x [KB1, KB2] y [kb2; 1] z (KB2)", self.SOURCES) == (
            f"x [{a}][{b}] y [{b}][{a}] z [{b}]"
        )
        # Inside a JSON string the result is still valid JSON.
        out = resolve_passage_tags('{"rationale": "Required [KB2]", "pages": [1]}', self.SOURCES)
        assert json.loads(out) == {"rationale": f"Required [{b}]", "pages": [1]}

    def test_a_tag_that_names_no_passage_is_removed(self):
        """Tags exist only between the engine and the model; one that names
        no passage is an invented citation and must not reach a reader."""
        assert resolve_passage_tags("x [KB9].", self.SOURCES) == "x."
        assert resolve_passage_tags("Pass [KB1] and done [KB1].", []) == "Pass and done."
        assert looks_like_citation("KB9")

    def test_a_tag_written_with_a_non_breaking_hyphen_resolves(self):
        a = self.SOURCES[0]["label"]
        assert resolve_passage_tags("x [KB‑1] y 【KB‑1】", self.SOURCES) == f"x [{a}] y [{a}]"

    def test_a_named_section_cites_but_a_bare_figure_does_not(self):
        sources = [
            {"chunk_id": "s", "content": "§ 200.306 Cost sharing or matching. (a) Under research proposals…"},
            {"chunk_id": "r", "content": "The negotiated research rate is 52.5 percent of MTDC."},
        ]
        assert cites_any("Not expected under 2 CFR 200.306.", sources)
        assert cites_any("See § 200.306(b).", sources)
        assert cites_any("Governed by 200.306.", sources)  # the passage writes "§ 200.306"
        assert not cites_any("Charged at 52.5% of MTDC.", sources)
        assert not cites_any("See 200.999.", sources)

    def test_ordinary_brackets_are_not_citations(self):
        assert unmatched_citations("[N/A] [see above] [Section II.B] [1]", self.SOURCES) == []
        assert not looks_like_citation("N/A")
        assert looks_like_citation("PAPPG.pdf · p. 234")
        assert looks_like_citation("PAPPG.pdf, page 234")
