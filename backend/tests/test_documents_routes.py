"""Integration tests for documents router.

Verifies team membership validation and auth enforcement.
"""

import secrets
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.access_control import TeamAccessContext
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser", current_team=None):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = current_team
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _make_document(
    doc_uuid="doc-uuid",
    *,
    user_id="testuser",
    team_id=None,
    title="Test Document",
    classification=None,
    retention_hold=False,
    task_status="complete",
    processing=False,
    extraction_nonletter_ratio=None,
    text_layer_rejected=False,
    extension="pdf",
    updated_at=None,
):
    doc = MagicMock()
    doc.uuid = doc_uuid
    doc.user_id = user_id
    doc.team_id = team_id
    doc.title = title
    doc.classification = classification
    doc.classification_confidence = None
    doc.classified_at = None
    doc.classified_by = None
    doc.retention_hold = retention_hold
    doc.retention_hold_reason = None
    doc.scheduled_deletion_at = "scheduled" if retention_hold else None
    # Explicit rather than MagicMock attributes: the retry route reads these
    # to decide whether to force OCR and whether a run is already in flight,
    # and a MagicMock is truthy and uncomparable.
    doc.task_status = task_status
    doc.processing = processing
    doc.extraction_nonletter_ratio = extraction_nonletter_ratio
    doc.text_layer_rejected = text_layer_rejected
    doc.extension = extension
    doc.updated_at = datetime.now() if updated_at is None else updated_at
    doc.created_at = doc.updated_at
    doc.save = AsyncMock()
    return doc


def _team_access(*, roles_by_uuid=None):
    roles_by_uuid = roles_by_uuid or {}
    return TeamAccessContext(
        team_uuids=set(roles_by_uuid.keys()),
        team_object_ids=set(),
        roles_by_uuid=roles_by_uuid,
        roles_by_object_id={},
    )


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestDocumentListAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client):
        resp = await client.get("/api/documents/list")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_own_documents_allowed(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.document_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.list_contents = AsyncMock(return_value={"folders": [], "documents": []})

            resp = await client.get(
                "/api/documents/list",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        # Verify the current user object was passed through
        mock_svc.list_contents.assert_called_once()
        call_kwargs = mock_svc.list_contents.call_args
        assert call_kwargs.kwargs.get("user") is user


class TestDocumentTeamValidation:
    @pytest.mark.asyncio
    async def test_non_member_team_uuid_rejected(self, client):
        """User not in a team cannot access that team's documents."""
        user = _make_user()
        cookies, headers = _auth()

        mock_team = MagicMock()
        mock_team.id = "team-obj-id"
        mock_team.uuid = "other-team-uuid"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.Team") as MockTeam, \
             patch("app.routers.documents.TeamMembership") as MockMembership:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=mock_team)
            MockMembership.find_one = AsyncMock(return_value=None)  # not a member

            resp = await client.get(
                "/api/documents/list?team_uuid=other-team-uuid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert "Not a member" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_team_member_allowed(self, client):
        """User who is a team member can access that team's documents."""
        user = _make_user()
        cookies, headers = _auth()

        mock_team = MagicMock()
        mock_team.id = "team-obj-id"
        mock_team.uuid = "my-team-uuid"

        mock_membership = MagicMock()
        mock_membership.role = "member"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.Team") as MockTeam, \
             patch("app.routers.documents.TeamMembership") as MockMembership, \
             patch("app.routers.documents.document_service") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            MockTeam.find_one = AsyncMock(return_value=mock_team)
            MockMembership.find_one = AsyncMock(return_value=mock_membership)
            mock_svc.list_contents = AsyncMock(return_value={"folders": [], "documents": []})

            resp = await client.get(
                "/api/documents/list?team_uuid=my-team-uuid",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200


class TestDocumentSearch:
    @pytest.mark.asyncio
    async def test_search_unauthenticated(self, client):
        resp = await client.get("/api/documents/search?q=test")
        assert resp.status_code == 401


class TestDocumentGovernanceAuth:
    @pytest.mark.asyncio
    async def test_owner_can_reclassify_personal_document(self, client):
        user = _make_user("owner1")
        doc = _make_document(doc_uuid="doc-1", user_id="owner1")
        cookies, headers = _auth("owner1")

        with patch("app.dependencies.decode_token", return_value={"sub": "owner1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-1/classify",
                json={"classification": "ferpa", "reason": "Contains student records"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["classification"] == "ferpa"
        assert resp.json()["classified_by"] == "owner1"
        assert doc.classification == "ferpa"
        assert doc.classified_by == "owner1"
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_users_personal_document_cannot_be_reclassified(self, client):
        user = _make_user("outsider")
        doc = _make_document(doc_uuid="doc-2", user_id="owner1")
        cookies, headers = _auth("outsider")

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-2/classify",
                json={"classification": "internal"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        doc.save.assert_not_awaited()
        mock_log_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_member_cannot_reclassify_other_teams_document(self, client):
        user = _make_user("outsider")
        doc = _make_document(doc_uuid="doc-3", user_id="owner1", team_id="team-abc")
        cookies, headers = _auth("outsider")

        with patch("app.dependencies.decode_token", return_value={"sub": "outsider", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.patch(
                "/api/documents/doc-3/classify",
                json={"classification": "internal"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        doc.save.assert_not_awaited()
        mock_log_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_team_admin_can_reclassify_team_document(self, client):
        user = _make_user("team-admin")
        doc = _make_document(doc_uuid="doc-4", user_id="owner1", team_id="team-abc")
        cookies, headers = _auth("team-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access(roles_by_uuid={"team-abc": "admin"})

            resp = await client.patch(
                "/api/documents/doc-4/classify",
                json={"classification": "cui", "reason": "Contains export-controlled details"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["classification"] == "cui"
        assert doc.classification == "cui"
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_admin_owner_cannot_apply_retention_hold(self, client):
        user = _make_user("owner1")
        cookies, headers = _auth("owner1")

        with patch("app.dependencies.decode_token", return_value={"sub": "owner1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/doc-5/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        mock_get_doc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_admin_team_admin_cannot_apply_retention_hold(self, client):
        user = _make_user("team-admin")
        cookies, headers = _auth("team-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/documents/doc-6/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        mock_get_doc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_can_apply_retention_hold_to_another_users_document(self, client):
        user = _make_user("platform-admin")
        user.is_admin = True
        doc = _make_document(doc_uuid="doc-7", user_id="owner1")
        cookies, headers = _auth("platform-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "platform-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.post(
                "/api/documents/doc-7/retention-hold",
                json={"reason": "Preserve for litigation"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["retention_hold"] is True
        assert doc.retention_hold is True
        assert doc.retention_hold_reason == "Preserve for litigation"
        assert doc.scheduled_deletion_at is None
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_can_remove_retention_hold_from_other_teams_document(self, client):
        user = _make_user("platform-admin")
        user.is_admin = True
        doc = _make_document(
            doc_uuid="doc-8",
            user_id="owner1",
            team_id="team-abc",
            retention_hold=True,
        )
        doc.retention_hold_reason = "Existing hold"
        cookies, headers = _auth("platform-admin")

        with patch("app.dependencies.decode_token", return_value={"sub": "platform-admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.access_control.SmartDocument") as MockDocument, \
             patch("app.services.access_control.get_team_access_context", new_callable=AsyncMock) as mock_team_access, \
             patch("app.routers.documents.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            MockDocument.find_one = AsyncMock(return_value=doc)
            MockDocument.uuid = "uuid"
            mock_team_access.return_value = _team_access()

            resp = await client.delete(
                "/api/documents/doc-8/retention-hold",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["retention_hold"] is False
        assert doc.retention_hold is False
        assert doc.retention_hold_reason is None
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()


class TestRetryExtractionRoute:
    """A retry re-reads the pages with OCR when the previous extraction failed
    or produced unreadable text, and re-reads a healthy document the ordinary
    way — an OCR round-trip to get back text that was already fine is pure
    cost, and on a busy deployment it is cost per impatient click."""

    async def _post(self, client, doc):
        user = _make_user("owner1")
        doc.path = "uploads/doc-1.pdf"
        cookies, headers = _auth("owner1")

        with patch("app.dependencies.decode_token", return_value={"sub": "owner1", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.documents.access_control.get_authorized_document", new_callable=AsyncMock) as mock_get_doc, \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-id-123") as mock_dispatch, \
             patch("app.services.audit_service.log_event", new_callable=AsyncMock) as mock_log_event:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_doc.return_value = doc

            resp = await client.post(
                "/api/documents/doc-1/retry-extraction",
                cookies=cookies,
                headers=headers,
            )
        return resp, mock_dispatch, mock_log_event

    @pytest.mark.asyncio
    async def test_errored_document_is_re_read_with_ocr(self, client):
        doc = _make_document(doc_uuid="doc-1", user_id="owner1", task_status="error")
        resp, mock_dispatch, mock_log_event = await self._post(client, doc)

        assert resp.status_code == 200
        assert resp.json() == {"uuid": "doc-1", "task_id": "task-id-123", "status": "extracting"}
        mock_dispatch.assert_called_once()
        assert mock_dispatch.call_args.kwargs["force_ocr"] is True
        # An errored document has no stored text to re-store, so the reader's
        # outage fallback is still the right answer for it.
        assert mock_dispatch.call_args.kwargs["ocr_required"] is False
        doc.save.assert_awaited_once()
        mock_log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_low_quality_document_is_re_read_with_ocr(self, client):
        """The garbled text layer that motivated #858 succeeds — the document
        is not in an error state, it just holds mojibake — so the error status
        alone would never force OCR for it."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="complete", extraction_nonletter_ratio=0.95,
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 200
        assert mock_dispatch.call_args.kwargs["force_ocr"] is True
        # And this is the one retry that may not fall back: the local reading
        # of these pages is the text being replaced.
        assert mock_dispatch.call_args.kwargs["ocr_required"] is True

    @pytest.mark.asyncio
    async def test_the_refusal_is_recorded_on_the_document(self, client):
        """The ratio that proves the stored text was garbage is cleared by
        this very dispatch, and every error write clears it too — so if the
        OCR-required run fails, the next click would read a document with
        nothing left to justify requiring OCR and would happily re-store the
        mojibake. The refusal is written down instead."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="complete", extraction_nonletter_ratio=0.95,
        )
        resp, _, _ = await self._post(client, doc)

        assert resp.status_code == 200
        assert doc.text_layer_rejected is True
        doc.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_previously_refused_layer_still_requires_ocr(self, client):
        """The second click of the loop: the first OCR-required retry failed,
        so the document is in the error state with its ratio nulled. Without
        the remembered refusal this is an ordinary errored document and the
        re-read may fall back to the very text layer that was refused."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="error", extraction_nonletter_ratio=None,
            text_layer_rejected=True,
        )
        resp, mock_dispatch, mock_log_event = await self._post(client, doc)

        assert resp.status_code == 200
        assert mock_dispatch.call_args.kwargs["force_ocr"] is True
        assert mock_dispatch.call_args.kwargs["ocr_required"] is True
        assert mock_log_event.call_args.kwargs["detail"] == {
            "force_ocr": True,
            "ocr_required": True,
            "previous_task_status": "error",
        }

    @pytest.mark.asyncio
    async def test_a_low_quality_non_pdf_carries_neither_flag(self, client):
        """Both flags are PDF-only: the extraction task forwards them to the
        PDF reader and nowhere else, so setting them for a DOCX would record
        an OCR requirement in the audit log that nothing ever applied."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1", extension="docx",
            task_status="error", extraction_nonletter_ratio=0.95,
        )
        resp, mock_dispatch, mock_log_event = await self._post(client, doc)

        assert resp.status_code == 200
        assert mock_dispatch.call_args.kwargs["force_ocr"] is False
        assert mock_dispatch.call_args.kwargs["ocr_required"] is False
        assert mock_log_event.call_args.kwargs["detail"] == {
            "force_ocr": False,
            "ocr_required": False,
            "previous_task_status": "error",
        }
        assert doc.text_layer_rejected is False

    @pytest.mark.asyncio
    async def test_healthy_document_is_re_read_the_ordinary_way(self, client):
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="complete", extraction_nonletter_ratio=0.01,
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 200
        assert mock_dispatch.call_args.kwargs["force_ocr"] is False
        assert mock_dispatch.call_args.kwargs["ocr_required"] is False

    @pytest.mark.asyncio
    async def test_document_already_processing_is_rejected(self, client):
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="extracting", processing=True,
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"]
        mock_dispatch.assert_not_called()
        doc.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_in_flight_extraction_can_be_retried(self, client):
        """processing=True, task_status="extracting", raw_text="" is the
        shape this route writes and no sweeper repairs; once the lock is
        older than the window the worker is presumed dead, and the route
        must not be the reason the document stays at "Reading text…"."""
        from app.services.extraction_staleness import EXTRACTION_STALE_AFTER

        # One minute past the shared window: the same age the reap_stuck
        # sweep marks the document failed at, so route and reaper can never
        # disagree about whether this lock is alive.
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="extracting", processing=True,
            updated_at=datetime.now() - EXTRACTION_STALE_AFTER - timedelta(minutes=1),
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 200
        mock_dispatch.assert_called_once()
        doc.save.assert_awaited_once()
        # The new lock is stamped, so a second retry inside the window is a 409.
        assert datetime.now() - doc.updated_at < timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_in_flight_extraction_inside_the_window_is_still_rejected(self, client):
        """A lock younger than the shared window is presumed live — the
        worker may still be reading a large OCR job — so a retry would put
        a second extraction on the same document."""
        from app.services.extraction_staleness import EXTRACTION_STALE_AFTER

        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="extracting", processing=True,
            updated_at=datetime.now() - EXTRACTION_STALE_AFTER + timedelta(minutes=5),
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 409
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_stalled_in_progress_status_is_rejected_too(self, client):
        """processing=False with an in-progress stage is the stuck-document
        shape the reaper repairs; a retry must not race it."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="readying", processing=False,
        )
        resp, mock_dispatch, _ = await self._post(client, doc)

        assert resp.status_code == 409
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_detail_records_the_decision(self, client):
        doc = _make_document(doc_uuid="doc-1", user_id="owner1", task_status="error")
        resp, _, mock_log_event = await self._post(client, doc)

        assert resp.status_code == 200
        detail = mock_log_event.call_args.kwargs["detail"]
        assert detail == {
            "force_ocr": True,
            "ocr_required": False,
            "previous_task_status": "error",
        }

    @pytest.mark.asyncio
    async def test_audit_detail_separates_the_two_reasons_for_ocr(self, client):
        """Both flags are recorded because they answer different questions
        after the fact: whether the retry spent an OCR round-trip, and
        whether it was allowed to finish without one."""
        doc = _make_document(
            doc_uuid="doc-1", user_id="owner1",
            task_status="complete", extraction_nonletter_ratio=0.95,
        )
        resp, _, mock_log_event = await self._post(client, doc)

        assert resp.status_code == 200
        detail = mock_log_event.call_args.kwargs["detail"]
        assert detail == {
            "force_ocr": True,
            "ocr_required": True,
            "previous_task_status": "complete",
        }


class TestTextLayerRejectedField:
    """The bit the retry route reads and writes is on the document, not on
    the extraction, so it has to outlive every error write."""

    def test_defaults_to_false(self):
        """Documents stored before the field existed read as False, so no
        migration is needed and no existing document starts requiring OCR."""
        from app.models.document import SmartDocument

        assert SmartDocument.model_fields["text_layer_rejected"].default is False
