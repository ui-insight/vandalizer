"""Output handlers for passive workflows: storage, notifications, webhooks.

Ported from Flask app/utilities/output_handlers.py.
Uses pymongo (sync) for DB access. Replaces Flask-Mail with aiosmtplib/smtplib.
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from app.tasks import get_sync_db

logger = logging.getLogger(__name__)


def _render_chainable_text(output_data, workflow_name: str) -> str:
    """Render workflow output as markdown so the saved doc is chainable as text."""
    import io
    buf = io.StringIO()
    if isinstance(output_data, list) and output_data and isinstance(output_data[0], dict):
        headers = list(dict.fromkeys(k for row in output_data for k in row.keys()))
        buf.write(f"# {workflow_name.replace('_', ' ')}\n\n")
        buf.write("| " + " | ".join(headers) + " |\n")
        buf.write("| " + " | ".join("---" for _ in headers) + " |\n")
        for row in output_data:
            vals = [str(row.get(h, "")).replace("|", "\\|") for h in headers]
            buf.write("| " + " | ".join(vals) + " |\n")
    elif isinstance(output_data, dict):
        buf.write(f"# {workflow_name.replace('_', ' ')}\n\n")
        for k, v in output_data.items():
            buf.write(f"**{k}:** {v}\n\n")
    else:
        buf.write(str(output_data) if output_data is not None else "")
    return buf.getvalue()


def save_results_to_folder(result_doc: dict, storage_config: dict) -> str:
    """Save workflow results to a local folder and create a chainable SmartDocument.

    Returns the file path string. The created SmartDocument carries `raw_text`
    populated from the markdown rendition, the workflow's team_id, and origin
    metadata identifying this run, so that downstream workflows can consume it
    as input and own-origin docs can be skipped to prevent loops.

    ``storage_config["actor_user_id"]`` overrides the document owner; without
    it, the doc is owned by the workflow's owner (the right default for passive
    runs). Manual "save output to my folder" uses the override.
    """
    db = get_sync_db()
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
    ext_map = {"text": "txt", "markdown": "md"}
    file_ext = ext_map.get(format_type, format_type)
    filename = f"{filename}.{file_ext}"

    final_output = result_doc.get("final_output") or {}
    output_data = final_output.get("output")

    user_id = storage_config.get("actor_user_id") or workflow.get("user_id", "system")
    team_id = folder.get("team_id") or workflow.get("team_id")
    from app.config import Settings as _Settings
    upload_dir = _Settings().upload_dir
    dir_path = Path(upload_dir) / user_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename

    if format_type == "csv":
        _save_as_csv(file_path, output_data)
    elif format_type == "json":
        _save_as_json(file_path, output_data)
    elif format_type == "markdown":
        _save_workflow_as_markdown(file_path, output_data, workflow_name)
    elif format_type == "pdf":
        _save_workflow_as_pdf(file_path, output_data, workflow_name)
    elif format_type in ("text", "txt"):
        _save_workflow_as_text(file_path, output_data)
    else:
        with open(file_path, "w") as f:
            f.write(str(output_data))

    # Render markdown for raw_text regardless of file format. PDF/CSV/JSON files
    # aren't useful as text input to the next workflow; the markdown rendition is.
    raw_text = _render_chainable_text(output_data, workflow_name)

    on_rerun = storage_config.get("on_rerun", "new")
    workflow_id_str = str(result_doc.get("workflow", "")) or None
    run_id_str = str(result_doc.get("_id", "")) or None
    now = datetime.now(timezone.utc)

    doc_payload = {
        "title": filename,
        "path": f"{user_id}/{filename}",
        "downloadpath": f"{user_id}/{filename}",
        "extension": file_ext,
        "user_id": user_id,
        "team_id": team_id,
        "folder": folder.get("uuid", ""),
        "raw_text": raw_text,
        "token_count": len(raw_text) // 4,
        "processing": False,
        "origin_workflow_id": workflow_id_str,
        "origin_workflow_run_id": run_id_str,
        "origin_run_at": now,
        "updated_at": now,
    }

    doc_uuid = None
    if on_rerun == "overwrite" and workflow_id_str:
        existing = db.smart_document.find_one({
            "origin_workflow_id": workflow_id_str,
            "folder": folder.get("uuid", ""),
        })
        if existing:
            doc_uuid = existing.get("uuid")
            db.smart_document.update_one(
                {"_id": existing["_id"]},
                {"$set": doc_payload},
            )

    if doc_uuid is None:
        doc_uuid = uuid4().hex
        doc_payload["uuid"] = doc_uuid
        doc_payload["created_at"] = now
        db.smart_document.insert_one(doc_payload)

    # Trigger semantic ingestion so the new doc is chat-searchable. Skip the
    # extraction round-trip — we already have raw_text.
    if not storage_config.get("skip_semantic_ingestion") and user_id and user_id != "system":
        try:
            from app.celery_app import celery_app
            celery_app.send_task(
                "tasks.document.semantic_ingestion",
                kwargs={
                    "raw_text": raw_text,
                    "document_uuid": doc_uuid,
                    "user_id": user_id,
                },
                queue="documents",
            )
        except Exception:
            logger.exception("Failed to dispatch semantic ingestion for %s", doc_uuid)

    return str(file_path)


def _save_as_csv(file_path: Path, data) -> None:
    if not data:
        file_path.write_text("")
        return
    if isinstance(data, list) and data and isinstance(data[0], dict):
        # Collect keys from ALL items so no columns are missing
        all_keys = list(dict.fromkeys(k for row in data for k in row.keys()))
        with open(file_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
    elif isinstance(data, dict):
        # Transpose to Field/Value rows instead of dumping into one wide row
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Field", "Value"])
            for k, v in data.items():
                cell = json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
                writer.writerow([str(k), cell])
    else:
        file_path.write_text(str(data))


def _save_as_json(file_path: Path, data) -> None:
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def _save_workflow_as_text(file_path: Path, data) -> None:
    """Save workflow output as human-readable plain text."""
    with open(file_path, "w") as f:
        if isinstance(data, list) and data and isinstance(data[0], dict):
            for i, row in enumerate(data):
                if i > 0:
                    f.write("\n---\n\n")
                for k, v in row.items():
                    f.write(f"{k}: {v}\n")
        elif isinstance(data, dict):
            for k, v in data.items():
                f.write(f"{k}: {v}\n")
        else:
            f.write(str(data) if data else "")


def _save_workflow_as_markdown(file_path: Path, data, title: str = "Results") -> None:
    """Save workflow output as a Markdown table."""
    lines = [f"# {title.replace('_', ' ')}", ""]
    if isinstance(data, list) and data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in data:
            vals = [str(row.get(h, "")).replace("|", "\\|") for h in headers]
            lines.append("| " + " | ".join(vals) + " |")
    elif isinstance(data, dict):
        lines.extend(["| Field | Value |", "|---|---|"])
        for k, v in data.items():
            lines.append(f"| {k} | {str(v).replace('|', chr(92) + '|')} |")
    else:
        lines.append(str(data) if data else "")
    with open(file_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _save_workflow_as_pdf(file_path: Path, data, title: str = "Results") -> None:
    """Save workflow output as a beautifully formatted PDF.

    String payloads are rendered as markdown (headings, lists, tables, bold,
    italic, code). Dicts/lists are rendered as a table.
    """
    from app.services.pdf_service import render_workflow_pdf

    pdf_bytes = render_workflow_pdf(data, title=title.replace("_", " "))
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)


def _save_extraction_as_markdown(file_path: Path, data: dict, title: str = "Extraction Results") -> None:
    """Save extraction results as a Markdown table."""
    lines = [f"# {title.replace('_', ' ')}", "", "| Field | Value |", "|---|---|"]
    for k, v in data.items():
        # Escape pipes in values
        v_str = str(v).replace("|", "\\|")
        lines.append(f"| {k} | {v_str} |")
    with open(file_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _save_extraction_as_pdf(file_path: Path, data: dict, title: str = "Extraction Results") -> None:
    """Save extraction results as a Field/Value PDF table."""
    from app.services.pdf_service import render_workflow_pdf

    pdf_bytes = render_workflow_pdf(data, title=title.replace("_", " "))
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)


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

    db = get_sync_db()
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

    from app.config import Settings

    settings = Settings()
    if not settings.smtp_host:
        logger.warning("SMTP not configured, skipping email notification")
        return

    from_addr = settings.smtp_from_email or "noreply@vandalizer.com"
    from_header = f"{settings.smtp_from_name} <{from_addr}>" if settings.smtp_from_name else from_addr

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_header
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.smtp_use_tls:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
            if settings.smtp_start_tls:
                server.starttls()
        with server:
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, recipients, msg.as_string())
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
        db = get_sync_db()
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
        db = get_sync_db()
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


def save_extraction_results_to_folder(
    extraction_results: dict,
    automation: dict,
    storage_config: dict,
) -> str:
    """Save extraction results to a folder as CSV or JSON.

    Returns the file path string.
    """
    db = get_sync_db()
    folder_id = storage_config.get("destination_folder")
    if not folder_id:
        raise ValueError("No destination folder configured")

    folder = db.smart_folder.find_one({"uuid": folder_id})
    if not folder:
        raise ValueError(f"Folder {folder_id} not found")

    auto_name = (automation.get("name") or "extraction").replace(" ", "_")

    filename_template = storage_config.get("file_naming", "{date}_{name}_results")
    filename = filename_template.format(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        time=datetime.now(timezone.utc).strftime("%H-%M-%S"),
        name=auto_name,
        workflow_name=auto_name,
    )

    format_type = storage_config.get("format", "csv")
    # Normalize format to file extension
    ext_map = {"text": "txt", "markdown": "md"}
    file_ext = ext_map.get(format_type, format_type)
    filename = f"{filename}.{file_ext}"

    # Flatten extraction results (list of entity dicts with document_id)
    if isinstance(extraction_results, list) and extraction_results:
        flat_results = {}
        for d in extraction_results:
            if isinstance(d, dict):
                flat_results.update({k: v for k, v in d.items() if k != "document_id"})
    elif isinstance(extraction_results, dict):
        flat_results = extraction_results
    else:
        flat_results = {}

    # Convert to list-of-dicts for CSV compatibility
    output_data = [{"key": k, "value": v} for k, v in flat_results.items()]

    user_id = automation.get("user_id", "system")
    from app.config import Settings as _Settings
    upload_dir = _Settings().upload_dir
    dir_path = Path(upload_dir) / user_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / filename

    if format_type == "csv":
        _save_as_csv(file_path, output_data)
    elif format_type == "json":
        _save_as_json(file_path, flat_results)
    elif format_type == "markdown":
        _save_extraction_as_markdown(file_path, flat_results, auto_name)
    elif format_type == "pdf":
        _save_extraction_as_pdf(file_path, flat_results, auto_name)
    else:
        # Human-readable text format
        lines = [f"{k}: {v}" for k, v in flat_results.items()]
        with open(file_path, "w") as f:
            f.write("\n".join(lines))

    # Create SmartDocument for the output file
    doc_uuid = uuid4().hex
    db.smart_document.insert_one({
        "title": filename,
        "path": f"{user_id}/{filename}",
        "downloadpath": f"{user_id}/{filename}",
        "extension": file_ext,
        "uuid": doc_uuid,
        "user_id": user_id,
        "folder": folder.get("uuid", ""),
        "raw_text": "",
        "processing": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })

    return str(file_path)


def compute_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload.

    Returns ``t={timestamp},v1={hex_digest}`` string.
    The receiver can verify by reconstructing ``{t}.{raw_body}`` and
    computing HMAC-SHA256 with the shared secret.
    """
    import hashlib
    import hmac
    import time

    timestamp = str(int(time.time()))
    message = f"{timestamp}.{payload_bytes.decode('utf-8')}"
    signature = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def call_webhook(result_doc: dict, webhook_config: dict) -> None:
    """Call a webhook with workflow result data."""
    from app.utils.url_validation import validate_outbound_url

    url = webhook_config.get("url")
    validate_outbound_url(url)  # raises ValueError for internal/private URLs
    method = webhook_config.get("method", "POST").upper()

    db = get_sync_db()
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
