"""Unit tests for the self-serve trial lifecycle fix (demo_service).

Self-registration used to set only the User demo flags; with no
DemoApplication, check_expirations could never lock the account — a "14-day
trial" that never ended. These tests cover the two halves of the fix:
begin_self_serve_trial (register now mints an active application) and
_backfill_orphan_trial_applications (existing flag-only users get one at
sweep time).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import demo_service
from tests.conftest import fake_model


def _constructible_fake_model(docs=None, *, find_one_result=None):
    """fake_model + a working constructor, for services that insert documents."""
    cls = fake_model(docs, find_one_result=find_one_result)
    created: list = []

    def _init(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.insert = AsyncMock()
        self.save = AsyncMock()
        created.append(self)

    cls.__init__ = _init
    cls.created = created
    return cls


def _settings() -> SimpleNamespace:
    return SimpleNamespace(frontend_url="https://example.test")


def _user(**overrides) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id="u-1",
        email="Ada@Example.EDU",
        name="Ada",
        is_demo_user=False,
        demo_status=None,
        demo_expires_at=None,
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    user.save = AsyncMock()
    return user


# ---------------------------------------------------------------------------
# begin_self_serve_trial
# ---------------------------------------------------------------------------


async def test_begin_trial_marks_user_and_mints_active_application():
    user = _user()
    apps = _constructible_fake_model(find_one_result=None)

    with patch.object(demo_service, "DemoApplication", apps):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert user.is_demo_user is True
    assert user.demo_status == "active"
    user.save.assert_awaited_once()

    now = datetime.datetime.now(datetime.timezone.utc)
    remaining = user.demo_expires_at - now
    assert (
        datetime.timedelta(days=demo_service.TRIAL_DAYS - 1)
        < remaining
        <= datetime.timedelta(days=demo_service.TRIAL_DAYS)
    )

    assert len(apps.created) == 1
    app = apps.created[0]
    assert app.status == "active"
    assert app.user_id == "u-1"
    assert app.email == "ada@example.edu"
    assert app.organization == "example.edu"
    assert app.expires_at == user.demo_expires_at
    app.insert.assert_awaited_once()


async def test_begin_trial_adopts_pending_waitlist_application():
    """A pending waitlist applicant who registers directly keeps one record."""
    user = _user()
    pending = SimpleNamespace(
        status="pending", user_id=None, activated_at=None, expires_at=None
    )
    pending.save = AsyncMock()
    apps = _constructible_fake_model(find_one_result=pending)

    with patch.object(demo_service, "DemoApplication", apps):
        await demo_service.begin_self_serve_trial(user, _settings())

    assert apps.created == []  # adopted, not duplicated
    assert pending.status == "active"
    assert pending.user_id == "u-1"
    assert pending.expires_at == user.demo_expires_at
    pending.save.assert_awaited_once()


def test_email_domain_buckets():
    assert demo_service._email_domain("ada@Example.EDU") == "example.edu"
    assert demo_service._email_domain("") == "self-registered"
    assert demo_service._email_domain("no-at-sign") == "no-at-sign"


# ---------------------------------------------------------------------------
# _backfill_orphan_trial_applications
# ---------------------------------------------------------------------------


async def test_backfill_mints_application_preserving_original_expiry():
    """An orphan flag-only trial user gets an application carrying their real
    expiry — an already-overdue one lands due for the same sweep."""
    past = datetime.datetime(2026, 8, 1)  # naive, as Mongo returns it
    orphan = _user(is_demo_user=True, demo_status="active", demo_expires_at=past)

    users = fake_model([orphan])
    apps = _constructible_fake_model(docs=[], find_one_result=None)

    now = datetime.datetime.now(datetime.timezone.utc)
    with (
        patch.object(demo_service, "User", users),
        patch.object(demo_service, "DemoApplication", apps),
    ):
        created = await demo_service._backfill_orphan_trial_applications(now)

    assert created == 1
    app = apps.created[0]
    assert app.status == "active"
    assert app.user_id == "u-1"
    assert app.expires_at == past.replace(tzinfo=datetime.timezone.utc)
    assert app.expires_at <= now  # the sweep that minted it can expire it
    app.insert.assert_awaited_once()


async def test_backfill_skips_users_with_linked_application():
    orphan = _user(is_demo_user=True, demo_status="active")
    users = fake_model([orphan])
    apps = _constructible_fake_model(docs=[SimpleNamespace(user_id="u-1")])

    with (
        patch.object(demo_service, "User", users),
        patch.object(demo_service, "DemoApplication", apps),
    ):
        created = await demo_service._backfill_orphan_trial_applications(
            datetime.datetime.now(datetime.timezone.utc)
        )

    assert created == 0
    assert apps.created == []


async def test_check_expirations_runs_backfill_first():
    """The sweep must see orphans minted in the same pass."""
    backfill = AsyncMock(return_value=0)
    with (
        patch.object(demo_service, "_backfill_orphan_trial_applications", backfill),
        patch.object(demo_service, "DemoApplication", fake_model([])),
    ):
        expired = await demo_service.check_expirations(_settings())

    assert expired == 0
    backfill.assert_awaited_once()
