"""An extraction whose every field came back null is a failed run, not a
completed one with a green tick and nothing behind it."""

from app.routers.extractions import _entity_has_values


def test_all_null_entity_has_no_values():
    assert not _entity_has_values({"a": None, "b": None})


def test_source_sidecar_alone_is_not_a_value():
    assert not _entity_has_values(
        {"a": None, "_field_sources": {"a": {"quote": "x", "verified": True}}}
    )


def test_one_real_value_is_enough():
    assert _entity_has_values({"a": None, "b": "0"})


def test_empty_string_and_containers_are_not_values():
    assert not _entity_has_values({"a": "", "b": [], "c": {}})


def test_non_dict_is_not_a_result():
    assert not _entity_has_values(None)
    assert not _entity_has_values("text")
