"""Dates and figures a web answer took from search snippets (NSF PAPPG ticket)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.web_answer_grounding import (
    correction_note,
    date_values,
    missed_corrections,
    unconfirmed_web_facts,
)

# Step 2 of the ticket: answered from web_search results alone.
EARLIER_ANSWER = (
    "The current version is the **NSF PAPPG (NSF 24-1)**, effective May 20, 2024.\n"
    "- Supplement 1 (effective Oct. 8, 2025)\n"
    "- Supplement 2 (effective Jan. 22, 2026)\n"
    "Official link: https://www.nsf.gov/policies/pappg"
)
SNIPPETS = (
    '{"results": [{"title": "PAPPG", "url": "https://www.nsf.gov/policies/pappg", '
    '"snippet": "NSF 24-1 effective May 20, 2024. Supplement 1 effective October 8, 2025"}]}'
)
# The hub page the answer linked.
HUB_PAGE = (
    "Proposal & Award Policies & Procedures Guide (PAPPG)\n"
    "NSF 24-1, effective May 20, 2024.\n"
    "Supplement 1 (NSF 26-200), effective Dec. 8, 2025.\n"
    "Supplement 2, effective Jan. 22, 2026."
)
HUB_URL = "https://www.nsf.gov/policies/pappg"


class TestDateValues:
    @pytest.mark.parametrize("text", [
        "December 8, 2025", "Dec. 8, 2025", "Dec 8 2025", "Dec. 8th, 2025",
        "8 December 2025", "2025-12-08", "12/8/2025",
    ])
    def test_formats_normalize_to_one_date(self, text):
        assert list(date_values(text)) == [(2025, 12, 8)]

    def test_non_dates_are_ignored(self):
        assert date_values("NSF 24-1, section 13/40/2025, May 2024, 2025-13-40") == {}


class TestUnconfirmedWebFacts:
    def test_snippet_only_dates_are_unconfirmed(self):
        # Snippets are not passed as read text: none of these dates is confirmed,
        # including the right ones, because no page was read.
        assert unconfirmed_web_facts(EARLIER_ANSWER, "question text") == [
            "May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026",
        ]

    def test_dates_on_a_read_page_are_confirmed(self):
        assert unconfirmed_web_facts(EARLIER_ANSWER, HUB_PAGE) == ["Oct. 8, 2025"]

    def test_money_and_percent_are_checked_and_not_double_reported(self):
        answer = "The threshold is $10,000 and the rate is 15%, effective 2025-10-01."
        page = "The threshold is $10,000."
        assert unconfirmed_web_facts(answer, page) == ["15%", "2025-10-01"]
        assert unconfirmed_web_facts(answer, page, already_flagged=["15%"]) == ["2025-10-01"]

    def test_a_retracted_value_is_not_asserted(self):
        answer = (
            "Correction: Supplement 1 is effective Dec. 8, 2025, not Oct. 8, 2025 "
            "as I said above."
        )
        assert unconfirmed_web_facts(answer, HUB_PAGE) == []

    def test_answer_without_facts(self):
        assert unconfirmed_web_facts("See the PAPPG hub page.", "") == []


def _missed(answer: str, *, page: str = HUB_PAGE, url: str = HUB_URL + "/", earlier=None):
    return missed_corrections(
        earlier_unconfirmed=earlier or ["May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026"],
        earlier_cited_urls=[HUB_URL, "https://www.nsf.gov/policies/pappg/24-1"],
        earlier_answer=EARLIER_ANSWER,
        answer=answer,
        pages_read=[(url, page)],
    )


class TestMissedCorrections:
    def test_silent_replacement_of_a_snippet_date_is_caught(self):
        # Step 3 of the ticket: right date, no acknowledgement.
        answer = "The exact effective date of Supplement 1 (NSF 26-200) is **December 8, 2025**."
        assert _missed(answer) == ["Oct. 8, 2025"]

    def test_other_earlier_dates_the_answer_leaves_alone_are_not_corrected(self):
        # Supplement 2's date isn't on this (trimmed) page and the new answer
        # doesn't mention it, but nothing replaced it.
        page = "Supplement 1 (NSF 26-200), effective Dec. 8, 2025."
        answer = "Supplement 1 (NSF 26-200) is effective December 8, 2025."
        assert _missed(answer, page=page) == ["Oct. 8, 2025"]

    def test_an_acknowledged_correction_needs_no_note(self):
        answer = "Correction: Supplement 1 is effective Dec. 8, 2025, not Oct. 8, 2025 as I said."
        assert _missed(answer) == []

    def test_a_page_the_earlier_answer_did_not_cite_proves_nothing(self):
        answer = "Supplement 1 is effective December 8, 2025."
        assert _missed(answer, url="https://example.edu/nsf-summary") == []

    def test_an_earlier_date_the_page_confirms_is_not_corrected(self):
        answer = "NSF 24-1 has been effective since May 20, 2024; Supplement 1 since Dec. 8, 2025."
        assert _missed(answer, earlier=["May 20, 2024"]) == []

    def test_note_names_the_earlier_value(self):
        note = correction_note(["Oct. 8, 2025"])
        assert "Correction" in note and "**Oct. 8, 2025**" in note
        assert correction_note([]) == ""


class TestSilentCorrectionNoteWiring:
    @pytest.mark.asyncio
    async def test_reads_previous_answer_and_this_turns_page(self):
        from app.services import chat_service

        earlier = SimpleNamespace(
            message=EARLIER_ANSWER,
            unconfirmed_web_facts=["May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026"],
            citations=[{"url": HUB_URL}],
        )
        query = MagicMock()
        query.sort.return_value.first_or_none = MagicMock(return_value=_awaitable(earlier))
        conversation = SimpleNamespace(messages=["m1", "m2"])
        with patch.object(chat_service.ChatMessage, "find", return_value=query):
            note = await chat_service._silent_correction_note(
                conversation,
                "Supplement 1 (NSF 26-200) is effective December 8, 2025.",
                [{"tool_name": "fetch_url", "tool_call_id": "c1", "args": {"url": HUB_URL}}],
                [{"tool_name": "fetch_url", "tool_call_id": "c1",
                  "content": {"url": HUB_URL + "/", "text": HUB_PAGE}}],
            )
        assert "**Oct. 8, 2025**" in note

    @pytest.mark.asyncio
    async def test_no_page_read_means_no_lookup(self):
        from app.services import chat_service

        with patch.object(chat_service.ChatMessage, "find") as find:
            note = await chat_service._silent_correction_note(
                SimpleNamespace(messages=["m1"]), "Dec. 8, 2025", [], [],
            )
        assert note == ""
        find.assert_not_called()


async def _coro(value):
    return value


def _awaitable(value):
    return _coro(value)


# ---------------------------------------------------------------------------
# Through chat_stream, with a scripted model.
# ---------------------------------------------------------------------------

from pydantic_ai import Agent, Tool  # noqa: E402
from pydantic_ai.models.function import DeltaToolCall, FunctionModel  # noqa: E402

from tests.test_chat_output import chat_harness  # noqa: E402,F401 — fixture


def _scripted(tool_name: str, tool_result: dict, answer: str) -> Agent:
    called: list[bool] = []

    async def tool() -> dict:
        called.append(True)
        return tool_result

    async def respond(messages, info):
        if not called:
            yield {0: DeltaToolCall(name=tool_name, json_args="{}", tool_call_id="t1")}
        else:
            for char in answer:
                yield char

    return Agent(FunctionModel(stream_function=respond), tools=[Tool(tool, name=tool_name)])


async def test_stream_flags_dates_taken_only_from_search_snippets(chat_harness):  # noqa: F811
    agent = _scripted("web_search", json_loads(SNIPPETS), EARLIER_ANSWER)
    chunks = await chat_harness.run(agent, message="What is the current NSF PAPPG version?")

    warnings = [c for c in chunks if c["kind"] == "grounding_warning"]
    assert warnings and warnings[0]["unconfirmed_web_facts"] == [
        "May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026",
    ]
    assert chat_harness.finalize.call_args.kwargs["unconfirmed_web_facts"] == [
        "May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026",
    ]


async def test_stream_counts_a_page_read_in_the_same_turn(chat_harness):  # noqa: F811
    calls: list[str] = []

    async def web_search() -> dict:
        calls.append("web_search")
        return json_loads(SNIPPETS)

    async def fetch_url() -> dict:
        calls.append("fetch_url")
        return {"url": HUB_URL, "text": HUB_PAGE}

    answer = (
        "NSF 24-1 is effective May 20, 2024. Supplement 1 (NSF 26-200) is effective "
        "Dec. 8, 2025, and the agency says the next revision follows on 2027-01-01."
    )

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaToolCall(name="web_search", json_args="{}", tool_call_id="s1")}
        elif calls == ["web_search"]:
            yield {0: DeltaToolCall(name="fetch_url", json_args="{}", tool_call_id="f1")}
        else:
            for char in answer:
                yield char

    agent = Agent(
        FunctionModel(stream_function=respond),
        tools=[Tool(web_search, name="web_search"), Tool(fetch_url, name="fetch_url")],
    )
    await chat_harness.run(agent, message="What is the current NSF PAPPG version?")
    # Only the date on no page read is unconfirmed.
    assert chat_harness.finalize.call_args.kwargs["unconfirmed_web_facts"] == ["2027-01-01"]


async def test_stream_checks_nothing_when_the_turn_did_not_search(chat_harness):  # noqa: F811
    agent = _scripted("list_documents", {"documents": []}, "Supplement 1 is effective Oct. 8, 2025.")
    chunks = await chat_harness.run(agent, message="When is Supplement 1 effective?")
    assert not [c for c in chunks if c["kind"] == "grounding_warning" and c.get("unconfirmed_web_facts")]
    assert chat_harness.finalize.call_args.kwargs["unconfirmed_web_facts"] is None


async def test_stream_appends_a_correction_when_the_read_page_contradicts(chat_harness, monkeypatch):  # noqa: F811
    from app.services import chat_service

    earlier = SimpleNamespace(
        message=EARLIER_ANSWER,
        unconfirmed_web_facts=["May 20, 2024", "Oct. 8, 2025", "Jan. 22, 2026"],
        citations=[{"url": HUB_URL}],
    )
    query = MagicMock()
    query.sort.return_value.first_or_none = MagicMock(side_effect=lambda: _awaitable(earlier))
    monkeypatch.setattr(chat_service.ChatMessage, "find", MagicMock(return_value=query))

    answer = "The exact effective date of Supplement 1 (NSF 26-200) is **December 8, 2025**."
    agent = _scripted("fetch_url", {"url": HUB_URL, "text": HUB_PAGE}, answer)
    chunks = await chat_harness.run(agent, message="Open the PAPPG hub page.")

    text = "".join(c["content"] for c in chunks if c["kind"] == "text")
    assert text.startswith(answer) and "**Oct. 8, 2025**" in text
    saved = chat_harness.finalize.call_args.args[1]
    assert "Correction" in saved and "**Oct. 8, 2025**" in saved


def json_loads(text: str) -> dict:
    import json

    return json.loads(text)
