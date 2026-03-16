"""Reusable model mixins for Beanie Document classes."""

import datetime
from typing import Optional

from pydantic import Field


class SoftDeleteMixin:
    """Mixin that adds soft-delete support to a Beanie Document.

    Usage:
        class MyModel(Document, SoftDeleteMixin):
            ...

    Then use `await obj.soft_delete()` instead of `await obj.delete()`.
    Query active records with `MyModel.find(MyModel.deleted_at == None)`.
    """

    deleted_at: Optional[datetime.datetime] = None
    deleted_by: Optional[str] = None

    async def soft_delete(self, user_id: str | None = None) -> None:
        self.deleted_at = datetime.datetime.now(tz=datetime.timezone.utc)
        self.deleted_by = user_id
        await self.save()  # type: ignore[attr-defined]

    async def restore(self) -> None:
        self.deleted_at = None
        self.deleted_by = None
        await self.save()  # type: ignore[attr-defined]

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class TimestampMixin:
    """Mixin that adds created_at/updated_at with proper default_factory."""

    created_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
    updated_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.timezone.utc)
    )
