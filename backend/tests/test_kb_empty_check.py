"""Empty-pool check (app.services.kb_empty_check): a chat question that keeps
no knowledge-base passage, even reworded, has its best candidates read by a
model, and keeps those it finds answer the question.

The store, the embedder and the cross-encoder are the fakes of
test_kb_precise_retrieval; the paraphraser and the checking model are stubs.
Nothing here touches Chroma, the network or a model."""

import asyncio

import pytest

from app.services import chat_answer_repair
from app.services import kb_empty_check as ke
from app.services import kb_grounding as kg
from app.services import kb_paraphrase as kp
from app.services import kb_retrieval as kr
from tests.test_kb_precise_retrieval import (
    KB,
    _store,
    precise,  # noqa: F401 — fixture
)

# One word of eight in § 200.307's text ("fees"), none in the rest: the fake
# scorer puts § 200.307's chunks at -7 and the others at -9, so the question
# keeps nothing, and its best candidates are § 200.307's.
QUESTION = "Whose fees are these, honestly, after helping outsiders yesterday?"
ON = {"chat_config": {"empty_pool_check_enabled": True}}


def _passage(prompt: str) -> str:
    return prompt.split('"""')[1].strip()


class StubAsk:
    """The checking model: ``decide(passage text, call number)`` gives the
    reply, an exception to raise, or ("slow", reply)."""

    def __init__(self, decide=None):
        self.calls = []
        self.decide = decide or (lambda text, n: '{"label": "no", "quote": ""}')

    async def __call__(self, model, instructions, prompt, max_tokens):
        self.calls.append({"model": model, "instructions": instructions, "prompt": prompt})
        out = self.decide(_passage(prompt), len(self.calls) - 1)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, tuple):
            await asyncio.sleep(1.0)
            out = out[1]
        return out


def _answers(text: str) -> str:
    return '{"label": "answers", "quote": "%s"}' % text[:80].replace('"', "'").replace("\n", " ")


def _fees_answer(text, n):
    return _answers(text) if "from fees" in text else '{"label": "no", "quote": ""}'


@pytest.fixture(autouse=True)
def _clean():
    ke._CACHE.clear()
    yield
    ke._CACHE.clear()


@pytest.fixture
def check(monkeypatch, precise):
    """The check on, its model a stub, and no paraphrase finding anything."""
    stub = StubAsk()
    state = {"doc": ON}
    monkeypatch.setattr(ke, "_system_config_doc", lambda: state["doc"])
    monkeypatch.setattr(chat_answer_repair, "model_ask", lambda answer_model, doc: stub)

    async def no_paraphrases(question, model_name):
        return []

    monkeypatch.setattr(kp, "paraphrases", no_paraphrases)
    stub.state = state
    return stub


async def _pool(store=None, question=QUESTION, model_name="m"):
    return await kp.precise_pool(store or _store(), KB, question, k=4, floor=0.0, model_name=model_name)


class TestSetting:
    def test_off_by_default(self):
        assert ke.check_model(None) is None
        assert ke.check_model({"chat_config": {}}) is None
        assert ke.check_model({"chat_config": {"empty_pool_check_enabled": False}}) is None

    def test_on_with_the_default_or_the_configured_model(self):
        assert ke.check_model(ON) == ke.DEFAULT_MODEL
        doc = {"chat_config": {"empty_pool_check_enabled": True, "empty_pool_check_model": "x/checker"}}
        assert ke.check_model(doc) == "x/checker"


class TestQuote:
    TEXT = "(a) Program income earned by the recipient — from fees for services — is used for the project."

    def test_a_quote_copied_with_other_punctuation_and_spacing_is_in(self):
        assert ke.quote_in("program income earned by the recipient – from fees", self.TEXT)
        assert ke.quote_in("Program  income\nearned by the recipient", self.TEXT)

    def test_a_long_quote_with_one_word_changed_is_in(self):
        text = "Program income earned by the recipient from fees for services is used for the project."
        assert ke.quote_in("program income earned by the recipient from fees for services is used for the "
                           "program", text)

    def test_a_quote_the_passage_does_not_hold_is_not(self):
        assert not ke.quote_in("the sponsor keeps all program income for itself", self.TEXT)

    def test_a_short_or_empty_quote_is_not(self):
        assert not ke.quote_in("fees", self.TEXT)
        assert not ke.quote_in("", self.TEXT)


class TestVerdict:
    TEXT = "Program income earned by the recipient from fees is used for the project."

    def test_answers_with_its_quote_keeps_the_passage(self):
        assert ke.verdict('{"label": "Answers", "quote": "program income earned by the recipient"}',
                          self.TEXT) == ("answers", True)

    def test_partial_no_or_a_quote_not_in_the_passage_does_not(self):
        assert ke.verdict('{"label": "partial", "quote": "program income earned by the recipient"}',
                          self.TEXT) == ("partial", False)
        assert ke.verdict('{"label": "no", "quote": ""}', self.TEXT) == ("no", False)
        assert ke.verdict('{"label": "answers", "quote": "the sponsor keeps all of it"}',
                          self.TEXT) == ("answers", False)

    def test_a_fenced_reply_is_read_and_one_without_json_raises(self):
        assert ke.verdict('```json\n{"label": "answers", "quote": "program income earned by the recipient"}\n```',
                          self.TEXT)[1]
        with pytest.raises(ValueError):
            ke.verdict("It answers the question.", self.TEXT)
        with pytest.raises(ValueError):
            ke.verdict('["answers"]', self.TEXT)


class TestBestCandidates:
    def test_the_best_candidates_with_no_cut(self, precise):
        store = _store()
        assert kg._precise_pool(store, KB, QUESTION, k=4, floor=0.0) == []
        best = kg.best_candidates(store, KB, QUESTION, n=3, floor=0.0)
        assert len(best) == 3
        scores = [r["rerank_score"] for r in best]
        assert scores == sorted(scores, reverse=True) and max(scores) < kr.MIN_SCORE
        assert all("from fees" in r["content"] for r in best)

    def test_none_when_precise_retrieval_cannot_run(self, precise, monkeypatch):
        monkeypatch.setattr(kr, "ready", lambda: False)
        assert kg.best_candidates(_store(), KB, QUESTION, n=3, floor=0.0) is None

    def test_after_a_pool_that_kept_nothing_its_scores_are_reused(self, precise):
        store = _store()
        assert kg._precise_pool(store, KB, QUESTION, k=4, floor=0.0) == []
        scored, searched = precise.calls, store.vector_calls
        best = kg.best_candidates(store, KB, QUESTION, n=3, floor=0.0)
        assert (precise.calls, store.vector_calls) == (scored, searched)
        # The same as scoring them afresh.
        kr._RESULTS.clear()
        fresh = kg.best_candidates(store, KB, QUESTION, n=3, floor=0.0)
        assert precise.calls > scored
        assert [(r["chunk_id"], r["rerank_score"], r["content"]) for r in best] == \
            [(r["chunk_id"], r["rerank_score"], r["content"]) for r in fresh]

    def test_another_floor_or_a_pool_that_kept_passages_is_scored_anew(self, precise):
        store = _store()
        assert kg._precise_pool(store, KB, QUESTION, k=4, floor=0.0) == []
        scored = precise.calls
        assert kg.best_candidates(store, KB, QUESTION, n=3, floor=0.5)
        assert precise.calls > scored
        kept = "program income earned by the recipient"
        assert kg._precise_pool(store, KB, kept, k=4, floor=0.0)
        scored = precise.calls
        assert kg.best_candidates(store, KB, kept, n=3, floor=0.0)
        assert precise.calls > scored


class TestCheckedPool:
    @pytest.mark.asyncio
    async def test_off_nothing_is_asked(self, check):
        check.state["doc"] = None
        check.decide = _fees_answer
        assert await _pool() == []
        assert check.calls == []

    @pytest.mark.asyncio
    async def test_a_passage_the_model_finds_answers_is_kept_and_marked_checked(self, check):
        check.decide = _fees_answer
        pool = await _pool()
        assert pool and all("from fees" in r["content"] for r in pool)
        assert all(r.get(ke.CHECKED) for r in pool)
        # Not marked as found by rewording: the prompt's reworded-search note
        # does not apply to it.
        assert not any(r.get(kp.RESCUED) for r in pool)
        assert len(check.calls) == ke.CANDIDATES
        call = check.calls[0]
        assert call["model"] == ke.DEFAULT_MODEL and call["instructions"] == ke.SYSTEM_PROMPT
        assert call["prompt"].startswith(f"Question: {QUESTION}\n") and "from fees" in call["prompt"]

    @pytest.mark.asyncio
    async def test_the_check_scores_no_candidate_the_pool_scored(self, check, precise):
        check.decide = _fees_answer
        store = _store()
        assert kg._precise_pool(store, KB, QUESTION, k=4, floor=0.0) == []
        pool_alone = precise.calls
        kr._RESULTS.clear()
        precise.calls = 0
        pool = await _pool(store)
        assert pool and all(r.get(ke.CHECKED) for r in pool)
        assert precise.calls == pool_alone

    @pytest.mark.asyncio
    async def test_partial_or_no_keeps_nothing(self, check):
        check.decide = lambda text, n: '{"label": "partial", "quote": "%s"}' % text[:60]
        assert await _pool() == []
        assert len(check.calls) == ke.CANDIDATES

    @pytest.mark.asyncio
    async def test_a_quote_not_in_the_passage_keeps_nothing(self, check):
        check.decide = lambda text, n: '{"label": "answers", "quote": "the sponsor keeps all program income"}'
        assert await _pool() == []

    @pytest.mark.asyncio
    async def test_a_failed_or_late_call_keeps_nothing_and_the_others_stand(self, check, monkeypatch):
        monkeypatch.setattr(ke, "CHECK_SECONDS", 0.2)
        replies = {0: RuntimeError("endpoint down"), 1: ("slow", None)}

        def decide(text, n):
            out = replies.get(n, _answers(text))
            return ("slow", _answers(text)) if isinstance(out, tuple) else out

        check.decide = decide
        pool = await _pool()
        assert len([r for r in pool if r.get(ke.CHECKED)]) == 1

    @pytest.mark.asyncio
    async def test_an_unreadable_reply_is_asked_for_once_more(self, check):
        seen = []

        def decide(text, n):
            seen.append(text)
            return "It does answer it." if seen.count(text) == 1 else _answers(text)

        check.decide = decide
        pool = await _pool()
        assert pool and len(check.calls) == 2 * ke.CANDIDATES
        assert sum(c["prompt"].endswith(ke.RETRY_NOTE) for c in check.calls) == ke.CANDIDATES

    @pytest.mark.asyncio
    async def test_the_configured_model_checks(self, check):
        check.state["doc"] = {"chat_config": {"empty_pool_check_enabled": True, "empty_pool_check_model": "x/c"}}
        check.decide = _fees_answer
        assert await _pool()
        assert {c["model"] for c in check.calls} == {"x/c"}

    @pytest.mark.asyncio
    async def test_a_verdict_is_asked_for_once(self, check):
        check.decide = _fees_answer
        store = _store()
        first = await _pool(store)
        again = await _pool(store)
        assert again == first and len(check.calls) == ke.CANDIDATES

    @pytest.mark.asyncio
    async def test_a_question_that_keeps_passages_is_not_checked(self, check):
        check.decide = _fees_answer
        pool = await _pool(question="program income earned by the recipient")
        assert pool and not any(r.get(ke.CHECKED) for r in pool)
        assert check.calls == []

    @pytest.mark.asyncio
    async def test_what_a_reworded_search_finds_is_not_checked(self, check, monkeypatch):
        async def paraphrases(question, model_name):
            return ["program income earned by the recipient"]

        monkeypatch.setattr(kp, "paraphrases", paraphrases)
        check.decide = _fees_answer
        pool = await _pool()
        assert pool and all(r[kp.RESCUED] for r in pool)
        assert check.calls == []

    @pytest.mark.asyncio
    async def test_without_an_answering_model_nothing_is_checked(self, check):
        check.decide = _fees_answer
        assert await _pool(model_name=None) == []
        assert check.calls == []

    @pytest.mark.asyncio
    async def test_workflow_grounding_does_not_check(self, check):
        check.decide = _fees_answer
        assert kg._precise_pool(_store(), KB, QUESTION, k=4, floor=0.0) == []
        assert check.calls == []
