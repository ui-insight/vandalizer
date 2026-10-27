"""Section selection (app.services.kb_sections, kb_grounding.with_section): the
chat model names the governing section from the bases' table of contents, and
that section's best chunks join a turn's passages after every cap.

The store, the embedder and the cross-encoder are the fakes of
test_kb_precise_retrieval; the model is a stub. Nothing here touches Chroma,
the network or a model."""

import asyncio
from types import SimpleNamespace

import pytest

from app.services import kb_grounding as kg
from app.services import kb_retrieval as kr
from app.services import kb_sections as ks
from tests.test_kb_precise_retrieval import KB, _store, precise  # noqa: F401 — fixture

QUESTION = "program income earned by the recipient"


@pytest.fixture(autouse=True)
def _clean_cache():
    ks._CACHE.clear()
    yield
    ks._CACHE.clear()


class StubAgent:
    def __init__(self, output="", *, delay=0.0, fail=False):
        self.output, self.delay, self.fail = output, delay, fail
        self.calls, self.prompts = 0, []

    async def run(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("endpoint down")
        return SimpleNamespace(output=self.output)


@pytest.fixture
def agent(monkeypatch):
    stub = StubAgent()
    built = []

    def build(purpose, model_name, system_prompt, model_settings=None):
        built.append((purpose, model_name, system_prompt, model_settings))
        return stub

    monkeypatch.setattr("app.services.kb_validation_service._get_or_build_agent", build)
    stub.built = built
    return stub


def _index(store):
    return kr.index_for(store, KB)


def _passage(index, i, kb_uuid=KB, **extra):
    return {**kr._chunk_result(index, i), "kb_uuid": kb_uuid, **extra}


def _first(index, key):
    return next(i for i, k in enumerate(index.keys) if k == key)


# ---------------------------------------------------------------------------
# The table of contents
# ---------------------------------------------------------------------------

class TestContents:
    def test_a_line_per_section_in_the_base_s_order_with_its_title(self, precise):
        index = _index(_store())
        toc = ks.table_of_contents(index)
        assert list(toc) == list(dict.fromkeys(k for i, k in enumerate(index.keys) if i not in index.excluded))
        assert toc["200.307"] == "200.307 — Program income"
        assert toc["45.13"] == "45.13 — Program Income on Sponsored Projects"

    def test_a_section_that_does_not_apply_here_is_left_out(self, precise):
        toc = ks.table_of_contents(_index(_store()))
        assert "Appendix VII" not in toc and "Appendix III" in toc

    def test_a_source_without_section_numbers_is_one_line_with_what_it_covers(self):
        index = SimpleNamespace(
            keys=["source:Guide", "source:Guide", "source:Guide", "1.1"], excluded=set(),
            prefixes=["Guide — Eligibility", "Guide — Budgets", "Guide — Eligibility", "1.1 Scope"],
            section_titles={"1.1": "Scope"}, chunks=[{}, {}, {}, {}],
        )
        assert ks.table_of_contents(index) == {
            "source:Guide": "source:Guide (whole document) — covers: Eligibility; Budgets",
            "1.1": "1.1 — Scope",
        }

    def test_the_prompt_lists_every_base_under_its_label_then_the_question(self):
        contents = [ks.Contents("A", "kb-a", "Uniform Guidance", {"200.307": "200.307 — Program income"}),
                    ks.Contents("B", "kb-b", "Policies", {"45.13": "45.13 — Program Income"})]
        text = ks.prompt(contents, "Whose is the fee revenue?", "Can we charge outsiders?")
        assert text.splitlines()[:5] == ["Table of contents:", "Knowledge base A: Uniform Guidance",
                                         "A|200.307 — Program income", "Knowledge base B: Policies",
                                         "B|45.13 — Program Income"]
        assert "Question: Whose is the fee revenue?" in text
        assert text.endswith("(The question follows this earlier question: Can we charge outsiders?)")
        assert "earlier question" not in ks.prompt(contents, "q")


# ---------------------------------------------------------------------------
# Reading the model's reply
# ---------------------------------------------------------------------------

class TestParse:
    def test_the_sections_list_is_read_best_first(self):
        assert ks.parse('{"sections": ["A|200.307", "A|200.308"]}') == ["A|200.307", "A|200.308"]

    def test_fences_reasoning_and_prose_around_it_are_skipped(self):
        out = '<think>maybe {"sections": ["A|1"]}</think>Here:\n```json\n{"sections": ["A|200.307"]}\n```'
        assert ks.parse(out) == ["A|200.307"]

    def test_an_object_without_sections_is_passed_over(self):
        assert ks.parse('{"note": 1} then {"sections": ["A|2"]}') == ["A|2"]

    def test_at_most_three_strings_are_kept(self):
        assert ks.parse('{"sections": ["a", 7, "b", "c", "d"]}') == ["a", "b", "c"]

    def test_a_reply_without_json_names_nothing(self):
        assert ks.parse("I cannot tell.") == [] and ks.parse("") == []


class TestResolve:
    CONTENTS = [
        ks.Contents("A", "kb-a", "", {"200.307": "200.307 — Program income",
                                      "source:2 CFR Part 200 — Appendices": "source:… (whole document)"}),
        ks.Contents("B", "kb-b", "", {"45.13": "45.13 — Program Income"}),
    ]

    @pytest.mark.parametrize("pick, found", [
        ("A|200.307", ("kb-a", "200.307")),
        ("200.307", ("kb-a", "200.307")),
        ("§ 200.307 — Program income", ("kb-a", "200.307")),
        ("A|200.307 — Program income", ("kb-a", "200.307")),
        ("B|200.307", ("kb-a", "200.307")),          # a wrong label: the key of another base
        ("B|45.13", ("kb-b", "45.13")),
        ("A|source:2 CFR Part 200 — Appendices (whole document)", ("kb-a", "source:2 CFR Part 200 — Appendices")),
        ("A|999.9", None),
        ("", None),
    ])
    def test_a_pick_is_a_section_of_these_bases_or_none(self, pick, found):
        assert ks.resolve(pick, self.CONTENTS) == found


# ---------------------------------------------------------------------------
# Asking the model
# ---------------------------------------------------------------------------

class TestPick:
    @pytest.mark.asyncio
    async def test_the_first_pick_is_the_section(self, precise, agent):
        agent.output = '{"sections": ["A|200.307", "A|200.308"]}'
        index = _index(_store())
        found = await ks.pick([(KB, "Uniform Guidance", index)], "Whose is the fee revenue?", None, "m")
        assert found == (KB, "200.307")
        assert "A|200.307 — Program income" in agent.prompts[0]
        assert agent.prompts[0].endswith("Question: Whose is the fee revenue?")
        purpose, model, system, settings = agent.built[0]
        assert (purpose, model, system) == ("kb_section_picker", "m", ks.SYSTEM_PROMPT)
        assert settings["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_a_first_pick_that_is_no_section_names_none(self, precise, agent):
        agent.output = '{"sections": ["A|999.9", "A|200.307"]}'
        assert await ks.pick([(KB, "", _index(_store()))], "q?", None, "m") is None

    @pytest.mark.asyncio
    async def test_without_a_model_or_a_base_nothing_is_asked(self, precise, agent):
        index = _index(_store())
        assert await ks.pick([(KB, "", index)], "q?", None, None) is None
        assert await ks.pick([], "q?", None, "m") is None
        assert await ks.pick([(KB, "", index)], "  ", None, "m") is None
        assert agent.calls == 0

    @pytest.mark.asyncio
    async def test_a_failed_or_slow_call_names_none_and_is_asked_again(self, precise, agent, monkeypatch):
        index = _index(_store())
        agent.fail = True
        assert await ks.pick([(KB, "", index)], "q?", None, "m") is None
        agent.fail, agent.delay = False, 0.05
        monkeypatch.setattr(ks, "TIMEOUT_S", 0.01)
        agent.output = '{"sections": ["A|200.307"]}'
        assert await ks.pick([(KB, "", index)], "q?", None, "m") is None
        assert agent.calls == 2

    @pytest.mark.asyncio
    async def test_the_same_question_is_asked_once(self, precise, agent):
        agent.output = '{"sections": ["A|200.307"]}'
        index = _index(_store())
        for _ in range(2):
            assert await ks.pick([(KB, "", index)], "q?", None, "m") == (KB, "200.307")
        assert agent.calls == 1
        await ks.pick([(KB, "", index)], "q?", "an earlier question", "m")
        assert agent.calls == 2 and "earlier question: an earlier question" in agent.prompts[1]

    @pytest.mark.asyncio
    async def test_a_low_effort_pick_is_a_call_and_an_answer_of_its_own(self, precise, agent):
        agent.output = '{"sections": ["A|200.307"]}'
        index = _index(_store())
        assert await ks.pick([(KB, "", index)], "q?", None, "m") == (KB, "200.307")
        assert await ks.pick([(KB, "", index)], "q?", None, "m", effort=ks.FAST_EFFORT) == (KB, "200.307")
        assert agent.calls == 2
        (purpose, _, _, settings), (low_purpose, _, _, low_settings) = agent.built
        assert purpose == "kb_section_picker" and "openai_reasoning_effort" not in settings
        assert low_purpose == "kb_section_picker_low"
        assert low_settings == {**settings, "openai_reasoning_effort": "low"}

    @pytest.mark.asyncio
    async def test_a_table_of_contents_of_three_lines_or_fewer_is_not_asked_about(self, agent):
        def index(*keys):
            return SimpleNamespace(keys=list(keys), excluded=set(), prefixes=list(keys), section_titles={},
                                   chunks=[{} for _ in keys])

        a_line_per_source = index("source:Guide", "source:Policy", "source:FAQ")
        assert await ks.pick([("kb-a", "", a_line_per_source)], "q?", None, "m") is None
        assert agent.calls == 0
        agent.output = '{"sections": ["A|source:Policy"]}'
        found = await ks.pick([("kb-a", "", a_line_per_source), ("kb-b", "", index("source:Notice"))], "q?", None, "m")
        assert found == ("kb-a", "source:Policy") and agent.calls == 1


# ---------------------------------------------------------------------------
# Adding the section's chunks
# ---------------------------------------------------------------------------

class TestWithSection:
    def test_the_picked_section_s_best_chunks_follow_the_passages(self, precise):
        store = _store()
        index = _index(store)
        held = _passage(index, _first(index, "200.308"))
        out = kg.with_section(store, [held], (KB, "200.307"), QUESTION)
        assert out[0] is held
        added = out[1:]
        assert 1 <= len(added) <= kr.SECTION_PICK_CHUNKS
        assert all(index.keys[index.position[r["chunk_id"]]] == "200.307" and r["kb_uuid"] == KB for r in added)
        scores = [r["rerank_score"] for r in added]
        assert scores == sorted(scores, reverse=True) and min(scores) >= kr.SECTION_MIN_SCORE

    def test_at_most_section_pick_chunks_are_added(self, precise, monkeypatch):
        store = _store()
        index = _index(store)
        monkeypatch.setattr(kr, "SECTION_PICK_CHUNKS", 1)
        out = kg.with_section(store, [_passage(index, _first(index, "200.308"))], (KB, "200.307"), QUESTION)
        assert len(out) == 2

    def test_a_turn_with_no_passage_gets_nothing(self, precise):
        assert kg.with_section(_store(), [], (KB, "200.307"), QUESTION) == []

    def test_nothing_is_added_when_a_passage_comes_from_that_section(self, precise):
        store = _store()
        index = _index(store)
        pool = [_passage(index, _first(index, "200.308")), _passage(index, _first(index, "200.307"))]
        assert kg.with_section(store, pool, (KB, "200.307"), QUESTION) == pool

    def test_the_same_section_number_in_another_base_counts_as_held(self, precise):
        store = _store()
        index = _index(store)
        pool = [_passage(index, _first(index, "200.307"), kb_uuid="kb-other", kb_title="Other")]
        assert kg.with_section(store, pool, (KB, "200.307"), QUESTION) == pool

    def test_a_chunk_below_the_cut_is_left_out(self, precise):
        store = _store()
        index = _index(store)
        pool = [_passage(index, _first(index, "200.308"))]
        assert kg.with_section(store, pool, (KB, "200.307"), "zebra xylophone quantum") == pool

    def test_a_chunk_whose_text_was_handed_over_is_not_repeated(self, precise):
        store = _store()
        index = _index(store)
        best = kg.with_section(store, [_passage(index, _first(index, "200.308"))], (KB, "200.307"), QUESTION)[1]
        twin = {"content": best["content"], "chunk_id": "elsewhere", "metadata": {}}
        out = kg.with_section(store, [twin], (KB, "200.307"), QUESTION)
        assert best["content"] not in [r["content"] for r in out[1:]]

    def test_the_title_labels_the_chunks_of_a_multi_kb_turn(self, precise):
        store = _store()
        index = _index(store)
        out = kg.with_section(store, [_passage(index, _first(index, "200.308"))], (KB, "200.307"), QUESTION,
                              kb_title="Uniform Guidance")
        assert out[1]["kb_title"] == "Uniform Guidance"

    def test_nothing_without_precise_retrieval_or_for_a_section_the_base_lacks(self, precise, monkeypatch):
        store = _store()
        index = _index(store)
        pool = [_passage(index, _first(index, "200.308"))]
        assert kg.with_section(store, pool, (KB, "999.9"), QUESTION) == pool
        monkeypatch.setattr(kr, "ready", lambda: False)
        assert kg.with_section(store, pool, (KB, "200.307"), QUESTION) == pool
