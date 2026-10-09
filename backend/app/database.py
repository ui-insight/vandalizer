import logging

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.user import User
from app.models.team import Team, TeamMembership, TeamInvite, TeamJoinLink
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.search_set import SearchSet, SearchSetItem
from app.models.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowStepTask,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowArtifact,
)
from app.models.system_config import SystemConfig
from app.models.user_config import UserModelConfig
from app.models.chat import ChatMessage, FileAttachment, UrlAttachment, ChatConversation
from app.models.activity import ActivityEvent
from app.models.library import LibraryFolder, LibraryItem, Library
from app.models.feedback import ChatFeedback, ExtractionQualityRecord, ProductFeedback
from app.models.verification import VerificationRequest, VerifiedItemMetadata, VerifiedCollection
from app.models.office import IntakeConfig, WorkItem
from app.models.automation import Automation
from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseReference,
    KnowledgeBaseSource,
    KnowledgeBaseUsage,
)
from app.models.kb_test_query import KBTestQuery
from app.models.kb_optimization_run import KBOptimizationRun
from app.models.kb_suggestion import KBSuggestion
from app.models.extraction_test_case import ExtractionTestCase
from app.models.extraction_optimization_run import ExtractionOptimizationRun
from app.models.workflow_optimization_run import WorkflowOptimizationRun
from app.models.validation_run import ValidationRun
from app.models.kb_validation_task import KBValidationTask
from app.models.automation_launch import AutomationLaunch
from app.models.quality_alert import QualityAlert
from app.models.verification_session import VerificationSession
from app.models.regression_suite_run import RegressionSuiteRun
from app.models.demo import DemoApplication, PostExperienceResponse
from app.models.passive import WorkflowTriggerEvent, ExtractionTriggerEvent, GraphSubscription, M365AuditEntry
from app.models.certification import CertificationProgress, CertificationEnrollment, CertificationEnrollmentSelection, CertificationCredential, CertificationAttempt, CertificationRecoveryRecord, CertificationLabInput, CertificationScenarioAttempt, CertificationLabExecution, CertificationReviewAttempt, CertificationLearnerDecision, CertificationProcessSubmission, CertificationWorkflowDesignSubmission, CertificationUpgradeDecision, CertificationCompletionNotice, CertificationUpgradeActivation, CertificationSavedCourseSelection, CertificationSelectionPreparationRecovery
from app.models.organization import Organization
from app.models.audit_log import AuditLog, AdminAuditLog
from app.models.approval import ApprovalRequest
from app.models.notification import Notification
from app.models.support import SupportTicket, SupportCounter
from app.models.feedback_prompt import FeedbackPrompt, FeedbackPromptResponse
from app.models.user_memory import UserMemory
from app.models.email_log import EmailLog
from app.models.api_key import ApiKey
from app.models.credential import Credential
from app.models.llm_usage import LlmUsageRecord
from app.models.project import Project, ProjectMembership, ProjectPin, ProjectJoinLink
from app.models.telemetry import TelemetryHeartbeat

ALL_MODELS = [
    User,
    Team,
    TeamMembership,
    TeamInvite,
    TeamJoinLink,
    SmartDocument,
    SmartFolder,
    SearchSet,
    SearchSetItem,
    Workflow,
    WorkflowStep,
    WorkflowStepTask,
    WorkflowAttachment,
    WorkflowResult,
    WorkflowArtifact,
    SystemConfig,
    UserModelConfig,
    ChatMessage,
    FileAttachment,
    UrlAttachment,
    ChatConversation,
    ActivityEvent,
    LibraryFolder,
    LibraryItem,
    Library,
    ChatFeedback,
    ExtractionQualityRecord,
    ProductFeedback,
    VerificationRequest,
    VerifiedItemMetadata,
    VerifiedCollection,
    IntakeConfig,
    WorkItem,
    Automation,
    KnowledgeBase,
    KnowledgeBaseReference,
    KnowledgeBaseSource,
    KnowledgeBaseUsage,
    KBTestQuery,
    KBOptimizationRun,
    KBSuggestion,
    ExtractionTestCase,
    ExtractionOptimizationRun,
    WorkflowOptimizationRun,
    ValidationRun,
    KBValidationTask,
    AutomationLaunch,
    QualityAlert,
    VerificationSession,
    RegressionSuiteRun,
    DemoApplication,
    PostExperienceResponse,
    WorkflowTriggerEvent,
    ExtractionTriggerEvent,
    GraphSubscription,
    M365AuditEntry,
    CertificationProgress,
    CertificationEnrollment,
    CertificationEnrollmentSelection,
    CertificationCredential,
    CertificationAttempt,
    CertificationRecoveryRecord,
    CertificationLabInput,
    CertificationScenarioAttempt,
    CertificationLabExecution,
    CertificationReviewAttempt,
    CertificationLearnerDecision,
    CertificationProcessSubmission,
    CertificationWorkflowDesignSubmission,
    CertificationUpgradeDecision,
    CertificationCompletionNotice,
    CertificationUpgradeActivation,
    CertificationSavedCourseSelection,
    CertificationSelectionPreparationRecovery,
    Organization,
    AuditLog,
    AdminAuditLog,
    ApprovalRequest,
    Notification,
    SupportTicket,
    SupportCounter,
    FeedbackPrompt,
    FeedbackPromptResponse,
    UserMemory,
    EmailLog,
    ApiKey,
    Credential,
    LlmUsageRecord,
    Project,
    ProjectMembership,
    ProjectPin,
    ProjectJoinLink,
    TelemetryHeartbeat,
]


logger = logging.getLogger(__name__)

# Process-wide Motor client, created once in init_db() and reused everywhere
# (e.g. the health check). Never construct a new AsyncIOMotorClient per request:
# each one opens sockets + a topology-monitor thread that are not promptly
# reclaimed, exhausting file descriptors in a long-running process.
_client: AsyncIOMotorClient | None = None

# Whether this process has already run Beanie's per-collection index management.
# Index creation is idempotent and only needs to happen once per process (the
# web app ensures it at startup). Re-running it on every short-lived async
# Celery task adds ~one ``listIndexes`` round-trip per model (~18) on top of the
# server handshake — an N+1 in the span waterfall for tasks like
# ``tasks.document.classify``. After the first ensure we auto-skip it.
_indexes_ensured = False

# Whether init_beanie has completed in this process. Beanie's per-model setup
# (settings, fields, caches, actions) is class-level state that a new client
# does not change, yet init_beanie redoes all of it — and issues one
# ``buildInfo`` per model (~70) even with skip_indexes. Every async Celery task
# builds a fresh event loop and therefore a fresh client, so after the first
# full init a task only needs its models pointed at the new client.
_beanie_inited = False


def get_client() -> AsyncIOMotorClient:
    """Return the shared Motor client. Raises if init_db() hasn't run yet."""
    if _client is None:
        raise RuntimeError("Database not initialized; init_db() must run first")
    return _client


async def _run_pre_index_migrations(db) -> None:
    """Data fixes that must land before Beanie builds indexes.

    A unique index declared in a model's ``Settings.indexes`` is built by
    ``init_beanie``; building it over data that already violates it fails,
    and that failure crashes every process at startup. Anything that clears
    such violations runs here, against the raw Motor database, right before
    ``init_beanie``. Each step is best-effort and logged: a step that cannot
    run must not itself block startup, and if duplicates remain the index
    build will say so.

    (The KB source URL unique index takes the other route — built outside
    Beanie by ``knowledge_service.ensure_source_url_unique_index`` after init,
    healing on failure — because deleting a duplicate source also has to drop
    its chunks, which needs the ODM.)
    """
    from app.services.kb_test_query_ids import dedupe_test_query_external_ids

    try:
        cleared = await dedupe_test_query_external_ids(db[KBTestQuery.Settings.name])
        if cleared:
            logger.warning(
                "Cleared duplicate test-query IDs from %d row(s) before building "
                "the (knowledge_base_uuid, external_id) unique index",
                cleared,
            )
    except Exception:
        logger.warning(
            "Pre-index dedup of KB test-query IDs failed; the unique index build "
            "will fail if duplicates remain",
            exc_info=True,
        )


async def init_db(
    settings: Settings, skip_indexes: bool = False, *, warm_pool: bool = False,
) -> None:
    """Initialize the Motor client and Beanie ODM.

    ``skip_indexes=True`` skips Beanie's per-collection index management
    (the ``listIndexes`` round-trips), which is redundant for short-lived
    periodic Celery tasks — indexes are already ensured by the web app startup.

    ``warm_pool=True`` keeps ``minPoolSize`` connections open in the
    background; only the web app, whose client lives as long as the process,
    asks for it. Everything else — every async Celery task builds a client
    for one run — opens connections on demand. A pre-filled pool there opened
    up to ten sockets per task that the task never used, and when Mongo
    stuttered pymongo cancelled the half-open ones and logged "MongoClient
    background task encountered an error: operation cancelled" (Sentry
    7764120249).

    Index management is also skipped automatically once it has run in this
    process (``_indexes_ensured``), so a Celery worker pays the cost on its
    first task only rather than on every task. The web app process runs it once
    at startup so indexes are created/updated on deploy.
    """
    global _client, _indexes_ensured, _beanie_inited
    _client = AsyncIOMotorClient(
        settings.mongo_host,
        maxPoolSize=100,
        minPoolSize=10 if warm_pool else 0,
        maxIdleTimeMS=30000,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=30000,
    )
    effective_skip = skip_indexes or _indexes_ensured
    # Rebinding is only a substitute for a run that would skip indexes anyway:
    # a default call in a process that has not ensured them still does.
    if effective_skip and _beanie_inited and _rebind_models(_client[settings.mongo_db]):
        return
    if not effective_skip:
        await _run_pre_index_migrations(_client[settings.mongo_db])
    await init_beanie(
        database=_client[settings.mongo_db],
        document_models=ALL_MODELS,
        skip_indexes=effective_skip,
    )
    _beanie_inited = True
    if not effective_skip:
        _indexes_ensured = True


def _rebind_models(db) -> bool:
    """Point every already-initialized model at ``db``; False to fall back.

    This is the part of ``init_beanie`` that depends on the client
    (``Initializer.init_document_collection``: ``set_database`` +
    ``set_collection``). It is not valid for time-series or union-document
    models, whose collection setup does more, nor for a model Beanie never
    initialized — any of those, or a Beanie whose internals have moved, falls
    back to the full ``init_beanie``.
    """
    try:
        for model in ALL_MODELS:
            model_settings = model.get_settings()
            if model_settings.timeseries is not None or model_settings.union_doc is not None:
                return False
            if not model_settings.name:
                return False
        for model in ALL_MODELS:
            model.set_database(db)
            model.set_collection(db[model.get_settings().name])
    except Exception:
        logger.warning("Rebinding Beanie models failed; running init_beanie", exc_info=True)
        return False
    return True
