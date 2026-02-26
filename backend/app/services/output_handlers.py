"""Output handlers for passive workflows: storage, notifications, webhooks.

Ported from Flask app/utilities/output_handlers.py.
Uses pymongo (sync) for DB access. Replaces Flask-Mail with aiosmtplib/smtplib.
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


def _get_db():
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    return MongoClient(mongo_host)[mongo_db]


def save_results_to_folder(result_doc: dict, storage_config: dict) -> str:
    """Save workflow results to a local folder in the configured format.

    Returns the file path string.
    """
    db = _get_db()
    folder_id = storage_config.get("destination_folder")
    if not folder_id:
        raise ValueError("No destination folder configured")

    folder = db.smart_folder.find_one({"uuid": folder_id})
    if not folder:
        raise ValueError(f"Folder {folder_id} not found")

    workflow = db.workflow.find_one({"_id": result_doc.get("workflow")}) or {}
    workflow_name = (workflow.get("name") or "workflow").replace(" ", "_")

    filename_template = storage_config.get("file_naming", "{date}_{workflow_name}_results")
    filename = filename_template.format(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        time=datetime.now(timezone.utc).strftime("%H-%M-%S"),
        workflow_name=workflow_name,
        workflow_id=str(result_doc.get("workflow", "")),
        run_id=str(result_doc.get("_id", "")),
    )

    format_type = storage_config.get("format", "csv")
    filename = f"{filename}.{format_type}"

    final_output = result_doc.get("final_output") or {}
    output_data = final_output.get("output")

    user_id = workflow.get("user_id", "system")
    upload_dir = os.environ.get("UPLOAD_DIR", "../app/static/uploads")
    dir_path = Path(upload_dir) / user_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename

    if format_type == "csv":
        _save_as_csv(file_path, output_data)
    elif format_type == "json":
        _save_as_json(file_path, output_data)
    else:
        with open(file_path, "w") as f:
            f.write(str(output_data))

    # Create SmartDocument for the output file
    doc_uuid = uuid4().hex
    db.smart_document.insert_one({
        "title": filename,
        "path": f"{user_id}/{filename}",
        "downloadpath": f"{user_id}/{filename}",
        "extension": format_type,
        "uuid": doc_uuid,
        "user_id": user_id,
        "space": folder.get("space", ""),
        "folder": folder.get("uuid", ""),
        "raw_text": "",
        "processing": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    return str(file_path)


def _save_as_csv(file_path: Path, data) -> None:
    if not data:
        file_path.write_text("")
        return
    if isinstance(data, list) and data and isinstance(data[0], dict):
        with open(file_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    else:
        file_path.write_text(str(data))


def _save_as_json(file_path: Path, data) -> None:
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def should_send_notification(result_doc: dict, notification: dict) -> bool:
    """Check if notification should be sent based on conditions."""
    condition = notification.get("conditions", "always")
    if condition == "always":
        return True
    elif condition == "success":
        return result_doc.get("status") == "completed"
    elif condition == "failure":
        return result_doc.get("status") == "failed"
    return True


def send_workflow_notification(
    result_doc: dict,
    notification: dict,
    work_item_doc: dict | None = None,
) -> None:
    """Send notification for workflow completion."""
    channel = notification.get("channel", "email")

    if channel == "teams":
        _send_teams_notification(result_doc, notification, work_item_doc)
        return

    if channel != "email":
        return

    db = _get_db()
    recipients = list(notification.get("recipients", []))

    if notification.get("notify_owner"):
        workflow = db.workflow.find_one({"_id": result_doc.get("workflow")})
        if workflow:
            user = db.user.find_one({"user_id": workflow.get("user_id")})
            if user and user.get("email") and user["email"] not in recipients:
                recipients.append(user["email"])

    if not recipients:
        return

    workflow = db.workflow.find_one({"_id": result_doc.get("workflow")}) or {}
    wf_name = workflow.get("name", "Workflow")
    status = result_doc.get("status", "unknown")

    if status == "completed":
        subject = f"✓ {wf_name} completed"
    elif status == "failed":
        subject = f"⚠️ {wf_name} failed"
    else:
        subject = f"{wf_name} - {status}"

    html_body = f"""
    <html>
    <body>
        <h2>{subject}</h2>
        <p>Your workflow "{wf_name}" has {status}.</p>
        <p><strong>Trigger Type:</strong> {result_doc.get('trigger_type', 'manual')}</p>
    </body>
    </html>
    """

    _send_email(recipients, subject, html_body)


def _send_email(recipients: list[str], subject: str, html_body: str) -> None:
    """Send an email using SMTP (sync)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    from_email = os.environ.get("SMTP_FROM_EMAIL", "noreply@vandalizer.com")

    if not smtp_host:
        logger.warning("SMTP not configured, skipping email notification")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if os.environ.get("SMTP_USE_TLS", "true").lower() == "true":
                server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, recipients, msg.as_string())
    except Exception as e:
        logger.error("Failed to send email: %s", e)


def _send_teams_notification(
    result_doc: dict,
    notification: dict,
    work_item_doc: dict | None = None,
) -> None:
    """Send a Teams Adaptive Card notification."""
    team_id = notification.get("team_id")
    channel_id = notification.get("channel_id")
    if not team_id or not channel_id:
        return

    from app.services.teams_cards import build_exception_card, build_work_item_card

    if result_doc.get("status") == "failed":
        error = str((result_doc.get("final_output") or {}).get("error", "Unknown error"))
        if work_item_doc:
            card = build_exception_card(work_item_doc, error)
        else:
            return
    elif work_item_doc:
        card = build_work_item_card(work_item_doc, result_doc=result_doc)
    else:
        return

    user_id = work_item_doc.get("owner_user_id") if work_item_doc else None
    if not user_id:
        db = _get_db()
        workflow = db.workflow.find_one({"_id": result_doc.get("workflow")})
        user_id = workflow.get("user_id") if workflow else None
    if not user_id:
        return

    try:
        from app.services.graph_client import GraphClient

        client = GraphClient(user_id)
        client.send_channel_message(team_id, channel_id, card_json=card)
    except Exception:
        logger.warning("Failed to send Teams notification for result %s", result_doc.get("_id"))


def save_results_to_onedrive_channel(
    result_doc: dict,
    onedrive_config: dict,
    work_item_doc: dict | None = None,
) -> str:
    """Save workflow results to a OneDrive case folder.

    Returns the case folder path.
    """
    from app.services.graph_client import GraphClient

    user_id = None
    if work_item_doc:
        user_id = work_item_doc.get("owner_user_id")
    if not user_id:
        db = _get_db()
        workflow = db.workflow.find_one({"_id": result_doc.get("workflow")})
        user_id = workflow.get("user_id") if workflow else None
    if not user_id:
        raise ValueError("No user_id available for OneDrive upload")

    client = GraphClient(user_id)
    drive_id = onedrive_config.get("drive_id")
    base_path = onedrive_config.get("base_path", "/Vandalizer/Results")

    # Create case folder
    result_id = str(result_doc.get("_id", ""))[:8]
    case_folder = f"{base_path}/{result_id}"
    client.ensure_folder_path(case_folder, drive_id=drive_id)

    # Upload results as JSON
    final_output = result_doc.get("final_output") or {}
    content = json.dumps(final_output, indent=2, default=str).encode("utf-8")
    client.upload_file(case_folder, "results.json", content, drive_id=drive_id)

    return case_folder


def call_webhook(result_doc: dict, webhook_config: dict) -> None:
    """Call a webhook with workflow result data."""
    url = webhook_config.get("url")
    method = webhook_config.get("method", "POST").upper()

    db = _get_db()
    workflow = db.workflow.find_one({"_id": result_doc.get("workflow")}) or {}

    payload = {
        "workflow_id": str(result_doc.get("workflow", "")),
        "workflow_name": workflow.get("name", ""),
        "result_id": str(result_doc.get("_id", "")),
        "status": result_doc.get("status"),
        "trigger_type": result_doc.get("trigger_type"),
        "output": (result_doc.get("final_output") or {}).get("output"),
    }

    headers = {"Content-Type": "application/json"}
    auth_config = webhook_config.get("auth", {})
    auth_type = auth_config.get("type")

    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth_config.get('token')}"
    elif auth_type == "api_key":
        key_name = auth_config.get("key_name", "X-API-Key")
        headers[key_name] = auth_config.get("api_key")

    if method == "POST":
        httpx.post(url, json=payload, headers=headers, timeout=30.0)
    elif method == "PUT":
        httpx.put(url, json=payload, headers=headers, timeout=30.0)
