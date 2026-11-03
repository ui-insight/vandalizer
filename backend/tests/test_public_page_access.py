"""Public Page links: expiry, sign-in audience and who may open them."""
import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import public_page_access as access

NOW = datetime.datetime.now(datetime.timezone.utc)


def test_settings_are_validated():
    s = access.normalize(NOW + datetime.timedelta(days=7), "signed_in", [" Grants@UIdaho.edu ", "grants@uidaho.edu"])
    assert s["audience"] == "signed_in" and s["emails"] == ["grants@uidaho.edu"]
    assert access.normalize(None, None, None) == {"expires_at": None, "audience": "anyone", "emails": []}
    # A naive datetime is read as UTC.
    naive = (NOW + datetime.timedelta(days=1)).replace(tzinfo=None)
    assert access.normalize(naive, "anyone", None)["expires_at"].tzinfo is not None
    for bad, message in [
        ((NOW - datetime.timedelta(minutes=1), "anyone", None), "future"),
        ((NOW + datetime.timedelta(days=400), "anyone", None), "a year"),
        ((None, "anyone", ["a@b.edu"]), "requires signing in"),
        ((None, "signed_in", ["not-an-email"]), "Not an email"),
        ((None, "everyone", None), "Choose who"),
    ]:
        with pytest.raises(HTTPException) as exc:
            access.normalize(*bad)
        assert message in exc.value.detail


def _user(email="ra@uidaho.edu", verified=True):
    return SimpleNamespace(user_id="u1", email=email, email_verified=verified, name="RA")


@pytest.mark.parametrize("settings, user, status", [
    ({"expires_at": NOW - datetime.timedelta(seconds=1), "audience": "anyone", "emails": []}, None, 410),
    ({"expires_at": None, "audience": "anyone", "emails": []}, None, None),
    ({"expires_at": None, "audience": "signed_in", "emails": []}, None, 401),
    ({"expires_at": None, "audience": "signed_in", "emails": []}, _user(verified=False), 403),
    ({"expires_at": None, "audience": "signed_in", "emails": []}, _user(), None),
    ({"expires_at": None, "audience": "signed_in", "emails": ["grants@uidaho.edu"]}, _user(), 403),
    ({"expires_at": None, "audience": "signed_in", "emails": ["ra@uidaho.edu"]}, _user(email="RA@uidaho.edu"), None),
    # Expiry wins over everything, even for an invited viewer.
    ({"expires_at": NOW - datetime.timedelta(days=1), "audience": "signed_in", "emails": ["ra@uidaho.edu"]}, _user(), 410),
])
def test_who_may_open_a_link(settings, user, status):
    if status is None:
        access.check(settings, user)
        return
    with pytest.raises(HTTPException) as exc:
        access.check(settings, user)
    assert exc.value.status_code == status
    if status == 401:
        assert exc.value.detail == "Not authenticated"  # the client refreshes a stale session on this


def test_link_for_token_reads_main_and_version_settings():
    doc = {"public_token": "main", "published_revision": "r2", "public_audience": "signed_in", "public_emails": ["a@b.edu"],
           "publications": [{"revision": "r1", "token": "v1", "expires_at": NOW + datetime.timedelta(days=3)}]}
    revision, settings, kind = access.link_for_token(doc, "main")
    assert (revision, kind, settings["audience"], settings["emails"]) == ("r2", "main", "signed_in", ["a@b.edu"])
    revision, settings, kind = access.link_for_token(doc, "v1")
    assert (revision, kind, settings["audience"]) == ("r1", "version", "anyone") and settings["expires_at"]
    assert access.link_for_token(doc, "nope") is None
    assert access.link_for_token({**doc, "published_revision": None}, "main") is None
