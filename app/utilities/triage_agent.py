#!/usr/bin/env python3
"""LLM-based triage agent for classifying incoming M365 work items.

Uses the existing Pydantic-AI agent pattern from agents.py to classify
work items by type, detect sensitivity, and recommend routing.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent

from app.utilities.agents import get_agent_model
from app.utilities.config import get_default_model_name

logger = logging.getLogger(__name__)

# Cache to prevent context leaks (follows pattern in agents.py)
_triage_agent_cache: dict[str, Agent] = {}


class TriageResult(BaseModel):
    """Structured output from the triage agent."""

    category: str = Field(
        description="Classification category (e.g. 'transcript_request', 'enrollment_verification', 'subaward_request')"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the classification (0.0 to 1.0)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Descriptive tags for the item"
    )
    sensitivity_flags: list[str] = Field(
        default_factory=list,
        description="Detected sensitive data types (e.g. 'PII', 'FERPA', 'SSN', 'health_info')"
    )
    summary: str = Field(
        description="2-3 sentence summary of the item"
    )
    suggested_action: str = Field(
        description="Recommended action: 'process', 'review', or 'reject'"
    )
    reasoning: str = Field(
        description="Brief explanation of the classification decision"
    )


TRIAGE_SYSTEM_PROMPT = """You are a university administrative document triage specialist.

Your job is to classify incoming work items (emails, documents) that arrive at
a university office, detect sensitive information, and recommend routing.

CLASSIFICATION CATEGORIES (choose the most specific match):
- transcript_request: Requests for academic transcripts
- enrollment_verification: Employment or enrollment verification letters
- grade_change: Grade change requests or appeals
- financial_aid: Financial aid applications, appeals, or inquiries
- subaward_request: Subaward or subcontract setup requests
- vendor_setup: New vendor/supplier registration
- travel_reimbursement: Travel expense claims and reimbursements
- hiring_packet: New hire paperwork or onboarding documents
- irb_submission: IRB/IACUC protocol submissions or amendments
- compliance_report: Compliance filings, audits, or reviews
- data_use_agreement: Data use, sharing, or transfer agreements
- purchasing_request: Purchase orders, requisitions, or procurement
- general_inquiry: General questions or informational requests
- faculty_submission: Faculty reports, tenure packets, or evaluations
- other: Does not fit any category above

SENSITIVITY DETECTION — Flag ANY of these:
- PII: Social Security numbers (SSN), driver's license numbers, passport numbers
- FERPA: Student grades linked to identifiable information, disciplinary records,
  education records containing student identifiers
- STUDENT_ID: Student ID numbers visible in context that could identify individuals
- FINANCIAL: Bank account numbers, routing numbers, credit card numbers
- HEALTH: Medical records, disability information, health conditions
- EXPORT_CONTROL: References to ITAR, EAR, controlled technology, sanctioned countries

SUGGESTED ACTION:
- "process": Safe to process automatically
- "review": Contains sensitivity flags or low confidence — hold for human review
- "reject": Clearly spam, misdirected, or policy-violating

Be conservative: when uncertain, flag for review rather than processing automatically.
Sensitivity detection should have zero false negatives — flag anything suspicious."""


def create_triage_agent(model_name: str) -> Agent:
    """Create or retrieve a cached triage agent."""
    cache_key = f"triage_{model_name}"
    if cache_key not in _triage_agent_cache:
        model = get_agent_model(model_name)
        _triage_agent_cache[cache_key] = Agent(
            model,
            output_type=TriageResult,
            system_prompt=TRIAGE_SYSTEM_PROMPT,
            retries=2,
        )
    return _triage_agent_cache[cache_key]


def triage_work_item_sync(work_item) -> TriageResult:
    """Run triage classification on a work item synchronously.

    Args:
        work_item: A WorkItem model instance with populated metadata.

    Returns:
        TriageResult with classification, sensitivity flags, and recommendation.
    """
    agent = create_triage_agent(get_default_model_name())

    # Build context from available work item fields
    attachment_names = []
    if work_item.attachments:
        for doc in work_item.attachments:
            try:
                attachment_names.append(doc.title)
            except Exception:
                pass

    # Include a preview of attachment text if available
    attachment_text_preview = ""
    if work_item.attachments:
        for doc in work_item.attachments[:3]:  # Max 3 attachments
            try:
                if doc.raw_text:
                    attachment_text_preview += f"\n--- Attachment: {doc.title} ---\n"
                    attachment_text_preview += doc.raw_text[:3000]
            except Exception:
                pass

    context = f"""
Source: {work_item.source}
Subject: {work_item.subject or '(no subject)'}
Sender: {work_item.sender_name or ''} <{work_item.sender_email or ''}>
Received: {work_item.received_at or 'unknown'}

Body:
{(work_item.body_text or '')[:5000]}

Attachments ({work_item.attachment_count} files): {', '.join(attachment_names) if attachment_names else 'none'}
{attachment_text_preview}
""".strip()

    result = agent.run_sync(context)
    return result.output
