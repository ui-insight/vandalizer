"""Workflow runs stored before ``session_id`` existed must still load.

A 2025 row without the field made ``GET /api/mgmt/v1/workflows/runs`` answer
500 on production: Beanie validates every row a query returns, so one old
row failed the whole page.
"""

import pytest
from beanie.odm.settings.document import DocumentSettings
from bson import ObjectId

from app.models.workflow import WorkflowResult


@pytest.fixture(autouse=True)
def _beanie_settings(monkeypatch):
    # Building a Document reads its settings, which init_beanie normally sets.
    monkeypatch.setattr(WorkflowResult, "_document_settings", DocumentSettings(), raising=False)


def test_row_without_session_id_validates():
    row = {
        "_id": ObjectId("68f7d2f0a1b2c3d4e5f60718"),
        "workflow": ObjectId("68f7d2f0a1b2c3d4e5f60719"),
        "num_steps_completed": 2,
        "num_steps_total": 2,
        "status": "completed",
        "document_title": None,
    }

    result = WorkflowResult.model_validate(row)

    assert result.session_id == ""
    assert result.status == "completed"


def test_session_id_is_kept_when_present():
    result = WorkflowResult.model_validate({"session_id": "abc123", "status": "running"})

    assert result.session_id == "abc123"
