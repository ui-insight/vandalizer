"""The badge keys off whether the value is IN the quote, not off whether the
quote exists.

`verified` only says the passage was located in the document. A model that
fabricates an award amount and returns any real sentence from the budget
section earns a located quote — and used to earn the same blue "traced to
p. 12" chip as a correct value.
"""

from app.services.extraction_sources import (
    SOURCE_KEY,
    resolve_entity_sources,
    support_state,
    support_state_of,
)

_MARKERS = [{"char_offset": 0, "kind": "page", "value": 1}]
_TEXT = "The total award is $500,000 for the period of performance. Cost sharing is required."


def _resolve(value, quote, field_meta=None):
    entities = [{"F": value, SOURCE_KEY: {"F": {"quote": quote}}}]
    resolve_entity_sources(
        entities, _TEXT, {"uuid": "d1", "title": "Doc", "text_markers": _MARKERS},
        field_meta,
    )
    return entities[0][SOURCE_KEY]["F"]


class TestSupportState:
    def test_located_quote_containing_the_value_is_supported(self):
        src = _resolve("$500,000", "The total award is $500,000 for the period of performance.")
        assert src["verified"] is True
        assert src["value_supported"] is True
        assert src["support"] == "supported"

    def test_real_passage_that_does_not_say_the_value_is_flagged(self):
        # The hallucination case: a genuine sentence from the document,
        # attached to a figure that is not in it.
        src = _resolve("$4,200,000", "The total award is $500,000 for the period of performance.")
        assert src["verified"] is True
        assert src["value_supported"] is False
        assert src["support"] == "quote_unsupported"

    def test_fabricated_passage_is_unverified(self):
        src = _resolve("$500,000", "No sentence like this appears in the document at all.")
        assert src["verified"] is False
        assert src["support"] == "unverified"

    def test_enum_answer_is_traceable_but_unconfirmable(self):
        src = _resolve("Yes", "Cost sharing is required.", {"F": {"enum_values": ["Yes", "No"]}})
        assert src["verified"] is True
        assert src["value_supported"] is None
        assert src["support"] == "unassessed"


class TestDerivation:
    def test_pairs_map_to_states(self):
        assert support_state(True, True) == "supported"
        assert support_state(True, False) == "quote_unsupported"
        assert support_state(True, None) == "unassessed"
        assert support_state(False, True) == "unverified"
        assert support_state(False, None) == "unverified"

    def test_stored_state_wins(self):
        assert support_state_of({"support": "supported"}) == "supported"

    def test_legacy_sidecar_without_measurement_is_not_promoted(self):
        # Written before value_supported existed: verified, unmeasured. It must
        # not inherit the strongest badge by default.
        assert support_state_of({"verified": True}) == "unassessed"
        assert support_state_of({"verified": False}) == "unverified"

    def test_missing_or_malformed_entries_are_unverified(self):
        assert support_state_of(None) == "unverified"
        assert support_state_of("nope") == "unverified"
