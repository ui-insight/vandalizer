"""Tests for the canonical bootstrap_install entrypoint."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bootstrap_install


def _patch_bootstrap_runtime(monkeypatch, *, ensure_admin_result, ensure_default_team_result=None):
    settings = object()
    init_db = AsyncMock()
    ensure_admin = AsyncMock(return_value=ensure_admin_result)
    ensure_default_team = AsyncMock(return_value=ensure_default_team_result)
    seed_catalog = AsyncMock()

    monkeypatch.setattr(bootstrap_install, "Settings", lambda: settings)
    monkeypatch.setattr(bootstrap_install, "init_db", init_db)
    monkeypatch.setattr(bootstrap_install, "ensure_admin", ensure_admin)
    monkeypatch.setattr(bootstrap_install, "ensure_default_team", ensure_default_team)
    monkeypatch.setattr(bootstrap_install, "seed_catalog", seed_catalog)

    return init_db, ensure_admin, ensure_default_team, seed_catalog, settings


@pytest.mark.asyncio
async def test_main_requires_admin_email_and_password(monkeypatch, capsys):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_NAME", raising=False)
    monkeypatch.delenv("DEFAULT_TEAM_NAME", raising=False)

    init_db, ensure_admin, ensure_default_team, seed_catalog, settings = _patch_bootstrap_runtime(
        monkeypatch,
        ensure_admin_result=(SimpleNamespace(user_id="ignored@example.edu"), "created"),
    )

    with pytest.raises(SystemExit) as exc_info:
        await bootstrap_install.main()

    assert exc_info.value.code == 1
    init_db.assert_awaited_once_with(settings)
    ensure_admin.assert_not_awaited()
    ensure_default_team.assert_not_awaited()
    seed_catalog.assert_not_awaited()
    assert "ADMIN_EMAIL and ADMIN_PASSWORD" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_bootstraps_admin_without_default_team(monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", " admin@example.edu ")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_NAME", "Initial Admin")
    monkeypatch.delenv("DEFAULT_TEAM_NAME", raising=False)

    admin_user = SimpleNamespace(user_id="admin@example.edu")
    init_db, ensure_admin, ensure_default_team, seed_catalog, settings = _patch_bootstrap_runtime(
        monkeypatch,
        ensure_admin_result=(admin_user, "created"),
    )

    await bootstrap_install.main()

    init_db.assert_awaited_once_with(settings)
    ensure_admin.assert_awaited_once_with("admin@example.edu", "secret", "Initial Admin")
    ensure_default_team.assert_not_awaited()
    seed_catalog.assert_awaited_once()

    output = capsys.readouterr().out
    assert "Admin user created: admin@example.edu" in output
    assert "No DEFAULT_TEAM_NAME set." in output


@pytest.mark.asyncio
async def test_main_bootstraps_default_team_when_requested(monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.edu")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_NAME", "Initial Admin")
    monkeypatch.setenv("DEFAULT_TEAM_NAME", "Research Administration")

    admin_user = SimpleNamespace(user_id="admin@example.edu")
    default_team = SimpleNamespace(name="Research Administration", uuid="team-123")
    init_db, ensure_admin, ensure_default_team, seed_catalog, settings = _patch_bootstrap_runtime(
        monkeypatch,
        ensure_admin_result=(admin_user, "updated"),
        ensure_default_team_result=(default_team, "created", "updated"),
    )

    await bootstrap_install.main()

    init_db.assert_awaited_once_with(settings)
    ensure_admin.assert_awaited_once_with("admin@example.edu", "secret", "Initial Admin")
    ensure_default_team.assert_awaited_once_with("Research Administration", "admin@example.edu")
    seed_catalog.assert_awaited_once()

    output = capsys.readouterr().out
    assert "Admin user updated with admin/examiner permissions: admin@example.edu" in output
    assert "Default team created: Research Administration (uuid=team-123)" in output
    assert "Bootstrap admin role on the default team was corrected to owner." in output
    assert "New users will auto-join the default team on first registration or SSO login." in output
