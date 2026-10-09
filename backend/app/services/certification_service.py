"""Service layer for the Vandal Workflow Architect certification system."""

import base64
import datetime
import hashlib
import json
import logging
from pathlib import Path


from app.models.certification import CertificationProgress
from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask, WorkflowResult
from app.models.search_set import SearchSet, SearchSetItem
from app.models.folder import SmartFolder
from app.models.document import SmartDocument
from app.models.verification import VerificationRequest, VerificationStatus
from app.services.certification_versions.runtime import course_operation, current_operation
from app.services.certification_versions.writes import save_progress

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exercises data (loaded once from certification-data/exercises.json)
# ---------------------------------------------------------------------------

_CERT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "certification-data"
_EXERCISES: dict = {}


def _load_exercises() -> dict:
    operation = current_operation()
    if operation:
        return operation.package.json('exercises.json')
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


# Lesson content + self-assessment questions, exported from the panel's
# authored source (frontend/src/pages/Certification.tsx and
# SelfAssessment.tsx) by frontend/scripts/export-lessons.mjs. Lets the
# in-chat certification flow teach the same lessons the panel shows.
_LESSONS: dict = {}


def _load_lessons() -> dict:
    operation = current_operation()
    if operation:
        return operation.package.json('lessons.json')
    global _LESSONS
    if _LESSONS:
        return _LESSONS
    lessons_path = _CERT_DATA_DIR / "lessons.json"
    if lessons_path.exists():
        _LESSONS = json.loads(lessons_path.read_text())
    return _LESSONS


def get_lessons(module_id: str) -> dict | None:
    return _load_lessons().get(module_id)


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

# Display titles, kept in sync with the frontend MODULES catalog
# (frontend/src/pages/Certification.tsx). Used by surfaces that only have the
# module id (chat tools, notifications).
MODULE_TITLES = {
    "ai_literacy": "AI Literacy",
    "foundations": "Foundations",
    "process_mapping": "Thinking in Workflows",
    "workflow_design": "Workflow Design",
    "extraction_engine": "Extraction Engine",
    "multi_step": "Multi-Step Workflows",
    "advanced_nodes": "Advanced Nodes",
    "output_delivery": "Output & Delivery",
    "validation_qa": "Validation & QA",
    "batch_processing": "Batch Processing",
    "governance": "Governance",
}

# Self-assessment answer keys required by the reflective modules' validators
# (_validate_ai_literacy / _validate_process_mapping / _validate_workflow_design).
ASSESSMENT_KEYS = {
    "ai_literacy": ("experience", "comfort", "concern"),
    "process_mapping": ("process", "time_sink", "judgment", "outcome"),
    "workflow_design": ("step_splitting", "pattern", "concern", "human_role"),
}


def _compute_level(xp: int) -> str:
    level = "novice"
    for name, threshold in course_levels():
        if xp >= threshold:
            level = name
    return level


def course_levels():
    operation = current_operation()
    if operation:
        from app.services.certification_versions.grading import load_rubric
        rubric = load_rubric(operation.package)
        if 'outcomes.json' in operation.package.manifest.artifacts:
            return [(item['name'], item['xp']) for item in operation.package.json('course-structure.json')['levels']]
        return rubric.LEVELS
    return LEVELS


def course_module_order() -> list[str]:
    operation = current_operation()
    return [module.id for module in operation.package.manifest.modules] if operation else MODULE_ORDER


def course_module_xp() -> dict[str, int]:
    operation = current_operation()
    return {module.id: module.base_xp for module in operation.package.manifest.modules} if operation else MODULE_XP


def course_module_titles() -> dict[str, str]:
    operation = current_operation()
    return {module.id: module.title for module in operation.package.manifest.modules} if operation else MODULE_TITLES


def course_identity() -> dict:
    operation = current_operation()
    return ({**operation.package.summary(), 'enrollment_id': operation.progress.enrollment_id,
             'maximum_stars': operation.package.manifest.maximum_stars,
             'credit_basis': 'required_outcomes' if 'outcomes.json' in operation.package.manifest.artifacts else 'legacy_rubric'}
            if operation else {})


@course_operation()
async def get_course_definition(user_id: str, *, enrollment_id: str | None = None) -> dict:
    operation = current_operation()
    if operation is None:
        return {'versioned': False}
    manifest = operation.package.manifest
    from .certification_versions.delivery import public_modules
    from .certification_versions.grading import selected_outcome_completion_available
    from .certification_versions.progression_policy import public_progression_policy
    from .certification_versions.credential_scope import public_credential_scope
    from .certification_versions.bridge_path import public_bridge_path
    return {
        **course_identity(), 'versioned': True,
        'modules': public_modules(operation.package),
        'prerequisites': {module.id: list(module.prerequisites) for module in manifest.modules},
        **operation.package.json('course-structure.json'),
        'selected_outcome_completion': selected_outcome_completion_available(operation.package),
        'progression_policy': public_progression_policy(operation.package),
        'credential_scope': public_credential_scope(operation.package),
        'bridge_path': public_bridge_path(operation.package),
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@course_operation()
async def get_progress(user_id: str) -> CertificationProgress:
    operation = current_operation()
    if operation:
        return operation.progress
    from .certification_versions.legacy_writes import read_progress
    return await read_progress(user_id)


@course_operation()
async def get_progress_dict(user_id: str) -> dict:
    prog = await get_progress(user_id)
    operation = current_operation()
    pending = []
    if operation:
        from .certification_versions.attempts import AttemptRepository
        pending = await AttemptRepository().pending(operation)
    return {
        **course_identity(),
        "id": str(prog.id),
        "user_id": prog.user_id,
        "modules": prog.modules,
        "total_xp": prog.total_xp,
        "level": prog.level,
        "certified": prog.certified,
        "certified_at": prog.certified_at.isoformat() if prog.certified_at else None,
        "last_activity_date": prog.last_activity_date,
        "unlocked": prog.unlocked,
        **({'learning_position': prog.learning_position, 'position_revision': prog.position_revision,
            'pending_completions': pending} if operation else {}),
    }


@course_operation(write=True)
async def save_learning_position(user_id: str, module_id: str, lesson_id: str, expected_revision: int) -> dict:
    from .certification_versions.catalog import CourseCatalogError
    from .certification_versions.delivery import CourseDelivery

    operation = current_operation()
    if operation is None:
        raise CourseCatalogError('Server lesson resume is unavailable for this course')
    return await CourseDelivery.store_position(operation.progress, operation.package, module_id, lesson_id, expected_revision)


# ---------------------------------------------------------------------------
# Activity tracking
# ---------------------------------------------------------------------------

def _touch_activity(prog: CertificationProgress) -> None:
    # Deliberately not a streak: the audience is professionals, and a
    # consecutive-day counter is daily-login pressure. Admin reporting only
    # needs the most recent activity date.
    prog.last_activity_date = datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Document provisioning
# ---------------------------------------------------------------------------

CERT_FOLDER_TITLE = "Certification Lab"


@course_operation(write=True)
async def provision_module_documents(user, module_id: str, settings, *, enrollment_id: str | None = None) -> dict:
    """Provision sample documents for a certification module.

    Creates a Certification Lab folder in the user's workspace if needed,
    uploads the module's sample PDFs, and records provisioned doc UUIDs
    in CertificationProgress.

    ``user`` is a ``User`` model instance.
    """
    from app.services import file_service
    from .access_control import get_authorized_folder
    from .certification_versions.enrollments import EnrollmentConflict
    from .certification_versions.lab_folders import ensure_lab_folder
    from .certification_versions.source_access import owned_source

    user_id = user.user_id

    exercise = get_exercise(module_id)
    if not exercise:
        return {"error": f"No exercise defined for module {module_id}"}

    doc_filenames = exercise.get("documents", [])
    if not doc_filenames:
        return {"provisioned_docs": []}

    operation = current_operation()
    folder_title = f'{CERT_FOLDER_TITLE} — {operation.package.manifest.title}' if operation else CERT_FOLDER_TITLE
    # Versioned labs have an enrollment-owned folder reference; identical
    # filenames from another course must not select its sample documents.
    if operation:
        folder = await SmartFolder.find_one(
            SmartFolder.uuid == operation.progress.lab_folder_id,
            SmartFolder.user_id == user_id,
        ) if operation.progress.lab_folder_id else None
    else:
        folder = await SmartFolder.find_one(
            SmartFolder.title == CERT_FOLDER_TITLE,
            SmartFolder.user_id == user_id,
        )
    if folder:
        if await get_authorized_folder(folder.uuid, user, contribute=True) is None:
            raise EnrollmentConflict('The selected course lab is no longer accessible for provisioning')
    # Validate and bind progress before any external creation. In particular,
    # disabled versioning must not upload into an already pinned learner's lab.
    prog = await get_progress(user_id)
    if not folder:
        folder = await ensure_lab_folder(user, prog, folder_title)
        if await get_authorized_folder(folder.uuid, user, contribute=True) is None:
            raise EnrollmentConflict('The selected course lab is no longer accessible for provisioning')
        if operation:
            operation.progress.lab_folder_id = folder.uuid
            await save_progress(operation.progress)

    # Upload each document (skip if already exists)
    provisioned = []
    assigned_names = {}
    docs_dir = _CERT_DATA_DIR / "documents"

    for filename in doc_filenames:
        filepath = docs_dir / filename
        if not operation and not filepath.exists():
            log.warning("Certification PDF not found: %s", filepath)
            continue

        # Reuse only this lab's copy, including for unversioned learners.
        # A same-named personal file is not an assigned course sample.
        filters = [
            SmartDocument.title == filename,
            SmartDocument.user_id == user_id,
            SmartDocument.folder == folder.uuid,
            SmartDocument.soft_deleted != True,  # noqa: E712
        ]
        existing = await SmartDocument.find_one(*filters)
        if existing:
            if await owned_source(user_id, existing.uuid, lab_folder_id=folder.uuid) is None:
                raise EnrollmentConflict('An assigned source is no longer accessible in this course lab')
        if existing:
            provisioned.append(existing.uuid)
            assigned_names[existing.uuid] = filename
            continue

        # Read and base64-encode
        pdf_bytes = operation.package.read('documents/' + filename) if operation else filepath.read_bytes()
        blob = base64.b64encode(pdf_bytes).decode("utf-8")

        result = await file_service.upload_document(
            blob=blob,
            filename=filename,
            raw_extension="pdf",
            user=user,
            settings=settings,
            folder=folder.uuid,
            certification_provisioning_key=hashlib.sha256(json.dumps([
                'vandalizer:course-sample:v1', user_id, str(prog.id),
                prog.enrollment_id or 'unversioned', folder.uuid, filename,
                hashlib.sha256(pdf_bytes).hexdigest(),
            ], separators=(',', ':')).encode()).hexdigest(),
        )
        provisioned.append(result["uuid"])
        assigned_names[result['uuid']] = filename

    # Upload/storage/queue work can outlast a permission or document change.
    # Recheck all assigned sources, including those reused before later uploads.
    if await get_authorized_folder(folder.uuid, user, contribute=True) is None:
        raise EnrollmentConflict('The selected course lab is no longer accessible for provisioning')
    if len(assigned_names) != len(provisioned):
        raise EnrollmentConflict('The assigned samples are no longer accessible as distinct course sources')
    for document_id, filename in assigned_names.items():
        source = await owned_source(user_id, document_id, lab_folder_id=folder.uuid)
        if source is None or source.title != filename:
            raise EnrollmentConflict('An assigned source is no longer accessible in this course lab')

    # Store provisioning info in progress
    module_data = prog.modules.get(module_id, {})
    module_data["provisioned_docs"] = provisioned
    prog.modules[module_id] = module_data
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await save_progress(prog)

    return {"provisioned_docs": provisioned, "folder_name": folder_title}


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

@course_operation()
async def validate_module(user_id: str, module_id: str, *, enrollment_id: str | None = None, assessment_selection: dict | None = None) -> dict:
    """Check a user's actual data against module completion criteria.

    Returns {passed: bool, stars: int, checks: [{name, passed, detail}]}
    """
    operation = current_operation()
    if operation:
        from app.services.certification_versions.grading import grade
        selected = {'assessment_selection': assessment_selection} if assessment_selection is not None else {}
        return {**course_identity(), **await grade(operation.package, operation.progress, module_id, **selected)}
    if assessment_selection is not None:
        from .certification_versions.enrollments import EnrollmentConflict
        raise EnrollmentConflict('Selected competency evidence requires an explicit versioned enrollment')
    if module_id not in MODULE_XP:
        return {"passed": False, "stars": 0, "checks": [{"name": "invalid", "passed": False, "detail": "Unknown module"}]}

    _prog = await get_progress(user_id)

    # Preserve the original legacy requirements, which impose no module
    # prerequisites. Versioned requirements use the pinned runner above;
    # do not introduce an unrecorded lock into an existing learner's course.

    validator = _VALIDATORS.get(module_id)
    if not validator:
        return {"passed": False, "stars": 0, "checks": []}

    from .certification_versions.check_roles import legacy_check_roles
    from .certification_versions.legacy_access import with_legacy_field_access
    return legacy_check_roles(module_id, await with_legacy_field_access(validator, user_id)(user_id))


@course_operation(write=True)
async def complete_module(user_id: str, module_id: str, *, enrollment_id: str | None = None, request_id: str | None = None, assessment_selection: dict | None = None, expected_attempts: int | None = None) -> dict:
    """Mark a module complete after validation passes. Returns updated progress."""
    operation = current_operation()
    if assessment_selection is not None and not operation:
        from .certification_versions.enrollments import EnrollmentConflict
        raise EnrollmentConflict('Selected competency evidence requires an explicit versioned enrollment')
    legacy_request = None
    if operation:
        from .certification_versions.legacy_completions import persist_pending
        await persist_pending(operation.progress)
    elif request_id is not None:
        from .certification_versions import legacy_completions
        legacy_completions.validate_request_id(request_id)
        legacy_progress = await get_progress(user_id)
        replay = await legacy_completions.previous(legacy_progress, module_id, request_id)
        if replay is not None:
            if legacy_progress.certified:
                await _fire_certification_complete_hooks(user_id)
            return replay
        legacy_request = request_id
    if operation and operation.progress.pending_credential:
        await _finish_pending_credential(operation.progress)
    attempt = None
    if operation:
        from .certification_versions.attempts import AttemptRepository, progress_digest, encode
        from .certification_versions.enrollments import EnrollmentConflict
        journal = AttemptRepository()
        # An already recorded request replays its original outcome even after
        # credit advances. Fence only a new request, before creating its journal.
        if expected_attempts is not None and not (request_id and await journal.records.find_one({'uuid': request_id})):
            from .certification_versions.completion_preconditions import check_completion_counter
            check_completion_counter(operation.progress, module_id, expected_attempts)
        attempt, started = await journal.begin(operation, module_id, request_id, assessment_selection=assessment_selection)
        if attempt['state'] in ('applied', 'rejected', 'failed'):
            result = journal.payload(attempt, 'result')
            if attempt['state'] == 'applied' and operation.progress.certified:
                await _fire_certification_complete_hooks(user_id, enrollment_id=operation.progress.enrollment_id)
            return result
        if not started:
            receipt = operation.progress.completion_receipt
            if receipt and receipt.get('attempt_id') == attempt['uuid']:
                result = journal.payload(receipt, 'result')
                result = await journal.finish(attempt, result)
                if operation.progress.certified:
                    await _fire_certification_complete_hooks(user_id, enrollment_id=operation.progress.enrollment_id)
                return result
            if attempt['state'] == 'evaluating':
                raise EnrollmentConflict('An interrupted assessment needs reconciliation before grading again')
            if progress_digest(operation.progress) != attempt['progress_sha256']:
                raise EnrollmentConflict('Earned progress or answers changed after grading; reconcile the saved assessment')
            validation = journal.payload(attempt, 'validation')
        else:
            try:
                selected = journal.assessment_selection(attempt)
                validation = await validate_module(user_id, module_id, **({'assessment_selection': selected} if selected is not None else {}))
            except Exception:
                await journal.finish(attempt, {'error': 'Assessment could not finish; submit a new request to try again', 'attempt_id': attempt['uuid']}, failed=True)
                raise
            attempt = await journal.graded(attempt, validation)
    else:
        if expected_attempts is not None:
            from .certification_versions.completion_preconditions import check_completion_counter
            check_completion_counter(await get_progress(user_id), module_id, expected_attempts)
        validation = await validate_module(user_id, module_id)
    if not validation["passed"]:
        result = {"error": "Validation did not pass", "validation": validation}
        if attempt:
            result['attempt_id'] = attempt['uuid']
            await journal.finish(attempt, result)
        if legacy_request:
            result = legacy_completions.prepare(legacy_progress, module_id, legacy_request, result)
            await save_progress(legacy_progress)
            await legacy_completions.persist_pending(legacy_progress)
        return result

    prog = await get_progress(user_id)
    outcome_credit = None
    repeated_outcomes = False
    if operation and 'outcomes.json' in operation.package.manifest.artifacts:
        from .certification_versions.catalog import CourseCatalogError
        from .certification_versions.outcome_credit import freeze_credit, repeats_earned_outcomes
        if attempt is None:
            raise CourseCatalogError('Competency credit requires a durable completion request')
        outcome_credit = freeze_credit(operation.package, prog, module_id, attempt)
        repeated_outcomes = repeats_earned_outcomes(operation.package, prog, module_id, outcome_credit)
    module_data = prog.modules.get(module_id, {})
    transferred = validation.get('assessment_kind') == 'transferred_outcome_validation'
    attempts = module_data.get("attempts", 0) + (0 if repeated_outcomes or transferred else 1)
    already_completed = module_data.get("completed", False)

    stars = validation["stars"]
    old_stars = module_data.get("stars", 0)

    # Only award XP for new completions or star upgrades
    xp_earned = 0
    xp_carried = 0
    if transferred:
        if already_completed:
            raise EnrollmentConflict('This module already has credit; replay its original transfer receipt')
        xp_carried = validation['credit_transfer']['xp_carried']
    elif not already_completed:
        xp_earned = course_module_xp()[module_id]
    # Bonus XP for star upgrades
    if stars > old_stars:
        operation = current_operation()
        bonus = operation.package.manifest.star_bonus_xp if operation else 25
        xp_earned += (stars - old_stars) * bonus

    prog.modules[module_id] = {
        **module_data,  # Preserve provisioned_docs
        "completed": True,
        "stars": max(stars, old_stars),
        # Keep first-earned credit dates on retries, including unknown legacy dates.
        "completed_at": module_data.get("completed_at") if already_completed else datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "attempts": attempts,
        "xp_earned": module_data.get("xp_earned", 0) + xp_earned,
    }
    if attempt and not repeated_outcomes:
        prog.modules[module_id]['completion_attempt_id'] = attempt['uuid']
    if outcome_credit is not None and not repeated_outcomes:
        prog.modules[module_id]['outcome_credit'] = outcome_credit
    if transferred:
        prog.modules[module_id].update(credit_origin='transferred', xp_carried=xp_carried)
    elif outcome_credit is not None and not repeated_outcomes:
        prog.modules[module_id]['credit_origin'] = 'assessed'

    prog.total_xp += xp_earned + xp_carried
    prog.level = _compute_level(prog.total_xp)

    # Check if fully certified
    all_complete = all(
        prog.modules.get(m, {}).get("completed", False)
        for m in course_module_order()
    )
    newly_certified = all_complete and not prog.certified
    if newly_certified:
        prog.certified = True
        prog.certified_at = datetime.datetime.now(tz=datetime.timezone.utc)
        if operation:
            from app.models.user import User
            from .certification_versions.credentials import CredentialRepository
            learner = await User.find_one(User.user_id == user_id)
            name = (learner.name or learner.email) if learner else user_id
            # Freeze the payload in the same progress save as graduation. A
            # retry finishes this original issuance before awarding anything.
            prog.pending_credential = CredentialRepository.prepare(prog, operation.package, name).model_dump(mode='json')

    _touch_activity(prog)
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    result = {
        **course_identity(),
        "module_id": module_id,
        "stars": prog.modules[module_id]["stars"],
        "xp_earned": xp_earned,
        "total_xp": prog.total_xp,
        "level": prog.level,
        "level_up": prog.level != _compute_level(prog.total_xp - xp_earned),
        "certified": prog.certified,
        "validation": validation,
    }
    if attempt:
        result['attempt_id'] = attempt['uuid']
        if transferred:
            result.update(credit_origin='transferred', xp_carried=xp_carried, source_enrollment_id=validation['credit_transfer']['source_enrollment_id'])
        payload, digest = encode(result)
        # Save the awarded result atomically with credit. A lost response or
        # journal update can recover it without regrading mutable artifacts.
        prog.completion_receipt = {'attempt_id': attempt['uuid'], 'result_json': payload, 'result_sha256': digest}
    elif legacy_request:
        result = legacy_completions.prepare(prog, module_id, legacy_request, result)
    await save_progress(prog)
    if legacy_request:
        await legacy_completions.persist_pending(prog)

    if operation and prog.pending_credential:
        await _finish_pending_credential(prog)

    if attempt:
        await journal.finish(attempt, result)

    if operation and prog.certified:
        await _fire_certification_complete_hooks(prog.user_id, enrollment_id=prog.enrollment_id)
    elif newly_certified:
        await _fire_certification_complete_hooks(prog.user_id)

    return result


async def _finish_pending_credential(progress):
    from app.models.certification import CertificationEnrollment
    from .certification_versions.credentials import CredentialRepository, parse_credential_snapshot
    from .certification_versions.enrollments import EnrollmentConflict
    operation = current_operation()
    record = parse_credential_snapshot(progress.pending_credential)
    if not operation or not operation.writable or (
        record.user_id != progress.user_id or record.enrollment_id != progress.enrollment_id
        or record.course_version != progress.course_version
        or record.manifest_sha256 != operation.package.manifest_sha256
    ):
        raise EnrollmentConflict('Pending credential does not match this course operation')
    enrollments = CertificationEnrollment.get_motor_collection()
    identity = {'uuid': progress.enrollment_id, 'user_id': progress.user_id,
                'progress_id': str(progress.id), 'course_version': record.course_version,
                'manifest_sha256': record.manifest_sha256, 'state': {'$in': ['active', 'completed']}}
    if await enrollments.find_one(identity) is None:
        raise EnrollmentConflict('The enrollment changed before completion could be recorded')
    await CredentialRepository().persist(record)
    # State is metadata; the inserted snapshot remains the issuance authority.
    completed = await enrollments.update_one(identity, {'$set': {'state': 'completed'}})
    if completed.matched_count != 1:
        raise EnrollmentConflict('The enrollment changed while completion was being recorded; its original credential remains preserved')
    progress.pending_credential = None
    await save_progress(progress)


# ---------------------------------------------------------------------------
# Helper: collect extraction field names from a user's workflows
# ---------------------------------------------------------------------------

async def _resolve_extraction_field_names(task_data: dict) -> list[str]:
    """Resolve extraction field names from a task's data dict.

    Fields can come from a linked SearchSet (``search_set_uuid``) AND/OR be stored
    inline as ``searchphrases`` / ``keys`` / ``extractions``. We merge every
    source so a user who configured fields in either place — or both — gets
    credit for every field they defined. Duplicates are deduped case-insensitively.
    """
    names: list[str] = []
    seen: set[str] = set()

    def _add(values) -> None:
        for raw in values:
            if not raw:
                continue
            name = str(raw).strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            names.append(name)

    # Linked SearchSet items
    ss_id = task_data.get("search_set_uuid")
    if ss_id:
        items = await SearchSetItem.find(SearchSetItem.searchset == ss_id).to_list()
        _add(item.searchphrase for item in items if item.searchphrase)

    # Inline sources — accept all so users who pick a saved set and ALSO type
    # fields directly on the task aren't silently shorted.
    for key in ("searchphrases", "keys", "extractions"):
        raw = task_data.get(key)
        if isinstance(raw, str):
            _add(s.strip() for s in raw.split(",") if s.strip())
        elif isinstance(raw, list):
            _add(raw)

    return names


async def _collect_extraction_fields(workflows: list) -> tuple[list[str], int]:
    """Aggregate extraction field names across every Extraction task in the user's workflows.

    Returns ``(combined_field_names, largest_single_extraction_count)``. The combined list
    is the union (case-insensitive dedupe) so the validator does not penalize users for
    splitting fields across multiple Extraction tasks or for the order of those tasks.
    """
    seen: set[str] = set()
    combined: list[str] = []
    largest = 0
    for wf in workflows:
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name == "Extraction":
                    field_names = await _resolve_extraction_field_names(task.data or {})
                    if len(field_names) > largest:
                        largest = len(field_names)
                    for name in field_names:
                        key = name.lower()
                        if key not in seen:
                            seen.add(key)
                            combined.append(name)
    return combined, largest


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


async def _collect_searchset_fields(user_id: str) -> list[str]:
    """Field names from the user's own standalone Extractions (SearchSets).

    The extraction challenge is built in the Extraction editor, which saves a
    SearchSet — not necessarily a workflow. Counting those items directly means
    a user is credited for the extraction they actually built, even if they
    haven't wired it into a workflow yet (or the workflow task didn't carry every
    field across). Each item counts once, by its display title (falling back to
    the searchphrase). Deduped case-insensitively.
    """
    seen: set[str] = set()
    names: list[str] = []
    sets = await SearchSet.find(
        {"$or": [{"user_id": user_id}, {"created_by_user_id": user_id}]}
    ).to_list()
    for ss in sets:
        items = await SearchSetItem.find(SearchSetItem.searchset == ss.uuid).to_list()
        for it in items:
            name = (it.title or it.searchphrase or "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in seen:
                seen.add(key)
                names.append(name)
    return names


def _union_fields(*field_lists: list[str]) -> list[str]:
    """Case-insensitive union of several field-name lists, preserving order."""
    seen: set[str] = set()
    combined: list[str] = []
    for fields in field_lists:
        for name in fields:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                combined.append(name)
    return combined


# ---------------------------------------------------------------------------
# Self-assessment storage
# ---------------------------------------------------------------------------

@course_operation(write=True)
async def store_assessment(user_id: str, module_id: str, answers: dict, *, enrollment_id: str | None = None) -> dict:
    operation = current_operation()
    if operation and module_id not in course_module_order():
        from app.services.certification_versions.enrollments import EnrollmentConflict
        raise EnrollmentConflict('This module is not part of the selected course')
    if operation and 'outcomes.json' in operation.package.manifest.artifacts:
        from app.services.certification_versions.enrollments import EnrollmentConflict
        raise EnrollmentConflict('This course requires selected saved outcome evidence. Open module assessment in the Certification panel; legacy reflection answers cannot be submitted for this course.')
    prog = await get_progress(user_id)
    module_data = prog.modules.get(module_id, {})
    module_data["self_assessment"] = {
        **answers,
        "completed_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
    }
    prog.modules[module_id] = module_data
    _touch_activity(prog)
    prog.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await save_progress(prog)
    return {**course_identity(), "stored": True}


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
    workflow_fields, _largest = await _collect_extraction_fields(workflows)
    standalone_fields = await _collect_searchset_fields(user_id)
    combined_fields = _union_fields(workflow_fields, standalone_fields)

    has_extraction_workflow = False
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

        if wf.num_executions and wf.num_executions >= 1:
            has_execution = True

    # Chat-driven path: a standalone SearchSet counts as the extraction
    # artifact, and a completed SEARCH_SET_RUN event counts as the execution.
    has_extraction_artifact = has_extraction_workflow or bool(standalone_fields)
    if not has_execution:
        _, _, ss_uuids = await _get_user_search_set_fields(user_id)
        has_execution = await _user_ran_search_set(user_id, ss_uuids)

    matched_fields = [
        ef for ef in expected_fields
        if _fuzzy_field_match(ef, combined_fields)
    ]
    missing_fields = [f for f in expected_fields if f not in matched_fields]

    checks.append({
        "name": "Extraction template exists",
        "passed": has_extraction_artifact,
        "detail": "Create an extraction template (from chat or the Library tab)",
    })
    checks.append({
        "name": "Expected fields configured",
        "passed": len(matched_fields) >= 3,
        "detail": f"Found {len(matched_fields)}/{len(expected_fields)} expected fields across your extraction tasks"
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
    if passed and len(combined_fields) >= 8:
        stars = 3

    return {"passed": passed, "stars": stars, "checks": checks}


async def _validate_extraction_engine(user_id: str) -> dict:
    checks = []
    exercise = get_exercise("extraction_engine")
    expected_fields = exercise.get("expected_fields", []) if exercise else []

    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    workflow_fields, _largest = await _collect_extraction_fields(workflows)
    standalone_fields = await _collect_searchset_fields(user_id)
    # Credit fields the user defined in a standalone Extraction OR in a workflow
    # Extraction task — the challenge is "fields across your extraction tasks",
    # and most users build the Extraction directly in the editor (including via
    # chat, which saves a SearchSet).
    combined_fields = _union_fields(workflow_fields, standalone_fields)
    total_fields = len(combined_fields)

    matched_fields = [
        ef for ef in expected_fields
        if _fuzzy_field_match(ef, combined_fields)
    ]
    missing_fields = [f for f in expected_fields if f not in matched_fields]

    checks.append({
        "name": "15+ extraction fields",
        "passed": total_fields >= 15,
        "detail": f"You have {total_fields} unique fields across your extraction tasks (need 15+)"
              + (f" — matched {len(matched_fields)}/{len(expected_fields)} expected" if expected_fields else ""),
    })
    if missing_fields:
        checks.append({
            "name": "Missing expected fields",
            "passed": len(missing_fields) == 0,
            "detail": f"Consider adding: {', '.join(missing_fields[:5])}",
        })

    passed = total_fields >= 15
    stars = 1 if passed else 0
    if passed and total_fields >= 20:
        stars = 2
    if passed and total_fields >= 25:
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

    # Task names are stored verbatim from the workflow editor palette
    # (WorkflowEditorPanel TASK_TYPES) and the engine factory in
    # build_workflow_engine — e.g. "ResearchNode" (shown in the UI as "Deep
    # Analysis"), not the display label. CodeNode is admin-only and hidden from
    # the palette, so a non-admin trainee completes this module via the Deep
    # Analysis / API / Crawler nodes that are reachable in the UI; CodeNode and
    # Browser still count for admins who can add them.
    advanced_task_names = {"CodeNode", "APINode", "ResearchNode", "CrawlerNode", "Browser"}

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

    checks.append({"name": "Advanced node type", "passed": has_advanced, "detail": "Use a Deep Analysis, API, or Crawler node (Code Execution is admin-only)"})
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
    has_zip_bundle = False

    output_task_names = {"DocumentRenderer", "DataExport", "PackageBuilder", "FormFiller"}

    for wf in workflows:
        deliverable_steps = 0
        for step_id in wf.steps:
            step = await WorkflowStep.get(step_id)
            if not step:
                continue
            if step.is_output:
                deliverable_steps += 1
            for task_id in step.tasks:
                task = await WorkflowStepTask.get(task_id)
                if task and task.name in output_task_names:
                    output_types.add(task.name)
        ran = bool(wf.num_executions and wf.num_executions >= 1)
        if ran:
            has_execution = True
        # A run workflow with 2+ steps marked "Include in deliverables"
        # downloads as a ZIP bundle. The Package Builder node is still
        # "Coming Soon" in the editor palette, so this is the reachable way to
        # earn the ZIP star; a PackageBuilder task still counts for when it ships.
        if ran and deliverable_steps >= 2:
            has_zip_bundle = True

    checks.append({"name": "Output node", "passed": len(output_types) >= 1, "detail": "Use a Document Renderer, Data Export, or Form Filler"})
    checks.append({"name": "Workflow executed", "passed": has_execution, "detail": "Run the workflow to produce output"})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and len(output_types) >= 2:
        stars = 2
    if passed and (has_zip_bundle or "PackageBuilder" in output_types):
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
    # WorkflowResult has no user_id field, so scope by the user's workflows
    # (the same way every other validator scopes its data). Querying a
    # non-existent field here used to raise and surface as a generic
    # "cannot be verified, try again later" error, making the module unpassable.
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    workflow_ids = [wf.id for wf in workflows]
    results = (
        await WorkflowResult.find({"workflow": {"$in": workflow_ids}}).to_list()
        if workflow_ids
        else []
    )

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
    """Governance module.

    Passing is gated on *submitting* a workflow for verification — an action the
    learner controls — not on an examiner approving it. Approval happens on the
    examiner's schedule (often days or weeks later), so gating the final module
    on it left every certifying user blocked on another person. Approved
    submissions still earn the extra stars, so the credential keeps its teeth.
    """
    checks = []
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()

    requests = await VerificationRequest.find(
        {"item_kind": "workflow", "submitter_user_id": user_id}
    ).to_list()
    # Passing means the learner asked at least once, whatever came of it: a
    # declined request still performed the module's action. The counts shown
    # are distinct workflows, so repeat requests for one workflow count once.
    asked_count = len({str(r.item_id) for r in requests})
    open_count = len({
        str(r.item_id) for r in requests if r.status != VerificationStatus.REJECTED.value
    })
    approved_count = len({
        str(r.item_id) for r in requests if r.status == VerificationStatus.APPROVED.value
    })

    # Users who already earned stars against verified workflows keep them, even
    # if the request record is missing (pre-queue verifications, seeded items).
    verified_count = max(approved_count, sum(1 for wf in workflows if wf.verified))

    detail = f"Asked to share {asked_count} workflow(s) with everyone (need 1+)"
    if requests:
        declined = asked_count - open_count
        if declined:
            detail += f" — {declined} declined by an examiner"
        detail += (
            f" — {verified_count} accepted by an examiner so far; "
            "acceptance is not required to pass"
        )
    checks.append({"name": "Asked to share with everyone", "passed": len(requests) >= 1, "detail": detail})

    passed = all(c["passed"] for c in checks)
    stars = 1 if passed else 0
    if passed and verified_count >= 1:
        stars = 2
    if passed and verified_count >= 2:
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


async def _fire_certification_complete_hooks(user_id: str, *, enrollment_id: str | None = None) -> None:
    """Side-effects for newly certified users: email + in-app notification.

    Never raises — logged and swallowed so that cert completion itself always
    succeeds even if downstream notifications fail.
    """
    from app.models.user import User
    from app.services.engagement_service import send_certification_complete_email_for
    from app.services.notification_service import create_notification

    if enrollment_id:
        from app.config import Settings
        from .certification_versions.completion_notices import CompletionNoticeRepository
        notices = CompletionNoticeRepository()
        try:
            original = await notices.prepare(user_id, enrollment_id)
        except Exception:
            log.exception('Failed to preserve completion notice for %s', user_id)
            return
        try:
            await notices.notify(original)
        except Exception:
            log.exception('Failed to create credential completion notification for %s', user_id)
        try:
            user = await User.find_one(User.user_id == user_id)
            if user:
                await notices.email(original, user, Settings())
        except Exception:
            log.exception('Failed to send credential completion email for %s', user_id)
        return

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
            body="Your course requirements are complete. Open Certification to view your earned certificate and course history.",
            link="/certification",
        )
    except Exception:
        log.exception("Failed to create cert-complete notification for %s", user_id)
