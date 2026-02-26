#!/usr/bin/env python3
"""Pre-built MVP workflow templates for the passive processing system.

These create Workflow objects using the existing model structure
(Workflow → WorkflowStep → WorkflowStepTask) so they plug directly
into the existing workflow execution engine.
"""

from __future__ import annotations

from app.models import Workflow, WorkflowStep, WorkflowStepTask


def create_completeness_check_workflow(user_id: str, space: str = "") -> Workflow:
    """Create a workflow that checks document completeness.

    Pipeline:
    1. Extract key fields (names, dates, IDs, signatures, required documents)
    2. Validate against a requirements checklist
    3. Generate a completeness report with missing items

    Args:
        user_id: Owner of the workflow.
        space: Optional space ID.

    Returns:
        Saved Workflow instance.
    """
    # Step 1: Extract key fields
    extract_task = WorkflowStepTask(
        name="Extract Required Fields",
        data={
            "searchphrases": (
                "Full Name, Date, Department, Signature Present, "
                "Document Type, Reference Number, Amount, "
                "Approval Status, Required Attachments Listed"
            ),
        },
    )
    extract_task.save()

    extract_step = WorkflowStep(
        name="Extract",
        tasks=[extract_task],
        data={
            "description": "Extract key fields and metadata from the submitted document(s)",
        },
    )
    extract_step.save()

    # Step 2: Validate completeness
    validate_task = WorkflowStepTask(
        name="Check Completeness",
        data={
            "prompt": (
                "Based on the extracted fields from the previous step, evaluate the "
                "completeness of this submission. For each required field:\n"
                "1. Mark as PRESENT if the field has a valid, non-empty value\n"
                "2. Mark as MISSING if the field is empty or not found\n"
                "3. Mark as INCOMPLETE if the field exists but appears to be partial\n\n"
                "List all missing or incomplete items. Assess whether the submission "
                "can proceed or if follow-up is needed."
            ),
        },
    )
    validate_task.save()

    validate_step = WorkflowStep(
        name="Validate",
        tasks=[validate_task],
        data={
            "description": "Check extracted fields against requirements and flag gaps",
        },
    )
    validate_step.save()

    # Step 3: Generate report
    report_task = WorkflowStepTask(
        name="Generate Report",
        data={
            "prompt": (
                "Create a clear, professional completeness report with these sections:\n\n"
                "## Submission Summary\n"
                "Brief description of what was submitted and by whom.\n\n"
                "## Completeness Status\n"
                "Overall status: COMPLETE / INCOMPLETE / NEEDS REVIEW\n\n"
                "## Fields Found\n"
                "List all extracted fields with their values.\n\n"
                "## Missing Items\n"
                "Bulleted list of any missing or incomplete items that need "
                "to be provided before this can proceed.\n\n"
                "## Recommended Next Steps\n"
                "Specific actions to resolve any gaps.\n\n"
                "Keep the tone professional and helpful."
            ),
        },
    )
    report_task.save()

    report_step = WorkflowStep(
        name="Report",
        tasks=[report_task],
        data={
            "description": "Generate a structured completeness report",
        },
    )
    report_step.save()

    workflow = Workflow(
        name="Completeness Check",
        description=(
            "Automatically checks submitted documents for required fields, "
            "flags missing items, and generates a completeness report. "
            "Designed for intake processing of packets, forms, and applications."
        ),
        user_id=user_id,
        steps=[extract_step, validate_step, report_step],
        space=space,
        input_config={
            "manual_enabled": True,
            "folder_watch": {"enabled": False, "folders": [], "delay_seconds": 300,
                             "file_filters": {"types": [], "exclude_patterns": []},
                             "batch_mode": "per_document"},
            "conditions": [],
        },
        output_config={
            "storage": {"enabled": False, "destination_folder": None,
                        "file_naming": "{date}_completeness_check_results",
                        "format": "json", "append_mode": False},
            "notifications": [],
        },
    )
    workflow.save()
    return workflow


def create_summarize_draft_reply_workflow(user_id: str, space: str = "") -> Workflow:
    """Create a workflow that summarizes content and drafts a reply.

    Pipeline:
    1. Summarize the incoming content
    2. Extract key entities (requester, request type, deadlines)
    3. Draft a professional reply email

    Args:
        user_id: Owner of the workflow.
        space: Optional space ID.

    Returns:
        Saved Workflow instance.
    """
    # Step 1: Summarize
    summarize_task = WorkflowStepTask(
        name="Summarize Content",
        data={
            "prompt": (
                "Analyze the provided content and create a structured summary:\n\n"
                "## What is being requested\n"
                "Clear statement of the request or action needed.\n\n"
                "## Key details\n"
                "- Who is requesting (name, title, department if available)\n"
                "- What specifically is needed\n"
                "- When it's needed by (deadlines, urgency)\n"
                "- Any constraints or special requirements\n\n"
                "## Background context\n"
                "Relevant context from the email thread or document.\n\n"
                "Keep it concise — this summary will be used to draft a response."
            ),
        },
    )
    summarize_task.save()

    summarize_step = WorkflowStep(
        name="Summarize",
        tasks=[summarize_task],
        data={
            "description": "Create a structured summary of the incoming content",
        },
    )
    summarize_step.save()

    # Step 2: Extract entities
    extract_task = WorkflowStepTask(
        name="Extract Key Entities",
        data={
            "searchphrases": (
                "Requester Name, Requester Email, Requester Department, "
                "Request Type, Deadline Date, Priority Level, "
                "Referenced Documents, Action Required By"
            ),
        },
    )
    extract_task.save()

    extract_step = WorkflowStep(
        name="Extract",
        tasks=[extract_task],
        data={
            "description": "Extract key entities from the content",
        },
    )
    extract_step.save()

    # Step 3: Draft reply
    draft_task = WorkflowStepTask(
        name="Draft Reply",
        data={
            "prompt": (
                "Based on the summary and extracted information from the previous steps, "
                "draft a professional email reply. The reply should:\n\n"
                "1. Acknowledge the request clearly\n"
                "2. Confirm what you understand is being asked\n"
                "3. If information is missing, politely list what's needed\n"
                "4. If the request can proceed, outline next steps\n"
                "5. Include a reasonable timeline if applicable\n"
                "6. Use a professional but warm tone appropriate for university admin\n\n"
                "Format the reply as a ready-to-send email (greeting, body, closing). "
                "Do NOT include a subject line — just the body text.\n\n"
                "IMPORTANT: This is a DRAFT for human review. Include a note at the top: "
                "'[DRAFT — Please review before sending]'"
            ),
        },
    )
    draft_task.save()

    draft_step = WorkflowStep(
        name="Draft Reply",
        tasks=[draft_task],
        data={
            "description": "Draft a professional reply based on the analysis",
        },
    )
    draft_step.save()

    workflow = Workflow(
        name="Summarize & Draft Reply",
        description=(
            "Analyzes incoming emails or documents, creates a structured summary "
            "of what's requested, extracts key entities, and drafts a professional "
            "reply for human review. Never sends automatically."
        ),
        user_id=user_id,
        steps=[summarize_step, extract_step, draft_step],
        space=space,
        input_config={
            "manual_enabled": True,
            "folder_watch": {"enabled": False, "folders": [], "delay_seconds": 300,
                             "file_filters": {"types": [], "exclude_patterns": []},
                             "batch_mode": "per_document"},
            "conditions": [],
        },
        output_config={
            "storage": {"enabled": False, "destination_folder": None,
                        "file_naming": "{date}_summary_draft_reply",
                        "format": "json", "append_mode": False},
            "notifications": [],
        },
    )
    workflow.save()
    return workflow
