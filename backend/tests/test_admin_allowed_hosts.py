"""Admin-managed SSRF exemptions: PUT /api/admin/config outbound_url_allowed_hosts.

The env-only allowlist was a hidden fix for everyone except the operator who
knew the variable existed. The admin page makes the same exemption
self-serve, so it has to validate what it stores (an entry that can never
match is worse than a 400) and leave its own audit trail (it widens what the
server will fetch on a workflow author's behalf).
"""

from __future__ import annotations

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token


def _auth():
    settings = Settings(jwt_secret_key="test-secret-key", environment="development")
    token = create_access_token("admin", settings)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


def _admin_user():
    user = MagicMock()
    user.user_id = "admin"
    user.is_admin = True
    user.token_version = 0
    user.is_demo_user = False
    user.demo_status = None
    return user


def _cfg(existing=()):
    cfg = MagicMock()
    cfg.outbound_url_allowed_hosts = list(existing)
    cfg.save = AsyncMock()
    return cfg


async def _put(body: dict, cfg):
    cookies, headers = _auth()
    audit = AsyncMock()
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        with patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.admin.SystemConfig.get_config", AsyncMock(return_value=cfg)), \
             patch("app.routers.admin._audit", audit), \
             patch("app.routers.admin.clear_agent_caches"):
            MockUser.find_one = AsyncMock(return_value=_admin_user())
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.put("/api/admin/config", json=body, cookies=cookies, headers=headers)
    return resp, audit


class TestPutAllowedHosts:
    @pytest.mark.asyncio
    async def test_entries_are_normalised_deduplicated_and_audited_by_name(self):
        cfg = _cfg()
        resp, audit = await _put(
            {"outbound_url_allowed_hosts": [" MindRouter.Example.EDU. ", "", "mindrouter.example.edu", "data-api.example.edu"]},
            cfg,
        )

        assert resp.status_code == 200, resp.text
        assert cfg.outbound_url_allowed_hosts == ["mindrouter.example.edu", "data-api.example.edu"]
        cfg.save.assert_awaited_once()
        actions = [c.args[1] for c in audit.await_args_list]
        assert "update_outbound_allowed_hosts" in actions
        entry = next(c for c in audit.await_args_list if c.args[1] == "update_outbound_allowed_hosts")
        assert entry.args[3] == {"before": [], "after": ["mindrouter.example.edu", "data-api.example.edu"]}

    @pytest.mark.asyncio
    async def test_an_unchanged_list_leaves_no_dedicated_audit_entry(self):
        cfg = _cfg(["mindrouter.example.edu"])
        resp, audit = await _put({"outbound_url_allowed_hosts": ["mindrouter.example.edu"]}, cfg)

        assert resp.status_code == 200
        assert "update_outbound_allowed_hosts" not in [c.args[1] for c in audit.await_args_list]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad",
        [
            "https://mindrouter.example.edu/v1",
            "mindrouter.example.edu:8443",
            "*.example.edu",
            "metadata.google.internal",
            "not a host",
        ],
    )
    async def test_an_entry_that_could_never_match_is_a_400_naming_it(self, bad):
        cfg = _cfg()
        resp, _ = await _put({"outbound_url_allowed_hosts": ["fine.example.edu", bad]}, cfg)

        assert resp.status_code == 400, resp.text
        assert "Allowed private hosts" in resp.json()["detail"]
        cfg.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_omitting_the_field_leaves_the_stored_list_alone(self):
        cfg = _cfg(["mindrouter.example.edu"])
        resp, audit = await _put({"llm_endpoint": "https://llm.example.edu"}, cfg)

        assert resp.status_code == 200
        assert cfg.outbound_url_allowed_hosts == ["mindrouter.example.edu"]
        assert "update_outbound_allowed_hosts" not in [c.args[1] for c in audit.await_args_list]


class TestGetConfigExposesBothLists:
    @pytest.mark.asyncio
    async def test_get_returns_the_stored_list_and_the_env_list_separately(self):
        cookies, headers = _auth()
        cfg = MagicMock()
        cfg.outbound_url_allowed_hosts = ["mindrouter.example.edu"]
        cfg.get_extraction_config.return_value = {}
        cfg.get_quality_config.return_value = {}
        cfg.get_compliance_config.return_value = {}
        cfg.get_retention_config.return_value = {}
        cfg.auth_methods = ["password"]
        cfg.oauth_providers = []
        cfg.available_models = []
        cfg.default_model = ""
        cfg.long_document_model = ""
        cfg.ocr_endpoint = ""
        cfg.ocr_api_key = ""
        cfg.ocr_provider = "raw"
        cfg.ocr_options = {}
        cfg.ocr_async = False
        cfg.ocr_timeout_seconds = 120
        cfg.llm_endpoint = ""
        cfg.highlight_color = "#eab308"
        cfg.ui_radius = "12px"
        cfg.default_team_id = ""
        cfg.support_contacts = []

        with patch("app.main.init_db", new_callable=AsyncMock):
            from app.main import app

            with patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}), \
                 patch("app.dependencies.User") as MockUser, \
                 patch("app.routers.admin.SystemConfig.get_config", AsyncMock(return_value=cfg)), \
                 patch("app.routers.admin._ensure_config_ids", AsyncMock()), \
                 patch("app.routers.admin.decrypt_value", return_value=""), \
                 patch("app.utils.url_validation.env_allowed_hosts", return_value=frozenset({"legacy.example.edu"})):
                MockUser.find_one = AsyncMock(return_value=_admin_user())
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.get("/api/admin/config", cookies=cookies, headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["outbound_url_allowed_hosts"] == ["mindrouter.example.edu"]
        assert body["outbound_url_env_allowed_hosts"] == ["legacy.example.edu"]
