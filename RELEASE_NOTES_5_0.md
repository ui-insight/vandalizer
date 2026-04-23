# Vandalizer 5.0 — Fully Agentic

**Release date:** 2026-04-22

The biggest change to Vandalizer since launch: the chat now drives the entire platform. Documents, knowledge bases, extractions, and workflows are all reachable through one conversation — with quality scores, source citations, and confirmation flows built in.

---

## Highlights

- **Chat is the product.** 19 pydantic-ai tools let the agent search documents, query knowledge bases, run extractions, dispatch workflows, and build test cases — all from plain-English prompts.
- **Every answer is validated.** Extraction results carry a `QualityBadge` with tier, accuracy, consistency, and active alerts. The LLM can't see or inflate the number; it comes from stored `ValidationRun` records.
- **Source-linked answers.** Knowledge-base replies show the document passages they used. Click any passage to jump to the source.
- **Writes require confirmation.** KB creation, workflow dispatch, and extraction-set creation all preview first, then execute only after the user approves.
- **Guided verification.** Turn any good extraction into a test case in one click. The more your team verifies, the higher the tier climbs.
- **Certification curriculum updated for v5.** Module 1 reframed as "generic chat fails; validated agentic chat is the answer." Foundations, Extraction, Multi-Step, Advanced Nodes, Output Delivery, Validation, Batch, and Governance exercises rewritten to drive from chat prompts. New lessons cover chat-driven workflow design, trust signals & quality tiers, and guided verification.

## Launch funnel (admin-facing)

- **v5.0 announcement email** — blastable via Admin → Email → "v5.0 Launch Announcement" panel (idempotent per user).
- **Agentic-chat tutorial drip** — 5-step sequence auto-enrolls new registrations; existing users can be enrolled via Admin → Email → "Agentic-chat drip backfill."
- **Power-user upsell** — fires automatically when a user completes 30 chat-dispatched workflows.
- **Certification completion email + in-app badge** — fires once per user when all 11 modules are complete; deep-links into the Certification panel.
- **Role segmentation** — `role_segment` captured at registration powers cohort-specific drip copy (PI / compliance / sponsored programs / research admin / IT / other).

## Product changes

- Added `role_segment` to register form and demo-request form.
- New "Request a Demo" form on the landing page (`POST /api/demo/request-contact`).
- Email preferences panel on the Account page now includes an **Announcements** toggle (opt-in by default).
- Cert-complete notifications deep-link to `/certification`.
- Chat-dispatched workflow runs create tagged `ActivityEvent` records so the power-user milestone only counts completed runs.
- Cert validators (`foundations`, `extraction_engine`, `validation_qa`, `batch_processing`) now accept both the classical Workflow path and the chat-driven SearchSet / `SEARCH_SET_RUN` activity path.

## Documentation

- New: `docs/AGENTIC_CHAT_USER_GUIDE.md` — end-user guide to the 19 tools.
- New: `docs/AGENTIC_CHAT_TOOLS_REFERENCE.md` — developer reference with params, auth rules, quality sidecar shape.
- New: `docs/QUALITY_SIGNALS_EXPLAINED.md` — explainer for the trust layer.
- Updated `CHANGELOG.md` with the full 5.0 entry.

## Configuration

- New env var: `demo_request_to_email` (falls back to `resend_from_email` / `smtp_from_email`).
- New Celery beat schedules: `engagement-agentic-chat-drip` (daily 10:15), `engagement-powerup-milestones` (daily 10:45).

## Upgrade notes

- **Database:** Existing users receive new optional fields (`v5_announcement_sent_at`, `agentic_drip_step`, `agentic_drip_next_at`, `first_chat_workflow_at`, `chat_workflow_count`, `powerup_milestone_sent_at`, `certification_complete_sent_at`, `role_segment`). No migration required — Beanie handles absent keys as defaults.
- **Rollout order recommended:**
  1. Deploy code, run a dry-run on the announcement blast to verify the eligible count.
  2. Run the drip backfill (admin panel) so existing users are enrolled.
  3. Send the announcement in batches (admin panel) until `sent == 0`.
- **Rollback:** Safe to revert the branch. New User fields are additive. Already-sent announcement emails are idempotently tracked per-user, so a re-run after revert-then-reapply won't double-send.

## Known gaps

- No recorded walkthrough / video on the landing page yet (visual is a stylized chat mock).
- No first-run in-product tour — user guide is written but not embedded in-app.
- Existing users without `role_segment` receive default drip copy.
