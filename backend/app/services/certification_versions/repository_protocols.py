"""Structural contracts shared by repositories with different write operations."""
from typing import Protocol


class RecordReader(Protocol):
    async def get(self, user_id: str, reference: str, /) -> dict | None:
        """Read one owned, integrity-checked record without creating it."""
        ...
