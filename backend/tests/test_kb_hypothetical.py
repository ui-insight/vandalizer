"""A question that keeps no passage, even reworded and checked, is searched
once more with the texts the model expects the base to hold, and what the
empty-pool check's model finds answers the question is handed over
(kb_hypothetical)."""

import asyncio

from app.services import kb_empty_check, kb_grounding, kb_hypothetical as H, kb_paraphrase, kb_retrieval

ON = {"chat_config": {"kb_hypothetical_search_enabled": True}}
Q = "A vendor bidding on one of our grant-funded contracts offered to take our buyer to dinner. Is that okay?"


# ------------------------------------------------------------------ the texts as queries

def test_the_text_is_cleaned_and_figures_the_question_lacks_are_struck():
    out = ("<think>hmm</think>Passage: **Standards of conduct** for procurement provide that no employee may "
           "solicit or accept gratuities, favors or anything of monetary value from contractors, per § 200.318(c)(1), "
           "unless the item is of nominal value under $50.")
    text = H.clean(Q, out)
    assert text.startswith("Standards of conduct for procurement provide that no employee may solicit or accept gratuities")
    assert "200.318" not in text and "$50" not in text and "*" not in text and "<think>" not in text
    assert "unless the item is of nominal value under" in text


def test_a_figure_the_question_holds_is_kept_and_a_short_output_is_nothing():
    q = "Can we pay a $2,500 laptop as a direct cost?"
    assert "$2,500" in H.clean(q, "Equipment and computing devices costing $2,500 or less may be charged as a direct cost when essential and allocable.")
    assert H.clean(q, "OK.") == ""
    assert len(H.clean(q, "word " * 400)) <= H.MAX_CHARS


def test_the_search_is_off_unless_chat_config_turns_it_on():
    assert H.enabled(None) is False and H.enabled({"chat_config": {}}) is False and H.enabled(ON) is True
    assert H.candidate_count(ON) == H.CANDIDATES
    assert H.candidate_count({"chat_config": {"kb_hypothetical_search_candidates": "7"}}) == 7


def test_both_texts_are_asked_for_at_once_and_an_empty_one_is_dropped(monkeypatch):
    asked = []

    async def fake_ask(kind, prompt, question, model_name):
        asked.append(kind)
        return "" if kind == "lines" else "Gratuities from contractors are prohibited by the standards of conduct."

    monkeypatch.setattr(H, "_ask", fake_ask)
    H._CACHE.clear()
    texts = asyncio.run(H.hypotheticals(Q, "m"))
    assert texts == ["Gratuities from contractors are prohibited by the standards of conduct."]
    assert sorted(asked) == ["lines", "passage"]
    assert asyncio.run(H.hypotheticals(Q, "m")) == texts and len(asked) == 2  # cached
    assert asyncio.run(H.hypotheticals(Q, None)) == []


# ------------------------------------------------------------------ the checked pool

def _rows(ids, scores):
    return [{"chunk_id": c, "content": f"passage {c} on gratuities", "rerank_score": s} for c, s in zip(ids, scores)]


def _wire(monkeypatch, *, doc=ON, texts=("Gratuities are prohibited.", "Costs of gratuities: unallowable."),
          keep=("c0", "c2")):
    calls = {"hypotheticals": 0, "best": [], "read": []}

    async def fake_hypotheticals(question, model_name):
        calls["hypotheticals"] += 1
        return list(texts)

    def fake_best(dm, kb_uuid, query, *, n, floor):
        calls["best"].append((query, n))
        return _rows(["c0", "c1"], [3.0, 2.0]) if query == texts[0] else _rows(["c1", "c2"], [2.5, 1.0])

    async def fake_keeps(ask, model, question, source, text):
        cid = text.split()[1]
        calls["read"].append(cid)
        return cid in keep

    monkeypatch.setattr(kb_empty_check, "_system_config_doc", lambda: doc)
    monkeypatch.setattr(H, "hypotheticals", fake_hypotheticals)
    monkeypatch.setattr(kb_grounding, "best_candidates", fake_best)
    monkeypatch.setattr(kb_empty_check, "_keeps", fake_keeps)
    monkeypatch.setattr(kb_retrieval, "index_for", lambda dm, kb_uuid: None)
    import app.services.chat_answer_repair as car
    monkeypatch.setattr(car, "model_ask", lambda model_name, doc: None)
    return calls


def test_the_candidates_of_both_texts_are_read_once_and_the_answering_ones_kept_in_score_order(monkeypatch):
    calls = _wire(monkeypatch)
    pool = asyncio.run(H.checked_pool(None, "kb1", Q, k=5, floor=0.3, model_name="m"))
    assert [r["chunk_id"] for r in pool] == ["c0", "c2"]
    assert all(r[kb_empty_check.CHECKED] and r[H.HYPOTHETICAL] for r in pool)
    assert calls["best"] == [("Gratuities are prohibited.", H.CANDIDATES), ("Costs of gratuities: unallowable.", H.CANDIDATES)]
    assert sorted(calls["read"]) == ["c0", "c1", "c2"]  # c1 found by both texts, read once


def test_off_or_without_a_text_nothing_is_searched(monkeypatch):
    calls = _wire(monkeypatch, doc={"chat_config": {}})
    assert asyncio.run(H.checked_pool(None, "kb1", Q, k=5, floor=0.3, model_name="m")) == []
    assert calls["hypotheticals"] == 0
    calls = _wire(monkeypatch, texts=())
    assert asyncio.run(H.checked_pool(None, "kb1", Q, k=5, floor=0.3, model_name="m")) == []
    assert calls["best"] == []


def test_the_precise_pool_falls_back_on_it_only_after_the_rescue_and_the_check(monkeypatch):
    order = []

    async def nothing(*a, **kw):
        order.append("check")
        return []

    async def hypo(dm, kb_uuid, query, **kw):
        order.append("hypothetical")
        return [{"chunk_id": "c9", "content": "the rule", kb_empty_check.CHECKED: True, H.HYPOTHETICAL: True}]

    async def no_phrases(question, model_name):
        order.append("paraphrases")
        return []

    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda *a, **kw: [])
    monkeypatch.setattr(kb_paraphrase, "paraphrases", no_phrases)
    monkeypatch.setattr(kb_empty_check, "checked_pool", nothing)
    monkeypatch.setattr(H, "checked_pool", hypo)
    monkeypatch.setattr(kb_grounding, "with_neighbours", lambda dm, kb_uuid, query, pool, *, k: pool)
    pool = asyncio.run(kb_paraphrase.precise_pool(None, "kb1", Q, k=5, floor=0.3, model_name="m"))
    assert [r["chunk_id"] for r in pool] == ["c9"] and kb_paraphrase.RESCUED not in pool[0]
    assert order == ["paraphrases", "check", "hypothetical"]


def test_a_pool_the_check_keeps_is_not_searched_again(monkeypatch):
    async def kept(*a, **kw):
        return [{"chunk_id": "c1", "content": "the rule", kb_empty_check.CHECKED: True}]

    async def never(*a, **kw):
        raise AssertionError("searched")

    async def no_phrases(question, model_name):
        return []

    monkeypatch.setattr(kb_grounding, "_precise_pool", lambda *a, **kw: [])
    monkeypatch.setattr(kb_paraphrase, "paraphrases", no_phrases)
    monkeypatch.setattr(kb_empty_check, "checked_pool", kept)
    monkeypatch.setattr(H, "checked_pool", never)
    monkeypatch.setattr(kb_grounding, "with_neighbours", lambda dm, kb_uuid, query, pool, *, k: pool)
    pool = asyncio.run(kb_paraphrase.precise_pool(None, "kb1", Q, k=5, floor=0.3, model_name="m"))
    assert [r["chunk_id"] for r in pool] == ["c1"]
