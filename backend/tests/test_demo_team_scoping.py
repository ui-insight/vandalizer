"""Unit tests for demo cohort team scoping (demo_service._find_or_create_org_team).

The org name on a demo application is self-asserted free text, and the old
behavior joined the applicant to *any* team whose name matched it — including
real workspaces, whose shared documents the applicant could then read. Joining
now requires the team to be demo-created AND the applicant's email domain to
match the team owner's; everything else gets a fresh team.
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
        self.id = f"id-{len(created)}"
        self.insert = AsyncMock()
        self.save = AsyncMock()
        created.append(self)

    cls.__init__ = _init
    cls.created = created
    return cls


def _team(**overrides) -> SimpleNamespace:
    team = SimpleNamespace(
        id="team-1",
        uuid="t-1",
        name="Example University - OSP",
        owner_user_id="owner@example.edu",
        is_demo_team=True,
        created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
    )
    for key, value in overrides.items():
        setattr(team, key, value)
    return team


async def test_never_joins_a_real_team_with_matching_name():
    """A non-demo team with the typed name must not gain the applicant."""
    real_team = _team(is_demo_team=False)
    teams = _constructible_fake_model(find_one_result=real_team)
    memberships = _constructible_fake_model()

    with (
        patch.object(demo_service, "Team", teams),
        patch.object(demo_service, "TeamMembership", memberships),
    ):
        team = await demo_service._find_or_create_org_team(
            "Example University",
            "ada@example.edu",
            "OSP",
            applicant_email="ada@example.edu",
        )

    assert team is not real_team
    assert team.is_demo_team is True
    # The clashing name gets a distinguishing suffix, not a silent duplicate.
    assert team.name.startswith("Example University - OSP (")
    team.insert.assert_awaited_once()


async def test_joins_demo_cohort_when_owner_domain_matches():
    cohort = _team(is_demo_team=True, owner_user_id="owner@example.edu")
    teams = _constructible_fake_model(find_one_result=cohort)
    owner = SimpleNamespace(user_id="owner@example.edu", email="owner@example.edu")

    with (
        patch.object(demo_service, "Team", teams),
        patch.object(demo_service, "User", fake_model(find_one_result=owner)),
    ):
        team = await demo_service._find_or_create_org_team(
            "Example University",
            "ada@example.edu",
            "OSP",
            applicant_email="Ada@Example.EDU",
        )

    assert team is cohort
    assert teams.created == []


async def test_domain_mismatch_gets_a_fresh_team():
    """Typing another org's name doesn't buy entry to its demo cohort."""
    cohort = _team(is_demo_team=True, owner_user_id="owner@example.edu")
    teams = _constructible_fake_model(find_one_result=cohort)
    memberships = _constructible_fake_model()
    owner = SimpleNamespace(user_id="owner@example.edu", email="owner@example.edu")

    with (
        patch.object(demo_service, "Team", teams),
        patch.object(demo_service, "TeamMembership", memberships),
        patch.object(demo_service, "User", fake_model(find_one_result=owner)),
    ):
        team = await demo_service._find_or_create_org_team(
            "Example University",
            "mallory@rival.edu",
            "OSP",
            applicant_email="mallory@rival.edu",
        )

    assert team is not cohort
    assert team.is_demo_team is True
    assert team.name.startswith("Example University - OSP (")


async def test_fresh_org_creates_demo_team_with_owner_membership():
    teams = _constructible_fake_model(find_one_result=None)
    memberships = _constructible_fake_model()

    with (
        patch.object(demo_service, "Team", teams),
        patch.object(demo_service, "TeamMembership", memberships),
    ):
        team = await demo_service._find_or_create_org_team(
            "Example University",
            "ada@example.edu",
            applicant_email="ada@example.edu",
        )

    assert team.name == "Example University"  # no department, no suffix
    assert team.is_demo_team is True
    assert len(memberships.created) == 1
    membership = memberships.created[0]
    assert membership.role == "owner"
    assert membership.user_id == "ada@example.edu"


def test_login_domain_edges():
    assert demo_service._login_domain("Ada@Example.EDU") == "example.edu"
    assert demo_service._login_domain("not-an-email") == ""
    assert demo_service._login_domain("") == ""
