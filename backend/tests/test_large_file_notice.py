"""A large attached file is reported as a large file, not a long conversation.

Support ticket: the first question in a new chat, with a COGR research
security matrix (.xlsx) attached, showed "This conversation is getting long
and is close to the model's memory limit" and "Context was compacted …
Trimmed 95001 tokens from reference documents".
"""

from app.services.context_budget import DocumentSegment, build_context_meter, plan_and_compact_context


def _compact(**kwargs):
    defaults = dict(
        model_name="test-model", model_config={"context_window": 1_500}, system_prompt="sys",
        user_message="what can you do with the attached?", history=[], documents=[], attachments=[],
        response_reserve=256,
    )
    return plan_and_compact_context(**{**defaults, **kwargs})


def test_a_cut_document_is_named_with_how_much_of_it_was_sent():
    sheet = DocumentSegment(label="doc:v_10_sept_30_2025.xlsx", text="row value " * 2_000)
    result = _compact(documents=[sheet])
    (action,) = [a for a in result.actions if a.kind == "documents_trimmed"]
    assert '"v_10_sept_30_2025.xlsx" (about ' in action.detail
    assert "%)" in action.detail and "Ask about a specific sheet" in action.detail
    assert "tokens" not in action.detail


def test_the_model_is_told_the_middle_was_left_out_and_how_to_read_it():
    sheet = DocumentSegment(label="doc:matrix.xlsx", text="row value " * 2_000)
    text = _compact(documents=[sheet]).documents[0].text
    assert "[Vandalizer note, not part of the file: the middle of this document was left out" in text
    assert "get_document_text" in text


def test_the_meter_reports_how_much_the_conversation_accounts_for():
    meter = build_context_meter(estimated_tokens=90_000, context_window=128_000, history_tokens=1_200)
    assert meter.to_dict()["history_tokens"] == 1_200
    assert build_context_meter(estimated_tokens=10, context_window=128_000).to_dict()["history_tokens"] is None
