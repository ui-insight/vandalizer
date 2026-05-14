"""Unit tests for the /api/mgmt/v1 surface and its auth dep."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.utils.security import (
    MGMT_API_KEY_PREFIX,
    generate_mgmt_api_key,
    hash_api_token,
)


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

class TestGenerateMgmtApiKey:
    def test_returns_prefixed_token(self):
        full, prefix, key_hash = generate_mgmt_api_key()
        assert full.startswith(MGMT_API_KEY_PREFIX)
        assert prefix == full[: len(prefix)]
        assert key_hash == hash_api_token(full)

    def test_tokens_are_unique(self):
        seen = {generate_mgmt_api_key()[0] for _ in range(50)}
        assert len(seen) == 50

    def test_hash_is_deterministic(self):
        full, _, key_hash = generate_mgmt_api_key()
        assert hash_api_token(full) == key_hash


# ---------------------------------------------------------------------------
# require_mgmt_scope dep
# ---------------------------------------------------------------------------

@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


def _make_key(
    *,
    scopes: list[str],
    revoked_at: datetime.datetime | None = None,
    expires_at: datetime.datetime | None = None,
):
    key = MagicMock()
    key.id = "fake-key-id"
    key.name = "test-key"
    key.scopes = scopes
    key.revoked_at = revoked_at
    key.expires_at = expires_at
    key.save = AsyncMock()
    return key


class TestRequireMgmtScope:
    @pytest.mark.asyncio
    async def test_unknown_scope_rejected_at_factory(self):
        from app.dependencies import require_mgmt_scope

        with pytest.raises(ValueError, match="Unknown mgmt scope"):
            require_mgmt_scope("not:a:real:scope")

    @pytest.mark.asyncio
    async def test_missing_header_returns_401(self, client):
        resp = await client.get("/api/mgmt/v1/stats")
        assert resp.status_code in (401, 422)  # Header(...) → 422 in fastapi

    @pytest.mark.asyncio
    async def test_unknown_key_returns_401(self, client):
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
        ):
            MockKey.find_one = AsyncMock(return_value=None)
            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_bogus"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_revoked_key_rejected(self, client):
        revoked = _make_key(
            scopes=["metrics:read"],
            revoked_at=datetime.datetime.now(tz=datetime.timezone.utc),
        )
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
        ):
            MockKey.find_one = AsyncMock(return_value=revoked)
            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_revoked"},
            )
        assert resp.status_code == 401
        assert "revoked" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_expired_key_rejected(self, client):
        past = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
            days=1
        )
        expired = _make_key(scopes=["metrics:read"], expires_at=past)
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
        ):
            MockKey.find_one = AsyncMock(return_value=expired)
            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_expired"},
            )
        assert resp.status_code == 401
        assert "expired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_missing_scope_returns_403(self, client):
        wrong_scope = _make_key(scopes=["users:read"])
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
        ):
            MockKey.find_one = AsyncMock(return_value=wrong_scope)
            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_wrongscope"},
            )
        assert resp.status_code == 403
        assert "metrics:read" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_wildcard_scope_grants_access(self, client):
        wildcard = _make_key(scopes=["*"])
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock) as mock_audit,
            patch("app.routers.mgmt.User") as MockUser,
            patch("app.routers.mgmt.Team") as MockTeam,
            patch("app.routers.mgmt.SmartDocument") as MockDoc,
            patch("app.routers.mgmt.Workflow") as MockWorkflow,
            patch("app.routers.mgmt.WorkflowResult") as MockWR,
            patch("app.routers.mgmt.ActivityEvent") as MockAct,
        ):
            MockKey.find_one = AsyncMock(return_value=wildcard)
            for M in (MockUser, MockTeam, MockDoc, MockWorkflow, MockWR, MockAct):
                M.find_all = MagicMock(return_value=MagicMock(
                    count=AsyncMock(return_value=0),
                    to_list=AsyncMock(return_value=[]),
                ))
                M.find = MagicMock(return_value=MagicMock(
                    count=AsyncMock(return_value=0),
                    distinct=AsyncMock(return_value=[]),
                ))
            # /stats now sums token_count via a Beanie aggregation rather than
            # materializing every document — older stub records in prod can be
            # missing required SmartDocument fields and trip Beanie validation.
            MockDoc.aggregate = MagicMock(return_value=MagicMock(
                to_list=AsyncMock(return_value=[]),
            ))
            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_wildcard"},
            )
        assert resp.status_code == 200
        # last_used updated, audit logged
        wildcard.save.assert_awaited_once()
        mock_audit.assert_awaited_once()
        body = resp.json()
        assert body["users_total"] == 0
        assert "generated_at" in body

    @pytest.mark.asyncio
    async def test_stats_uses_aggregation_for_token_sum(self, client):
        """The token-bytes total comes from a MongoDB aggregation, not from
        materializing every SmartDocument. Regression for Sentry 7479098685:
        legacy stub records missing required fields would otherwise crash the
        endpoint with Beanie ValidationError."""
        wildcard = _make_key(scopes=["*"])
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
            patch("app.routers.mgmt.User") as MockUser,
            patch("app.routers.mgmt.Team") as MockTeam,
            patch("app.routers.mgmt.SmartDocument") as MockDoc,
            patch("app.routers.mgmt.Workflow") as MockWorkflow,
            patch("app.routers.mgmt.WorkflowResult") as MockWR,
            patch("app.routers.mgmt.ActivityEvent") as MockAct,
        ):
            MockKey.find_one = AsyncMock(return_value=wildcard)
            for M in (MockUser, MockTeam, MockDoc, MockWorkflow, MockWR, MockAct):
                M.find_all = MagicMock(return_value=MagicMock(
                    count=AsyncMock(return_value=0),
                    to_list=AsyncMock(return_value=[]),
                ))
                M.find = MagicMock(return_value=MagicMock(
                    count=AsyncMock(return_value=0),
                    distinct=AsyncMock(return_value=[]),
                ))
            aggregate_mock = MagicMock(return_value=MagicMock(
                to_list=AsyncMock(return_value=[{"_id": None, "total_tokens": 1_000_000}]),
            ))
            MockDoc.aggregate = aggregate_mock

            resp = await client.get(
                "/api/mgmt/v1/stats",
                headers={"X-API-Key": "vk_live_wildcard"},
            )

        assert resp.status_code == 200
        # The endpoint asked Mongo to sum token_count, not Python.
        aggregate_mock.assert_called_once()
        pipeline = aggregate_mock.call_args.args[0]
        assert pipeline == [{"$group": {"_id": None, "total_tokens": {"$sum": "$token_count"}}}]
        # 1M tokens * 4 bytes/token = 4M bytes.
        assert resp.json()["documents_size_bytes_total"] == 4_000_000


# ---------------------------------------------------------------------------
# New scopes: validation read/write/run, workflows:run, extractions:run
# ---------------------------------------------------------------------------

class TestMgmtScopeSet:
    """The MGMT_SCOPES frozen set is the source of truth for valid scopes."""

    def test_includes_new_scopes(self):
        from app.dependencies import MGMT_SCOPES

        for scope in (
            "validation:read",
            "validation:write",
            "validation:run",
            "workflows:run",
            "extractions:run",
        ):
            assert scope in MGMT_SCOPES

    def test_drops_unused_write_scopes(self):
        from app.dependencies import MGMT_SCOPES

        for scope in ("workflows:rerun", "users:invite", "users:disable", "config:update"):
            assert scope not in MGMT_SCOPES


class TestValidationReadEndpoints:
    @pytest.mark.asyncio
    async def test_list_validation_runs(self, client):
        key = _make_key(scopes=["validation:read"])
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
            patch("app.routers.mgmt.ValidationRun") as MockVR,
        ):
            MockKey.find_one = AsyncMock(return_value=key)
            chain = MagicMock()
            chain.count = AsyncMock(return_value=0)
            chain.sort.return_value.skip.return_value.limit.return_value.to_list = (
                AsyncMock(return_value=[])
            )
            MockVR.find = MagicMock(return_value=chain)
            MockVR.find_all = MagicMock(return_value=chain)
            MockVR.created_at = MagicMock()
            resp = await client.get(
                "/api/mgmt/v1/validation/runs",
                headers={"X-API-Key": "vk_live_x"},
            )
        assert resp.status_code == 200
        assert resp.json()["page"]["total"] == 0


class TestValidationWriteEndpoints:
    @pytest.mark.asyncio
    async def test_create_test_case(self, client):
        key = _make_key(scopes=["validation:write"])
        key.created_by = "admin-user"
        actor = MagicMock()
        actor.user_id = "admin-user"
        actor.is_demo_user = False
        actor.demo_status = None
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
            patch("app.routers.mgmt.User") as MockUser,
            patch(
                "app.routers.mgmt.ExtractionTestCase"
            ) as MockTC,
        ):
            MockKey.find_one = AsyncMock(return_value=key)
            MockUser.find_one = AsyncMock(return_value=actor)

            instance = MagicMock()
            instance.uuid = "tc-uuid-1"
            instance.search_set_uuid = "ss-1"
            instance.label = "case A"
            instance.source_type = "text"
            instance.source_text = "hello"
            instance.document_uuid = None
            instance.expected_values = {"x": "1"}
            instance.user_id = "admin-user"
            instance.created_at = datetime.datetime.now(tz=datetime.timezone.utc)
            instance.insert = AsyncMock()
            MockTC.return_value = instance

            resp = await client.post(
                "/api/mgmt/v1/validation/test-cases",
                headers={"X-API-Key": "vk_live_x"},
                json={
                    "search_set_uuid": "ss-1",
                    "label": "case A",
                    "source_type": "text",
                    "source_text": "hello",
                    "expected_values": {"x": "1"},
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["uuid"] == "tc-uuid-1"
        assert body["search_set_uuid"] == "ss-1"
        assert body["user_id"] == "admin-user"
        instance.insert.assert_awaited_once()


class TestRunEndpoints:
    @pytest.mark.asyncio
    async def test_run_validation_invokes_service(self, client):
        key = _make_key(scopes=["validation:run"])
        key.created_by = "admin-user"
        actor = MagicMock()
        actor.user_id = "admin-user"
        actor.is_demo_user = False
        actor.demo_status = None

        ss = MagicMock()
        ss.uuid = "ss-1"
        ss.title = "Test Set"

        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
            patch("app.routers.mgmt.User") as MockUser,
            patch(
                "app.services.access_control.get_authorized_search_set",
                new_callable=AsyncMock,
            ) as mock_authz,
            patch(
                "app.services.extraction_validation_service.run_validation_v2",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            MockKey.find_one = AsyncMock(return_value=key)
            MockUser.find_one = AsyncMock(return_value=actor)
            mock_authz.return_value = ss
            mock_run.return_value = {"score": 0.95, "ok": True}

            resp = await client.post(
                "/api/mgmt/v1/validation/run",
                headers={"X-API-Key": "vk_live_x"},
                json={
                    "search_set_uuid": "ss-1",
                    "sources": [{"document_uuid": "doc-1"}],
                    "num_runs": 1,
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"score": 0.95, "ok": True}
        mock_run.assert_awaited_once()
        kwargs = mock_run.call_args.kwargs
        assert kwargs["user_id"] == "admin-user"
        assert kwargs["search_set_uuid"] == "ss-1"

    @pytest.mark.asyncio
    async def test_run_endpoint_rejects_missing_issuer(self, client):
        """If the admin who issued the key was deleted, the run is refused."""
        key = _make_key(scopes=["extractions:run"])
        key.created_by = "ghost-admin"
        with (
            patch("app.dependencies.ApiKey") as MockKey,
            patch("app.dependencies.audit_service.log_event", new_callable=AsyncMock),
            patch("app.routers.mgmt.User") as MockUser,
        ):
            MockKey.find_one = AsyncMock(return_value=key)
            MockUser.find_one = AsyncMock(return_value=None)
            resp = await client.post(
                "/api/mgmt/v1/extractions/run",
                headers={"X-API-Key": "vk_live_x"},
                json={
                    "search_set_uuid": "ss-1",
                    "document_uuids": ["doc-1"],
                },
            )
        assert resp.status_code == 403
        assert "issuer" in resp.json()["detail"].lower()
