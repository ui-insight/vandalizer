# Verification + Support Center Integration

**Date:** 2026-03-26
**Status:** Draft

## Problem

The verification management queue has several UX problems:

1. **Confusing icons** — the Eye (Review) and RotateCcw (Return for Improvement) icons trigger identical behavior (both open the same review panel with no state difference).
2. **No feedback on reject** — a reviewer can single-click reject with no notes. The submitter gets a generic "did not meet verification requirements" message.
3. **No confirmation on destructive actions** — approve, reject, and return are all single-click from the icon row.
4. **No conversation channel** — the only communication is a one-shot `reviewer_notes` field. No back-and-forth, no ability to ask questions.
5. **Broken resubmission flow** — "My Submissions" is read-only. No resubmit button, no way to discuss a return.
6. **Lost context on resubmission** — a resubmission creates a new request with no link to the prior one. A different reviewer has no context on previous exchanges.
7. **Reviewer rubric not surfaced** — the backend has `get_reviewer_rubric()` but the UI never shows it.

## Solution

Integrate verification conversations into the existing support center. When a reviewer needs to communicate with a submitter (return, reject, ask a question), the system creates a support ticket linked to the verification request. The support center's existing threading, attachments, read tracking, notifications, and polling handle the conversation.

## Approach

**Lightweight Linking** — add `context_kind`/`context_id` to `SupportTicket` and `support_ticket_uuid` to `VerificationRequest`. Auto-create tickets on Return/Reject/Ask Question. Examiners get reply access via context-aware auth. Reuse all existing support UI with a verification context banner.

Rejected alternatives:
- **Embedded chat widget** in the verification queue — duplicates the entire support chat UI, doubles maintenance.
- **Standalone discussion system** — rebuilds threading, attachments, notifications, read tracking from scratch.

## Data Model Changes

### SupportTicket — add fields

```python
context_kind: Optional[str] = None    # "verification" | None (extensible)
context_id: Optional[str] = None      # verification request UUID
```

### VerificationRequest — add fields

```python
support_ticket_uuid: Optional[str] = None    # linked support ticket
previous_request_uuid: Optional[str] = None  # chains resubmissions to prior request
```

`previous_request_uuid` lets reviewers trace the full history of a submission across resubmissions. The linked support ticket carries forward when a submitter resubmits.

## Ticket Creation Rules

| Reviewer Action | Creates Ticket? | Behavior |
|---|---|---|
| Ask a Question | Yes (new or append) | Status stays `in_review`. Examiner's question is the first message. |
| Return for Revision | Yes (new or append) | Return guidance becomes a message. Ticket stays open for submitter to reply. |
| Reject | Yes (new or append) | Rejection reason becomes a message. Ticket auto-closes; submitter can reopen by replying. |
| Approve | No | If a linked ticket exists, auto-close it with a system message. |

"New or append": if `support_ticket_uuid` already exists on the verification request, add a message to that ticket. Otherwise create a new one with `context_kind="verification"` and `context_id=<request_uuid>`.

Auto-generated ticket subject format: `"Verification: {item_name}"`. If a ticket already exists, the subject stays unchanged.

## Auth Changes

Modify `_is_support_user()` in the support router to accept an optional ticket:

```python
async def _is_support_user(user: User, ticket: SupportTicket | None = None) -> bool:
    if user.is_admin:
        return True
    if ticket and ticket.context_kind == "verification" and user.is_examiner:
        return True
    config = await SystemConfig.get_config()
    contacts = config.support_contacts or []
    return any(c.get("user_id") == user.user_id for c in contacts)
```

Examiners can reply to verification-linked tickets but cannot see or reply to general support tickets.

Ticket listing queries also need updating: examiners should see tickets where `context_kind == "verification"` in addition to normal support contact visibility rules.

## Verification Queue UI Redesign

### Remove the 4-icon action row

Replace with:
- **Expand/collapse chevron** (unchanged)
- **Open item** external link (unchanged)
- **Review** — single text button that opens the review panel

No bare icon approve/reject. All final actions live inside the review panel.

### Review panel contents

1. **Reviewer rubric** — fetched from `get_reviewer_rubric()`, displayed as a checklist so the reviewer knows what to evaluate.
2. **Notes textarea** — mandatory for Reject and Return, optional for Approve and Ask Question.
3. **Org/collection assignment** — shown only when approving (unchanged from current).
4. **Action buttons:**
   - **Approve** — confirmation dialog: "Approve this submission?"
   - **Reject** — notes required. Confirmation dialog: "This will reject the submission and notify the submitter with your feedback."
   - **Return for Revision** — notes required. No confirmation (reversible action).
   - **Ask a Question** — creates/opens linked support ticket, sets status to `in_review`.
   - **Cancel** — closes review panel.
5. **Conversation indicator** — if a linked support ticket exists, show "View Discussion" link that opens the support panel to that ticket. The link appears whenever `support_ticket_uuid` is set on the request; no message count is shown (avoids an extra API call per queue item).

## Submitter "My Submissions" — Add Actions

Currently read-only. Add:

- **Resubmit** (for `returned` status) — opens `VerificationSubmitModal` (the multi-step wizard) pre-filled with data from the previous submission. Creates a new `VerificationRequest` with `previous_request_uuid` pointing to the old one. Carries forward the same `support_ticket_uuid`.
- **Discuss** (when `support_ticket_uuid` exists) — opens the support panel to the linked ticket.
- **Withdraw** (for `submitted` status) — sets status to `rejected` with `reviewer_notes: "Withdrawn by submitter"`. Confirmation dialog required. If a linked support ticket exists, it is auto-closed.

## Support Panel — Verification Context Banner

When a ticket has `context_kind == "verification"`, show a banner at the top of the chat view:

```
[ShieldCheck] Verification Discussion
"Workflow Name Here" — Status: Returned
[View Submission] [View Item]
```

- **View Submission** — navigates to the Library page's verification tab. The banner stores the `context_id` (request UUID) and the queue can accept a `highlight` query parameter to scroll to and highlight that request.
- **View Item** — navigates to the workflow/extraction in the workspace (same as the existing ExternalLink behavior in the queue).

This provides context so the conversation isn't disconnected from the item under review.

## Notifications

| Event | Recipient | Message | Opens |
|---|---|---|---|
| Examiner asks a question | Submitter | "An examiner has a question about '{name}'" | Support panel |
| Submitter replies in ticket | Assigned reviewer | "New message on verification for '{name}'" | Support panel |
| Return for revision | Submitter | "'{name}' needs revision — reviewer feedback attached" | Support panel |
| Reject | Submitter | "'{name}' was not approved — see reviewer feedback" | Support panel |
| Approve | Submitter | "'{name}' has been approved" | Verification queue |
| Resubmission | Previous reviewer | "'{name}' has been resubmitted for review" | Verification queue |

All verification notifications involving feedback route to the support panel.

## Resubmission History

When a reviewer opens a request with `previous_request_uuid`, the detail section shows:

- **"Resubmission"** badge next to the status badge.
- **Previous review** section: prior reviewer notes, return guidance, link to conversation thread.
- Chain is walkable: each resubmission links to its predecessor.

## Backend Service Changes

### verification_service.py

- New function `_create_or_append_ticket(request, user, message)` — creates a linked support ticket or appends a message to the existing one. Sets `context_kind="verification"`, `context_id=request.uuid`.
- Modify `update_status()` — call `_create_or_append_ticket` for reject/return/ask-question. Close ticket on approve.
- Modify `submit_for_verification()` — accept optional `previous_request_uuid`, carry forward `support_ticket_uuid` from the prior request.

### support_service.py

- Modify `create_ticket()` — accept optional `context_kind` and `context_id` parameters.
- Modify ticket listing — examiners see tickets where `context_kind == "verification"`.

### support router

- Modify `_is_support_user()` — context-aware auth as described above.

## Out of Scope

- No inline chat widget in the verification queue.
- No changes to the existing general support flow — this is purely additive.
- No auto-assignment of examiners to tickets — the examiner who takes action gets linked.
- No formal appeal process for rejections — submitters can reply in the ticket to discuss, but there is no "appeal" status.
