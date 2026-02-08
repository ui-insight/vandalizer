#!/usr/bin/env python3
"""Handler for Microsoft Graph change notifications (webhooks).

Graph sends POST requests to our notification URL when subscribed resources
change (new email, new OneDrive file, etc.).  This module validates and
dispatches those notifications to the appropriate Celery ingest tasks.
"""

from __future__ import annotations

import logging
import os

from app.models import GraphSubscription, IntakeConfig

logger = logging.getLogger(__name__)

# Shared secret set via env var; Graph echoes it back in each notification
# so we can verify the notification is authentic.
CLIENT_STATE_SECRET = os.environ.get("GRAPH_CLIENT_STATE_SECRET", "")


def validate_client_state(client_state: str | None) -> bool:
    """Check that the clientState in a notification matches our secret."""
    if not CLIENT_STATE_SECRET:
        # If not configured, skip validation (dev mode)
        return True
    return client_state == CLIENT_STATE_SECRET


def handle_graph_notification(notification: dict) -> None:
    """Process a single Graph change notification.

    Called for each item in the ``value`` array of a Graph webhook POST.
    Looks up the subscription → intake config and dispatches the right
    Celery ingest task.
    """
    subscription_id = notification.get("subscriptionId")
    resource = notification.get("resource", "")
    change_type = notification.get("changeType", "")
    client_state = notification.get("clientState")

    if not validate_client_state(client_state):
        logger.warning("Invalid clientState in Graph notification — ignoring")
        return

    # Look up our subscription record
    sub = GraphSubscription.objects(
        subscription_id=subscription_id, active=True
    ).first()
    if not sub:
        logger.warning(f"Unknown or inactive subscription {subscription_id}")
        return

    # Find the intake config that owns this subscription
    intake = IntakeConfig.objects(subscription=sub, enabled=True).first()
    if not intake:
        logger.warning(f"No enabled intake config for subscription {subscription_id}")
        return

    logger.info(
        f"Graph notification: {change_type} on {resource} "
        f"(intake={intake.name}, type={intake.intake_type})"
    )

    # Dispatch to the right ingest task based on resource type
    from app.utilities.m365_tasks import ingest_email_message, ingest_drive_item

    if "messages" in resource or intake.intake_type in (
        "outlook_shared",
        "outlook_folder",
    ):
        ingest_email_message.delay(
            user_id=sub.owner_user_id,
            message_resource=resource,
            intake_config_id=intake.uuid,
        )
    elif "driveItem" in resource or intake.intake_type == "onedrive_drop":
        ingest_drive_item.delay(
            user_id=sub.owner_user_id,
            item_resource=resource,
            intake_config_id=intake.uuid,
        )
    else:
        logger.warning(f"Unrecognized resource type in notification: {resource}")
