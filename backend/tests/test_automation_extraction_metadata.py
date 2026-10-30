"""Folder-watch extraction automations hand the engine its field metadata in
the shape the engine reads (#1057).

``_run_automation_extraction`` built a dict keyed by field name; the engine
iterates a list of ``{"key": ...}`` entries, so any field with allowed values
or an optional flag raised TypeError, and descriptions never arrived.
"""

from unittest.mock import MagicMock, patch

from app.services.extraction_engine import ExtractionEngine
from app.tasks.document_tasks import _run_automation_extraction


def _db(items):
    db = MagicMock()
    db.search_set_item.find.return_value = items
    db.search_set.find_one.return_value = {"uuid": "ss-1"}
    db.system_config.find_one.return_value = {"available_models": [{"name": "m"}]}
    return db


def test_metadata_reaches_the_engine_as_a_list_with_descriptions():
    items = [
        {"searchphrase": "Status", "enum_values": ["Open", "Closed"], "is_optional": True},
        {"searchphrase": "Total Direct Costs", "description": "Also labelled Direct-cost total."},
    ]
    captured = {}

    def fake_extract(self, **kwargs):
        captured.update(kwargs)
        # The engine's own first step with this argument.
        {m["key"]: m for m in kwargs["field_metadata"]}
        return {"Status": "Open"}

    with (
        patch.object(ExtractionEngine, "__init__", lambda self, **kw: None),
        patch.object(ExtractionEngine, "extract", fake_extract),
        patch("app.services.search_set_service.effective_extraction_config", return_value={}),
        patch("app.tasks.document_tasks._process_extraction_outputs"),
    ):
        _run_automation_extraction(_db(items), {"_id": "a1", "name": "watch"}, "ss-1", {"_id": "d1", "uuid": "d1", "raw_text": "text"})

    assert captured["field_metadata"] == [
        {"key": "Status", "is_optional": True, "enum_values": ["Open", "Closed"], "description": None},
        {"key": "Total Direct Costs", "is_optional": False, "enum_values": [], "description": "Also labelled Direct-cost total."},
    ]
