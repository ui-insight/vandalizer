"""Service layer for the Vandal Workflow Architect certification system."""

import datetime
from typing import Optional

from beanie import PydanticObjectId

from app.models.certification import CertificationProgress
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask, WorkflowResult
from app.models.search_set import SearchSet, SearchSetItem

# ---------------------------------------------------------------------------
# XP & Level constants
# ---------------------------------------------------------------------------

MODULE_XP = {
    "foundations": 100,
    "extraction_engine": 150,
    "multi_step": 150,
    "advanced_nodes": 200,
    "output_delivery": 200,
    "validation_qa": 250,
    "batch_processing": 250,
    "governance": 300,
}

LEVELS = [
    ("novice", 0),
    ("apprentice", 100),
    ("builder", 250),
    ("designer", 400),
    ("engineer", 600),
    ("specialist", 800),
    ("expert", 1050),
    ("master", 1300),
    ("architect", 1600),
]

MODULE_ORDER = [
    "foundations",
    "extraction_engine",
    "multi_step",
    "advanced_nodes",
    "output_delivery",
    "validation_qa",
    "batch_processing",
    "governance",
]


def _compute_level(xp: int) -> str:
    level = "novice"
    for name, threshold in LEVELS:
        if xp >= threshold:
            level = name
    return level


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_progress(user_id: str) -> CertificationProgress:
    prog = await CertificationProgress.find_one(CertificationProgress.user_id == user_id)
    if not prog:
        prog = CertificationProgress(user_id=user_id)
        await prog.insert()
    return prog


async def get_progress_dict(user_id: str) -> dict:
    prog = await get_progress(user_id)
    return {
        "id": str(prog.id),
        "user_id": prog.user_id,
        "modules": prog.modules,
        "total_xp": prog.total_xp,
        "level": prog.level,
        "certified": prog.certified,
        "certified_at": prog.certified_at.isoformat() if prog.certified_at else None,
        "streak_days": prog.streak_days,
        "last_activity_date": prog.last_activity_date,
    }


# ---------------------------------------------------------------------------
# Streak tracking
# ---------------------------------------------------------------------------

def _update_streak(prog: CertificationProgress) -> None:
    today = datetime.date.today().isoformat()
    if prog.last_activity_date == today:
        return
    if prog.last_activity_date:
        last = datetime.date.fromisoformat(prog.last_activity_date)
        diff = (datetime.date.today() - last).days
        if diff == 1:
            prog.streak_days += 1
        elif diff > 1:
            prog.streak_days = 1
    else:
        prog.streak_days = 1
    prog.last_activity_date = today


# ---------------------------------------------------------------------------
# Module validation
# ---------------------------------------------------------------------------

async def validate_module(user_id: str, module_id: str) -> dict:
    """Check a user's actual data against module completion criteria.

    Returns {passed: bool, stars: int, checks: [{name, passed, detail}]}
    """
    if module_id not in MODULE_XP:
        return {"passed": False, "stars": 0, "checks": [{"name": "invalid", "passed": False, "detail": "Unknown module"}]}

    prog = await get_progress(user_id)

    # Check prerequisites (must complete prior modules)
    idx = MODULE_ORDER.index(module_id)
    if idx > 0:
        prev = MODULE_ORDER[idx - 1]
        prev_data = prog.modules.get(prev, {})
        if not prev_data.get("completed"):
            return {
                "passed": False,
                "stars": 0,
                "checks": [{"name": "prerequisite", "passed": False, "detail": f"Complete the previous module first"}],
            }

    validator = _VALIDATORS.get(module_id)
    if not validator:
        return {"passed": False, "stars": 0, "checks": []}

    return await validator(user_id)


async def complete_module(user_id: str, module_id: str) -> dict:
    """Mark a module complete after validation passes. Returns updated progress."""
    validation = await validate_module(user_id, module_id)
    if not validation["passed"]:
        return {"error": "Validation did not pass", "validation": validation}

    prog = await get_progress(user_id)
    module_data = prog.modules.get(module_id, {})
    attempts = module_data.get("attempts", 0) + 1
    already_completed = module_data.get("completed", False)

    stars = validation["stars"]
    old_stars = module_data.get("stars", 0)

    # Only award XP for new completions or star upgrades
    xp_earned = 0
    if not already_completed:
        xp_earned = MODULE_XP[module_id]
    # Bonus XP for star upgrades
    if stars > old_stars:
        xp_earned += (stars - old_stars) * 25

    prog.modules[module_id] = {
        "completed": True,
        "stars": max(stars, old_stars),
        "completed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "attempts": attempts,
        "xp_earned": module_data.get("xp_earned", 0) + xp_earned,
    }

    prog.total_xp += xp_earned
    prog.level = _compute_level(prog.total_xp)

    # Check if fully certified
    all_complete = all(
        prog.modules.get(m, {}).get("completed", False)
        for m in MODULE_ORDER
    )
    if all_complete and not prog.certified:
        prog.certified = True
        prog.certified_at = datetime.datetime.now(tz=datetime.timezone.utc)

    _update_streak(prog)
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await prog.save()

    return {
        "module_id": module_id,
        "stars": prog.modules[module_id]["stars"],
        "xp_earned": xp_earned,
        "total_xp": prog.total_xp,
        "level": prog.level,
        "level_up": prog.level != _compute_level(prog.total_xp - xp_earned),
        "certified": prog.certified,
        "validation": validation,
    }


# ---------------------------------------------------------------------------
# Per-module validators
# ---------------------------------------------------------------------------

async def _validate_foundations(user_id: str) -> dict:
    checks = []

    # Check: has a workflow with an Extraction task
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    has_extraction_workflow = False
    extraction_field_count = 0
    has_execution = False

    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name == "Extraction":
                    has_extraction_workflow = True
                    # Count fields in the referenced search set
                    ss_id = (task.data or {}).get("search_set_id")
                    if ss_id:
                        items = await SearchSetItem.find(SearchSetItem.searchset == ss_id).to_list()
                        extraction_field_count = max(extraction_field_count, len(items))

        if wf.num_executions and wf.num_executions >= 1:
            has_execution = True

    checks.append({"name": "Has extraction workflow", "passed": has_extraction_workflow, "detail": "Create a workflow with an Extraction step"})
    checks.append({"name": "3+ extraction fields", "passed": extraction_field_count >= 3, "detail": f"Found {extraction_field_count} fields (need 3+)"})
    checks.append({"name": "Workflow executed", "passed": has_execution, "detail": "Run your workflow at least once"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and extraction_field_count >= 5:
        stars = 2
    if passed and extraction_field_count >= 8:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_extraction_engine(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    max_fields = 0

    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name == "Extraction":
                    ss_id = (task.data or {}).get("search_set_id")
                    if ss_id:
                        items = await SearchSetItem.find(SearchSetItem.searchset == ss_id).to_list()
                        max_fields = max(max_fields, len(items))

    checks.append({"name": "15+ extraction fields", "passed": max_fields >= 15, "detail": f"Largest extraction has {max_fields} fields (need 15+)"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and max_fields >= 20:
        stars = 2
    if passed and max_fields >= 30:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_multi_step(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    best_step_count = 0
    has_required_types = False
    task_types_found: set[str] = set()

    for wf in workflows:
        step_count = len(wf.steps)
        best_step_count = max(best_step_count, step_count)
        wf_task_types: set[str] = set()
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task:
                    wf_task_types.add(task.name)
                    task_types_found.add(task.name)
        if step_count >= 3 and {"Extraction", "Prompt", "Formatter"} <= wf_task_types:
            has_required_types = True

    checks.append({"name": "3+ step workflow", "passed": best_step_count >= 3, "detail": f"Best workflow has {best_step_count} steps"})
    checks.append({"name": "Extraction + Prompt + Format", "passed": has_required_types, "detail": "Single workflow must include all three task types"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and best_step_count >= 4:
        stars = 2
    if passed and best_step_count >= 5 and len(task_types_found) >= 5:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_advanced_nodes(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    has_advanced = False
    has_parallel = False
    advanced_types: set[str] = set()
    max_parallel = 0

    advanced_task_names = {"CodeExecution", "APICall", "Research", "Crawler", "BrowserAutomation"}

    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            max_parallel = max(max_parallel, len(step.tasks))
            if len(step.tasks) >= 2:
                has_parallel = True
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name in advanced_task_names:
                    has_advanced = True
                    advanced_types.add(task.name)

    checks.append({"name": "Advanced node type", "passed": has_advanced, "detail": "Use CodeExecution, APICall, Research, Crawler, or BrowserAutomation"})
    checks.append({"name": "Parallel tasks", "passed": has_parallel, "detail": f"Max {max_parallel} parallel tasks in a step (need 2+)"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and len(advanced_types) >= 2:
        stars = 2
    if passed and max_parallel >= 3:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_output_delivery(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    output_types: set[str] = set()
    has_execution = False

    output_task_names = {"DocumentRenderer", "DataExport", "PackageBuilder", "FormFiller"}

    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name in output_task_names:
                    output_types.add(task.name)
        if wf.num_executions and wf.num_executions >= 1:
            has_execution = True

    checks.append({"name": "Output node", "passed": len(output_types) >= 1, "detail": "Use DocumentRenderer, DataExport, PackageBuilder, or FormFiller"})
    checks.append({"name": "Workflow executed", "passed": has_execution, "detail": "Run the workflow to produce output"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and len(output_types) >= 2:
        stars = 2
    if passed and "PackageBuilder" in output_types:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_validation_qa(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    max_checks = 0
    has_validated = False

    for wf in workflows:
        plan_len = len(wf.validation_plan or [])
        max_checks = max(max_checks, plan_len)
        if plan_len >= 2 and wf.num_executions and wf.num_executions >= 1:
            has_validated = True

    checks.append({"name": "Validation plan", "passed": max_checks >= 2, "detail": f"Best plan has {max_checks} checks (need 2+)"})
    checks.append({"name": "Ran validation", "passed": has_validated, "detail": "Run a workflow that has a validation plan"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and max_checks >= 5:
        stars = 2
    if passed and max_checks >= 8:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_batch_processing(user_id: str) -> dict:
    checks = []
    results = await WorkflowResult.find(WorkflowResult.user_id == user_id).to_list()

    batch_ids: dict[str, list] = {}
    for r in results:
        if r.batch_id:
            batch_ids.setdefault(r.batch_id, []).append(r)

    best_batch_size = 0
    best_batch_all_ok = False
    for bid, batch_results in batch_ids.items():
        count = len(batch_results)
        if count > best_batch_size:
            best_batch_size = count
            best_batch_all_ok = all(r.status == "completed" for r in batch_results)

    checks.append({"name": "Batch execution", "passed": best_batch_size >= 3, "detail": f"Largest batch has {best_batch_size} documents (need 3+)"})
    checks.append({"name": "All succeeded", "passed": best_batch_all_ok and best_batch_size >= 3, "detail": "All documents in batch must complete successfully"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and best_batch_size >= 5:
        stars = 2
    if passed and best_batch_size >= 10:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_governance(user_id: str) -> dict:
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()

    verified_count = sum(1 for wf in workflows if wf.verified)
    spaces_used = len(set(wf.space for wf in workflows if wf.space))

    checks.append({"name": "Verified workflow", "passed": verified_count >= 1, "detail": f"Have {verified_count} verified workflows (need 1+)"})
    checks.append({"name": "Multiple spaces", "passed": spaces_used >= 2, "detail": f"Using {spaces_used} spaces (need 2+)"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and verified_count >= 2:
        stars = 2
    if passed and verified_count >= 3 and spaces_used >= 3:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


_VALIDATORS = {
    "foundations": _validate_foundations,
    "extraction_engine": _validate_extraction_engine,
    "multi_step": _validate_multi_step,
    "advanced_nodes": _validate_advanced_nodes,
    "output_delivery": _validate_output_delivery,
    "validation_qa": _validate_validation_qa,
    "batch_processing": _validate_batch_processing,
    "governance": _validate_governance,
}
