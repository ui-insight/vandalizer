"""Paraphrase recall (app.services.kb_paraphrase): a question that keeps no
knowledge-base passage is asked again in the base's own words, and what
that finds must clear its own, higher cut.

The store, the embedder and the cross-encoder are the fakes of
test_kb_precise_retrieval; the model is a stub. Nothing here touches Chroma,
the network or a model."""

import asyncio
from types import SimpleNamespace

import pytest

from app.services import kb_grounding as kg
from app.services import kb_paraphrase as kp
from app.services import kb_retrieval as kr
from tests.test_kb_precise_retrieval import KB, _store, precise  # noqa: F401 — fixture

# Words none of the fake corpus holds: the fake scorer gives every passage
# -9, so precise retrieval keeps nothing.
PLAIN = "Something we charge outsiders for brings in revenue; whose is it?"


@pytest.fixture(autouse=True)
def _clean_cache():
    kp._CACHE.clear()
    kp._PENDING.clear()
    yield
    kp._CACHE.clear()
    kp._PENDING.clear()


class StubAgent:
    def __init__(self, output="", *, delay=0.0, fail=False):
        self.output, self.delay, self.fail = output, delay, fail
        self.calls = 0

    async def run(self, prompt):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("endpoint down")
        return SimpleNamespace(output=self.output)


@pytest.fixture
def agent(monkeypatch):
    stub = StubAgent()
    monkeypatch.setattr("app.services.kb_validation_service._get_or_build_agent", lambda *a, **k: stub)
    return stub


# ---------------------------------------------------------------------------
# Cleaning the model's queries
# ---------------------------------------------------------------------------

class TestParse:
    def test_list_marks_and_quotes_are_removed_and_two_are_kept(self):
        out = '1. "program income earned by the recipient"\n- disposition of program income\n* third query'
        assert kp.parse(PLAIN, out) == ["program income earned by the recipient", "disposition of program income"]

    def test_a_section_number_the_question_does_not_name_is_struck(self):
        q = "Can the company pay the plant manager's club dues from overhead?"
        assert kp.parse(q, "FAR 31.205-6 membership dues allowable indirect cost") == [
            "FAR membership dues allowable indirect cost"]

    def test_a_section_number_the_question_names_is_kept(self):
        q = "What does § 200.313 say about selling equipment?"
        assert kp.parse(q, "§ 200.313 equipment disposition sale proceeds") == [
            "§ 200.313 equipment disposition sale proceeds"]

    def test_a_figure_from_memory_is_struck_but_one_from_the_question_kept(self):
        q = "Is a $7,500 centrifuge equipment?"
        assert kp.parse(q, "equipment threshold $10,000 capitalization level $7,500\n"
                           "one-time 12-month no-cost extension") == [
            "equipment threshold capitalization level $7,500", "one-time -month no-cost extension"]

    def test_the_question_itself_and_repeats_are_not_queries(self):
        assert kp.parse(PLAIN, f"{PLAIN}\nprogram income\nprogram income") == ["program income"]

    def test_a_long_line_is_cut_to_the_word_limit(self):
        assert len(kp.parse(PLAIN, " ".join(f"w{i}" for i in range(40)))[0].split()) == kp.MAX_WORDS


# ---------------------------------------------------------------------------
# Asking the model
# ---------------------------------------------------------------------------

class TestParaphrases:
    @pytest.mark.asyncio
    async def test_the_calls_are_made_once_per_question_and_model(self, agent):
        agent.output = "program income earned by the recipient"
        assert await kp.paraphrases(PLAIN, "m") == ["program income earned by the recipient"]
        assert await kp.paraphrases(PLAIN, "m") == ["program income earned by the recipient"]
        assert agent.calls == kp.CALLS

    @pytest.mark.asyncio
    async def test_the_queries_of_every_call_are_used_once(self, monkeypatch):
        outputs = iter(["program income\ncost sharing", "cost sharing\ndisposition of fees"])

        async def run(prompt):
            return SimpleNamespace(output=next(outputs))
        monkeypatch.setattr("app.services.kb_validation_service._get_or_build_agent",
                            lambda *a, **k: SimpleNamespace(run=run))
        assert await kp.paraphrases(PLAIN, "m") == ["program income", "cost sharing", "disposition of fees"]

    @pytest.mark.asyncio
    async def test_a_failed_call_leaves_the_others_queries(self, monkeypatch):
        calls: list[str] = []

        async def run(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                raise RuntimeError("endpoint down")
            return SimpleNamespace(output="program income")
        monkeypatch.setattr("app.services.kb_validation_service._get_or_build_agent",
                            lambda *a, **k: SimpleNamespace(run=run))
        assert await kp.paraphrases(PLAIN, "m") == ["program income"]

    @pytest.mark.asyncio
    async def test_the_knowledge_bases_of_one_turn_share_the_calls(self, agent):
        agent.output, agent.delay = "program income", 0.05
        results = await asyncio.gather(*[kp.paraphrases(PLAIN, "m") for _ in range(3)])
        assert results == [["program income"]] * 3
        assert agent.calls == kp.CALLS

    @pytest.mark.asyncio
    async def test_no_model_or_a_failed_call_gives_no_queries(self, agent):
        assert await kp.paraphrases(PLAIN, None) == []
        agent.fail = True
        assert await kp.paraphrases(PLAIN, "m") == []
        assert not kp._PENDING

    @pytest.mark.asyncio
    async def test_a_slow_model_times_out(self, agent, monkeypatch):
        monkeypatch.setattr(kp, "TIMEOUT_S", 0.01)
        agent.output, agent.delay = "program income", 0.5
        assert await kp.paraphrases(PLAIN, "m") == []


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

class TestParaphrasePool:
    def test_the_base_s_own_words_find_the_section_the_question_missed(self, precise):
        store = _store()
        assert kg._precise_pool(store, KB, PLAIN, k=4, floor=0.0) == []
        pool = kg.paraphrase_pool(store, KB, PLAIN, ["program income earned by the recipient"], k=4, floor=0.0)
        assert pool and all("program income" in r["content"] for r in pool)
        assert all(r["rerank_score"] >= kr.PARAPHRASE_MIN_SCORE for r in pool)

    def test_a_paraphrase_must_clear_the_higher_cut(self, precise):
        # Half its words in the passage: above the question's cut (-3), below
        # the paraphrase cut.
        pool = kg.paraphrase_pool(_store(), KB, PLAIN, ["program income outsiders whose"], k=4, floor=0.0)
        assert pool == []

    def test_a_paraphrase_has_only_its_first_candidates_scored(self, precise, monkeypatch):
        read: list[int] = []
        scores = precise.scores
        monkeypatch.setattr(precise, "scores", lambda q, passages: read.append(len(passages)) or scores(q, passages))
        monkeypatch.setattr(kr, "RESCUE_RERANK_POOL", 2)
        pool = kg.paraphrase_pool(_store(), KB, PLAIN, ["program income earned by the recipient"], k=4, floor=0.0)
        assert read == [2]
        assert pool and all("program income" in r["content"] for r in pool)

    def test_a_passage_two_paraphrases_find_is_handed_over_once(self, precise):
        phrases = ["program income earned by the recipient", "program income earned recipient fees"]
        pool = kg.paraphrase_pool(_store(), KB, PLAIN, phrases, k=8, floor=0.0)
        ids = [r["chunk_id"] for r in pool]
        assert len(ids) == len(set(ids))


class TestCompound:
    @pytest.mark.parametrize("question", [
        "What form does a university use for its CAS disclosure statement, and where do the copies go?",
        "Is there a federal deadline for moving an expense onto a grant, or is the 90-day window just a UI rule?",
        "Is that business days or calendar days? And what if the last day lands on a Sunday?",
        "Can we count our F&A toward the DOE cost share, and what about funds from another federal grant?",
    ])
    def test_a_question_asking_two_things_reads_as_compound(self, question):
        assert kp.looks_compound(question)

    @pytest.mark.parametrize("question", [
        "Can grant funds pay for travel and lodging at a conference?",
        "What is program income?",
        "Do we need prior approval to rebudget participant support costs into salaries and wages?",
    ])
    def test_one_question_with_an_and_is_not(self, question):
        assert not kp.looks_compound(question)

    @pytest.mark.asyncio
    async def test_a_compound_question_is_split_into_its_parts(self, agent):
        agent.output = "Disclosure Statement form for educational institutions\nfiling copies of the Disclosure Statement"
        assert await kp.parts("What form, and where do the copies go?", "m") == [
            "Disclosure Statement form for educational institutions", "filing copies of the Disclosure Statement"]

    @pytest.mark.asyncio
    async def test_a_question_that_asks_one_thing_has_no_parts(self, agent):
        agent.output = "ONE"
        assert await kp.parts(PLAIN, "m") == []
        agent.output = "only one query came back"
        kp._CACHE.clear()
        assert await kp.parts(PLAIN, "m") == []

    @pytest.mark.asyncio
    async def test_parts_and_paraphrases_are_separate_calls(self, agent):
        agent.output = "program income\ncost sharing"
        await kp.parts(PLAIN, "m")
        await kp.paraphrases(PLAIN, "m")
        assert agent.calls == 1 + kp.CALLS

    @pytest.mark.asyncio
    async def test_each_part_gets_its_own_pool(self, precise):
        pools = await kp.part_pools(_store(), KB, PLAIN, ["program income earned by the recipient",
                                                         "budget revision prior approval"], k=4, floor=0.0)
        assert len(pools) == 2
        assert all("program income" in r["content"] for r in pools[0])
        assert pools[1] and all("budget revision" in r["content"] for r in pools[1])


class TestNeighbours:
    def _pool(self, store):
        """A passage of § 200.308 with § 200.308 chunks on both sides."""
        index = kr.index_for(store, KB)
        i = next(i for i in range(1, len(index.keys) - 1)
                 if index.keys[i - 1] == index.keys[i] == index.keys[i + 1] == "200.308")
        return index, i, [kr._chunk_result(index, i)]

    def test_the_chunks_either_side_in_the_section_are_handed_over_when_they_score(self, precise):
        store = _store()
        index, i, pool = self._pool(store)
        out = kg.with_neighbours(store, KB, "budget revision prior approval", pool, k=8)
        assert out[0] is pool[0]
        assert sorted(index.position[r["chunk_id"]] for r in out[1:]) == [i - 1, i + 1]
        assert all(r["rerank_score"] >= kr.NEIGHBOUR_MIN_SCORE for r in out[1:])

    def test_a_neighbour_that_does_not_score_is_left_out(self, precise):
        store = _store()
        _, _, pool = self._pool(store)
        assert kg.with_neighbours(store, KB, "alcoholic beverages entertainment", pool, k=8) == pool

    def test_a_full_pool_gets_no_neighbours(self, precise):
        store = _store()
        _, _, pool = self._pool(store)
        assert kg.with_neighbours(store, KB, "budget revision prior approval", pool, k=1) == pool


class TestPrecisePool:
    @pytest.mark.asyncio
    async def test_a_question_that_keeps_passages_asks_no_model(self, precise, agent):
        pool = await kp.precise_pool(_store(), KB, "program income earned by the recipient", k=4, floor=0.0,
                                     model_name="m")
        assert pool and agent.calls == 0
        assert not any(r.get(kp.RESCUED) for r in pool)

    @pytest.mark.asyncio
    async def test_a_question_that_keeps_nothing_is_asked_again(self, precise, agent):
        agent.output = "program income earned by the recipient\ndisposition of fees"
        pool = await kp.precise_pool(_store(), KB, PLAIN, k=4, floor=0.0, model_name="m")
        assert agent.calls == kp.CALLS
        assert pool and all("program income" in r["content"] for r in pool)
        # What a paraphrase found is marked as found by rewording.
        assert all(r[kp.RESCUED] for r in pool)

    @pytest.mark.asyncio
    async def test_the_cached_passages_are_not_marked(self, precise, agent):
        agent.output = "program income earned by the recipient\ndisposition of fees"
        store = _store()
        await kp.precise_pool(store, KB, PLAIN, k=4, floor=0.0, model_name="m")
        # The same pool, from the cache: another question may keep these
        # passages itself.
        cached = kg.paraphrase_pool(store, KB, PLAIN, ["program income earned by the recipient",
                                                      "disposition of fees"], k=4, floor=0.0)
        assert cached and not any(r.get(kp.RESCUED) for r in cached)

    @pytest.mark.asyncio
    async def test_without_a_model_or_paraphrases_the_empty_pool_stands(self, precise, agent):
        assert await kp.precise_pool(_store(), KB, PLAIN, k=4, floor=0.0, model_name=None) == []
        agent.fail = True
        assert await kp.precise_pool(_store(), KB, PLAIN, k=4, floor=0.0, model_name="m") == []

    @pytest.mark.asyncio
    async def test_precise_retrieval_off_is_none_without_asking(self, agent, monkeypatch):
        monkeypatch.setattr(kg, "_precise_pool", lambda *a, **k: None)
        assert await kp.precise_pool(object(), KB, PLAIN, k=4, floor=0.0, model_name="m") is None
        assert agent.calls == 0
