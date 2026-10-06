"""get_app_help gives real, role-aware UI paths for actions chat can't perform.

Support ticket: asked to delete a KB, change the default model, or add a team
admin, chat refused correctly but invented the directions ("three-dot menu",
"Settings → Model or similar", "Teams dropdown → Add member") and showed the
admin-only steps to every user.
"""

import types

import pytest

from app.services.access_control import TeamAccessContext
from app.services.chat_tools import get_app_help
from app.services.help_content import HELP_TOPICS, find_topics


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ("delete knowledge base", "delete-knowledge-base"),
        ("delete the QA Smoke 2 knowledge base", "delete-knowledge-base"),
        ("deleting a knowledge base", "delete-knowledge-base"),
        ("what is a knowledge base", "knowledge-bases"),
        ("change default chat model", "system-config"),
        ("system config", "system-config"),
        ("add member to team as admin", "teams"),
        ("invite member", "teams"),
    ],
)
def test_admin_action_queries_match_the_right_topic(query, expected_id):
    assert find_topics(query)[0]["id"] == expected_id


def test_every_multi_word_alias_routes_to_its_own_topic():
    # Single words ("team", "api") are genuinely shared across topics; a
    # multi-word alias is a specific phrasing and must land on its topic.
    misrouted = [
        (t["id"], alias, find_topics(alias)[0]["id"])
        for t in HELP_TOPICS
        for alias in t["aliases"]
        if " " in alias and find_topics(alias)[0]["id"] != t["id"]
    ]
    assert misrouted == []


def test_topics_carry_the_real_ui_paths():
    kb = find_topics("delete-knowledge-base")[0]["body"]
    assert "trash icon" in kb
    assert "three-dot" not in kb

    cfg = find_topics("system-config")[0]
    assert "**Admin**" in cfg["body"] and "**Config**" in cfg["body"]
    assert cfg["requires"] == "system admin"

    teams = find_topics("teams")[0]
    assert "Manage teams" in teams["body"] and "Invite" in teams["body"]
    assert "owner or admin" in teams["requires"]


def _ctx(*, is_admin: bool, team_role: str | None):
    roles = {"team-1": team_role} if team_role else {}
    return types.SimpleNamespace(deps=types.SimpleNamespace(
        user=types.SimpleNamespace(is_admin=is_admin),
        team_id="team-1",
        team_access=TeamAccessContext(team_uuids={"team-1"}, roles_by_uuid=roles),
        system_config_doc={},
    ))


@pytest.mark.asyncio
async def test_viewer_access_reports_a_plain_member():
    result = await get_app_help(_ctx(is_admin=False, team_role="member"), "system config")
    assert result["topic"]["requires"] == "system admin"
    assert result["viewer_access"] == {
        "is_system_admin": False,
        "current_team_role": "member",
    }


@pytest.mark.asyncio
async def test_viewer_access_reports_a_system_admin_and_team_owner():
    result = await get_app_help(_ctx(is_admin=True, team_role="owner"), "invite member")
    assert result["topic"]["id"] == "teams"
    assert result["viewer_access"] == {
        "is_system_admin": True,
        "current_team_role": "owner",
    }


@pytest.mark.asyncio
async def test_viewer_access_without_a_team():
    result = await get_app_help(_ctx(is_admin=False, team_role=None), "teams")
    assert result["viewer_access"]["current_team_role"] == "none"
