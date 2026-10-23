"""Plain update status for a pinned course: is a newer optional course offered?

Reads only the registry. Loading the offered packages belongs to the explicit
comparison; this flag must stay cheap enough to attach to every course response.
"""
from .catalog import CourseCatalog, CourseCatalogError


def optional_update_available(package) -> bool | None:
    """True/False from the published offers; None when the registry cannot be read."""
    try:
        registry = (CourseCatalog(package.catalog_root) if package.catalog_root else CourseCatalog()).registry()
    except CourseCatalogError:
        return None
    offers = registry.get('optional_upgrade_offers', {}).get(package.manifest.release_id, [])
    return any(registry['releases'][version].get('state') == 'published' for version in offers)
