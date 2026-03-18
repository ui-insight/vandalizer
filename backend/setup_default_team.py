#!/usr/bin/env python3
"""Create a team and set it as the default for new user auto-assignment.

Idempotent: if a team with this name already exists and is owned by the
same admin, it will be reused rather than duplicated.

Usage (via deploy.sh):
    docker compose exec -T api env TEAM_NAME="Research Administration" python setup_default_team.py

Environment variables:
    TEAM_NAME    (required) Name of the team to create / reuse
    ADMIN_EMAIL  (required) Admin user who will own the team
"""

import asyncio
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from app.config import Settings
from app.database import init_db
from app.models.team import Team, TeamMembership
from app.models.system_config import SystemConfig
from app.models.user import User


def select_reusable_team(candidates: list[Team], admin_user_id: str) -> Team | None:
    """Reuse only a team owned by the bootstrap admin.

    Team names are not unique, so blindly reusing the first matching team can
    bind new users to another user's workspace.
    """
    for team in candidates:
        if team.owner_user_id == admin_user_id:
            return team
    return None


async def ensure_default_team(team_name: str, admin_email: str) -> tuple[Team, str, str]:
    """Create or reuse the bootstrap default team.

    Returns ``(team, team_status, membership_status)`` where:
    - ``team_status`` is ``created`` or ``reused``
    - ``membership_status`` is ``created``, ``updated``, or ``unchanged``
    """
    normalized_team_name = team_name.strip()
    normalized_admin_email = admin_email.strip().lower()

    admin = await User.find_one(User.user_id == normalized_admin_email)
    if not admin:
        admin = await User.find_one(User.email == normalized_admin_email)
    if not admin:
        raise ValueError(
            f"Admin user '{normalized_admin_email}' not found. Run create_admin.py first."
        )

    candidates = await Team.find(Team.name == normalized_team_name).to_list()
    team = select_reusable_team(candidates, admin.user_id)
    team_status = "reused"

    if not team:
        team = Team(
            uuid=uuid.uuid4().hex,
            name=normalized_team_name,
            owner_user_id=admin.user_id,
        )
        await team.insert()
        team_status = "created"

    membership = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == admin.user_id,
    )
    membership_status = "unchanged"
    if not membership:
        membership = TeamMembership(team=team.id, user_id=admin.user_id, role="owner")
        await membership.insert()
        membership_status = "created"
    elif membership.role != "owner":
        membership.role = "owner"
        await membership.save()
        membership_status = "updated"

    cfg = await SystemConfig.get_config()
    cfg.default_team_id = team.uuid
    await cfg.save()

    return team, team_status, membership_status


async def main():
    settings = Settings()
    await init_db(settings)

    team_name = os.environ.get("TEAM_NAME", "").strip()
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()

    if not team_name:
        print("Error: TEAM_NAME environment variable is required.")
        sys.exit(1)
    if not admin_email:
        print("Error: ADMIN_EMAIL environment variable is required.")
        sys.exit(1)

    try:
        team, team_status, membership_status = await ensure_default_team(team_name, admin_email)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if team_status == "created":
        print(f"Created team: '{team.name}' (uuid={team.uuid})")
    else:
        print(f"Team '{team.name}' already exists for this admin (uuid={team.uuid}) — reusing it.")

    if membership_status == "created":
        print("Bootstrap admin added to the default team as owner.")
    elif membership_status == "updated":
        print("Bootstrap admin membership was upgraded to owner.")

    print(f"Default team set to: '{team.name}' (uuid={team.uuid})")
    print("New users will automatically join this team when they sign up or log in.")


if __name__ == "__main__":
    asyncio.run(main())
