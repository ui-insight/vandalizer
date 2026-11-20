"""An extraction step's fields, whichever way they were stored.

Seeded catalog workflows keep them as ``searchphrases`` (one comma-separated
string). The engine runs those, but the editor, chat's workflow description and
the diagnostics read only ``extractions`` and saw a step with no fields.
"""

import json
from pathlib import Path

import pytest

from app.services.workflow_diagnostics import _extraction_fields, inline_extraction_fields

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "workflows"


@pytest.mark.parametrize("data, expected", [
    ({"searchphrases": "PI Name, Sponsor/Funder,  Award Number ,"}, ["PI Name", "Sponsor/Funder", "Award Number"]),
    ({"searchphrases": ["A", "", " B "]}, ["A", "B"]),
    ({"keys": ["Start Date", " End Date "]}, ["Start Date", "End Date"]),
    ({"extractions": ["Award Number", {"key": " F&A Rate ", "description": "x"}]}, ["Award Number", "F&A Rate"]),
    # The engine's order: searchphrases, then keys, then extractions.
    ({"searchphrases": "Old", "keys": ["Older"], "extractions": ["New"]}, ["Old"]),
    ({"searchphrases": " , ", "keys": [], "extractions": ["New"]}, ["New"]),
    ({}, []),
    ({"extractions": None, "searchphrases": 5, "keys": {}}, []),
])
def test_fields_are_read_in_every_stored_form(data, expected):
    assert inline_extraction_fields(data) == expected
    assert _extraction_fields(data) == expected


def test_same_order_of_preference_as_the_engine():
    import inspect

    from app.services.workflow_engine import ExtractionNode

    source = inspect.getsource(ExtractionNode.process)
    order = [source.index(f'"{key}"') for key in ("searchphrases", "keys", "extractions")]
    assert order == sorted(order)


def test_every_seeded_extraction_step_shows_its_fields():
    checked = 0
    for path in sorted(SEEDS.glob("*.json")):
        data = json.loads(path.read_text())
        for item in data.get("items") or [data]:
            for step in item.get("steps", []):
                for task in step.get("tasks", []):
                    if task.get("name") == "Extraction" and not task.get("data", {}).get("search_set_uuid"):
                        checked += 1
                        assert inline_extraction_fields(task["data"]), f"{path.name}: {step.get('name')}"
    assert checked > 0


def test_chat_describes_a_step_stored_the_older_way():
    from app.services import chat_workflow_tools

    source = Path(chat_workflow_tools.__file__).read_text()
    assert "inline_extraction_fields(data)" in source
    assert 'data.get("extractions")' not in source
