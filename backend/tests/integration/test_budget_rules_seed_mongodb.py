"""The Budget Analyzer's arithmetic rules reach a run, new install or upgrade (#1013 §4).

    INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_budget_rules_seed_mongodb.py
"""

import json
import os
from pathlib import Path

import pytest

from app.models.search_set import SearchSet
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
from scripts import seed_catalog

pytestmark = [
    pytest.mark.skipif(not os.environ.get("INTEGRATION_MONGODB"), reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests"),
    pytest.mark.asyncio(loop_scope="session"),
]

SEED = Path(__file__).resolve().parents[2] / "seeds" / "workflows" / "pre_award_budget_analyzer.json"
RULE_IDS = [
    "wf-budget-analyzer-direct-sum", "wf-budget-analyzer-total-sum",
    "wf-budget-analyzer-rate-applied", "wf-budget-analyzer-base-exclusions",
]


async def _seed():
    data = json.loads(SEED.read_text())
    lib = await seed_catalog.get_or_create_verified_library()
    return await seed_catalog.seed_workflow(data, data["_seed_meta"], lib, {})


async def _extraction_set() -> SearchSet:
    wf = await Workflow.find_one({"resource_config.seed_id": "wf-pre-award-budget-analyzer"})
    step = await WorkflowStep.get(wf.steps[0])
    for task_id in step.tasks:
        task = await WorkflowStepTask.get(task_id)
        if task.name == "Extraction":
            return await SearchSet.find_one({"uuid": task.data["search_set_uuid"]})
    raise AssertionError("no extraction task")


async def test_a_new_install_puts_the_rules_on_the_extraction_set(mongo_client):
    assert await _seed() == "created"
    ss = await _extraction_set()
    assert [r["id"] for r in ss.cross_field_rules] == RULE_IDS
    # Normalized like any saved rule, so the rules editor and counters work.
    assert all("eval_count" in r and r["enabled"] is True for r in ss.cross_field_rules)


async def test_an_upgrade_adds_missing_rules_and_keeps_an_admins_change(mongo_client):
    await _seed()
    ss = await _extraction_set()
    # An install from before 1.3.9 has no rules; an admin then adds one by
    # hand and disables it.
    ss.cross_field_rules = [{**ss.cross_field_rules[0], "enabled": False}]
    await ss.save()

    assert await _seed() == "updated"
    ss = await _extraction_set()
    assert [r["id"] for r in ss.cross_field_rules] == RULE_IDS
    assert ss.cross_field_rules[0]["enabled"] is False


async def test_a_run_hands_the_rules_to_the_extraction_step(mongo_client, sync_mongo):
    from app.tasks.workflow_tasks import build_steps_data

    await _seed()
    wf = sync_mongo.workflow.find_one({"resource_config.seed_id": "wf-pre-award-budget-analyzer"})
    steps_data, _outputs = build_steps_data(sync_mongo, wf, str(wf["_id"]), {"doc_uuids": []})
    extraction = next(
        t for s in steps_data for t in s["tasks"] if t["name"] == "Extraction"
    )
    assert [r["id"] for r in extraction["data"]["cross_field_rules"]] == RULE_IDS
