"""The JSON-fallback path must not turn a key mismatch into "not found".

``two_pass.pass_1.structured`` is False by default, so the fallback parser is
the default first pass. It used to project the payload onto the requested keys
with an exact ``parsed.get(key)``, so a model answering "Award Amount" for the
requested key "Award amount" produced an entity of all-nulls — recorded,
displayed and exported as a confident set of "not in the document" answers.
"""

import pytest

from app.services.extraction_engine import ExtractionEngine, ExtractionError


class _Result:
    def __init__(self, output):
        self.output = output

    def usage(self):  # pragma: no cover - not asserted on
        raise AttributeError


class _Agent:
    def __init__(self, output):
        self._output = output

    def run_sync(self, _prompt):
        return _Result(self._output)


@pytest.fixture
def engine():
    return ExtractionEngine(system_config_doc={})


def _run(monkeypatch, engine, payload, keys, capture_sources=False):
    monkeypatch.setattr(
        "app.services.extraction_engine.create_chat_agent",
        lambda *a, **k: _Agent(payload),
    )
    return engine._extract_fallback_json(
        "some document text", keys, "test-model", capture_sources=capture_sources,
    )


KEYS = ["Award amount", "PI Name", "2 CFR Part 200"]


def test_case_and_punctuation_drift_still_resolves(monkeypatch, engine):
    payload = '{"Award Amount": "$500,000", "pi_name": "Jane Smith", "2 CFR part 200": "Yes"}'
    (entity,) = _run(monkeypatch, engine, payload, KEYS)
    assert entity == {
        "Award amount": "$500,000",
        "PI Name": "Jane Smith",
        "2 CFR Part 200": "Yes",
    }


def test_exact_keys_are_preferred_over_folded_collisions(monkeypatch, engine):
    payload = '{"Award amount": "exact", "AWARDAMOUNT": "folded"}'
    (entity,) = _run(monkeypatch, engine, payload, ["Award amount"])
    assert entity["Award amount"] == "exact"


def test_genuinely_absent_fields_stay_null_without_raising(monkeypatch, engine):
    payload = '{"Award amount": null, "PI Name": null, "2 CFR Part 200": null}'
    (entity,) = _run(monkeypatch, engine, payload, KEYS)
    assert entity == {"Award amount": None, "PI Name": None, "2 CFR Part 200": None}


def test_zero_matching_keys_fails_the_run(monkeypatch, engine):
    payload = '{"totally": "unrelated", "other": "keys"}'
    with pytest.raises(ExtractionError, match="none of the requested fields"):
        _run(monkeypatch, engine, payload, KEYS)


def test_empty_object_fails_the_run(monkeypatch, engine):
    with pytest.raises(ExtractionError, match="none of the requested fields"):
        _run(monkeypatch, engine, "{}", KEYS)


def test_sources_block_survives_key_drift(monkeypatch, engine):
    payload = (
        '{"Award Amount": "$500,000", '
        '"_sources": {"award amount": "The total award is $500,000."}}'
    )
    (entity,) = _run(
        monkeypatch, engine, payload, ["Award amount"], capture_sources=True,
    )
    sidecar = entity["_field_sources"]
    assert sidecar["Award amount"]["quote"] == "The total award is $500,000."


def test_list_payload_is_remapped_and_keeps_extra_keys(monkeypatch, engine):
    payload = '[{"Award Amount": "$1", "extra": "kept"}, {"Award Amount": "$2"}]'
    entities = _run(monkeypatch, engine, payload, ["Award amount"])
    assert [e["Award amount"] for e in entities] == ["$1", "$2"]
    assert entities[0]["extra"] == "kept"


def test_list_payload_with_no_matching_keys_fails_the_run(monkeypatch, engine):
    with pytest.raises(ExtractionError, match="none of the requested fields"):
        _run(monkeypatch, engine, '[{"nope": 1}]', KEYS)


# ---------------------------------------------------------------------------
# The envelope the prompts actually ask for
# ---------------------------------------------------------------------------
#
# Every variant in PROMPT_VARIANTS ends with "Return a JSON object with an
# 'entities' key containing a list of extracted objects", and
# _extract_fallback_json uses those prompts. So the *obedient* answer is an
# envelope. Reading it as "an object with none of the requested fields" is the
# original all-null bug wearing a different coat: same payload, still wrong.


def test_the_envelope_the_prompt_asks_for_extracts_normally(monkeypatch, engine):
    payload = (
        '{"entities": [{"Award Amount": "$500,000", "pi_name": "Jane Smith", '
        '"2 CFR part 200": "Yes"}]}'
    )
    out = _run(monkeypatch, engine, payload, KEYS)
    assert out == [{
        "Award amount": "$500,000",
        "PI Name": "Jane Smith",
        "2 CFR Part 200": "Yes",
    }]


def test_an_envelope_holding_a_bare_object_also_extracts(monkeypatch, engine):
    payload = '{"entities": {"Award Amount": "$500,000"}}'
    out = _run(monkeypatch, engine, payload, KEYS)
    assert out[0]["Award amount"] == "$500,000"


def test_an_envelope_with_many_entities_keeps_them_all(monkeypatch, engine):
    payload = (
        '{"entities": [{"Award Amount": "$1"}, {"Award Amount": "$2"}]}'
    )
    out = _run(monkeypatch, engine, payload, KEYS)
    assert [e["Award amount"] for e in out] == ["$1", "$2"]


def test_quotes_on_the_envelope_reach_the_sidecar(monkeypatch, engine):
    """The _sources block is the envelope's sibling, not the entity's — the
    unwrap must not lose it."""
    from app.services.extraction_sources import SOURCE_KEY

    payload = (
        '{"entities": [{"Award Amount": "$500,000"}], '
        '"_sources": {"Award Amount": "The award is $500,000."}}'
    )
    out = _run(monkeypatch, engine, payload, KEYS, capture_sources=True)
    assert out[0][SOURCE_KEY]["Award amount"]["quote"] == "The award is $500,000."


def test_the_quote_block_never_becomes_a_field(monkeypatch, engine):
    """Carried through as a value it reads as "a real value" to the router's
    all-null guard, and the run this PR exists to fail would pass."""
    from app.services.extraction_sources import SOURCE_KEY

    payload = (
        '{"entities": [{"Award Amount": null, "pi_name": null, '
        '"_sources": {"Award Amount": "irrelevant"}}]}'
    )
    out = _run(monkeypatch, engine, payload, KEYS, capture_sources=True)
    entity = out[0]
    assert "_sources" not in entity
    assert all(v is None for k, v in entity.items() if k != SOURCE_KEY)


def test_a_field_named_sources_is_not_filled_with_the_quote_block(monkeypatch, engine):
    payload = '{"entities": [{"Sources": "Appendix B"}], "_sources": {"x": "y"}}'
    out = _run(monkeypatch, engine, payload, ["Sources"])
    assert out[0]["Sources"] == "Appendix B"


def test_an_answer_about_something_else_still_fails(monkeypatch, engine):
    """The guard this PR adds must survive the unwrap."""
    payload = '{"entities": [{"Colour": "blue", "Shape": "round"}]}'
    with pytest.raises(ExtractionError):
        _run(monkeypatch, engine, payload, KEYS)


def test_an_empty_envelope_is_not_a_false_success(monkeypatch, engine):
    payload = '{"entities": []}'
    assert _run(monkeypatch, engine, payload, KEYS) == []


def test_quotes_inside_an_enveloped_object_reach_the_sidecar(monkeypatch, engine):
    """The list branch looks in the item *and* the envelope; the dict branch
    looked only in the envelope, which for this shape holds nothing but the
    "entities" key — so every quote was silently dropped and the values
    rendered untraced."""
    from app.services.extraction_sources import SOURCE_KEY

    payload = (
        '{"entities": {"Award Amount": "$500,000", '
        '"_sources": {"Award Amount": "The award is $500,000."}}}'
    )
    out = _run(monkeypatch, engine, payload, KEYS, capture_sources=True)
    assert out[0]["Award amount"] == "$500,000"
    assert out[0][SOURCE_KEY]["Award amount"]["quote"] == "The award is $500,000."


def test_remap_is_a_classmethod_not_an_accidental_instance_method(engine):
    """``_unwrap_entities_envelope`` carried ``@classmethod`` stacked on
    ``@staticmethod`` and ``_remap_to_requested_keys`` — which takes ``cls`` —
    carried no decorator at all. It worked only because CPython chained the
    two descriptors, which 3.13 removed. Bind both off the class."""
    body, envelope = ExtractionEngine._unwrap_entities_envelope({"entities": {"a": 1}})
    assert body == {"a": 1}
    assert envelope == {"entities": {"a": 1}}

    entity, matched, _ = ExtractionEngine._remap_to_requested_keys(
        {"Award Amount": "$1"}, ["Award amount"],
    )
    assert matched == 1
    assert entity == {"Award amount": "$1"}
