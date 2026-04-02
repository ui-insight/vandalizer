"""Pluggable file storage backend.

Supports local filesystem (default) and S3-compatible object storage.
Configure via environment variables:

    STORAGE_BACKEND=local   # default
    STORAGE_BACKEND=s3

    S3_BUCKET=my-bucket
    S3_REGION=us-east-1
    S3_ACCESS_KEY_ID=...          # optional; uses IAM role if omitted
    S3_SECRET_ACCESS_KEY=...      # optional; uses IAM role if omitted
    S3_ENDPOINT_URL=...           # optional; for MinIO / custom S3-compatible stores
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Protocol


class StorageBackend(Protocol):
    """Minimal interface all storage backends must implement."""

    async def write(self, relative_path: str, data: bytes) -> None:
        """Persist *data* at *relative_path*."""
        ...

    async def read(self, relative_path: str) -> bytes:
        """Return the bytes stored at *relative_path*."""
        ...

    async def delete(self, relative_path: str) -> None:
        """Remove the object at *relative_path* (no-op if absent)."""
        ...

    async def exists(self, relative_path: str) -> bool:
        """Return True if *relative_path* exists in the store."""
        ...

    def public_path(self, relative_path: str) -> str | None:
        """Return a local filesystem path for serving, or None for remote stores."""
        ...


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------

class LocalStorage:
    """Stores files under *root_dir* on the local filesystem."""

    def __init__(self, root_dir: str) -> None:
        self._root = Path(root_dir)

    def _resolve(self, relative_path: str) -> Path:
        root = self._root.resolve()
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Path traversal detected: {relative_path!r}")
        return target

    async def write(self, relative_path: str, data: bytes) -> None:
        path = self._resolve(relative_path)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def read(self, relative_path: str) -> bytes:
        return await asyncio.to_thread(self._resolve(relative_path).read_bytes)

    async def delete(self, relative_path: str) -> None:
        path = self._resolve(relative_path)
        await asyncio.to_thread(lambda: path.unlink(missing_ok=True))

    async def exists(self, relative_path: str) -> bool:
        return await asyncio.to_thread(self._resolve(relative_path).exists)

    def public_path(self, relative_path: str) -> str | None:
        return str(self._resolve(relative_path))


# ---------------------------------------------------------------------------
# S3 backend
# ---------------------------------------------------------------------------

class S3Storage:
    """Stores files in an S3-compatible bucket using aioboto3."""

    def __init__(
        self,
        bucket: str,
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._endpoint_url = endpoint_url

    def _session(self) -> Any:
        try:
            import aioboto3
        except ImportError as e:
            raise RuntimeError(
                "aioboto3 is required for S3 storage. "
                "Install it: pip install aioboto3"
            ) from e
        kwargs = {"region_name": self._region}
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        if self._endpoint_url:
            kwargs["endpoint_url"] = self._endpoint_url
        return aioboto3.Session().client("s3", **kwargs)

    async def write(self, relative_path: str, data: bytes) -> None:
        import io
        async with self._session() as s3:
            await s3.upload_fileobj(io.BytesIO(data), self._bucket, relative_path)

    async def read(self, relative_path: str) -> bytes:
        import io
        buf = io.BytesIO()
        async with self._session() as s3:
            await s3.download_fileobj(self._bucket, relative_path, buf)
        return buf.getvalue()

    async def delete(self, relative_path: str) -> None:
        async with self._session() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=relative_path)

    async def exists(self, relative_path: str) -> bool:
        from botocore.exceptions import ClientError
        async with self._session() as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=relative_path)
                return True
            except ClientError:
                return False

    def public_path(self, relative_path: str) -> str | None:
        return None  # S3 objects are not on the local filesystem


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_storage: StorageBackend | None = None


def get_storage(settings: Any = None) -> StorageBackend:
    """Return the configured storage backend (singleton)."""
    global _storage
    if _storage is not None:
        return _storage

    if settings is None:
        from app.config import Settings
        settings = Settings()

    backend = getattr(settings, "storage_backend", "local")

    if backend == "s3":
        _storage = S3Storage(
            bucket=settings.s3_bucket,
            region=getattr(settings, "s3_region", "us-east-1"),
            access_key_id=getattr(settings, "s3_access_key_id", None),
            secret_access_key=getattr(settings, "s3_secret_access_key", None),
            endpoint_url=getattr(settings, "s3_endpoint_url", None),
        )
    else:
        _storage = LocalStorage(settings.upload_dir)

    return _storage


def reset_storage() -> None:
    """Reset the storage singleton (for testing)."""
    global _storage
    _storage = None
