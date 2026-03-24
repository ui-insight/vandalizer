#!/usr/bin/env python3
"""Create an initial admin account for a fresh Vandalizer deployment.

Idempotent: safe to run multiple times. If the admin user already exists,
it ensures the is_admin and is_examiner flags are set.

Usage:
    cd backend
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=yourpassword python create_admin.py

Environment variables (or .env file):
    ADMIN_EMAIL     (required)
    ADMIN_PASSWORD  (required)
    ADMIN_NAME      (default: Admin)
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from app.config import Settings
from app.database import init_db
from app.models.user import User


async def ensure_admin(email: str, password: str, name: str = "Admin") -> tuple[User, str]:
    """Create or update the bootstrap admin user.

    Returns ``(user, status)`` where status is one of:
    - ``created``: new admin account was created
    - ``updated``: existing user was promoted to admin/examiner or password was reset
    - ``unchanged``: existing user already had the expected permissions
    """
    from app.utils.security import hash_password

    normalized_email = email.strip().lower()

    existing = await User.find_one(User.email == normalized_email)
    if existing:
        changed = False
        if not existing.is_admin:
            existing.is_admin = True
            changed = True
        if not existing.is_examiner:
            existing.is_examiner = True
            changed = True
        if changed:
            # Reset password when promoting permissions
            existing.password_hash = hash_password(password)
            await existing.save()
            return existing, "updated"
        return existing, "unchanged"

    from app.services.auth_service import register

    user = await register(
        user_id=normalized_email,
        email=normalized_email,
        password=password,
        name=name,
    )
    user.is_admin = True
    user.is_examiner = True
    await user.save()
    return user, "created"


async def main():
    settings = Settings()
    await init_db(settings)

    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    name = os.environ.get("ADMIN_NAME", "Admin")

    if not email or not password:
        print("Error: ADMIN_EMAIL and ADMIN_PASSWORD environment variables are required.")
        print("Usage: ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=secret python create_admin.py")
        sys.exit(1)

    user, status = await ensure_admin(email, password, name)

    if status == "updated":
        print(f"Updated existing user '{user.user_id}' with admin + examiner access.")
        return

    if status == "unchanged":
        print(f"Admin user '{user.user_id}' already exists with correct permissions.")
        return

    print("Created admin user:")
    print(f"  Email:    {email.strip().lower()}")
    print(f"  Name:     {name}")
    print("  Admin:    Yes")
    print("  Examiner: Yes")


if __name__ == "__main__":
    asyncio.run(main())
