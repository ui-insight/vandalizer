#!/usr/bin/env python3
"""OneDrive case folder creation and result upload.

Creates organized folder structures in OneDrive and uploads workflow
results, summaries, and draft replies as case artifacts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from app.utilities.graph_client import GraphClient, GraphAPIError

logger = logging.getLogger(__name__)

# Subfolder names within each case folder
SUBFOLDERS = [
    "00_Source",
    "01_Extracted",
    "02_Reports",
    "03_Drafts",
]


def create_case_folder(
    client: GraphClient,
    work_item,
    base_path: str = "Vandalizer/Cases",
    *,
    drive_id: str | None = None,
) -> str:
    """Create an organized case folder in OneDrive.

    Structure: ``{base_path}/YYYY/Category/Case-{uuid[:8]}/``

    Args:
        client: Authenticated GraphClient.
        work_item: WorkItem instance.
        base_path: Root folder path in OneDrive (default: ``Vandalizer/Cases``).
        drive_id: Optional drive ID. Uses user's default drive if None.

    Returns:
        The full folder path relative to the drive root.
    """
    year = (work_item.created_at or datetime.utcnow()).strftime("%Y")
    category = _sanitize(work_item.triage_category or "General")
    case_slug = f"Case-{work_item.uuid[:8]}"

    # Build the path: Vandalizer/Cases/2026/General/Case-abc12345
    case_path = f"{base_path}/{year}/{category}/{case_slug}"

    # Create all folders (including subfolders)
    client.ensure_folder_path(case_path, drive_id=drive_id)
    for sub in SUBFOLDERS:
        try:
            client.create_folder(case_path, sub, drive_id=drive_id)
        except GraphAPIError as e:
            if e.status_code != 409:  # 409 = already exists
                logger.warning(f"Could not create subfolder {sub}: {e}")

    # Generate and upload index.md
    index_md = _generate_index(work_item, case_path)
    try:
        client.upload_file(
            case_path, "index.md", index_md.encode("utf-8"), drive_id=drive_id
        )
    except GraphAPIError as e:
        logger.warning(f"Could not upload index.md: {e}")

    return case_path


def upload_results_to_case_folder(
    client: GraphClient,
    drive_id: str | None,
    folder_path: str,
    result,
    work_item,
) -> list[str]:
    """Upload workflow results to the case folder.

    Args:
        client: Authenticated GraphClient.
        drive_id: Drive ID (or None for user default).
        folder_path: Case folder path from create_case_folder().
        result: WorkflowResult instance.
        work_item: WorkItem instance.

    Returns:
        List of uploaded file paths.
    """
    uploaded = []

    # Upload extraction results (JSON)
    if result.final_output:
        try:
            content = json.dumps(result.final_output, indent=2, default=str)
            path = f"{folder_path}/01_Extracted"
            client.upload_file(
                path, "extraction_results.json", content.encode("utf-8"),
                drive_id=drive_id,
            )
            uploaded.append(f"{path}/extraction_results.json")
        except GraphAPIError as e:
            logger.warning(f"Could not upload extraction results: {e}")

    # Upload step outputs as reports
    if result.steps_output:
        for step_name, step_data in result.steps_output.items():
            try:
                safe_name = _sanitize(step_name)
                content = json.dumps(step_data, indent=2, default=str)
                path = f"{folder_path}/02_Reports"
                filename = f"{safe_name}_output.json"
                client.upload_file(
                    path, filename, content.encode("utf-8"), drive_id=drive_id,
                )
                uploaded.append(f"{path}/{filename}")
            except GraphAPIError as e:
                logger.warning(f"Could not upload step output {step_name}: {e}")

    # Upload summary / triage info as a report
    if work_item.triage_summary:
        try:
            report = _build_summary_report(work_item)
            path = f"{folder_path}/02_Reports"
            client.upload_file(
                path, "triage_summary.md", report.encode("utf-8"), drive_id=drive_id,
            )
            uploaded.append(f"{path}/triage_summary.md")
        except GraphAPIError as e:
            logger.warning(f"Could not upload triage summary: {e}")

    # Upload draft reply if present in final output
    draft = _extract_draft_reply(result)
    if draft:
        try:
            path = f"{folder_path}/03_Drafts"
            client.upload_file(
                path, "draft_reply.md", draft.encode("utf-8"), drive_id=drive_id,
            )
            uploaded.append(f"{path}/draft_reply.md")
        except GraphAPIError as e:
            logger.warning(f"Could not upload draft reply: {e}")

    return uploaded


def upload_original_source(
    client: GraphClient,
    drive_id: str | None,
    folder_path: str,
    work_item,
) -> None:
    """Upload original email body or source document to 00_Source."""
    if work_item.body_text:
        try:
            content = f"Subject: {work_item.subject}\nFrom: {work_item.sender_email}\n\n{work_item.body_text}"
            path = f"{folder_path}/00_Source"
            client.upload_file(
                path, "original_email.txt", content.encode("utf-8"), drive_id=drive_id,
            )
        except GraphAPIError as e:
            logger.warning(f"Could not upload original email: {e}")


def save_results_to_onedrive(result, work_item, onedrive_config: dict) -> str:
    """High-level function: create case folder and upload all results.

    Called from output_handlers.py when OneDrive output is configured.

    Args:
        result: WorkflowResult instance.
        work_item: WorkItem instance.
        onedrive_config: Dict with drive_id, base_path, etc.

    Returns:
        The case folder path.
    """
    client = GraphClient(work_item.owner_user_id)
    drive_id = onedrive_config.get("drive_id")
    base_path = onedrive_config.get("base_path", "Vandalizer/Cases")

    folder_path = create_case_folder(client, work_item, base_path, drive_id=drive_id)

    upload_original_source(client, drive_id, folder_path, work_item)
    upload_results_to_case_folder(client, drive_id, folder_path, result, work_item)

    # Update work item with case folder info
    work_item.case_folder_drive_path = folder_path
    work_item.save()

    return folder_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(name: str) -> str:
    """Sanitize a string for use as a folder/file name."""
    safe = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name)
    return safe.strip()[:100] or "Untitled"


def _generate_index(work_item, case_path: str) -> str:
    """Generate an index.md for the case folder."""
    return f"""# Case: {work_item.subject or work_item.uuid[:8]}

- **Status**: {work_item.status}
- **Source**: {work_item.source}
- **Category**: {work_item.triage_category or 'Unclassified'}
- **Sender**: {work_item.sender_name or ''} <{work_item.sender_email or ''}>
- **Received**: {work_item.received_at or 'N/A'}
- **Created**: {work_item.created_at}
- **Attachments**: {work_item.attachment_count}

## Summary

{work_item.triage_summary or 'No summary available.'}

## Sensitivity Flags

{', '.join(work_item.sensitivity_flags) if work_item.sensitivity_flags else 'None detected.'}

## Folder Structure

- `00_Source/` — Original email and attachments
- `01_Extracted/` — OCR text and extracted fields
- `02_Reports/` — Summary, validation, and triage reports
- `03_Drafts/` — Draft emails and response templates
"""


def _build_summary_report(work_item) -> str:
    """Build a triage summary report in Markdown."""
    flags = ", ".join(work_item.sensitivity_flags) if work_item.sensitivity_flags else "None"
    tags = ", ".join(work_item.triage_tags) if work_item.triage_tags else "None"
    return f"""# Triage Summary

- **Category**: {work_item.triage_category}
- **Confidence**: {work_item.triage_confidence:.0%}
- **Tags**: {tags}
- **Sensitivity Flags**: {flags}

## Summary

{work_item.triage_summary}
"""


def _extract_draft_reply(result) -> str | None:
    """Try to extract a draft reply from workflow result output."""
    if not result.final_output:
        return None
    output = result.final_output.get("output")
    if isinstance(output, str) and "[DRAFT" in output:
        return output
    if isinstance(output, dict):
        for key in ("draft_reply", "draft", "reply"):
            if key in output:
                return str(output[key])
    return None
