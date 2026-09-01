"""A KB source whose document was deleted from Files.

The chunks stay in the index and keep answering questions, so the source row
stays too — but it has to keep the filename and say the document is gone,
the way an extraction test case with a deleted source does. Before this, the
row fell back to the document UUID with no explanation.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services import knowledge_service
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _source(uuid="src-1", document_uuid="doc-1", document_title=None, source_type="document"):
    s = MagicMock()
    s.uuid = uuid
    s.source_type = source_type
    s.document_uuid = document_uuid
    s.document_title = document_title
    s.url = None
    s.url_title = None
    s.custom_name = None
    s.source_reference = None
    s.status = "ready"
    s.error_message = None
    s.chunk_count = 7
    s.created_at = None
    return s


def _doc(uuid, title):
    d = MagicMock()
    d.uuid = uuid
    d.title = title
    return d


def _find_returning(docs):
    """Stand in for ``SmartDocument.find(...).to_list()``."""
    model = MagicMock()
    model.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=docs)))
    return model


class TestResolveDocumentTitles:
    @pytest.mark.asyncio
    async def test_falls_back_to_the_title_ingest_recorded(self):
        source = _source(document_title="Award Letter.pdf")

        # Document deleted: nothing comes back from the collection.
        with patch.object(knowledge_service, "SmartDocument", _find_returning([])):
            titles = await knowledge_service.resolve_document_titles([source])

        assert titles == {"doc-1": "Award Letter.pdf"}

    @pytest.mark.asyncio
    async def test_live_title_wins_over_the_stored_one(self):
        source = _source(document_title="Award Letter.pdf")

        with patch.object(
            knowledge_service, "SmartDocument",
            _find_returning([_doc("doc-1", "Award Letter (renamed).pdf")]),
        ):
            titles = await knowledge_service.resolve_document_titles([source])

        assert titles == {"doc-1": "Award Letter (renamed).pdf"}

    @pytest.mark.asyncio
    async def test_no_title_anywhere_resolves_to_nothing(self):
        # Pre-backfill row whose document is already gone: still nothing to
        # show, and the caller falls back to the UUID as before.
        with patch.object(knowledge_service, "SmartDocument", _find_returning([])):
            titles = await knowledge_service.resolve_document_titles([_source()])

        assert titles == {}


class TestResolveExistingDocuments:
    @pytest.mark.asyncio
    async def test_reports_only_documents_that_still_exist(self):
        sources = [
            _source(uuid="src-1", document_uuid="doc-1"),
            _source(uuid="src-2", document_uuid="doc-gone"),
            _source(uuid="src-3", document_uuid=None, source_type="url"),
        ]

        with patch.object(
            knowledge_service, "SmartDocument", _find_returning([_doc("doc-1", "Kept.pdf")]),
        ):
            existing = await knowledge_service.resolve_existing_documents(sources)

        assert existing == {"doc-1"}

    @pytest.mark.asyncio
    async def test_a_lookup_failure_does_not_mark_everything_deleted(self):
        model = MagicMock()
        model.find = MagicMock(side_effect=RuntimeError("no beanie"))

        with patch.object(knowledge_service, "SmartDocument", model):
            existing = await knowledge_service.resolve_existing_documents(
                [_source(document_uuid="doc-1")],
            )

        assert existing == {"doc-1"}


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as ac:
            yield ac


class TestKBDetailMarksDeletedSources:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("existing,expected", [(set(), False), ({"doc-1"}, True)])
    async def test_detail_reports_whether_the_document_still_exists(
        self, client, existing, expected,
    ):
        user = _make_user()
        cookies, headers = _auth()
        kb = MagicMock()
        kb.uuid = "kb-1"
        kb.title = "Awards"
        kb.description = None
        kb.user_id = "user1"
        kb.team_id = None
        kb.shared_with_team = False
        kb.team_owned = False
        kb.verified = False
        kb.implicit = False
        kb.organization_ids = []
        kb.tags = []
        kb.status = "ready"
        kb.total_sources = 1
        kb.sources_ready = 1
        kb.sources_failed = 0
        kb.total_chunks = 7
        kb.created_at = None
        kb.updated_at = None

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.knowledge.svc") as mock_svc,
            patch("app.routers.knowledge.organization_service") as mock_org,
            # Beanie isn't initialised in unit tests, so the team-access lookup
            # this endpoint makes has to be stubbed.
            patch("app.routers.knowledge.access_control") as mock_ac,
            patch("app.routers.knowledge.ValidationRun") as MockRun,
            patch("app.routers.knowledge.KBOptimizationRun") as MockOpt,
            patch("app.routers.knowledge.optimization_status_by_kb", AsyncMock(return_value={})),
            patch(
                "app.routers.knowledge._resolve_document_titles",
                new_callable=AsyncMock,
                # What the deleted-document path yields: the stored title.
                return_value={"doc-1": "Award Letter.pdf"},
            ),
            patch(
                "app.services.knowledge_service.resolve_existing_documents",
                new_callable=AsyncMock, return_value=existing,
            ),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_org.get_user_org_ancestry = AsyncMock(return_value=[])
            mock_ac.get_team_access_context = AsyncMock(return_value=MagicMock())
            mock_ac.can_manage_knowledge_base = MagicMock(return_value=True)
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            mock_svc.get_kb_sources = AsyncMock(return_value=[_source()])
            MockRun.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            MockOpt.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

            resp = await client.get("/api/knowledge/kb-1", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        source = resp.json()["sources"][0]
        assert source["document_exists"] is expected
        # Named either way — never the bare UUID.
        assert source["document_title"] == "Award Letter.pdf"
