"""Account deletion service — removes all user-owned data."""

import asyncio
import logging

from app.config import Settings

logger = logging.getLogger(__name__)


async def get_deletion_summary(user_id: str) -> dict:
    """Pre-flight check: count user-owned data and identify blocking conditions."""
    from app.models.document import SmartDocument
    from app.models.folder import SmartFolder
    from app.models.chat import ChatConversation
    from app.models.workflow import Workflow
    from app.models.search_set import SearchSet
    from app.models.knowledge import KnowledgeBase
    from app.models.team import Team, TeamMembership

    docs = await SmartDocument.find(
        SmartDocument.user_id == user_id,
        SmartDocument.soft_deleted != True,  # noqa: E712
    ).count()
    folders = await SmartFolder.find(SmartFolder.user_id == user_id).count()
    conversations = await ChatConversation.find(ChatConversation.user_id == user_id).count()
    workflows = await Workflow.find(Workflow.user_id == user_id).count()
    search_sets = await SearchSet.find(SearchSet.user_id == user_id).count()
    knowledge_bases = await KnowledgeBase.find(KnowledgeBase.user_id == user_id).count()

    memberships = await TeamMembership.find(TeamMembership.user_id == user_id).to_list()
    owned_teams = await Team.find(Team.owner_user_id == user_id).to_list()

    # Check for blocking conditions: owned teams with other members
    blocking_teams = []
    for team in owned_teams:
        member_count = await TeamMembership.find(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id != user_id,
        ).count()
        if member_count > 0:
            blocking_teams.append({
                "uuid": team.uuid,
                "name": team.name,
                "member_count": member_count,
            })

    return {
        "can_delete": len(blocking_teams) == 0,
        "blocking_reason": (
            "You own teams with other members. Transfer ownership or delete these teams first."
            if blocking_teams else None
        ),
        "data_summary": {
            "documents": docs,
            "folders": folders,
            "chat_conversations": conversations,
            "workflows": workflows,
            "search_sets": search_sets,
            "knowledge_bases": knowledge_bases,
            "teams_owned": len(owned_teams),
            "teams_member": len(memberships),
        },
        "owned_teams_with_members": blocking_teams,
    }


async def delete_user_account(user_id: str) -> None:
    """Delete all data owned by a user, then delete the user record.

    Must be called with Beanie already initialized.
    """
    from app.models.user import User
    from app.models.document import SmartDocument
    from app.models.folder import SmartFolder
    from app.models.chat import ChatConversation, ChatMessage, FileAttachment, UrlAttachment
    from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask, WorkflowResult
    from app.models.search_set import SearchSet, SearchSetItem
    from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
    from app.models.team import Team, TeamMembership
    from app.models.library import Library, LibraryItem, LibraryFolder
    from app.services.storage import get_storage

    settings = Settings()
    storage = get_storage(settings)

    user = await User.find_one(User.user_id == user_id)
    if not user:
        logger.warning("User %s not found for deletion", user_id)
        return

    logger.info("Starting account deletion for user %s", user_id)

    # 1. Delete documents + files from storage
    documents = await SmartDocument.find(SmartDocument.user_id == user_id).to_list()
    for doc in documents:
        try:
            path = doc.downloadpath or doc.path
            if path:
                await storage.delete(path)
        except Exception as e:
            logger.warning("Failed to delete file for doc %s: %s", doc.uuid, e)
    if documents:
        await SmartDocument.find(SmartDocument.user_id == user_id).delete()
        logger.info("Deleted %d documents", len(documents))

    # 2. Delete ChromaDB user collection
    try:
        from app.services.document_manager import DocumentManager
        dm = DocumentManager(persist_directory=settings.chromadb_persist_dir)
        collection_name = f"user_{user_id}_docs"
        dm.client.delete_collection(name=collection_name)
        logger.info("Deleted ChromaDB collection %s", collection_name)
    except Exception as e:
        logger.warning("Failed to delete ChromaDB user collection: %s", e)

    # 3. Delete knowledge bases + their ChromaDB collections
    kbs = await KnowledgeBase.find(KnowledgeBase.user_id == user_id).to_list()
    for kb in kbs:
        try:
            dm = DocumentManager(persist_directory=settings.chromadb_persist_dir)
            dm.delete_kb_collection(kb.uuid)
        except Exception as e:
            logger.warning("Failed to delete KB ChromaDB collection %s: %s", kb.uuid, e)
        await KnowledgeBaseSource.find(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid
        ).delete()
    if kbs:
        await KnowledgeBase.find(KnowledgeBase.user_id == user_id).delete()
        logger.info("Deleted %d knowledge bases", len(kbs))

    # 4. Delete folders
    await SmartFolder.find(SmartFolder.user_id == user_id).delete()

    # 5. Delete workflows (cascade: steps, tasks, results)
    workflows = await Workflow.find(Workflow.user_id == user_id).to_list()
    for wf in workflows:
        steps = await WorkflowStep.find({"_id": {"$in": wf.steps}}).to_list()
        for step in steps:
            await WorkflowStepTask.find({"_id": {"$in": step.tasks}}).delete()
        await WorkflowStep.find({"_id": {"$in": wf.steps}}).delete()
        await WorkflowResult.find(WorkflowResult.workflow_id == wf.id).delete()
    if workflows:
        await Workflow.find(Workflow.user_id == user_id).delete()
        logger.info("Deleted %d workflows", len(workflows))

    # 6. Delete search sets + items
    search_sets = await SearchSet.find(SearchSet.user_id == user_id).to_list()
    for ss in search_sets:
        await SearchSetItem.find(SearchSetItem.searchset == ss.uuid).delete()
    if search_sets:
        await SearchSet.find(SearchSet.user_id == user_id).delete()

    # 7. Delete chat data (messages referenced by conversation.messages list)
    conversations = await ChatConversation.find(
        ChatConversation.user_id == user_id
    ).to_list()
    for conv in conversations:
        if conv.messages:
            await ChatMessage.find({"_id": {"$in": conv.messages}}).delete()
    if conversations:
        await ChatConversation.find(ChatConversation.user_id == user_id).delete()
    await FileAttachment.find(FileAttachment.user_id == user_id).delete()
    await UrlAttachment.find(UrlAttachment.user_id == user_id).delete()

    # 8. Delete team memberships + owned teams (without other members)
    await TeamMembership.find(TeamMembership.user_id == user_id).delete()
    owned_teams = await Team.find(Team.owner_user_id == user_id).to_list()
    for team in owned_teams:
        remaining = await TeamMembership.find(TeamMembership.team_id == team.id).count()
        if remaining == 0:
            await team.delete()

    # 9. Delete library data
    libs = await Library.find(Library.owner_user_id == user_id).to_list()
    for lib in libs:
        await LibraryItem.find({"_id": {"$in": lib.items}}).delete()
        await lib.delete()
    await LibraryFolder.find(LibraryFolder.owner_user_id == user_id).delete()

    # 10. Delete remaining ancillary data (best-effort, skip missing collections)
    ancillary_deletions = [
        ("activity_event", {"user_id": user_id}),
        ("automation", {"user_id": user_id}),
        ("notification", {"user_id": user_id}),
        ("support_ticket", {"user_id": user_id}),
        ("certification_progress", {"user_id": user_id}),
        ("user_model_config", {"user_id": user_id}),
        ("knowledge_base_references", {"user_id": user_id}),
        ("chat_feedback", {"user_id": user_id}),
        ("extraction_quality_record", {"user_id": user_id}),
        ("extraction_test_cases", {"user_id": user_id}),
        ("validation_runs", {"user_id": user_id}),
        ("kb_suggestions", {"suggested_by_user_id": user_id}),
        ("kb_test_queries", {"user_id": user_id}),
        ("intake_configs", {"owner_user_id": user_id}),
        ("work_items", {"owner_user_id": user_id}),
        ("team_invite", {"invited_by_user_id": user_id}),
        ("graph_subscriptions", {"owner_user_id": user_id}),
        ("demo_application", {"user_id": user_id}),
        ("workflow_attachment", {"user_id": user_id}),
        ("workflow_artifacts", {"user_id": user_id}),
    ]
    db = user.get_motor_collection().database
    for collection_name, query in ancillary_deletions:
        try:
            await db[collection_name].delete_many(query)
        except Exception:
            pass  # collection may not exist

    # 11. Anonymize audit logs
    try:
        await db["audit_log"].update_many(
            {"actor_user_id": user_id},
            {"$set": {"actor_user_id": "[deleted]"}},
        )
        await db["admin_audit_log"].update_many(
            {"user_id": user_id},
            {"$set": {"user_id": "[deleted]"}},
        )
    except Exception:
        pass

    # 12. Log the deletion event before removing the user
    from app.services import audit_service
    await audit_service.log_event(
        action="user.account_deleted",
        actor_user_id="[deleted]",
        resource_type="user",
        resource_id=user_id,
    )

    # 13. Delete the user record
    await user.delete()
    logger.info("Account deletion complete for user %s", user_id)
