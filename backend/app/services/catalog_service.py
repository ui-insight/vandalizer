"""Verified-catalog version helpers used by the in-app upgrade feature."""

import logging

from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import notification_service

logger = logging.getLogger(__name__)


async def notify_admins_of_catalog_update_if_new() -> None:
    """If the bundled catalog is newer than what's applied, drop a one-time
    'update available' notification to every admin/staff user.

    Called on startup. Uses an atomic compare-and-set on the notified-version
    marker so that, with multiple API workers each running this on boot, only
    one worker actually sends the notifications (and only once per new version).
    """
    # Imported here to avoid a circular import at module load.
    from scripts.seed_catalog import _read_seed_version, _version_newer

    try:
        bundled = _read_seed_version()
    except Exception:
        logger.warning("Could not read bundled catalog version; skipping update check")
        return

    cfg = await SystemConfig.get_config()
    if not _version_newer(bundled, cfg.catalog_version):
        return  # already current (or ahead) — nothing to announce
    if cfg.catalog_upgrade_notified_version == bundled:
        return  # already announced this version

    # Atomic claim: only the worker that flips the marker proceeds to notify.
    coll = SystemConfig.get_motor_collection()
    res = await coll.update_one(
        {"_id": cfg.id, "catalog_upgrade_notified_version": {"$ne": bundled}},
        {"$set": {"catalog_upgrade_notified_version": bundled}},
    )
    if res.modified_count == 0:
        return  # another worker already claimed this announcement

    admins = await User.find({"$or": [{"is_admin": True}, {"is_staff": True}]}).to_list()
    applied = cfg.catalog_version or "none"
    for admin in admins:
        try:
            await notification_service.create_notification(
                user_id=admin.user_id,
                kind="catalog_upgrade_available",
                title=f"Catalog update available: {bundled}",
                body=f"Your verified catalog is at {applied}. Review and apply the update from Admin → Catalog.",
                link="/admin?tab=catalog",
            )
        except Exception:
            logger.warning("catalog-available notify failed for %s", getattr(admin, "user_id", "?"))
    logger.info("Notified %d admin(s) of catalog update %s", len(admins), bundled)
