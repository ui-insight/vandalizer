"""Admin-triggered verified-catalog upgrade Celery task.

Runs the seed pass (and, optionally, the prune/retire pass) against the
bundled seed files, records progress on the SystemConfig singleton so the admin
UI can poll it, and notifies admins on completion or failure.
"""

import asyncio
import datetime
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@celery.task(bind=True, name="tasks.catalog.upgrade")
def upgrade_catalog_task(self, target_version: str, prune: bool, user_id: str):
    """Apply the bundled catalog: seed (add/refresh) then optionally retire
    items dropped from the catalog. State is mirrored to
    SystemConfig.catalog_upgrade throughout for the admin UI to poll."""
    started = _now_iso()

    async def _run():
        from app.config import Settings
        from app.database import init_db
        from app.models.system_config import SystemConfig
        from app.models.user import User
        from app.services import notification_service
        from scripts.seed_catalog import ALL_TYPES, prune_stale_seeded_items, seed_catalog

        await init_db(Settings())

        async def _notify_admins(kind: str, title: str, body: str) -> None:
            admins = await User.find(
                {"$or": [{"is_admin": True}, {"is_staff": True}]}
            ).to_list()
            for admin in admins:
                try:
                    await notification_service.create_notification(
                        user_id=admin.user_id,
                        kind=kind,
                        title=title,
                        body=body,
                        link="/admin?tab=catalog",
                    )
                except Exception:  # one bad recipient shouldn't abort the rest
                    logger.warning("catalog notify failed for %s", getattr(admin, "user_id", "?"))

        # Mark running (router also sets this; refresh started_at defensively).
        cfg = await SystemConfig.get_config()
        cfg.catalog_upgrade = {
            "state": "running",
            "target_version": target_version,
            "started_at": started,
            "by": user_id,
            "prune": prune,
        }
        await cfg.save()

        try:
            seed_summary = await seed_catalog(types=set(ALL_TYPES))
            retired = []
            if prune:
                retired = await prune_stale_seeded_items(set(ALL_TYPES), dry_run=False)

            summary = {
                "created": seed_summary.get("created", 0),
                "updated": seed_summary.get("updated", 0),
                "retired": len(retired),
                "retired_items": retired,
            }
            message = (
                f"Upgraded to {target_version}: {summary['created']} added, "
                f"{summary['updated']} refreshed, {summary['retired']} retired."
            )
            cfg = await SystemConfig.get_config()
            cfg.catalog_upgrade = {
                "state": "completed",
                "target_version": target_version,
                "started_at": started,
                "finished_at": _now_iso(),
                "by": user_id,
                "prune": prune,
                "summary": summary,
                "message": message,
            }
            await cfg.save()
            await _notify_admins(
                "catalog_upgrade_complete",
                f"Catalog upgraded to {target_version}",
                message,
            )
            return summary
        except Exception as e:
            logger.exception("Catalog upgrade to %s failed", target_version)
            cfg = await SystemConfig.get_config()
            cfg.catalog_upgrade = {
                "state": "failed",
                "target_version": target_version,
                "started_at": started,
                "finished_at": _now_iso(),
                "by": user_id,
                "prune": prune,
                "message": f"Upgrade to {target_version} failed: {e}",
            }
            await cfg.save()
            await _notify_admins(
                "catalog_upgrade_failed",
                f"Catalog upgrade to {target_version} failed",
                str(e),
            )
            raise

    return _run_async(_run())
