"""FastAPI router for Microsoft Graph webhook notifications."""

import logging
import re

from fastapi import APIRouter, HTTPException, Query, Request, Response

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("")
async def graph_webhook(request: Request):
    """Receive Graph change notifications.

    Graph sends a validation request with ?validationToken=... on subscription
    creation (must echo the token as plain text). Subsequent requests contain
    JSON change notifications.
    """
    # Subscription validation handshake
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    notifications = body.get("value", [])
    if not notifications:
        return {"status": "no_notifications"}

    from app.celery_app import celery_app

    dispatched = 0

    _CLIENT_STATE_RE = re.compile(r"^vandalizer:[a-f0-9\-]{8,}:[a-f0-9\-]{8,}$")

    for notification in notifications:
        client_state = notification.get("clientState", "")
        resource = notification.get("resource", "")
        change_type = notification.get("changeType", "")

        # Validate clientState format strictly
        if not _CLIENT_STATE_RE.match(client_state):
            logger.warning("Invalid clientState format: %s", client_state)
            continue

        # Parse user_id and intake_config_id from clientState
        # Format: "vandalizer:{user_id}:{intake_config_uuid}"
        parts = client_state.split(":")
        user_id = parts[1]
        intake_config_id = parts[2]

        # Validate ID lengths (ObjectId = 24 chars, UUID = 32-36 chars)
        if not (24 <= len(user_id) <= 36 and 24 <= len(intake_config_id) <= 36):
            logger.warning("Invalid ID lengths in clientState: user_id=%s, config_id=%s", user_id, intake_config_id)
            continue

        # Route based on resource type
        if "/messages/" in resource or "/messages" in resource:
            celery_app.send_task(
                "tasks.passive.ingest_email_message",
                args=[user_id, resource, intake_config_id],
                queue="passive",
            )
            dispatched += 1

        elif "/items/" in resource or "/root" in resource:
            celery_app.send_task(
                "tasks.passive.ingest_drive_item",
                args=[user_id, resource, intake_config_id],
                queue="passive",
            )
            dispatched += 1

        else:
            logger.info("Unhandled resource type: %s", resource)

    return {"status": "ok", "dispatched": dispatched}


@router.post("/lifecycle")
async def graph_lifecycle(request: Request):
    """Handle Graph subscription lifecycle notifications.

    These include reauthorization and missed-notification events.
    """
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for event in body.get("value", []):
        lifecycle_event = event.get("lifecycleEvent", "")
        subscription_id = event.get("subscriptionId", "")

        if lifecycle_event == "reauthorizationRequired":
            logger.info("Reauthorization required for subscription %s", subscription_id)
            # The renew_graph_subscriptions beat task handles renewal

        elif lifecycle_event == "subscriptionRemoved":
            logger.warning("Subscription %s was removed by Graph", subscription_id)

        elif lifecycle_event == "missed":
            logger.warning("Missed notifications for subscription %s", subscription_id)

    return {"status": "ok"}
