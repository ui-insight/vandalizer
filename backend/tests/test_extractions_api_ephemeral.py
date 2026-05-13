"""Ephemeral-cleanup behavior for the external extract API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from app.utils.security import hash_api_token

API_KEY = "test-api-key"


def _make_api_user(user_id="api-user"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "API User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.demo_status = None
    user.api_token_hash = hash_api_token(API_KEY)
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _mock_smart_document_class():
    """Return a mock SmartDocument that bypasses Beanie collection init."""
    created = []

    def constructor(**kwargs):
        doc = MagicMock()
        doc.id = ObjectId()
        doc.uuid = kwargs.get("uuid", "mock-uuid")
        doc.title = kwargs.get("title", "")
        doc.raw_text = kwargs.get("raw_text", "")
        doc.processing = kwargs.get("processing", False)
        doc.user_id = kwargs.get("user_id", "")
        doc.task_id = None
        doc.insert = AsyncMock()
        doc.save = AsyncMock()
        created.append(doc)
        return doc

    cls = MagicMock(side_effect=constructor)
    cls.find_one = AsyncMock(return_value=None)
    return cls, created


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app
        from app.rate_limit import limiter

        limiter.enabled = False
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
        limiter.enabled = True


def _common_patches(mock_smart_doc):
    """Build the patch stack shared by all ephemeral tests."""
    search_set = MagicMock()
    search_set.title = "Test Set"

    activity = MagicMock()
    activity.id = ObjectId()

    activity_service = MagicMock()
    activity_service.activity_start = AsyncMock(return_value=activity)
    activity_service.activity_finish = AsyncMock()
    activity_service.activity_update = AsyncMock()

    svc = MagicMock()
    svc.run_extraction_sync = AsyncMock(return_value=[])

    return search_set, activity_service, svc


class TestEphemeralCleanup:
    @pytest.mark.asyncio
    async def test_text_input_is_cleaned_up_by_default(self, client):
        user = _make_api_user()
        mock_smart_doc, created = _mock_smart_document_class()
        search_set, activity_service, svc = _common_patches(mock_smart_doc)

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.models.document.SmartDocument", mock_smart_doc),
            patch(
                "app.routers.extractions._get_search_set_or_404",
                new_callable=AsyncMock,
                return_value=search_set,
            ),
            patch(
                "app.routers.extractions._authorize_documents",
                new_callable=AsyncMock,
                side_effect=lambda uuids, _u: [],
            ),
            patch("app.routers.extractions.activity_service", activity_service),
            patch("app.routers.extractions.svc", svc),
            patch(
                "app.routers.extractions._cleanup_ephemeral_docs",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/extractions/run-integrated",
                headers={"x-api-key": API_KEY},
                data={
                    "search_set_uuid": "ss-1",
                    "text": "hello world",
                },
            )

        assert resp.status_code == 200, resp.text
        # The text doc was created and queued for cleanup.
        assert len(created) == 1
        mock_cleanup.assert_awaited_once()
        cleanup_uuids = mock_cleanup.await_args.args[0]
        assert cleanup_uuids == [created[0].uuid]

    @pytest.mark.asyncio
    async def test_ephemeral_false_skips_cleanup(self, client):
        user = _make_api_user()
        mock_smart_doc, created = _mock_smart_document_class()
        search_set, activity_service, svc = _common_patches(mock_smart_doc)

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.models.document.SmartDocument", mock_smart_doc),
            patch(
                "app.routers.extractions._get_search_set_or_404",
                new_callable=AsyncMock,
                return_value=search_set,
            ),
            patch(
                "app.routers.extractions._authorize_documents",
                new_callable=AsyncMock,
                side_effect=lambda uuids, _u: [],
            ),
            patch("app.routers.extractions.activity_service", activity_service),
            patch("app.routers.extractions.svc", svc),
            patch(
                "app.routers.extractions._cleanup_ephemeral_docs",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/extractions/run-integrated",
                headers={"x-api-key": API_KEY},
                data={
                    "search_set_uuid": "ss-1",
                    "text": "hello world",
                    "ephemeral": "false",
                },
            )

        assert resp.status_code == 200, resp.text
        assert len(created) == 1  # doc was still created
        mock_cleanup.assert_not_awaited()  # but cleanup did not run

    @pytest.mark.asyncio
    async def test_existing_document_uuids_are_never_cleaned_up(self, client):
        """Pre-existing docs supplied via document_uuids must survive even
        when ephemeral=true — only docs created by this request are removed.
        """
        user = _make_api_user()
        mock_smart_doc, created = _mock_smart_document_class()
        search_set, activity_service, svc = _common_patches(mock_smart_doc)

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.models.document.SmartDocument", mock_smart_doc),
            patch(
                "app.routers.extractions._get_search_set_or_404",
                new_callable=AsyncMock,
                return_value=search_set,
            ),
            patch(
                "app.routers.extractions._authorize_documents",
                new_callable=AsyncMock,
                side_effect=lambda uuids, _u: list(uuids),
            ),
            patch("app.routers.extractions.activity_service", activity_service),
            patch("app.routers.extractions.svc", svc),
            patch(
                "app.routers.extractions._cleanup_ephemeral_docs",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/extractions/run-integrated",
                headers={"x-api-key": API_KEY},
                data={
                    "search_set_uuid": "ss-1",
                    "document_uuids": "existing-1,existing-2",
                },
            )

        assert resp.status_code == 200, resp.text
        assert len(created) == 0  # no new docs were created
        mock_cleanup.assert_not_awaited()  # nothing to clean up

    @pytest.mark.asyncio
    async def test_cleanup_runs_even_when_extraction_fails(self, client):
        """If run_extraction_sync raises, the request fails but ephemeral
        cleanup must still happen (try/finally semantics).
        """
        user = _make_api_user()
        mock_smart_doc, created = _mock_smart_document_class()
        search_set, activity_service, svc = _common_patches(mock_smart_doc)
        svc.run_extraction_sync = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch("app.dependencies.User") as MockUser,
            patch("app.models.document.SmartDocument", mock_smart_doc),
            patch(
                "app.routers.extractions._get_search_set_or_404",
                new_callable=AsyncMock,
                return_value=search_set,
            ),
            patch(
                "app.routers.extractions._authorize_documents",
                new_callable=AsyncMock,
                side_effect=lambda uuids, _u: [],
            ),
            patch("app.routers.extractions.activity_service", activity_service),
            patch("app.routers.extractions.svc", svc),
            patch(
                "app.routers.extractions._cleanup_ephemeral_docs",
                new_callable=AsyncMock,
            ) as mock_cleanup,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            # ASGITransport re-raises server exceptions by default, so the
            # RuntimeError surfaces here instead of becoming a 500. What we
            # care about is that cleanup still ran via the finally block.
            with pytest.raises(RuntimeError, match="boom"):
                await client.post(
                    "/api/extractions/run-integrated",
                    headers={"x-api-key": API_KEY},
                    data={
                        "search_set_uuid": "ss-1",
                        "text": "hello world",
                    },
                )

        assert len(created) == 1
        mock_cleanup.assert_awaited_once()
