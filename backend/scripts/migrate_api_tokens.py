"""One-shot migration: hash existing plaintext api_token values.

Before: User.api_token stored the plaintext token.
After:  User.api_token_hash stores sha256(token); User.api_token is unset.

Run once after deploying the hashing change. Idempotent: rerunning is safe
(users already migrated have no api_token field).

Usage:
    uv run python -m scripts.migrate_api_tokens
"""

from __future__ import annotations

import asyncio

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import Settings
from app.models.user import User
from app.utils.security import hash_api_token


async def migrate() -> dict[str, int]:
    settings = Settings()
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.mongo_host)
    db = client[settings.mongo_db]
    await init_beanie(database=db, document_models=[User])

    hashed = 0
    already_migrated = 0
    empty = 0

    # Query the raw collection so we can see the legacy api_token field even
    # though it's no longer on the Beanie model.
    cursor = db.user.find({"api_token": {"$exists": True}})
    async for doc in cursor:
        plaintext = doc.get("api_token")
        if not plaintext:
            # Empty/None legacy field — just unset it.
            await db.user.update_one(
                {"_id": doc["_id"]},
                {"$unset": {"api_token": ""}},
            )
            empty += 1
            continue

        if doc.get("api_token_hash"):
            # Already has a hash — just drop the plaintext.
            await db.user.update_one(
                {"_id": doc["_id"]},
                {"$unset": {"api_token": ""}},
            )
            already_migrated += 1
            continue

        await db.user.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {"api_token_hash": hash_api_token(plaintext)},
                "$unset": {"api_token": ""},
            },
        )
        hashed += 1

    return {"hashed": hashed, "already_migrated": already_migrated, "empty": empty}


if __name__ == "__main__":
    result = asyncio.run(migrate())
    print(
        f"Migration complete: hashed={result['hashed']}, "
        f"already_migrated={result['already_migrated']}, empty_unset={result['empty']}"
    )
