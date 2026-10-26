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


# --- #1013 §5: validation evidence and starter tiers -------------------------

async def test_an_upgrade_never_rewrites_a_users_copy(mongo_client):
    # A copy made from the library keeps the catalog seed_id.
    copy = Workflow(
        name="My budget review", user_id="user-1", space="global", steps=[],
        resource_config={"seed_id": "wf-pre-award-budget-analyzer"},
        validation_plan=[{"id": "mine", "name": "Our own check", "category": "content", "description": "x"}],
    )
    await copy.insert()
    assert await _seed() == "created"
    copy = await Workflow.get(copy.id)
    assert copy.name == "My budget review"
    assert [c["id"] for c in copy.validation_plan] == ["mine"]
    assert copy.validation_inputs == []


async def test_an_upgrade_retracts_an_unmeasured_author_tier(mongo_client):
    from app.models.verification import VerifiedItemMetadata

    await _seed()
    wf = await Workflow.find_one({"resource_config.seed_id": "wf-pre-award-budget-analyzer", "user_id": "system"})
    meta = await VerifiedItemMetadata.find_one({"item_kind": "workflow", "item_id": str(wf.id)})
    meta.quality_tier = "excellent"  # what catalogs before 1.3.10 asserted
    await meta.save()

    await _seed()
    meta = await VerifiedItemMetadata.find_one({"item_kind": "workflow", "item_id": str(wf.id)})
    assert meta.quality_tier is None
    # The seeded plan and the example budget arrived with the upgrade.
    wf = await Workflow.get(wf.id)
    assert len(wf.validation_plan) >= 4
    assert "overstated by $5,000" in wf.validation_inputs[0]["label"]


async def test_a_tier_measured_on_this_install_is_kept(mongo_client):
    from app.models.verification import VerifiedItemMetadata

    await _seed()
    wf = await Workflow.find_one({"resource_config.seed_id": "wf-pre-award-budget-analyzer", "user_id": "system"})
    meta = await VerifiedItemMetadata.find_one({"item_kind": "workflow", "item_id": str(wf.id)})
    meta.quality_tier, meta.quality_score = "good", 78.0
    await meta.save()

    await _seed()
    meta = await VerifiedItemMetadata.find_one({"item_kind": "workflow", "item_id": str(wf.id)})
    assert (meta.quality_tier, meta.quality_score) == ("good", 78.0)


# --- #1057: field descriptions map ordinary budget labels ---------------------

async def _items_by_name():
    from app.models.search_set import SearchSetItem

    ss = await _extraction_set()
    items = await SearchSetItem.find(SearchSetItem.searchset == ss.uuid).to_list()
    return {i.searchphrase: i for i in items}


async def test_a_new_install_describes_the_budget_fields(mongo_client):
    assert await _seed() == "created"
    items = await _items_by_name()
    assert "Direct-cost total" in items["Total Direct Costs"].description
    assert "Total request" in items["Total Project Cost"].description
    assert items["Fringe Benefit Rate"].description is None  # not every field needs one


async def test_an_upgrade_adds_descriptions_and_keeps_an_admins(mongo_client):
    await _seed()
    items = await _items_by_name()
    # An install from before 1.3.13 has none; an admin has since written one.
    for item in items.values():
        item.description = None
        await item.save()
    items["Subcontracts"].description = "Our own wording"
    await items["Subcontracts"].save()

    assert await _seed() == "updated"
    items = await _items_by_name()
    assert "Direct-cost total" in items["Total Direct Costs"].description
    assert items["Subcontracts"].description == "Our own wording"


async def test_a_run_hands_the_descriptions_to_the_extraction_step(mongo_client, sync_mongo):
    from app.tasks.workflow_tasks import build_steps_data

    await _seed()
    wf = sync_mongo.workflow.find_one({"resource_config.seed_id": "wf-pre-award-budget-analyzer"})
    steps_data, _outputs = build_steps_data(sync_mongo, wf, str(wf["_id"]), {"doc_uuids": []})
    extraction = next(
        t for s in steps_data for t in s["tasks"] if t["name"] == "Extraction"
    )
    meta = {m["key"]: m for m in extraction["data"]["field_metadata"]}
    assert "Total request" in meta["Total Project Cost"]["description"]
