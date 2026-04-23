"""Service layer for the Vandal Workflow Architect certification system."""

import base64
import datetime
import json
import logging
from pathlib import Path


from app.models.certification import CertificationProgress
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask, WorkflowResult
from app.models.search_set import SearchSetItem
from app.models.folder import SmartFolder
from app.models.document import SmartDocument

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exercises data (loaded once from certification-data/exercises.json)
# ---------------------------------------------------------------------------

_CERT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "certification-data"
_EXERCISES: dict = {}


def _load_exercises() -> dict:
    global _EXERCISES
    if _EXERCISES:
        return _EXERCISES
    exercises_path = _CERT_DATA_DIR / "exercises.json"
    if exercises_path.exists():
        _EXERCISES = json.loads(exercises_path.read_text())
    return _EXERCISES


def get_exercise(module_id: str) -> dict | None:
    exercises = _load_exercises()
    return exercises.get(module_id)


# ---------------------------------------------------------------------------
# XP & Level constants
# ---------------------------------------------------------------------------

MODULE_XP = {
    "ai_literacy": 50,
    "foundations": 100,
    "process_mapping": 100,
    "workflow_design": 100,
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
    "ai_literacy",
    "foundations",
    "process_mapping",
    "workflow_design",
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
# Document provisioning
# ---------------------------------------------------------------------------

CERT_FOLDER_TITLE = "Certification Lab"


async def provision_module_documents(user, module_id: str, settings) -> dict:
    """Provision sample documents for a certification module.

    Creates a Certification Lab folder in the user's workspace if needed,
    uploads the module's sample PDFs, and records provisioned doc UUIDs
    in CertificationProgress.

    ``user`` is a ``User`` model instance.
    """
    from app.services import file_service, folder_service

    user_id = user.user_id

    exercise = get_exercise(module_id)
    if not exercise:
        return {"error": f"No exercise defined for module {module_id}"}

    doc_filenames = exercise.get("documents", [])
    if not doc_filenames:
        return {"provisioned_docs": []}

    # Find or create Certification Lab folder in user's workspace
    folder = await SmartFolder.find_one(
        SmartFolder.title == CERT_FOLDER_TITLE,
        SmartFolder.user_id == user_id,
    )
    if not folder:
        folder = await folder_service.create_folder(
            name=CERT_FOLDER_TITLE,
            parent_id="0",
            user=user,
        )

    # Upload each document (skip if already exists)
    provisioned = []
    docs_dir = _CERT_DATA_DIR / "documents"

    for filename in doc_filenames:
        filepath = docs_dir / filename
        if not filepath.exists():
            log.warning("Certification PDF not found: %s", filepath)
            continue

        # Check if already uploaded (skip soft-deleted docs)
        existing = await SmartDocument.find_one(
            SmartDocument.title == filename,
            SmartDocument.user_id == user_id,
            SmartDocument.soft_deleted != True,  # noqa: E712
        )
        if existing:
            provisioned.append(existing.uuid)
            continue

        # Read and base64-encode
        pdf_bytes = filepath.read_bytes()
        blob = base64.b64encode(pdf_bytes).decode("utf-8")

        result = await file_service.upload_document(
            blob=blob,
            filename=filename,
            raw_extension="pdf",
            user=user,
            settings=settings,
            folder=folder.uuid,
        )
        provisioned.append(result["uuid"])

    # Store provisioning info in progress
    prog = await get_progress(user_id)
    module_data = prog.modules.get(module_id, {})
    module_data["provisioned_docs"] = provisioned
    prog.modules[module_id] = module_data
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await prog.save()

    return {"provisioned_docs": provisioned}


# ---------------------------------------------------------------------------
# Fuzzy field matching
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    return s.lower().strip().replace("_", " ").replace("-", " ")


def _fuzzy_field_match(expected: str, field_names: list[str]) -> bool:
    """Check if an expected field name matches any of the actual field names."""
    norm_expected = _normalize(expected)
    expected_words = set(norm_expected.split())
    for field in field_names:
        norm_field = _normalize(field)
        # Exact match
        if norm_expected == norm_field:
            return True
        # Substring match
        if norm_expected in norm_field or norm_field in norm_expected:
            return True
        # Word overlap (at least 2 words or all words match)
        field_words = set(norm_field.split())
        overlap = expected_words & field_words
        if len(overlap) >= min(2, len(expected_words)):
            return True
    return False


# ---------------------------------------------------------------------------
# Module validation
# ---------------------------------------------------------------------------

async def validate_module(user_id: str, module_id: str) -> dict:
    """Check a user's actual data against module completion criteria.

    Returns {passed: bool, stars: int, checks: [{name, passed, detail}]}
    """
    if module_id not in MODULE_XP:
        return {"passed": False, "stars": 0, "checks": [{"name": "invalid", "passed": False, "detail": "Unknown module"}]}

    _prog = await get_progress(user_id)

    # TEMP: prerequisite check bypassed for review
    # idx = MODULE_ORDER.index(module_id)
    # if idx > 0:
    #     prev = MODULE_ORDER[idx - 1]
    #     prev_data = prog.modules.get(prev, {})
    #     if not prev_data.get("completed"):
    #         return {
    #             "passed": False,
    #             "stars": 0,
    #             "checks": [{"name": "prerequisite", "passed": False, "detail": f"Complete the previous module first"}],
    #         }

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
        **module_data,  # Preserve provisioned_docs
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
    newly_certified = all_complete and not prog.certified
    if newly_certified:
        prog.certified = True
        prog.certified_at = datetime.datetime.now(tz=datetime.timezone.utc)

    _update_streak(prog)
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await prog.save()

    if newly_certified:
        await _fire_certification_complete_hooks(prog.user_id)

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
# Helper: collect extraction field names from a user's workflows
# ---------------------------------------------------------------------------

async def _resolve_extraction_field_names(task_data: dict) -> list[str]:
    """Resolve extraction field names from a task's data dict.

    Fields can come from a linked SearchSet (search_set_uuid) or be stored
    inline as ``searchphrases`` (list or comma-separated string) / ``keys``.
    """
    # Try linked SearchSet first
    ss_id = task_data.get("search_set_uuid")
    if ss_id:
        items = await SearchSetItem.find(SearchSetItem.searchset == ss_id).to_list()
        names = [item.searchphrase for item in items if item.searchphrase]
        if names:
            return names

    # Fall back to inline searchphrases / keys / extractions
    raw = task_data.get("searchphrases") or task_data.get("keys") or task_data.get("extractions") or []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if s]
    return []


async def _get_extraction_fields(workflows: list) -> tuple[int, list[str]]:
    """Returns (max_field_count, all_field_names) across all extraction tasks."""
    max_fields = 0
    all_field_names: list[str] = []
    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name == "Extraction":
                    field_names = await _resolve_extraction_field_names(task.data or {})
                    if len(field_names) > max_fields:
                        max_fields = len(field_names)
                        all_field_names = field_names
    return max_fields, all_field_names


async def _get_user_search_set_fields(user_id: str) -> tuple[int, list[str], list[str]]:
    """Chat-driven path: find the user's SearchSet with the most fields.

    Returns (max_field_count, all_field_names, search_set_uuids). Matches the
    classical Workflow+Extraction discovery so chat-only cert paths are equivalent.
    """
    from app.models.search_set import SearchSet as _SS, SearchSetItem as _SSI

    ss_list = await _SS.find(_SS.user_id == user_id).to_list()
    max_fields = 0
    all_field_names: list[str] = []
    uuids: list[str] = []
    for ss in ss_list:
        uuids.append(ss.uuid)
        items = await _SSI.find(_SSI.searchset == ss.uuid).to_list()
        names = [i.searchphrase for i in items if i.searchphrase]
        if len(names) > max_fields:
            max_fields = len(names)
            all_field_names = names
    return max_fields, all_field_names, uuids


async def _user_ran_search_set(user_id: str, search_set_uuids: list[str]) -> bool:
    """Check for a completed SEARCH_SET_RUN activity event for any of the UUIDs."""
    if not search_set_uuids:
        return False
    from app.models.activity import ActivityEvent, ActivityType, ActivityStatus

    evt = await ActivityEvent.find_one(
        ActivityEvent.user_id == user_id,
        ActivityEvent.type == ActivityType.SEARCH_SET_RUN.value,
        ActivityEvent.status == ActivityStatus.COMPLETED.value,
        {"search_set_uuid": {"$in": search_set_uuids}},
    )
    return evt is not None


async def _user_ran_search_set_on_n_docs(user_id: str, min_docs: int) -> int:
    """Return the largest single-run document count across completed chat extractions."""
    from app.models.activity import ActivityEvent, ActivityType, ActivityStatus

    evts = await ActivityEvent.find(
        ActivityEvent.user_id == user_id,
        ActivityEvent.type == ActivityType.SEARCH_SET_RUN.value,
        ActivityEvent.status == ActivityStatus.COMPLETED.value,
    ).to_list()
    best = 0
    for e in evts:
        best = max(best, e.documents_touched or 0)
    return best


# ---------------------------------------------------------------------------
# Self-assessment storage
# ---------------------------------------------------------------------------

async def store_assessment(user_id: str, module_id: str, answers: dict) -> dict:
    prog = await get_progress(user_id)
    module_data = prog.modules.get(module_id, {})
    module_data["self_assessment"] = {
        **answers,
        "completed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    }
    prog.modules[module_id] = module_data
    _update_streak(prog)
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await prog.save()
    return {"stored": True}


# ---------------------------------------------------------------------------
# Per-module validators
# ---------------------------------------------------------------------------

async def _validate_ai_literacy(user_id: str) -> dict:
    prog = await get_progress(user_id)
    assessment = prog.modules.get("ai_literacy", {}).get("self_assessment", {})
    all_answered = all(assessment.get(k) for k in ("experience", "comfort", "concern"))
    checks = [
        {
            "name": "Self-assessment completed",
            "passed": all_answered,
            "detail": "Answer all 3 reflection questions",
        }
    ]
    return {"passed": all_answered, "stars": 3 if all_answered else 0, "checks": checks}


async def _validate_process_mapping(user_id: str) -> dict:
    prog = await get_progress(user_id)
    assessment = prog.modules.get("process_mapping", {}).get("self_assessment", {})
    keys = ("process", "time_sink", "judgment", "outcome")
    all_answered = all(assessment.get(k) for k in keys)
    checks = [
        {
            "name": "Process reflection completed",
            "passed": all_answered,
            "detail": "Answer all 4 reflection questions about your work processes",
        }
    ]
    return {"passed": all_answered, "stars": 3 if all_answered else 0, "checks": checks}


async def _validate_workflow_design(user_id: str) -> dict:
    prog = await get_progress(user_id)
    assessment = prog.modules.get("workflow_design", {}).get("self_assessment", {})
    keys = ("step_splitting", "pattern", "concern", "human_role")
    all_answered = all(assessment.get(k) for k in keys)
    checks = [
        {
            "name": "Design reflection completed",
            "passed": all_answered,
            "detail": "Answer all 4 reflection questions about workflow design",
        }
    ]
    return {"passed": all_answered, "stars": 3 if all_answered else 0, "checks": checks}


async def _validate_foundations(user_id: str) -> dict:
    """Accept either the classical Workflow+Extraction path or the v5 chat-driven
    path (user-owned SearchSet + a logged SEARCH_SET_RUN activity).
    """
    checks = []
    exercise = get_exercise("foundations")
    expected_fields = exercise.get("expected_fields", []) if exercise else []

    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    has_extraction_artifact = False
    extraction_field_count = 0
    matched_fields: list[str] = []
    has_execution = False

    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name == "Extraction":
                    has_extraction_artifact = True
                    field_names = await _resolve_extraction_field_names(task.data or {})
                    if len(field_names) > extraction_field_count:
                        extraction_field_count = len(field_names)
                        matched_fields = [
                            ef for ef in expected_fields
                            if _fuzzy_field_match(ef, field_names)
                        ]

        if wf.num_executions and wf.num_executions >= 1:
            has_execution = True

    # Chat-driven path: also inspect user SearchSets and SEARCH_SET_RUN events
    ss_max_fields, ss_field_names, ss_uuids = await _get_user_search_set_fields(user_id)
    if ss_max_fields > 0:
        has_extraction_artifact = True
    if ss_max_fields > extraction_field_count:
        extraction_field_count = ss_max_fields
        matched_fields = [
            ef for ef in expected_fields if _fuzzy_field_match(ef, ss_field_names)
        ]
    if not has_execution and await _user_ran_search_set(user_id, ss_uuids):
        has_execution = True

    missing_fields = [f for f in expected_fields if f not in matched_fields]

    checks.append({
        "name": "Extraction template exists",
        "passed": has_extraction_artifact,
        "detail": "Create an extraction template (from chat or the Library tab)",
    })
    checks.append({
        "name": "Expected fields configured",
        "passed": len(matched_fields) >= 3,
        "detail": f"Found {len(matched_fields)}/{len(expected_fields)} expected fields"
              + (f" (missing: {', '.join(missing_fields[:3])})" if missing_fields else ""),
    })
    checks.append({
        "name": "Extraction executed",
        "passed": has_execution,
        "detail": "Run the extraction at least once (the agent can do this for you)",
    })

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and len(matched_fields) >= 5:
        stars = 2
    if passed and extraction_field_count >= 8:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_extraction_engine(user_id: str) -> dict:
    checks = []
    exercise = get_exercise("extraction_engine")
    expected_fields = exercise.get("expected_fields", []) if exercise else []

    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    wf_max_fields, wf_field_names = await _get_extraction_fields(workflows)
    ss_max_fields, ss_field_names, _ = await _get_user_search_set_fields(user_id)

    # Take whichever path has more fields — chat and classical are equivalent here.
    if ss_max_fields >= wf_max_fields:
        max_fields, all_field_names = ss_max_fields, ss_field_names
    else:
        max_fields, all_field_names = wf_max_fields, wf_field_names

    matched_fields = [
        ef for ef in expected_fields
        if _fuzzy_field_match(ef, all_field_names)
    ]
    missing_fields = [f for f in expected_fields if f not in matched_fields]

    checks.append({
        "name": "15+ extraction fields",
        "passed": max_fields >= 15,
        "detail": f"Largest extraction has {max_fields} fields (need 15+)"
              + (f" - matched {len(matched_fields)}/{len(expected_fields)} expected" if expected_fields else ""),
    })
    if missing_fields:
        checks.append({
            "name": "Missing expected fields",
            "passed": len(missing_fields) == 0,
            "detail": f"Consider adding: {', '.join(missing_fields[:5])}",
        })

    passed = max_fields >= 15
    stars = 1 if passed else 0
    if passed and max_fields >= 20:
        stars = 2
    if passed and max_fields >= 25:
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
    """Accept either the classical (workflow-validation-plan) path or the v5
    chat-driven path (test cases on a SearchSet + a ValidationRun).
    """
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    max_checks = 0
    has_validated = False

    for wf in workflows:
        plan_len = len(wf.validation_plan or [])
        max_checks = max(max_checks, plan_len)
        if plan_len >= 2 and wf.num_executions and wf.num_executions >= 1:
            has_validated = True

    # Chat-driven path: count test cases on user's SearchSets and any completed ValidationRun
    from app.models.search_set import SearchSet as _SS
    from app.models.extraction_test_case import ExtractionTestCase as _TC
    from app.models.validation_run import ValidationRun as _VR

    ss_list = await _SS.find(_SS.user_id == user_id).to_list()
    uuids = [ss.uuid for ss in ss_list]
    if uuids:
        tc_count = await _TC.find({"search_set_uuid": {"$in": uuids}}).count()
        if tc_count > max_checks:
            max_checks = tc_count
        vr = await _VR.find_one(
            _VR.item_kind == "search_set",
            {"item_id": {"$in": uuids}},
        )
        if vr is not None:
            has_validated = True

    checks.append({
        "name": "Validation plan (test cases)",
        "passed": max_checks >= 2,
        "detail": f"Best plan has {max_checks} checks/test cases (need 2+)",
    })
    checks.append({
        "name": "Ran validation",
        "passed": has_validated,
        "detail": "Run validation (from chat: 'validate this template') or a workflow with a validation plan",
    })

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and max_checks >= 5:
        stars = 2
    if passed and max_checks >= 8:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_batch_processing(user_id: str) -> dict:
    """Accept either the classical batched-workflow path or a v5 chat-driven
    run_extraction call that touched 3+ documents in a single invocation.
    """
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

    # Chat-driven path: a single SEARCH_SET_RUN with 3+ documents counts as a batch.
    chat_batch_size = await _user_ran_search_set_on_n_docs(user_id, min_docs=3)
    if chat_batch_size > best_batch_size:
        best_batch_size = chat_batch_size
        best_batch_all_ok = True  # Activity event is only written on success

    checks.append({
        "name": "Batch execution",
        "passed": best_batch_size >= 3,
        "detail": f"Largest batch has {best_batch_size} documents (need 3+)",
    })
    checks.append({
        "name": "All succeeded",
        "passed": best_batch_all_ok and best_batch_size >= 3,
        "detail": "All documents in the batch must complete successfully",
    })

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

    checks.append({"name": "Verified workflow", "passed": verified_count >= 1, "detail": f"Have {verified_count} verified workflows (need 1+)"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and verified_count >= 2:
        stars = 2
    if passed and verified_count >= 3:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


_VALIDATORS = {
    "ai_literacy": _validate_ai_literacy,
    "process_mapping": _validate_process_mapping,
    "workflow_design": _validate_workflow_design,
    "foundations": _validate_foundations,
    "extraction_engine": _validate_extraction_engine,
    "multi_step": _validate_multi_step,
    "advanced_nodes": _validate_advanced_nodes,
    "output_delivery": _validate_output_delivery,
    "validation_qa": _validate_validation_qa,
    "batch_processing": _validate_batch_processing,
    "governance": _validate_governance,
}


async def _fire_certification_complete_hooks(user_id: str) -> None:
    """Side-effects for newly certified users: email + in-app notification.

    Never raises — logged and swallowed so that cert completion itself always
    succeeds even if downstream notifications fail.
    """
    from app.models.user import User
    from app.services.engagement_service import send_certification_complete_email_for
    from app.services.notification_service import create_notification

    try:
        user = await User.find_one(User.user_id == user_id)
        if user:
            await send_certification_complete_email_for(user)
    except Exception:
        log.exception("Failed to send cert-complete email for %s", user_id)

    try:
        await create_notification(
            user_id=user_id,
            kind="certification_complete",
            title="You're a Certified Vandal Workflow Architect",
            body="All 11 modules complete. Your Certified badge is now visible on every workflow you publish.",
            link="/certification",
        )
    except Exception:
        log.exception("Failed to create cert-complete notification for %s", user_id)
