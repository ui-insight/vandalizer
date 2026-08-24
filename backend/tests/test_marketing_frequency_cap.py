"""One marketing-class email per user per day, across every sequence.

A new registration is enrolled in the onboarding drip and the agentic-chat
drip at the same moment, and the one-shot sends (v5 announcement, power-user
upsell) sweep the same users on the same morning. Each sender was individually
reasonable and the inbox was not: a trial user who never signed in could
collect seven or eight of these in two weeks. The cap is shared state on the
user, checked before a sender advances its own bookkeeping so a capped email
goes out on a later sweep rather than being dropped.

The per-sequence rules (opt-out prefs, cooldowns, idempotency stamps) are
covered in test_engagement_service.py and test_v5_launch_funnel.py.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from app.services.engagement_service import _marketing_capped


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _user(last_marketing_email_at) -> SimpleNamespace:
    return SimpleNamespace(last_marketing_email_at=last_marketing_email_at)


class TestMarketingFrequencyCap:
    def test_a_user_who_got_one_an_hour_ago_is_capped(self):
        now = _now()
        assert _marketing_capped(_user(now - datetime.timedelta(hours=1)), now)

    def test_a_user_who_got_one_yesterday_is_not_capped(self):
        now = _now()
        assert not _marketing_capped(_user(now - datetime.timedelta(days=1)), now)

    def test_a_user_who_never_got_one_is_not_capped(self):
        assert not _marketing_capped(_user(None), _now())

    def test_the_gap_is_under_a_full_day_so_fixed_hour_sweeps_do_not_slip(self):
        """The beat schedule runs at a fixed hour. At a flat 24h, a sweep that
        starts a minute earlier than yesterday's misses the window and the
        sequence stalls a whole day each time."""
        now = _now()
        assert not _marketing_capped(_user(now - datetime.timedelta(hours=23)), now)

    def test_a_naive_timestamp_from_mongo_is_handled(self):
        """Motor is not tz_aware, so stored datetimes come back naive; a raw
        comparison would raise and take the nightly sweep down."""
        now = _now()
        naive = (now - datetime.timedelta(hours=2)).replace(tzinfo=None)
        assert _marketing_capped(_user(naive), now)

    def test_a_user_document_predating_the_field_is_not_capped(self):
        """Engagement sweeps never raise: a user written before this field
        existed must not take down the whole batch."""
        assert not _marketing_capped(SimpleNamespace(), _now())
