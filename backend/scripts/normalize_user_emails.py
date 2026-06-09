"""One-shot remediation: lowercase mixed-case stored email addresses.

Background: login normalizes the typed identity to lowercase before a
case-sensitive MongoDB lookup (User.user_id / User.email). Demo users were
historically created with their email verbatim (e.g. "Janis.Miller@unt.edu"),
so a mixed-case stored email could never be matched at login — the user got
the misleading "We couldn't find an account for that email" message instead of
"wrong password".

The write path is now fixed (demo_service normalizes on create). This script
repairs existing records.

We only lowercase the *email* field, NOT user_id: user_id is a foreign key
referenced by TeamMembership, DemoApplication.user_id, audit logs and document
ownership, so rewriting it would orphan that data. Login's email fallback
(User.find_one(User.email == normalized)) resolves these users once email is
lowercase, regardless of user_id casing.

Idempotent: rerunning only touches records still holding a mixed-case email.

Usage:
    uv run python -m scripts.normalize_user_emails
"""

from __future__ import annotations

import asyncio

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.user import User


async def migrate() -> dict[str, int]:
    settings = Settings()
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_host)
    db = client[settings.mongo_db]
    await init_beanie(database=db, document_models=[User])

    users_fixed = 0
    apps_fixed = 0

    # Users: any stored email that isn't already lowercase.
    cursor = db.user.find({"email": {"$exists": True, "$ne": None}})
    async for doc in cursor:
        email = doc.get("email")
        if not isinstance(email, str):
            continue
        lowered = email.strip().lower()
        if lowered != email:
            await db.user.update_one(
                {"_id": doc["_id"]},
                {"$set": {"email": lowered}},
            )
            users_fixed += 1

    # Demo applications: keep the lookup-by-email dedup consistent too.
    cursor = db.demo_application.find({"email": {"$exists": True, "$ne": None}})
    async for doc in cursor:
        email = doc.get("email")
        if not isinstance(email, str):
            continue
        lowered = email.strip().lower()
        if lowered != email:
            await db.demo_application.update_one(
                {"_id": doc["_id"]},
                {"$set": {"email": lowered}},
            )
            apps_fixed += 1

    return {"users_fixed": users_fixed, "apps_fixed": apps_fixed}


if __name__ == "__main__":
    result = asyncio.run(migrate())
    print(
        f"Normalization complete: users_fixed={result['users_fixed']}, "
        f"demo_applications_fixed={result['apps_fixed']}"
    )
