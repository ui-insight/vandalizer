"""The site address used in outgoing links.

Support ticket (vandalizer-dev): "Add to calendar" .ics files linked to
http://localhost:5173/?deadline=…, as did reminder and page-feedback emails
and sign-in links. Every link builder reads FRONTEND_URL, which defaulted to
localhost; the deploy docs name VANDALIZER_BASE_URL instead.
"""

import pytest

from app.config import Settings

SITE = "https://vandalizer-dev.insight.uidaho.edu"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("FRONTEND_URL", "VANDALIZER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def _settings(**env):
    return Settings(_env_file=None, **env)


def test_vandalizer_base_url_is_used_when_frontend_url_is_not_set(monkeypatch):
    monkeypatch.setenv("VANDALIZER_BASE_URL", SITE + "/")
    settings = _settings()
    assert settings.frontend_url == SITE
    assert not settings.frontend_url_is_local


def test_frontend_url_wins_when_both_are_set(monkeypatch):
    monkeypatch.setenv("VANDALIZER_BASE_URL", "https://other.example.edu")
    monkeypatch.setenv("FRONTEND_URL", SITE)
    assert _settings().frontend_url == SITE


@pytest.mark.parametrize("url, local", [
    ("http://localhost:5173", True),
    ("http://127.0.0.1", True),
    ("http://app.localhost", True),
    (SITE, False),
    ("http://vandalizer.intranet", False),
])
def test_a_localhost_address_is_recognised(monkeypatch, url, local):
    monkeypatch.setenv("FRONTEND_URL", url)
    assert _settings().frontend_url_is_local is local


def test_calendar_links_use_the_site_address(monkeypatch):
    import datetime

    from app.services.deadline_reminders import calendar_file
    from tests.test_deadline_reminders import _ob

    monkeypatch.setenv("VANDALIZER_BASE_URL", SITE)
    ob = _ob("617d85c2", "Greenhouse trial dataset due", datetime.date(2026, 12, 15))
    body = calendar_file(
        [(ob, "Drought project")], frontend_url=_settings().frontend_url, alarm_days=[7],
        now=datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc),
    )
    unfolded = body.replace("\r\n ", "")
    assert f"{SITE}/?deadline=617d85c2" in unfolded
    assert "localhost" not in unfolded
