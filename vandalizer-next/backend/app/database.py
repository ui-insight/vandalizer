from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.user import User
from app.models.team import Team, TeamMembership, TeamInvite
from app.models.document import SmartDocument
from app.models.folder import SmartFolder
from app.models.space import Space
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
from app.models.feedback import ChatFeedback, ExtractionQualityRecord
from app.models.verification import VerificationRequest, VerifiedItemMetadata, VerifiedCollection
from app.models.office import IntakeConfig, WorkItem
from app.models.automation import Automation
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.models.group import Group, GroupMembership
from app.models.extraction_test_case import ExtractionTestCase

ALL_MODELS = [
    User,
    Team,
    TeamMembership,
    TeamInvite,
    SmartDocument,
    SmartFolder,
    Space,
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
    VerificationRequest,
    VerifiedItemMetadata,
    VerifiedCollection,
    IntakeConfig,
    WorkItem,
    Automation,
    KnowledgeBase,
    KnowledgeBaseSource,
    Group,
    GroupMembership,
    ExtractionTestCase,
]


async def init_db(settings: Settings) -> None:
    client = AsyncIOMotorClient(settings.mongo_host)
    await init_beanie(
        database=client[settings.mongo_db],
        document_models=ALL_MODELS,
    )
