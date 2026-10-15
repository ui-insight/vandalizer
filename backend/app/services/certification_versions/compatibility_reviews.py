"""Recorded course/product compatibility reviews; a record is evidence, not a waiver.

A production-authorized authored course is "advertised as current" when it is
the new-learner default. That requires a committed review of the exact manifest
against an exact product commit. CI rejects the review once a later commit
changes a watched product path, so a material product change forces a new
recorded review before the course can keep being offered as current.
"""
import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .catalog import CourseCatalogError

REVIEWS_ROOT = Path(__file__).resolve().parents[3] / 'certification-data' / 'compatibility-reviews'
# Each maintenance trigger owns one check; see the course README for owners.
CHECKS = ('product_release', 'lessons_and_screenshots', 'labs', 'tool_availability', 'rubrics', 'learner_preservation')
# Recording the review itself, or the registry change that advertises the
# course, is not a product change that needs another review.
SELF_PATHS = ('backend/certification-data/compatibility-reviews/', 'backend/certification-data/courses/registry.json')


class ReviewCheck(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    result: Literal['passed', 'failed', 'not_applicable']
    evidence: str = Field(min_length=3, max_length=2000)


class CompatibilityReview(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    release_id: str
    manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    product_commit: str = Field(pattern=r'^[a-f0-9]{40}$')
    product_change_report_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    deployment_fingerprint: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    checks: dict[str, ReviewCheck]
    result: Literal['compatible', 'incompatible']
    unresolved_limits: tuple[str, ...] = ()
    reviewer_role: str = Field(min_length=3, max_length=200)
    reviewed_at: str

    @model_validator(mode='after')
    def consistent(self):
        if set(self.checks) != set(CHECKS):
            raise ValueError('A compatibility review must record every maintenance check: ' + ', '.join(CHECKS))
        if self.result == 'compatible' and any(check.result == 'failed' for check in self.checks.values()):
            raise ValueError('A failed check cannot produce a compatible review')
        stamp = datetime.datetime.fromisoformat(self.reviewed_at)
        if stamp.tzinfo is None:
            raise ValueError('Review time needs a timezone')
        return self


def load_review(release_id: str, root: Path = REVIEWS_ROOT) -> CompatibilityReview | None:
    path = root / f'{release_id}.json'
    if not path.exists():
        return None
    try:
        review = CompatibilityReview.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as exc:
        raise CourseCatalogError(f'Compatibility review for {release_id} is invalid: {exc}') from exc
    if review.release_id != release_id:
        raise CourseCatalogError(f'Compatibility review file {path.name} names another release')
    return review


def needs_review(package) -> bool:
    """Only a production-authorized authored course is advertised as current."""
    return package.manifest.historical_provenance != 'continuation-baseline' and not package.entry.qa_staging


def require_compatible(package, root: Path = REVIEWS_ROOT) -> CompatibilityReview | None:
    if not needs_review(package):
        return None
    release_id = package.manifest.release_id
    review = load_review(release_id, root)
    if review is None:
        raise CourseCatalogError(f'Record a compatibility review in compatibility-reviews/{release_id}.json before offering {release_id} as current')
    if review.manifest_sha256 != package.manifest_sha256:
        raise CourseCatalogError('The compatibility review covers a different manifest; review the exact package')
    if review.result != 'compatible':
        raise CourseCatalogError('The recorded compatibility review found the course incompatible: '
                                 + ', '.join(name for name, check in review.checks.items() if check.result == 'failed'))
    return review


def stale_paths(changed_paths: list[dict]) -> list[dict]:
    """Watched product changes made after the reviewed commit."""
    return [item for item in changed_paths if not item['path'].startswith(SELF_PATHS)]
