"""Tests for Sentry bootstrap (app.observability.init_sentry).

Guards the deliberate disabling of Sentry's auto-enabled LLM integrations
(pydantic_ai / openai / anthropic), which otherwise capture every exception
escaping an agent/provider call as mechanism.handled=False — mislabeling the
app's gracefully-handled LLM errors as unhandled and doubling every real
failure. A sentry-sdk bump that re-enables them would silently reintroduce the
flood, so pin the behavior here.
"""

import pytest
import sentry_sdk

from app.config import Settings
from app.observability import init_sentry

_FAKE_DSN = "https://examplepublickey@o0.ingest.sentry.io/0"


@pytest.fixture(autouse=True)
def _sentry_offline_and_isolated(monkeypatch):
    """Run the real ``sentry_sdk.init()`` — that is what is under test — but
    never touch the network, and do not leave a live client installed once this
    module is done.

    ``init()`` installs a *process-global* client. Without the teardown below,
    every later test in the session runs under a live client with a real
    HttpTransport aimed at sentry.io and ``traces_sample_rate=1.0`` (the
    non-production branch of ``app/observability.py``). See #615.

    Autouse is scoped to this module on purpose: applying it suite-wide would
    re-enter ``init()`` once per test across the whole run.
    """
    real_init = sentry_sdk.init

    def offline_init(*args, **kwargs):
        kwargs["transport"] = lambda envelope: None  # discard, never send
        return real_init(*args, **kwargs)

    monkeypatch.setattr(sentry_sdk, "init", offline_init)
    yield
    real_init(dsn="")  # uninstall the global client


def _active_integrations() -> set[str]:
    return set(sentry_sdk.get_client().integrations.keys())


class TestInitSentry:
    def test_llm_integrations_are_disabled(self):
        init_sentry(Settings(sentry_dsn=_FAKE_DSN, environment="development"), with_celery=True)
        active = _active_integrations()
        assert "pydantic_ai" not in active
        assert "openai" not in active
        assert "anthropic" not in active

    def test_core_integrations_remain_enabled(self):
        init_sentry(Settings(sentry_dsn=_FAKE_DSN, environment="development"), with_celery=True)
        active = _active_integrations()
        # The boundary integrations we rely on for real, correctly-labeled
        # captures must still be present.
        assert "starlette" in active
        assert "celery" in active

    def test_noop_without_dsn(self):
        # Should not raise and should not call sentry_sdk.init.
        from unittest.mock import patch

        with patch("sentry_sdk.init") as mock_init:
            init_sentry(Settings(sentry_dsn="", environment="development"))
            mock_init.assert_not_called()
