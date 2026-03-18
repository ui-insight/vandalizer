#!/usr/bin/env python3
"""Bootstrap a fresh Vandalizer deployment for self-hosted operators.

This is the canonical first-run path for Docker Compose installs:
1. Create or update the initial admin account.
2. Optionally create/reuse a shared default team for all new users.

Usage:
    docker compose exec -T api \
      env ADMIN_EMAIL=admin@example.edu \
          ADMIN_PASSWORD=secret \
          ADMIN_NAME="Initial Admin" \
          DEFAULT_TEAM_NAME="Research Administration" \
      python bootstrap_install.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from app.config import Settings
from app.database import init_db
from create_admin import ensure_admin
from setup_default_team import ensure_default_team


def _print_usage() -> None:
    print("Error: ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required.")
    print(
        "Usage: ADMIN_EMAIL=admin@example.edu ADMIN_PASSWORD=secret "
        "ADMIN_NAME='Initial Admin' DEFAULT_TEAM_NAME='Research Administration' "
        "python bootstrap_install.py"
    )


async def main():
    settings = Settings()
    await init_db(settings)

    admin_email = os.environ.get("ADMIN_EMAIL", "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    admin_name = os.environ.get("ADMIN_NAME", "Admin")
    default_team_name = os.environ.get("DEFAULT_TEAM_NAME", "").strip()

    if not admin_email or not admin_password:
        _print_usage()
        sys.exit(1)

    admin_user, admin_status = await ensure_admin(admin_email, admin_password, admin_name)

    if admin_status == "created":
        print(f"Admin user created: {admin_user.user_id}")
    elif admin_status == "updated":
        print(f"Admin user updated with admin/examiner permissions: {admin_user.user_id}")
    else:
        print(f"Admin user already ready: {admin_user.user_id}")

    if not default_team_name:
        print("No DEFAULT_TEAM_NAME set. New users will start in their personal team only.")
        return

    team, team_status, membership_status = await ensure_default_team(
        default_team_name,
        admin_email,
    )

    if team_status == "created":
        print(f"Default team created: {team.name} (uuid={team.uuid})")
    else:
        print(f"Default team reused: {team.name} (uuid={team.uuid})")

    if membership_status == "created":
        print("Bootstrap admin added to the default team as owner.")
    elif membership_status == "updated":
        print("Bootstrap admin role on the default team was corrected to owner.")
    else:
        print("Bootstrap admin already had owner access to the default team.")

    print("New users will auto-join the default team on first registration or SSO login.")
    print("The bootstrap admin keeps its personal team as well; switch teams in the UI if needed.")


if __name__ == "__main__":
    asyncio.run(main())
