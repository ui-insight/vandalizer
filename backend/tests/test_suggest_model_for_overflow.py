"""The suggestion that feeds the context-limit dialog.

`suggest_document_model` answers "is there a model that could have held this?"
That question is only meaningful about the request the user actually made — the
one that was too big. Asking it about the *compacted* request always answers
"no", because compaction is defined as making it fit.

The dialog's own tests render with a suggestion handed to them, so they pass
whether or not one is ever produced. These tests cover the value itself.
"""

from app.services.chat_service import _suggest_model_for_overflow
from app.services.context_budget import (
    DocumentSegment,
    estimate_input_tokens,
    plan_and_compact_context,
)

SMALL = {"name": "small", "tag": "small", "context_window": 32768, "privacy": "internal"}
LARGE = {"name": "large", "tag": "large", "context_window": 262144, "privacy": "internal"}
SYS_CONFIG = {"available_models": [SMALL, LARGE]}


def _request(text: str):
    """Build a request the way chat_stream does: measure first, then compact."""
    pieces = dict(
        system_prompt="You are a helpful assistant.",
        user_message="What is the total budget?",
        history=[],
        documents=[DocumentSegment(label="proposal", text=text)],
        attachments=[],
    )
    requested_tokens = estimate_input_tokens(model_name="small", **pieces)
    compacted = plan_and_compact_context(
        model_name="small", model_config=SMALL, **pieces
    )
    return compacted, requested_tokens


def _overflowing():
    return _request("word " * 60_000)


def test_the_fixture_actually_overflows():
    """Guard: if this stops trimming, the tests below prove nothing."""
    compacted, _ = _overflowing()
    assert compacted.actions, "fixture must overflow or there is nothing to suggest"


def test_the_compacted_total_cannot_answer_the_question():
    """The bug this file exists for, stated as a property.

    After compaction the total always fits the current model, so feeding it to
    the suggester can only ever produce None.
    """
    compacted, requested = _overflowing()
    assert compacted.plan.total_input_tokens <= compacted.plan.input_budget
    assert requested > compacted.plan.input_budget


def test_offers_a_model_that_could_have_held_the_request():
    compacted, requested = _overflowing()
    suggestion = _suggest_model_for_overflow(
        compacted, "small", SMALL, SYS_CONFIG, requested
    )
    assert suggestion is not None, (
        "a 262k model was configured and the request overflowed a 32k one — "
        "the dialog must be able to offer it"
    )
    assert suggestion["name"] == "large"
    assert suggestion["tag"] == "large"
    assert suggestion["context_window"] == 262144


def test_no_suggestion_when_nothing_was_compacted():
    compacted, requested = _request("short body")
    assert not compacted.actions
    assert _suggest_model_for_overflow(
        compacted, "small", SMALL, SYS_CONFIG, requested
    ) is None


def test_no_suggestion_when_no_other_model_is_configured():
    compacted, requested = _overflowing()
    assert _suggest_model_for_overflow(
        compacted, "small", SMALL, {"available_models": [SMALL]}, requested
    ) is None


def test_never_suggests_a_model_with_weaker_privacy():
    """The privacy gate has to survive the pre-compaction fix."""
    external = dict(LARGE, name="cloud", tag="cloud", privacy="external")
    compacted, requested = _overflowing()
    assert _suggest_model_for_overflow(
        compacted, "small", SMALL, {"available_models": [SMALL, external]}, requested
    ) is None
