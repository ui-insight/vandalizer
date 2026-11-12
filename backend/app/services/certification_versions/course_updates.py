"""Plain update status for a pinned course: is a newer optional course offered?

Reads only the registry. Loading the offered packages belongs to the explicit
comparison; this flag must stay cheap enough to attach to every course response.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.certification_versions.catalog import CoursePackage

from .catalog import CourseCatalog, CourseCatalogError


def optional_update_available(package: CoursePackage) -> bool | None:
    """True/False from the published offers; None when the registry cannot be read."""
    try:
        registry = (CourseCatalog(package.catalog_root) if package.catalog_root else CourseCatalog()).registry()
    except CourseCatalogError:
        return None
    offers = registry.get('optional_upgrade_offers', {}).get(package.manifest.release_id, [])
    return any(registry['releases'][version].get('state') == 'published' for version in offers)
