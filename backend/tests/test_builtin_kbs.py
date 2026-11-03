"""Chat consults Vandalizer's built-in regulation knowledge bases unattached.

Support ticket: with nothing attached, "What is the effective date of PAPPG
24-1 Supplement 1?" was answered from memory (Jan 20, 2025; NSF says Dec. 8,
2025) and the Single Audit threshold from commercial blogs. With the built-in
KBs attached, both were right and cited.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.function import FunctionModel

from app.services import builtin_kbs
from app.services.context_budget import DocumentSegment
from tests.test_chat_output import chat_harness  # noqa: F401  (fixture)


@pytest.mark.parametrize("question, seeds", [
    ("What is the effective date of PAPPG 24-1 Supplement 1?", ["kb-nsf-pappg"]),
    ("What is the Single Audit expenditure threshold? Cite the section.", ["kb-2cfr200"]),
    ("Is a $12,000 microscope equipment under 2 CFR 200.1?", ["kb-2cfr200"]),
    ("What does the NIH salary cap apply to?", ["kb-nih-gps"]),
    ("When must an investigator disclose a significant financial interest under FCOI?", ["kb-fcoi"]),
    ("Does an NSF award follow the Uniform Guidance for indirect costs?", ["kb-2cfr200", "kb-nsf-pappg"]),
    ("Which FAR clause covers contract termination?", ["kb-far"]),
    ("Does this study need IRB review under the Common Rule?", ["kb-common-rule"]),
])
def test_policy_questions_route_to_the_matching_built_in_kb(question, seeds):
    assert builtin_kbs.matching_seed_ids(question) == seeds


@pytest.mark.parametrize("message", [
    "Run the NSF budget review workflow on my folder",   # a task, not a question
    "Create a knowledge base from the PAPPG",
    "What's on my calendar this week?",                   # no regulation named
    "Summarize this proposal",
    "Thanks!",
])
def test_tasks_and_unrelated_messages_do_not_route(message):
    assert builtin_kbs.matching_seed_ids(message) == []


def _kb(seed, title, chunks=40, status="ready"):
    return SimpleNamespace(uuid=f"uuid-{seed}", title=title, description=f"{title} (current edition)",
                           resource_config={"seed_id": seed}, total_chunks=chunks, status=status, updated_at=None)


PAPPG = _kb("kb-nsf-pappg", "NSF PAPPG Reference")
UG = _kb("kb-2cfr200", "OMB Uniform Guidance (2 CFR 200)")


@pytest.mark.asyncio
async def test_only_searchable_built_in_kbs_are_routed():
    with patch.object(builtin_kbs, "builtin_kbs", AsyncMock(return_value=[PAPPG])):
        routed = await builtin_kbs.route("Does an NSF award follow the Uniform Guidance for indirect costs?")
    assert [kb.title for kb in routed] == ["NSF PAPPG Reference"]
    assert builtin_kbs._searchable(_kb("x", "Empty", chunks=0)) is False


def _agent(seen: list[str], answer: str):
    async def respond(messages, info):
        seen.append(json.dumps([str(p) for m in messages for p in getattr(m, "parts", [])]))
        yield answer
    return Agent(FunctionModel(stream_function=respond))


@pytest.fixture
def kb_env(monkeypatch):
    from app.services import chat_service as chat, knowledge_service

    retrieved = []

    async def segment(kbs, message, model_name, **kwargs):
        retrieved.append(list(kbs))
        sources = [{"kb_uuid": kbs[0][0], "document_title": "Chapter II", "chunk_id": "c1", "content_preview": "Supplement 1 is effective December 8, 2025."}]
        return DocumentSegment(label="kb", text="[S1] Supplement 1 is effective December 8, 2025.", required=True), sources

    monkeypatch.setattr(chat, "_build_multi_kb_segment", segment)
    monkeypatch.setattr(knowledge_service, "get_kb_manifest", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_kb_status_entries", AsyncMock(return_value=[]))
    monkeypatch.setattr(builtin_kbs, "builtin_kbs", AsyncMock(return_value=[PAPPG, UG]))
    return retrieved


@pytest.mark.asyncio
async def test_unattached_policy_question_is_answered_from_the_built_in_kb(chat_harness, kb_env):  # noqa: F811
    seen: list[str] = []
    chunks = await chat_harness.run(_agent(seen, "Supplement 1 took effect December 8, 2025 [S1]."),
                                    message="What is the effective date of PAPPG 24-1 Supplement 1?")
    assert not [c for c in chunks if c["kind"] == "error"], chunks
    assert kb_env == [[("uuid-kb-nsf-pappg", "NSF PAPPG Reference")]]
    notice = [c for c in chunks if c.get("action") == "builtin_kbs_consulted"]
    assert notice and "NSF PAPPG Reference" in notice[0]["content"]
    assert "searched its built-in knowledge base" in seen[0] and "edition" in seen[0]
    assert "December 8, 2025" in seen[0]


@pytest.mark.asyncio
async def test_attached_kbs_and_tasks_are_left_alone(chat_harness, kb_env):  # noqa: F811
    seen: list[str] = []
    await chat_harness.run(_agent(seen, "Done."), message="What is the effective date of PAPPG 24-1 Supplement 1?",
                           kbs=[("chosen", "My KB")])
    assert kb_env == [[("chosen", "My KB")]]
    kb_env.clear()
    chunks = await chat_harness.run(_agent(seen, "Started."), message="Run the NSF budget review workflow")
    assert kb_env == []
    assert not [c for c in chunks if c.get("action") == "builtin_kbs_consulted"]
    # Not consulted, but the agent is told they exist and how to search them.
    assert "search_knowledge_base with the matching kb_uuid" in seen[-1] and "uuid-kb-nsf-pappg" in seen[-1]


@pytest.mark.asyncio
async def test_a_built_in_kb_with_nothing_relevant_falls_back_to_an_ordinary_chat(chat_harness, kb_env, monkeypatch):  # noqa: F811
    from app.services import chat_service as chat

    monkeypatch.setattr(chat, "_build_multi_kb_segment", AsyncMock(return_value=(None, [])))
    seen: list[str] = []
    chunks = await chat_harness.run(_agent(seen, "I couldn't find it."), message="What does NSF say about llamas?")
    assert not [c for c in chunks if c.get("action") == "builtin_kbs_consulted"]
    assert "returned nothing relevant" in seen[0]
    # Not the attached-KB "nothing retrieved" mode the user would have chosen.
    assert "statement about this search" not in seen[0]


@pytest.mark.asyncio
async def test_web_results_put_official_sources_first():
    from app.services.chat_tools import web_search
    from tests.test_chat_tools import _make_context

    ctx = _make_context()
    ctx.tool_call_id = "call-1"
    ctx.deps.system_config_doc = {"web_search_provider": "tavily"}
    service = {"query": "single audit threshold", "results": [
        {"title": "Grantsights blog", "url": "https://www.grantsights.com/single-audit", "snippet": "..."},
        {"title": "2 CFR 200.501", "url": "https://www.ecfr.gov/current/title-2/section-200.501", "snippet": "$1,000,000"},
        {"title": "Trullion", "url": "https://trullion.com/blog", "snippet": "..."},
        {"title": "NSF PAPPG", "url": "https://www.nsf.gov/policies/pappg", "snippet": "..."},
    ]}
    with patch("app.services.web_search_service.web_search", AsyncMock(return_value=service)):
        out = await web_search(ctx, "single audit threshold")
    assert [r["official"] for r in out["results"]] == [True, True, False, False]
    assert out["results"][0]["url"].startswith("https://www.ecfr.gov")
    assert "official" in out["official_note"]
    assert ctx.deps.citation_annotations["call-1"][0]["url"].startswith("https://www.ecfr.gov")


@pytest.mark.parametrize("url, official", [
    ("https://www.ecfr.gov/x", True), ("https://grants.nih.gov/policy", True), ("https://www.acq.osd.mil/", True),
    ("https://www.fs.fed.us/x", True), ("https://ecfr.gov.example.com/x", False), ("https://cogr.edu", False),
    ("not a url", False), (None, False),
])
def test_official_url(url, official):
    from app.services.chat_tools import _is_official_url
    assert _is_official_url(url) is official
