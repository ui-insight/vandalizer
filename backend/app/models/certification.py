import datetime
from typing import Literal, Optional

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class CertificationProgress(Document):
    """Tracks a user's progress through the Vandal Workflow Architect certification."""

    user_id: str
    enrollment_id: Optional[str] = None
    course_version: Optional[str] = None
    lab_folder_id: Optional[str] = None
    learning_position: Optional[dict] = None
    position_revision: int = 0
    pending_credential: Optional[dict] = None
    completion_receipt: Optional[dict] = None
    modules: dict = {}  # {module_id: {completed, stars, completed_at, attempts, xp_earned}}
    total_xp: int = 0
    level: str = "novice"
    certified: bool = False
    certified_at: Optional[datetime.datetime] = None
    # Retired gamification counter — no longer updated or exposed. Kept so
    # existing documents still validate; safe to drop in a future migration.
    streak_days: int = 0
    last_activity_date: Optional[str] = None  # YYYY-MM-DD of last module/assessment activity
    unlocked: bool = False  # Admin debug flag — bypasses module prerequisite gating
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = "certification_progress"


class CertificationEnrollment(Document):
    """Course identity is separate from both user identity and earned progress."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    course_version: str = Field(pattern=r'^[a-z0-9][a-z0-9.-]{0,95}$')
    manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    progress_id: str = Field(pattern=r'^[a-f0-9]{24}$')
    provenance: Literal['new_enrollment', 'legacy_version_unknown', 'explicit_upgrade']
    state: Literal['prepared', 'active', 'completed', 'transferred', 'abandoned'] = 'active'
    source_enrollment_id: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = 'certification_enrollments'
        indexes = [
            IndexModel('uuid', unique=True),
            [('user_id', 1), ('course_version', 1)],
        ]


class CertificationEnrollmentSelection(Document):
    """One explicit active choice per learner; publication never updates this row."""

    user_id: str
    active_enrollment_id: str
    revision: int = 0
    in_flight_writes: int = 0
    active_write: Optional[dict] = None
    last_transition: Optional[dict] = None
    pending_transition_id: Optional[str] = None

    class Settings:
        name = 'certification_enrollment_selections'
        indexes = [IndexModel('user_id', unique=True)]


class CertificationUpgradeDecision(Document):
    """Insert-only explicit preservation choice; never an activation receipt."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    source_enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    target_version: Optional[str] = None
    decision_basis_sha256: Optional[str] = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    class Settings:
        name = 'certification_upgrade_decisions'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('source_enrollment_id', 1)],
                   [('user_id', 1), ('source_enrollment_id', 1), ('target_version', 1), ('decision_basis_sha256', 1)]]


class CertificationUpgradeActivation(Document):
    """Durable activation intent and original selection receipt."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    decision_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['prepared', 'applied'] = 'prepared'
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None

    class Settings:
        name = 'certification_upgrade_activations'
        indexes = [IndexModel('uuid', unique=True), IndexModel('decision_id', unique=True), 'user_id']


class CertificationSavedCourseSelection(Document):
    """Reviewed return/resume within an already activated course pair."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['prepared', 'applied'] = 'prepared'
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None

    class Settings:
        name = 'certification_saved_course_selections'
        indexes = [IndexModel('uuid', unique=True), 'user_id']


class CertificationSelectionPreparationRecovery(Document):
    """Owner-requested fencing of an uncommitted selection preparation only."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['prepared', 'applied'] = 'prepared'
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None

    class Settings:
        name = 'certification_selection_preparation_recoveries'
        indexes = [IndexModel('uuid', unique=True), 'user_id']


class CertificationCompletionNotice(Document):
    """One frozen completion message and automatic email attempt per issuance."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    email_state: Literal['pending', 'sending', 'sent', 'uncertain', 'skipped'] = 'pending'
    notification_created: bool = False

    class Settings:
        name = 'certification_completion_notices'
        indexes = [IndexModel('uuid', unique=True), 'user_id']


class CertificationCredential(Document):
    """Insert-only issuance snapshot; progress is not the download authority."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    record_json: str
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    class Settings:
        name = 'certification_credentials'
        indexes = [IndexModel('uuid', unique=True), IndexModel('enrollment_id', unique=True), 'user_id']


class CertificationAttempt(Document):
    """Pinned completion request and its durable grading/credit receipt."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    rubric_id: str
    artifact_sha256: dict[str, str]
    progress_json: str
    progress_sha256: str
    assessment_selection_json: Optional[str] = None
    assessment_selection_sha256: Optional[str] = None
    transfer_request_json: Optional[str] = None
    transfer_request_sha256: Optional[str] = None
    write_id: Optional[str] = None
    recovery: Optional[dict] = None
    state: Literal['evaluating', 'graded', 'applied', 'rejected', 'failed'] = 'evaluating'
    validation_json: Optional[str] = None
    validation_sha256: Optional[str] = None
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = 'certification_attempts'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('state', 1)],
                   [('user_id', 1), ('enrollment_id', 1), ('created_at', -1), ('uuid', -1)]]


class CertificationScenarioAttempt(Document):
    """Immutable authenticated scenario submission and deterministic result."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    request_sha256: str
    answers_sha256: str | None = None
    record_json: str
    record_sha256: str

    class Settings:
        name = 'certification_scenario_attempts'
        indexes = [IndexModel('uuid', unique=True),
                   IndexModel('answers_sha256', unique=True, partialFilterExpression={'answers_sha256': {'$type': 'string'}}),
                   [('user_id', 1), ('enrollment_id', 1), ('module_id', 1)]]


class CertificationLabInput(Document):
    """Insert-only inputs captured before an assessed execution is dispatched."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    artifact_id: str
    record_json: str
    record_sha256: str

    class Settings:
        name = 'certification_lab_inputs'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1)]]


class CertificationLabExecution(Document):
    """Pinned dispatch intent with one immutable terminal execution receipt."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    input_snapshot_id: str
    plan_json: str
    plan_sha256: str
    state: Literal['prepared', 'executing', 'completed', 'failed', 'uncertain'] = 'prepared'
    worker_id: Optional[str] = None
    scope_decision_id: Optional[str] = None
    scope_decision_sha256: Optional[str] = None
    authorization_json: Optional[str] = None
    authorization_sha256: Optional[str] = None
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None
    stage_events_json: Optional[str] = None
    stage_events_sha256: Optional[str] = None
    stage_event_count: int = Field(default=0, ge=0, le=6)

    class Settings:
        name = 'certification_lab_executions'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('input_snapshot_id', 1)],
                   [('user_id', 1), ('enrollment_id', 1), ('state', 1), ('_id', -1)],
                   [('user_id', 1), ('enrollment_id', 1), ('_id', -1)]]


class CertificationLearnerDecision(Document):
    """Immutable authenticated practical decision, separate from its grade."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    run_id: str
    prompt_id: str
    request_sha256: str
    record_json: str
    record_sha256: str

    class Settings:
        name = 'certification_learner_decisions'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('run_id', 1)],
                   [('user_id', 1), ('enrollment_id', 1), ('prompt_id', 1), ('_id', -1)]]


class CertificationReviewAttempt(Document):
    """Immutable review inputs with a single persisted automatic judgment."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    request_sha256: str
    evidence_request_sha256: Optional[str] = None
    record_json: str
    record_sha256: str
    parent_attempt_id: Optional[str] = None
    state: Literal['prepared', 'evaluating', 'evaluated', 'unavailable'] = 'prepared'
    worker_id: Optional[str] = None
    review_started_at: Optional[datetime.datetime] = None
    review_deadline_at: Optional[datetime.datetime] = None
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None

    class Settings:
        name = 'certification_review_attempts'
        indexes = [IndexModel('uuid', unique=True),
                   IndexModel('evidence_request_sha256', unique=True, partialFilterExpression={'evidence_request_sha256': {'$type': 'string'}}),
                   IndexModel('parent_attempt_id', unique=True, partialFilterExpression={'parent_attempt_id': {'$type': 'string'}}),
                   [('user_id', 1), ('enrollment_id', 1), ('module_id', 1)],
                   [('user_id', 1), ('enrollment_id', 1), ('state', 1), ('_id', -1)],
                   [('user_id', 1), ('enrollment_id', 1), ('_id', -1)]]


class CertificationRecoveryRecord(Document):
    """Durable reviewed recovery intent and immutable terminal receipt."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    actor_user_id: str
    request_json: str
    request_sha256: str
    review_json: str
    review_sha256: str
    state: Literal['started', 'completed'] = 'started'
    result_json: Optional[str] = None
    result_sha256: Optional[str] = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc))

    class Settings:
        name = 'certification_recoveries'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('created_at', -1)]]


class CertificationProcessSubmission(Document):
    """Immutable learner process design; submission does not award competence."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    request_sha256: str
    record_json: str
    record_sha256: str

    class Settings:
        name = 'certification_process_submissions'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('module_id', 1)]]


class CertificationWorkflowDesignSubmission(Document):
    """Immutable approval and decisions bound to a captured workflow revision."""

    uuid: str = Field(pattern=r'^[a-f0-9]{32}$')
    user_id: str
    enrollment_id: str
    module_id: str
    course_version: str
    manifest_sha256: str
    request_sha256: str
    record_json: str
    record_sha256: str

    class Settings:
        name = 'certification_workflow_design_submissions'
        indexes = [IndexModel('uuid', unique=True), [('user_id', 1), ('enrollment_id', 1), ('module_id', 1)]]
