"""Catalog budget and compliance workflows read their regulation KB (#1009).

No seeded workflow queried a knowledge base: each checked documents against
rules its prompt stated, which is how the pre-2024 $5,000 / $25,000
thresholds shipped until #996. Six now retrieve the governing regulation's
text alongside their extraction and cite the section they apply. A seed
names the KB by seed id; ``attach_catalog_kb_queries`` links it to the
install's KB after KBs are seeded, on fresh and existing installs alike.
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import seed_catalog

SEEDS = Path(__file__).resolve().parents[1] / "seeds"
WIRED = {
    "financial_fa_rate_validator": "kb-2cfr200",
    "pre_award_budget_analyzer": "kb-2cfr200",
    "financial_cost_allocation": "kb-2cfr200",
    "compliance_coi_review": "kb-fcoi",
    "compliance_export_control": "kb-export-control",
    "compliance_irb_protocol": "kb-common-rule",
}
KB_SEED_IDS = {
    json.loads(p.read_text())["_seed_meta"]["seed_id"] for p in (SEEDS / "knowledge_bases").glob("*.json")
}


def _seed(name):
    return json.loads((SEEDS / "workflows" / f"{name}.json").read_text())


@pytest.mark.parametrize("name,kb", WIRED.items())
def test_the_workflow_reads_its_regulation_beside_the_extraction(name, kb):
    item = _seed(name)["items"][0]
    first = item["steps"][0]
    assert [t["name"] for t in first["tasks"]] == ["Extraction", "KnowledgeBaseQuery"]
    query = first["tasks"][1]["data"]
    assert query["kb_seed_id"] == kb and kb in KB_SEED_IDS
    assert query["query"].strip() and query["mode"] == "passages"


@pytest.mark.parametrize("name", WIRED)
def test_the_prompt_applies_and_cites_the_passages_without_figures_from_memory(name):
    seed = _seed(name)
    prompt = seed["items"][0]["steps"][1]["tasks"][0]["data"]["prompt"]
    assert "cite its section" in prompt
    assert "Never fill in a threshold, rate or requirement from memory" in prompt
    assert not re.search(r"\$\d", prompt), "thresholds come from the regulation passages"
    assert seed["_seed_meta"]["superseded_prompt_sha256"], "existing installs must receive the new prompt"
    checks = seed["items"][0]["validation_plan"]
    assert any(c["name"] == "Cites the regulation it applied" for c in checks)


def test_the_coi_review_no_longer_states_the_old_five_percent_test():
    """$5,000/5% was NIH's pre-2011 rule; 42 CFR 50.603 has no percentage."""
    prompt = _seed("compliance_coi_review")["items"][0]["steps"][1]["tasks"][0]["data"]["prompt"]
    assert "5%" not in prompt and "50.603" in prompt


# --- attach_catalog_kb_queries --------------------------------------------

def _write_seed(tmp_path, *, with_query=True):
    tasks = [{"name": "Extraction", "data": {"searchphrases": "Rate"}}]
    if with_query:
        tasks.append({"name": "KnowledgeBaseQuery", "data": {"kb_seed_id": "kb-2cfr200", "query": "MTDC", "mode": "passages", "k": 8}})
    seed = {"_seed_meta": {"seed_id": "wf-fa"}, "items": [{"steps": [
        {"name": "Extract Rate Data", "tasks": tasks},
        {"name": "Rate Validation", "tasks": [{"name": "Prompt", "data": {"prompt": "p"}}]},
    ]}]}
    (tmp_path / "fa.json").write_text(json.dumps(seed))


def _installed(existing_tasks):
    step = SimpleNamespace(name="Extract Rate Data", tasks=[t.id for t in existing_tasks], save=AsyncMock())
    wf = SimpleNamespace(steps=["s1"])
    by_id = {t.id: t for t in existing_tasks}
    return wf, step, by_id


def _task(name, data, tid):
    return SimpleNamespace(id=tid, name=name, data=dict(data), save=AsyncMock())


async def _attach(tmp_path, wf, step, by_id, kb, created):
    def make_task(name, data):
        t = SimpleNamespace(id="new-task", name=name, data=data, insert=AsyncMock())
        created.append(t)
        return t

    with patch.object(seed_catalog, "Workflow", MagicMock(find_one=AsyncMock(return_value=wf))) as W, \
         patch.object(seed_catalog, "WorkflowStep", MagicMock(get=AsyncMock(return_value=step))), \
         patch.object(seed_catalog, "KnowledgeBase", MagicMock(find_one=AsyncMock(return_value=kb))), \
         patch.object(seed_catalog, "WorkflowStepTask", MagicMock(side_effect=make_task, get=AsyncMock(side_effect=lambda i: by_id.get(i)))):
        changed = await seed_catalog.attach_catalog_kb_queries(tmp_path)
    return changed, W.find_one.await_args


@pytest.mark.asyncio
async def test_a_catalog_workflow_gains_the_lookup_linked_to_this_installs_kb(tmp_path):
    _write_seed(tmp_path)
    extraction = _task("Extraction", {"search_set_uuid": "ss"}, "t-ext")
    wf, step, by_id = _installed([extraction])
    created = []
    changed, lookup = await _attach(tmp_path, wf, step, by_id, SimpleNamespace(uuid="kb-uuid-here"), created)
    assert changed == 1
    assert step.tasks == ["t-ext", "new-task"]
    assert created[0].data["kb_uuid"] == "kb-uuid-here" and created[0].data["kb_seed_id"] == "kb-2cfr200"
    step.save.assert_awaited_once()
    # Only the catalog-owned workflow, never a user's copy that kept the seed id.
    assert lookup.args[0] == {"resource_config.seed_id": "wf-fa", "user_id": "system"}


@pytest.mark.asyncio
async def test_a_lookup_pointing_at_an_old_kb_is_relinked_not_duplicated(tmp_path):
    _write_seed(tmp_path)
    stale = _task("KnowledgeBaseQuery", {"kb_seed_id": "kb-2cfr200", "kb_uuid": "gone"}, "t-kb")
    wf, step, by_id = _installed([_task("Extraction", {}, "t-ext"), stale])
    created = []
    changed, _ = await _attach(tmp_path, wf, step, by_id, SimpleNamespace(uuid="kb-new"), created)
    assert changed == 1 and not created
    assert stale.data["kb_uuid"] == "kb-new"
    stale.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_linked_lookup_is_left_alone(tmp_path):
    _write_seed(tmp_path)
    linked = _task("KnowledgeBaseQuery", {"kb_seed_id": "kb-2cfr200", "kb_uuid": "kb-1"}, "t-kb")
    wf, step, by_id = _installed([_task("Extraction", {}, "t-ext"), linked])
    changed, _ = await _attach(tmp_path, wf, step, by_id, SimpleNamespace(uuid="kb-1"), [])
    assert changed == 0
    linked.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_without_the_kb_installed_the_workflow_is_left_as_it_was(tmp_path):
    """A lookup with no KB stops every run, so none is added."""
    _write_seed(tmp_path)
    wf, step, by_id = _installed([_task("Extraction", {}, "t-ext")])
    created = []
    changed, _ = await _attach(tmp_path, wf, step, by_id, None, created)
    assert changed == 0 and not created and step.tasks == ["t-ext"]


@pytest.mark.asyncio
async def test_a_seed_without_lookups_reads_nothing(tmp_path):
    _write_seed(tmp_path, with_query=False)
    with patch.object(seed_catalog, "Workflow", MagicMock(find_one=AsyncMock())) as W:
        assert await seed_catalog.attach_catalog_kb_queries(tmp_path) == 0
    W.find_one.assert_not_awaited()


def test_new_installs_skip_the_lookup_until_kbs_exist():
    assert seed_catalog._is_catalog_kb_query({"name": "KnowledgeBaseQuery", "data": {"kb_seed_id": "kb-fcoi"}})
    assert not seed_catalog._is_catalog_kb_query({"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "x"}})
    assert not seed_catalog._is_catalog_kb_query({"name": "Extraction", "data": {"kb_seed_id": "kb-fcoi"}})
