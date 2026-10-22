"""Supplement historical teaching without rewriting its package or requirements."""
from functools import lru_cache
import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .catalog import CourseCatalogError

SOURCE = Path(__file__).resolve().parents[3] / 'certification-data/editorial-corrections.json'
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class EditorialNoticeBase(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=96)
    manifest_sha256: Digest
    issued_at: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    title: str = Field(min_length=1, max_length=120)
    paragraphs: list[str] = Field(min_length=1, max_length=8)
    assessment_changed: Literal[False]
    unversioned_content_sha256: list[Digest] = Field(min_length=1)


class EditorialNotice(EditorialNoticeBase):
    lesson_ids: list[str] = Field(min_length=1)


class ModuleEditorialNotice(EditorialNoticeBase):
    module_ids: list[str] = Field(min_length=1)


class EditorialNotices(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1]
    notices: list[EditorialNotice]
    module_notices: list[ModuleEditorialNotice] = Field(default_factory=list)

    @model_validator(mode='after')
    def unambiguous(self):
        all_notices = [*self.notices, *self.module_notices]
        if len({notice.id for notice in all_notices}) != len(all_notices):
            raise ValueError('Editorial notice identities must be unique')
        for notice in all_notices:
            targets = notice.lesson_ids if isinstance(notice, EditorialNotice) else notice.module_ids
            if len(set(targets)) != len(targets) or not all(targets + notice.paragraphs):
                raise ValueError('Editorial targets and paragraphs must be nonempty and unambiguous')
        return self


@lru_cache(maxsize=1)
def _load():
    try:
        return EditorialNotices.model_validate_json(SOURCE.read_bytes())
    except (OSError, ValueError) as exc:
        raise CourseCatalogError('Current editorial guidance is unavailable; retry the course read later.') from exc


def notices_for(manifest_sha256: str | None, lesson_id: str | None, content: str | None = None) -> list[dict]:
    if not manifest_sha256 and not content:
        return []
    content_digest = hashlib.sha256(content.encode()).hexdigest() if not manifest_sha256 and content else None
    return [{**notice.model_dump(exclude={'manifest_sha256', 'lesson_ids', 'unversioned_content_sha256'}),
             'identity_basis': 'course_manifest' if manifest_sha256 else 'preserved_lesson_text'}
            for notice in _load().notices if (
                notice.manifest_sha256 == manifest_sha256 and lesson_id in notice.lesson_ids
                if manifest_sha256 else content_digest in notice.unversioned_content_sha256)]


def module_notices_for(manifest_sha256: str | None, module_id: str | None, description: str | None = None) -> list[dict]:
    if not manifest_sha256 and not description:
        return []
    digest = hashlib.sha256(description.encode()).hexdigest() if not manifest_sha256 and description else None
    return [{**notice.model_dump(exclude={'manifest_sha256', 'module_ids', 'unversioned_content_sha256'}),
             'identity_basis': 'course_manifest' if manifest_sha256 else 'preserved_module_description'}
            for notice in _load().module_notices if (
                notice.manifest_sha256 == manifest_sha256 and module_id in notice.module_ids
                if manifest_sha256 else digest in notice.unversioned_content_sha256)]
