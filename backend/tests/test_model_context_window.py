"""A model's context window is detected or entered, never silently guessed.

The add-model form sent 128,000 for every model nobody probed, and a model
with no window at all was budgeted as 65,536 tokens. A COGR spreadsheet was
then cut on the first question in a chat on dev. These tests cover where a
window comes from, the flag for models whose window was never confirmed, and
the one-click probe that fixes them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.admin import context_window_status
from app.services.model_probe import ProbeResult
from tests.test_admin_routes import _auth, _make_user, client  # noqa: F401 (fixture)


def _cfg(*models):
    return SimpleNamespace(
        available_models=[dict(m) for m in models], oauth_providers=[], default_model="",
        updated_at=None, updated_by=None, save=AsyncMock(),
    )


async def _call(client, cfg, method, url, body, probe=None):  # noqa: F811
    admin = _make_user("admin", is_admin=True)
    cookies, headers = _auth("admin")
    with (
        patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.routers.admin.SystemConfig") as MockCfg,
        patch("app.routers.admin.encrypt_value", side_effect=lambda v: v),
        patch("app.routers.admin.decrypt_value", side_effect=lambda v: v),
        patch("app.routers.admin.clear_agent_caches"),
        patch("app.routers.admin._audit", new_callable=AsyncMock),
        patch("app.services.model_probe.probe_context_window", AsyncMock(return_value=probe)),
    ):
        MockUser.find_one = AsyncMock(return_value=admin)
        MockCfg.get_config = AsyncMock(return_value=cfg)
        return await getattr(client, method)(url, json=body, cookies=cookies, headers=headers)


@pytest.mark.parametrize("model, status", [
    ({"context_window": 131072, "context_window_source": "detected"}, "detected"),
    ({"context_window": 1000000, "context_window_source": "entered"}, "entered"),
    ({"context_window": 128000}, "unconfirmed"),  # the old form placeholder
    ({"context_window": None}, "missing"),
    ({}, "missing"),
])
def test_status_says_whether_the_window_is_known(model, status):
    assert context_window_status(model) == status


@pytest.mark.asyncio
async def test_a_model_added_without_a_window_is_stored_without_one(client):  # noqa: F811
    cfg = _cfg()
    resp = await _call(client, cfg, "post", "/api/admin/config/models", {"name": "gpt-oss-120b", "tag": "fast"})
    assert resp.status_code == 200
    stored = cfg.available_models[0]
    assert stored["context_window"] is None and stored["context_window_source"] is None
    assert resp.json()["models"][0]["context_window_status"] == "missing"


@pytest.mark.asyncio
async def test_a_window_saved_from_the_form_records_its_source(client):  # noqa: F811
    cfg = _cfg()
    await _call(client, cfg, "post", "/api/admin/config/models",
                {"name": "kimi-k3", "tag": "strong", "context_window": 262144, "context_window_source": "detected"})
    assert cfg.available_models[0]["context_window_source"] == "detected"

    cfg = _cfg({"id": "m1", "name": "kimi-k3", "tag": "strong", "context_window": 128000})
    await _call(client, cfg, "put", "/api/admin/config/models/m1", {"name": "kimi-k3", "tag": "strong", "context_window": 1000000})
    assert cfg.available_models[0]["context_window"] == 1000000
    assert cfg.available_models[0]["context_window_source"] == "entered"


MODEL = {"id": "m1", "name": "gpt-oss-120b", "tag": "fast", "endpoint": "https://llm.example/v1", "api_protocol": "vllm", "api_key": ""}
URL = "/api/admin/config/models/m1/context-window/probe"


@pytest.mark.asyncio
async def test_probing_an_unconfirmed_model_records_the_detected_window(client):  # noqa: F811
    cfg = _cfg({**MODEL, "context_window": 128000})
    resp = await _call(client, cfg, "post", URL, {}, probe=ProbeResult(131072, "vllm_max_model_len"))
    body = resp.json()
    assert body["applied"] is True
    assert cfg.available_models[0]["context_window"] == 131072
    assert body["models"][0]["context_window_status"] == "detected"


@pytest.mark.asyncio
async def test_a_window_an_admin_entered_is_not_overwritten_unless_asked(client):  # noqa: F811
    cfg = _cfg({**MODEL, "context_window": 1000000, "context_window_source": "entered"})
    probe = ProbeResult(65536, "vllm_max_model_len")
    body = (await _call(client, cfg, "post", URL, {}, probe=probe)).json()
    assert body["applied"] is False and body["entered_differs"] is True
    assert cfg.available_models[0]["context_window"] == 1000000
    cfg.save.assert_not_awaited()

    body = (await _call(client, cfg, "post", URL, {"force": True}, probe=probe)).json()
    assert body["applied"] is True and cfg.available_models[0]["context_window"] == 65536


@pytest.mark.asyncio
async def test_a_server_that_reports_nothing_changes_nothing(client):  # noqa: F811
    cfg = _cfg({**MODEL, "context_window": None})
    body = (await _call(client, cfg, "post", URL, {}, probe=ProbeResult(None, "openai_no_field", "No context length reported"))).json()
    assert body["applied"] is False and body["probe"]["detail"] == "No context length reported"
    cfg.save.assert_not_awaited()


def test_the_model_list_reports_the_window_the_budget_uses_when_none_is_saved():
    from app.routers.config import _model_context_window
    from app.services.context_budget import DEFAULT_CONTEXT_WINDOW

    assert _model_context_window({"name": "gpt-oss-120b", "context_window": None}) == DEFAULT_CONTEXT_WINDOW
    assert _model_context_window({"name": "qwen3-8b", "context_window": None}) == 131072
    assert _model_context_window({"name": "kimi-k3", "context_window": 262144}) == 262144
