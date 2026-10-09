"""Shipped guidance must state the 2024 Uniform Guidance thresholds (#996).

The 2024 revision of 2 CFR 200 (awards on or after October 1, 2024) raised
the equipment threshold to the lesser of the capitalization level or $10,000
and the subaward portion of the MTDC base to the first $50,000. Catalog
workflows and the onboarding demo still stated $5,000 and $25,000 while the
bundled 2 CFR 200 text said otherwise. The figures may still be *named* as
the earlier thresholds, but never stated as the rule.
"""

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import domain_prompts, onboarding_service
from scripts import seed_catalog

SEEDS = Path(__file__).resolve().parents[1] / "seeds"
STALE = re.compile(
    r"\$5,?000\b|\$5K\b|\$25,?000\b[^.\n]{0,40}subaward|subaward[^.\n]{0,40}\$25,?000\b|\$25K\b",
    re.I,
)


def _stale_rule_statements(text: str) -> list[str]:
    """Old figures in ``text`` that aren't introduced as the earlier thresholds."""
    found = []
    for m in STALE.finditer(text):
        before = text[max(0, m.start() - 120):m.start()]
        if "earlier thresholds" in before:
            continue
        found.append(text[max(0, m.start() - 60):m.end() + 20])
    return found


def _budget_prompts():
    for path in sorted((SEEDS / "workflows").glob("*.json")):
        data = json.loads(path.read_text())
        if path.stem == "compliance_coi_review":
            continue  # $5,000 there is the PHS FCOI significant-interest threshold (42 CFR 50.603)
        for step in data["items"][0]["steps"]:
            for task in step["tasks"]:
                prompt = task.get("data", {}).get("prompt")
                if prompt and re.search(r"MTDC|indirect cost|equipment", prompt, re.I):
                    yield f"{path.stem}/{step['name']}", prompt


_PROMPTS = list(_budget_prompts())


@pytest.mark.parametrize("where,prompt", _PROMPTS, ids=[w for w, _ in _PROMPTS])
def test_seed_workflow_prompts_state_current_thresholds(where, prompt):
    assert _stale_rule_statements(prompt) == [], where


def test_the_mtdc_workflows_take_the_thresholds_from_the_regulation_text():
    """Since #1009 the figures come from the bundled 2 CFR 200 passages the
    workflow retrieves, not from the prompt: a figure written into a prompt is
    how $5,000 / $25,000 outlived the 2024 revision."""
    prompts = dict(_budget_prompts())
    for prefix in ("financial_fa_rate_validator/", "pre_award_budget_analyzer/"):
        text = next(p for w, p in prompts.items() if w.startswith(prefix))
        assert "2 CFR 200.1" in text
        assert "$10,000" not in text and "$50,000" not in text
        seed = json.loads((SEEDS / "workflows" / f"{prefix[:-1]}.json").read_text())
        kb_tasks = [t for s in seed["items"][0]["steps"] for t in s["tasks"] if t["name"] == "KnowledgeBaseQuery"]
        assert [t["data"]["kb_seed_id"] for t in kb_tasks] == ["kb-2cfr200"]


def test_demo_pappg_text_and_domain_prompt_state_current_thresholds():
    texts = [s["content"] for s in onboarding_service._PAPPG_SOURCES]
    texts += [v for v in vars(domain_prompts).values() if isinstance(v, str)]
    assert [hit for t in texts for hit in _stale_rule_statements(t)] == []
    budget_chapter = onboarding_service._PAPPG_SOURCES[0]["content"]
    assert "$10,000" in budget_chapter and "$50,000" in budget_chapter


def test_a_seed_never_lists_its_current_prompt_as_superseded():
    for path in sorted((SEEDS / "workflows").glob("*.json")):
        data = json.loads(path.read_text())
        superseded = set(data["_seed_meta"].get("superseded_prompt_sha256") or [])
        for step in data["items"][0]["steps"]:
            for task in step["tasks"]:
                prompt = task.get("data", {}).get("prompt")
                if prompt:
                    assert hashlib.sha256(prompt.encode()).hexdigest() not in superseded, path.stem


# --- seeder: correcting prompts already installed ---------------------------

OLD = "Check equipment over $5,000."
NEW = "Check equipment at or above the lesser of the capitalization level or $10,000."


def _installed(prompt, *, owner="system", step_name="Budget Analysis"):
    task = SimpleNamespace(name="Prompt", data={"prompt": prompt, "input_source": "step_input"}, save=AsyncMock())
    step = SimpleNamespace(name=step_name, tasks=["t1"])
    wf = SimpleNamespace(user_id=owner, steps=["s1"])
    return wf, step, task


SEED_ITEM = {"steps": [{"name": "Budget Analysis", "tasks": [{"name": "Prompt", "data": {"prompt": NEW}}]}]}
META = {"superseded_prompt_sha256": [hashlib.sha256(OLD.encode()).hexdigest()]}


async def _patch(wf, step, task, meta=META):
    with patch.object(seed_catalog.WorkflowStep, "get", AsyncMock(return_value=step)), \
         patch.object(seed_catalog.WorkflowStepTask, "get", AsyncMock(return_value=task)):
        return await seed_catalog._patch_superseded_prompts(wf, SEED_ITEM, meta)


@pytest.mark.asyncio
async def test_an_installed_superseded_prompt_is_replaced():
    wf, step, task = _installed(OLD)
    assert await _patch(wf, step, task) == 1
    assert task.data == {"prompt": NEW, "input_source": "step_input"}
    task.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_edited_prompt_is_left_alone():
    wf, step, task = _installed(OLD + " Also check our local policy.")
    assert await _patch(wf, step, task) == 0
    task.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_users_copy_of_a_catalog_workflow_is_left_alone():
    wf, step, task = _installed(OLD, owner="user-123")
    assert await _patch(wf, step, task) == 0
    assert task.data["prompt"] == OLD


@pytest.mark.asyncio
async def test_a_step_the_seed_no_longer_has_is_left_alone():
    wf, step, task = _installed(OLD, step_name="Renamed Step")
    assert await _patch(wf, step, task) == 0


@pytest.mark.asyncio
async def test_a_seed_without_superseded_prompts_reads_nothing():
    wf, step, task = _installed(OLD)
    with patch.object(seed_catalog.WorkflowStep, "get", AsyncMock()) as get:
        assert await seed_catalog._patch_superseded_prompts(wf, SEED_ITEM, {}) == 0
    get.assert_not_awaited()


# --- onboarding demo: re-indexing outdated inline sources -------------------

def _source(content, *, url="https://new.nsf.gov/policies/pappg#x", status="ready"):
    return SimpleNamespace(uuid="src-1", url=url, status=status, content=content, chunk_count=3, save=AsyncMock())


async def _refresh(source):
    dm = MagicMock()
    dm.replace_kb_source.return_value = 4
    find_one = AsyncMock(return_value=source)
    with patch.object(onboarding_service, "_PAPPG_SOURCES", [{"name": "Budget", "content": "new text"}]), \
         patch.object(onboarding_service, "KnowledgeBaseSource", MagicMock(find_one=find_one)), \
         patch("app.services.document_manager.get_document_manager", return_value=dm), \
         patch.object(onboarding_service.logger, "warning") as warned:
        replaced = await onboarding_service._refresh_stale_pappg_sources(SimpleNamespace(uuid="kb-1"))
    find_one.assert_awaited_once()
    warned.assert_not_called()
    return replaced, dm


@pytest.mark.asyncio
async def test_an_outdated_demo_source_is_reindexed():
    source = _source("old text")
    replaced, dm = await _refresh(source)
    assert replaced == 1
    dm.replace_kb_source.assert_called_once_with("kb-1", "src-1", "Budget", "new text")
    assert (source.content, source.chunk_count) == ("new text", 4)
    source.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_current_demo_source_is_not_reindexed():
    replaced, dm = await _refresh(_source("new text"))
    assert replaced == 0
    dm.replace_kb_source.assert_not_called()


@pytest.mark.asyncio
async def test_a_catalog_source_with_the_same_title_is_not_touched():
    replaced, dm = await _refresh(_source("old text", url="https://www.nsf.gov/pappg"))
    assert replaced == 0
    dm.replace_kb_source.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_reindex_keeps_the_old_source_and_does_not_raise():
    source = _source("old text")
    dm = MagicMock()
    dm.replace_kb_source.side_effect = RuntimeError("chroma down")
    with patch.object(onboarding_service, "_PAPPG_SOURCES", [{"name": "Budget", "content": "new text"}]), \
         patch.object(onboarding_service, "KnowledgeBaseSource", MagicMock(find_one=AsyncMock(return_value=source))), \
         patch("app.services.document_manager.get_document_manager", return_value=dm):
        assert await onboarding_service._refresh_stale_pappg_sources(SimpleNamespace(uuid="kb-1")) == 0
    assert source.content == "old text"
    source.save.assert_not_awaited()
