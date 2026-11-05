"""The rest of a short section a turn's passages come from joins the pool (kb_grounding.complete_sections), behind
chat_config.kb_section_completion_enabled."""
from unittest.mock import MagicMock

import pytest

from app.services import chat_service, kb_grounding, kb_retrieval as kr


class _Index:
    """A base's chunks in document order: section keys, with a source without numbers and an excluded section."""

    def __init__(self, spec):
        self.chunks, self.keys = [], []
        for n, (key, text) in enumerate(spec):
            self.chunks.append({"content": text, "metadata": {"section_key": key, "source_id": "src"},
                                "chunk_id": f"c{n}"})
            self.keys.append(key)
        self.excluded = set()
        self.position = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}
        self.count = len(self.chunks)


SPEC = [
    ("200.307", "a" * 100), ("200.307", "b" * 100), ("200.307", "c" * 100),      # c0 c1 c2: short, 300 chars
    ("200.308", "d" * 100), ("200.308", "e" * 100),                              # c3 c4: short, 200 chars
    ("200.400", "f" * 7000), ("200.400", "g" * 7000),                            # c5 c6: 14,000 chars, over the cap
    ("source:policy", "h" * 50), ("source:policy", "i" * 50),                    # c7 c8: no section numbers
]


def _passage(index, j, **extra):
    return {**kr._chunk_result(index, j), "kb_uuid": "kb-1", "kb_title": "UG", **extra}


@pytest.fixture
def base(monkeypatch):
    index = _Index(SPEC)
    monkeypatch.setattr(kr, "ready", lambda: True)
    monkeypatch.setattr(kr, "index_for", lambda dm, kb_uuid: index if kb_uuid == "kb-1" else None)
    monkeypatch.setattr(kb_grounding, "attach_lead_ins", lambda dm, kb_uuid, passages: passages)
    return index


def test_a_short_section_is_completed_after_its_last_passage_in_document_order(base):
    pool = [_passage(base, 1), _passage(base, 3), _passage(base, 0)]
    out = kb_grounding.complete_sections(MagicMock(), pool)
    assert [p["chunk_id"] for p in out] == ["c1", "c3", "c4", "c0", "c2"]
    added = {p["chunk_id"]: p for p in out if p.get("_completed")}
    assert set(added) == {"c4", "c2"}
    assert added["c2"]["_completed"] == "200.307" and added["c2"]["kb_uuid"] == "kb-1" and added["c2"]["kb_title"] == "UG"
    # The passages the turn had are the same objects, untouched.
    assert out[0] is pool[0] and "_completed" not in pool[0]


def test_a_long_section_a_source_without_numbers_and_an_excluded_chunk_are_left_alone(base):
    base.excluded.add(2)
    pool = [_passage(base, 5), _passage(base, 7), _passage(base, 0)]
    out = kb_grounding.complete_sections(MagicMock(), pool)
    assert [p["chunk_id"] for p in out] == ["c5", "c7", "c0", "c1"]


def test_the_turn_s_budget_completes_the_best_section_first(base):
    pool = [_passage(base, 3), _passage(base, 0)]
    out = kb_grounding.complete_sections(MagicMock(), pool, turn_chars=250)
    # 200.308 (first passage) gains c4 (100 chars); 200.307 would need 200 more, over the 250 budget.
    assert [p["chunk_id"] for p in out] == ["c3", "c4", "c0"]
    out = kb_grounding.complete_sections(MagicMock(), pool, max_chars=250)
    # A 300-char section is over a 250-char cap; the 200-char one is completed.
    assert [p["chunk_id"] for p in out] == ["c3", "c4", "c0"]


def test_a_section_the_turn_already_holds_whole_and_a_base_without_an_index_add_nothing(base):
    pool = [_passage(base, 3), _passage(base, 4), {**_passage(base, 0), "kb_uuid": "kb-2"}]
    assert kb_grounding.complete_sections(MagicMock(), pool) is pool
    assert kb_grounding.complete_sections(MagicMock(), []) == []


def test_the_setting_is_off_by_default_and_carries_its_caps():
    assert kb_grounding.section_completion(None) is None
    assert kb_grounding.section_completion({"chat_config": {}}) is None
    on = kb_grounding.section_completion({"chat_config": {"kb_section_completion_enabled": True}})
    assert on == {"max_chars": kr.SECTION_COMPLETE_MAX_CHARS, "turn_chars": kr.SECTION_COMPLETE_TURN_CHARS}
    custom = kb_grounding.section_completion({"chat_config": {
        "kb_section_completion_enabled": True, "kb_section_completion_max_chars": "5000",
        "kb_section_completion_turn_chars": "x"}})
    assert custom == {"max_chars": 5000, "turn_chars": kr.SECTION_COMPLETE_TURN_CHARS}


@pytest.mark.asyncio
async def test_chat_completes_sections_only_when_the_setting_is_on(monkeypatch):
    calls = []

    def complete(dm, passages, *, max_chars=None, turn_chars=None):
        calls.append((max_chars, turn_chars))
        return passages + [{"chunk_id": "more", "_completed": "200.307"}]

    monkeypatch.setattr(kb_grounding, "complete_sections", complete)
    monkeypatch.setattr("app.services.document_manager.get_document_manager", lambda: MagicMock())
    pool = [{"chunk_id": "c0", "kb_uuid": "kb-1"}]
    monkeypatch.setattr("app.services.kb_empty_check._system_config_doc", lambda: {"chat_config": {}})
    assert await chat_service._with_complete_sections(pool) is pool
    assert calls == []
    monkeypatch.setattr("app.services.kb_empty_check._system_config_doc",
                        lambda: {"chat_config": {"kb_section_completion_enabled": True, "kb_section_completion_max_chars": 8000}})
    out = await chat_service._with_complete_sections(pool)
    assert [p["chunk_id"] for p in out] == ["c0", "more"]
    assert calls == [(8000, kr.SECTION_COMPLETE_TURN_CHARS)]
    # A failure inside leaves the snippets as they were.
    monkeypatch.setattr(kb_grounding, "complete_sections", lambda *a, **k: 1 / 0)
    assert await chat_service._with_complete_sections(pool) is pool
