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

    # Resolve admin user
    admin = await User.find_one(User.user_id == admin_email)
    if not admin:
        admin = await User.find_one(User.email == admin_email)
    if not admin:
        print(f"Error: Admin user '{admin_email}' not found. Run create_admin.py first.")
        sys.exit(1)

    # Check if a non-personal team with this name already exists
    existing = await Team.find_one(Team.name == team_name)
    if existing:
        print(f"Team '{team_name}' already exists (uuid={existing.uuid}) — reusing it.")
        team = existing
    else:
        team = Team(
            uuid=uuid.uuid4().hex,
            name=team_name,
            owner_user_id=admin.user_id,
        )
        await team.insert()

        membership = TeamMembership(team=team.id, user_id=admin.user_id, role="owner")
        await membership.insert()

        print(f"Created team: '{team_name}' (uuid={team.uuid})")

    # Ensure admin is a member
    existing_m = await TeamMembership.find_one(
        TeamMembership.team == team.id,
        TeamMembership.user_id == admin.user_id,
    )
    if not existing_m:
        await TeamMembership(team=team.id, user_id=admin.user_id, role="owner").insert()

    # Set as default in SystemConfig
    cfg = await SystemConfig.get_config()
    cfg.default_team_id = team.uuid
    await cfg.save()

    print(f"Default team set to: '{team_name}' (uuid={team.uuid})")
    print("New users will automatically join this team when they sign up or log in.")


if __name__ == "__main__":
    asyncio.run(main())
