#!/usr/bin/env python3
"""Create an initial admin account for a fresh Vandalizer deployment.

Idempotent: safe to run multiple times. If the admin user already exists,
it ensures the is_admin and is_examiner flags are set.

Usage:
    cd backend
    python create_admin.py

Environment variables (or .env file):
    ADMIN_EMAIL     (default: admin@admin.com)
    ADMIN_PASSWORD  (default: admin)
    ADMIN_NAME      (default: Admin)
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from app.config import Settings
from app.database import init_db
from app.models.user import User


async def main():
    settings = Settings()
    await init_db(settings)

    email = os.environ.get("ADMIN_EMAIL", "admin@admin.com")
    password = os.environ.get("ADMIN_PASSWORD", "admin")
    name = os.environ.get("ADMIN_NAME", "Admin")

    # Check if user already exists
    existing = await User.find_one(User.email == email.strip().lower())
    if existing:
        changed = False
        if not existing.is_admin:
            existing.is_admin = True
            changed = True
        if not existing.is_examiner:
            existing.is_examiner = True
            changed = True
        if changed:
            await existing.save()
            print(f"Updated existing user '{existing.user_id}' with admin + examiner access.")
        else:
            print(f"Admin user '{existing.user_id}' already exists with correct permissions.")
        return

    # Create new admin via the register flow
    from app.services.auth_service import register

    user = await register(
        user_id=email.strip().lower(),
        email=email.strip().lower(),
        password=password,
        name=name,
    )
    user.is_admin = True
    user.is_examiner = True
    await user.save()

    print(f"Created admin user:")
    print(f"  Email:    {email}")
    print(f"  Password: {password}")
    print(f"  Name:     {name}")
    print(f"  Admin:    Yes")
    print(f"  Examiner: Yes")


if __name__ == "__main__":
    asyncio.run(main())
