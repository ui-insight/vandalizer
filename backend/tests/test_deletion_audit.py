"""Deletions must be written to the audit log with actor, resource, and detail.

Covers the support-ticket gap: document, folder (with doc count), knowledge
base, credential, extraction (search set), automation, chat, and library item
removals each emit an audit event.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import PydanticObjectId

from app.models.library import LibraryItemKind, LibraryScope


def _user(user_id="u1"):
    user = MagicMock()
    user.user_id = user_id
    user.is_admin = False
    return user


class TestDocumentDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_document_delete(self):
        from app.services import file_service

        user = _user()
        doc = MagicMock()
        doc.uuid = "doc-1"
        doc.title = "Budget.pdf"
        doc.team_id = "team-1"
        doc.folder = "folder-1"
        doc.downloadpath = None
        doc.path = None
        doc.delete = AsyncMock()

        with patch.object(file_service.access_control, "get_authorized_document", AsyncMock(return_value=doc)), \
             patch.object(file_service.audit_service, "log_event", new_callable=AsyncMock) as log:
            ok = await file_service.delete_document("doc-1", MagicMock(), user=user)

        assert ok is True
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "document.delete"
        assert kwargs["actor_user_id"] == "u1"
        assert kwargs["resource_id"] == "doc-1"
        assert kwargs["resource_name"] == "Budget.pdf"
        assert kwargs["team_id"] == "team-1"

    @pytest.mark.asyncio
    async def test_no_log_when_document_not_found(self):
        from app.services import file_service

        with patch.object(file_service.access_control, "get_authorized_document", AsyncMock(return_value=None)), \
             patch.object(file_service.audit_service, "log_event", new_callable=AsyncMock) as log:
            ok = await file_service.delete_document("missing", MagicMock(), user=_user())

        assert ok is False
        log.assert_not_awaited()


class TestFolderDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_folder_delete_with_document_count(self):
        from app.services import folder_service

        user = _user()
        folder = MagicMock()
        folder.uuid = "folder-1"
        folder.title = "Grants"
        folder.team_id = None
        folder.is_shared_team_root = False

        # One subfolder level, then no more children.
        child = MagicMock(uuid="child-1")
        children_find = MagicMock()
        children_find.to_list = AsyncMock(side_effect=[[child], []])
        folder_delete_find = MagicMock()
        folder_delete_find.delete = AsyncMock()
        folder_find = MagicMock(side_effect=[children_find, children_find, folder_delete_find])

        doc_find = MagicMock()
        doc_find.count = AsyncMock(return_value=7)
        doc_find.delete = AsyncMock()

        with patch.object(folder_service.access_control, "get_authorized_folder", AsyncMock(return_value=folder)), \
             patch.object(folder_service, "SmartFolder", MagicMock(find=folder_find)), \
             patch.object(folder_service, "SmartDocument", MagicMock(find=MagicMock(return_value=doc_find))), \
             patch.object(folder_service.audit_service, "log_event", new_callable=AsyncMock) as log:
            ok = await folder_service.delete_folder("folder-1", user)

        assert ok is True
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "folder.delete"
        assert kwargs["resource_name"] == "Grants"
        assert kwargs["detail"] == {"documents_deleted": 7, "subfolders_deleted": 1}


class TestKnowledgeBaseDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_knowledge_base_delete(self):
        from app.services import knowledge_service

        user = _user()
        kb = MagicMock()
        kb.uuid = "kb-1"
        kb.title = "Uniform Guidance"
        kb.team_id = "team-1"
        kb.shared_with_team = False
        kb.verified = True
        kb.total_sources = 12
        kb.delete = AsyncMock()

        sources_find = MagicMock()
        sources_find.delete = AsyncMock()

        with patch.object(knowledge_service, "get_knowledge_base", AsyncMock(return_value=kb)), \
             patch.object(knowledge_service, "_get_dm", MagicMock(return_value=MagicMock())), \
             patch.object(knowledge_service, "KnowledgeBaseSource", MagicMock(find=MagicMock(return_value=sources_find))), \
             patch.object(knowledge_service, "KnowledgeBaseReference", MagicMock(find=MagicMock(return_value=sources_find))), \
             patch.object(knowledge_service.audit_service, "log_event", new_callable=AsyncMock) as log:
            ok = await knowledge_service.delete_knowledge_base("kb-1", user)

        assert ok is True
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "knowledge_base.delete"
        assert kwargs["resource_name"] == "Uniform Guidance"
        assert kwargs["detail"]["verified"] is True
        assert kwargs["detail"]["total_sources"] == 12


class TestLibraryItemRemoveAudit:
    @pytest.mark.asyncio
    async def test_logs_library_item_remove(self):
        from app.services import library_service

        user = _user()
        item_oid = PydanticObjectId()
        lib = MagicMock()
        lib.title = "Verified Catalog"
        lib.scope = LibraryScope.VERIFIED
        lib.items = [item_oid]
        lib.save = AsyncMock()

        item = MagicMock()
        item.kind = LibraryItemKind.WORKFLOW
        item.delete = AsyncMock()

        with patch.object(library_service.access_control, "get_authorized_library", AsyncMock(return_value=lib)), \
             patch.object(library_service, "LibraryItem", MagicMock(get=AsyncMock(return_value=item))), \
             patch.object(library_service, "_dereference_item", AsyncMock(return_value={"name": "Award Setup"})), \
             patch.object(library_service.audit_service, "log_event", new_callable=AsyncMock) as log:
            ok = await library_service.remove_item("lib-1", str(item_oid), user)

        assert ok is True
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "library_item.remove"
        assert kwargs["resource_name"] == "Award Setup"
        assert kwargs["detail"] == {
            "library": "Verified Catalog",
            "library_scope": "verified",
            "kind": "workflow",
        }


class TestCredentialDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_credential_delete(self):
        from app.routers import credentials as cred_router

        user = _user()
        cred = MagicMock()
        cred.id = "cred-1"
        cred.name = "Lakehouse API"
        cred.type = "static_header"
        cred.team_id = None
        cred.delete = AsyncMock()

        with patch.object(cred_router, "_load_for_manage", AsyncMock(return_value=cred)), \
             patch.object(cred_router.credentials_service, "invalidate_cached_token", MagicMock()), \
             patch.object(cred_router.audit_service, "log_event", new_callable=AsyncMock) as log:
            resp = await cred_router.delete_credential("cred-1", user)

        assert resp["status"] == "deleted"
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "credential.delete"
        assert kwargs["resource_name"] == "Lakehouse API"
        assert kwargs["detail"] == {"credential_type": "static_header"}
        # Never include secret material in the audit trail.
        assert "payload" not in kwargs.get("detail", {})


class TestExtractionDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_extraction_delete(self):
        from app.routers import extractions as ext_router

        user = _user()
        ss = MagicMock()
        ss.title = "Award Terms"
        ss.team_id = "team-1"

        with patch.object(ext_router, "_get_search_set_or_404", AsyncMock(return_value=ss)), \
             patch.object(ext_router.svc, "delete_search_set", AsyncMock(return_value=True)), \
             patch.object(ext_router.audit_service, "log_event", new_callable=AsyncMock) as log:
            resp = await ext_router.delete_search_set("ss-1", user)

        assert resp == {"ok": True}
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "extraction.delete"
        assert kwargs["resource_id"] == "ss-1"
        assert kwargs["resource_name"] == "Award Terms"


class TestAutomationDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_automation_delete(self):
        from app.routers import automations as auto_router

        user = _user()
        auto = MagicMock()
        auto.name = "Watch RFP folder"
        auto.team_id = None
        auto.trigger_type = "folder_watch"
        auto.action_type = "workflow"
        auto.delete = AsyncMock()

        with patch.object(auto_router, "_load_authorized_automation", AsyncMock(return_value=(auto, None))), \
             patch.object(auto_router.audit_service, "log_event", new_callable=AsyncMock) as log:
            resp = await auto_router.delete_automation("auto-1", user)

        assert resp == {"ok": True}
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "automation.delete"
        assert kwargs["resource_name"] == "Watch RFP folder"
        assert kwargs["detail"] == {"trigger_type": "folder_watch", "action_type": "workflow"}


class TestChatDeleteAudit:
    @pytest.mark.asyncio
    async def test_logs_chat_delete_with_message_count(self):
        from app.routers import chat as chat_router

        user = _user()
        conversation = MagicMock()
        conversation.uuid = "conv-1"
        conversation.title = "F&A rate questions"
        conversation.team_id = None
        conversation.messages = [PydanticObjectId(), PydanticObjectId()]
        conversation.file_attachments = []
        conversation.url_attachments = []
        conversation.delete = AsyncMock()

        messages_find = MagicMock()
        messages_find.delete = AsyncMock()

        with patch.object(chat_router, "ChatConversation", MagicMock(find_one=AsyncMock(return_value=conversation))), \
             patch.object(chat_router, "ChatMessage", MagicMock(find=MagicMock(return_value=messages_find))), \
             patch.object(chat_router.audit_service, "log_event", new_callable=AsyncMock) as log:
            resp = await chat_router.delete_chat_history("conv-1", user)

        assert resp["success"] is True
        log.assert_awaited_once()
        kwargs = log.call_args.kwargs
        assert kwargs["action"] == "chat.delete"
        assert kwargs["resource_id"] == "conv-1"
        assert kwargs["detail"] == {"messages_deleted": 2}
