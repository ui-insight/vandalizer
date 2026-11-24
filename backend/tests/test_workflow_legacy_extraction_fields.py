"""An extraction step's fields, whichever way they were stored.

Seeded catalog workflows keep them as ``searchphrases`` (one comma-separated
string). The engine ran those, but the editor, chat's workflow description, the
diagnostics and the validation plan read only ``extractions`` and saw a step
with no fields. All of them now read the fields through one function, so what
is shown is what runs.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_workflow_tools import _describe_step
from app.services.workflow_diagnostics import (
    _extraction_fields,
    inline_extraction_field_details,
    inline_extraction_fields,
    use_linked_set_fields,
)
from app.services.workflow_engine import ExtractionNode
from app.services.workflow_service import _extraction_plan_fields

SEEDS = Path(__file__).resolve().parents[1] / "seeds" / "workflows"

# The same rows are in frontend/src/lib/extractionFields.test.ts.
CASES = [
    # Every stored form.
    ({"searchphrases": "PI Name, Sponsor/Funder,  Award Number ,"}, ["PI Name", "Sponsor/Funder", "Award Number"]),
    ({"searchphrases": ["A", "", " B "]}, ["A", "B"]),
    ({"keys": ["Start Date", " End Date "]}, ["Start Date", "End Date"]),
    ({"keys": "A, B"}, ["A", "B"]),
    ({"extractions": ["Award Number", "F&A Rate"]}, ["Award Number", "F&A Rate"]),
    ({"extractions": "A, B"}, ["A", "B"]),
    # Order of preference: searchphrases, then keys, then extractions.
    ({"searchphrases": "Old", "keys": ["Older"], "extractions": ["New"]}, ["Old"]),
    ({"searchphrases": "", "keys": ["Keys"], "extractions": ["New"]}, ["Keys"]),
    ({"keys": ["Older"], "extractions": ["New"]}, ["Older"]),
    # A list with nothing but blanks gives way to the next one.
    ({"searchphrases": " , ", "keys": [], "extractions": ["New"]}, ["New"]),
    ({"searchphrases": [""], "extractions": ["New"]}, ["New"]),
    ({"keys": [" "], "extractions": ["New"]}, ["New"]),
    # Blank entries are dropped; duplicates are kept as stored.
    ({"searchphrases": "A,,B,"}, ["A", "B"]),
    ({"searchphrases": ["A", ""], "extractions": ["New"]}, ["A"]),
    ({"extractions": ["A", "a", "A"]}, ["A", "a", "A"]),
    # A field stored with a description is read by its name.
    ({"extractions": [{"key": " F&A Rate ", "description": "x"}, "B"]}, ["F&A Rate", "B"]),
    ({"searchphrases": [{"key": "A"}]}, ["A"]),
    ({"extractions": [{"description": "no name"}, {"key": ""}, {"key": {"key": "nested"}}, "B"]}, ["B"]),
    # A number becomes its text; anything else that is not a name is skipped.
    ({"extractions": [5, None, "B"]}, ["5", "B"]),
    ({"searchphrases": [5, "A"]}, ["5", "A"]),
    ({"extractions": [2.5, 3.0, True, False, ["x"], "B"]}, ["2.5", "3", "B"]),
    # A value that is not a list or text holds no fields.
    ({"searchphrases": 5, "extractions": ["N"]}, ["N"]),
    ({"searchphrases": {"a": 1}, "extractions": ["N"]}, ["N"]),
    ({"extractions": None, "searchphrases": 5, "keys": {}}, []),
    ({}, []),
]


def _run(data: dict) -> list[str]:
    """The field names the engine hands to the extractor for this task."""
    with patch("app.services.workflow_engine.data_extraction_model") as extractor:
        extractor.return_value = {"raw": [], "formatted": ""}
        ExtractionNode({"model": "test-model", **data}).process({"output": "text", "step_name": "Prompt"})
    return extractor.call_args[0][1]


@pytest.mark.parametrize("data, expected", CASES)
def test_fields_are_read_in_every_stored_form(data, expected):
    assert inline_extraction_fields(data) == expected
    assert _extraction_fields(data) == expected


@pytest.mark.parametrize("data, expected", CASES)
def test_the_engine_runs_the_fields_that_are_shown(data, expected):
    assert _run(data) == expected


def test_a_field_stored_with_a_description_keeps_it():
    data = {"extractions": [
        "Plain",
        {"key": " Status ", "description": "Award status", "is_optional": True, "enum_values": ["Open", "Closed"]},
    ]}
    assert inline_extraction_field_details(data) == [
        {"key": "Plain"},
        {"key": "Status", "description": "Award status", "is_optional": True, "enum_values": ["Open", "Closed"]},
    ]


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


# ---------------------------------------------------------------------------
# Chat's description of a workflow
# ---------------------------------------------------------------------------

def _step(data: dict) -> dict:
    return {"name": "Pull fields", "tasks": [{"name": "Extraction", "data": data}]}


def test_chat_describes_a_step_stored_the_older_way():
    described = _describe_step(_step({"searchphrases": "PI Name, Award Number"}))
    assert described["extractions"] == ["PI Name", "Award Number"]
    assert "extraction_set_uuid" not in described


def test_chat_describes_a_linked_step_by_its_set_only():
    described = _describe_step(_step({"search_set_uuid": "u", "searchphrases": "Old", "extractions": ["Older"]}))
    assert described["extraction_set_uuid"] == "u"
    assert "extractions" not in described


# ---------------------------------------------------------------------------
# A linked saved set's fields are the ones that run
# ---------------------------------------------------------------------------

def test_a_linked_set_replaces_every_list_on_the_step():
    data = {"search_set_uuid": "u", "searchphrases": "Old", "keys": ["Older"], "extractions": ["Oldest"], "name": "x"}
    use_linked_set_fields(data, ["Name", "Date"])
    assert data == {"search_set_uuid": "u", "keys": ["Name", "Date"], "name": "x"}
    assert _run(data) == ["Name", "Date"]


def test_a_run_uses_the_linked_set_not_an_old_field_line():
    from app.tasks.workflow_tasks import build_steps_data

    db = MagicMock()
    db.workflow_step.find_one.return_value = {"_id": "s1", "name": "Extract", "tasks": ["t1"]}
    db.workflow_step_task.find_one.return_value = {
        "_id": "t1", "name": "Extraction",
        "data": {"search_set_uuid": "u", "searchphrases": "Old", "extractions": ["Older"]},
    }
    db.search_set.find_one.return_value = {"uuid": "u"}
    db.search_set_item.find.return_value = [{"searchphrase": "Name"}, {"searchphrase": "Date"}]
    db.smart_document.find_one.return_value = None

    steps_data, _ = build_steps_data(db, {"steps": ["s1"], "input_config": {}}, "wf1", {"doc_uuids": []})

    task_data = steps_data[1]["tasks"][0]["data"]
    assert "searchphrases" not in task_data and "extractions" not in task_data
    assert task_data["keys"] == ["Name", "Date"]
    assert _run(task_data) == ["Name", "Date"]


@patch("app.services.workflow_service.SearchSetItem")
@patch("app.services.workflow_service.celery_app")
@patch("app.services.workflow_service.get_user_model_name", new_callable=AsyncMock, return_value="test-model")
async def test_a_step_test_uses_the_linked_set_not_an_old_field_line(_model, celery, items):
    from app.services import workflow_service

    items.find.return_value.to_list = AsyncMock(return_value=[
        MagicMock(searchphrase="Name"), MagicMock(searchphrase="Date"),
    ])
    await workflow_service.test_step("Extraction", {"search_set_uuid": "u", "searchphrases": "Old"}, [], "u1")

    sent = celery.send_task.call_args[1]["kwargs"]["task_data"]
    assert "searchphrases" not in sent
    assert sent["keys"] == ["Name", "Date"]
    assert _run(sent) == ["Name", "Date"]


# ---------------------------------------------------------------------------
# The validation plan
# ---------------------------------------------------------------------------

def test_the_validation_plan_describes_a_step_stored_the_older_way():
    assert _extraction_plan_fields({"searchphrases": "PI Name, Award Number"}) == [
        {"key": "PI Name"}, {"key": "Award Number"},
    ]
    assert _extraction_plan_fields({"keys": ["Start Date"]}) == [{"key": "Start Date"}]


def test_the_validation_plan_keeps_a_field_s_description_and_allowed_values():
    assert _extraction_plan_fields({"extractions": [
        "Plain",
        {"key": "Status", "description": "Award status", "is_optional": True, "enum_values": ["Open", "Closed"]},
        {"key": "Notes"},
        {"key": "Amount", "description": None, "enum_values": []},
    ]}) == [
        {"key": "Plain"},
        {"key": "Status", "description": "Award status", "optional": True, "allowed_values": ["Open", "Closed"]},
        {"key": "Notes"},
        {"key": "Amount", "description": ""},
    ]
