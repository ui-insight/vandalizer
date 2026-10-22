# Vandalizer 5.0 — Fully Agentic

**Status:** unreleased — pending merge of `major/agentic-chat`. Set the release date at tag time and mirror it into `CHANGELOG.md`.

The biggest change to Vandalizer since launch: the chat now drives the entire platform. Documents, knowledge bases, extractions, workflows, projects, automations, and the certification program are all reachable through one conversation — with quality scores, source citations, and confirmation flows built in.

The dedicated editors are unchanged and remain the precision surface. Chat is a second way into the same machinery, not a replacement for it.

---

## Highlights

- **Chat is the product.** 49 pydantic-ai tools let the agent search documents, query knowledge bases, run extractions, dispatch workflows, manage projects, and run validation — all from plain-English prompts.
- **Chat builds, not just runs.** Describe a process and the agent authors a real multi-step workflow, an extraction template, or an automation. This is the single biggest capability jump in the release.
- **Projects.** A goal-scoped workspace per grant or effort. Files added are auto-indexed into the project's implicit knowledge base, so "chat across all my files" works with no knowledge base to build.
- **Answers carry measured quality.** Results from validated templates carry a `QualityBadge` with tier, accuracy, consistency, and active alerts; unvalidated templates show Unscored. The model never sees the number — it comes from stored `ValidationRun` records and is stripped before the payload reaches the LLM, so the agent cannot inflate its own grade.
- **Source-linked answers.** Knowledge-base replies show the passages they used. Click any passage to jump to the source.
- **Writes require confirmation.** All 19 state-changing tools preview first and execute only after approval. Every tool call runs as the calling user, in that user's team scope — the agent holds no privileges of its own.
- **Guided verification.** Turn any good extraction into a test case in one click. The more your team verifies, the higher the tier climbs.
- **Certification runs in chat.** The full Vandal Workflow Architect program — lessons, practice documents, grading — happens in the conversation, sharing one progress store with the panel.
- **Web access.** The agent can search the public web and read pasted URLs, with your own documents always checked first. Off until an admin configures a provider.
- **Built to survive long sessions.** Auto-compaction, prompt-cache-aware assembly, parallel read execution, a live progress checklist, and a mid-run message queue so you can keep typing while it works.

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
- Rebuilt chat home: state-aware first-session / returning / power-user variants, a cold-start hero, capability pills gated on real workspace state, and a first-run tour.

## Documentation

- New: `docs/AGENTIC_CHAT_USER_GUIDE.md` — end-user guide to what the chat can do.
- New: `docs/AGENTIC_CHAT_TOOLS_REFERENCE.md` — developer reference for all 49 tools, with params, auth rules, execution model, and the quality sidecar shape.
- New: `docs/QUALITY_SIGNALS_EXPLAINED.md` — explainer for the trust layer.
- README gains an agentic-chat section and web-search configuration.
- DEPLOY.md gains an **Agentic Chat** section: model choice, token cost, the team-context requirement, and web-access egress posture.
- OPERATIONS.md gains an agentic chat smoke test (including a confirm-gate check).
- `CHANGELOG.md` carries the full 5.0 entry.

## Configuration

- New System Config fields: `web_search_provider`, `web_search_endpoint`, `web_search_api_key` (Admin → System Config → Endpoints). Web search is unavailable until these are set — it fails closed, with no default provider and no implicit egress.
- New env var: `demo_request_to_email` (falls back to `resend_from_email` / `smtp_from_email`).
- New Celery beat schedules: `engagement-agentic-chat-drip` (daily 10:15), `engagement-powerup-milestones` (daily 10:45).

## Upgrade notes

- **Database:** Existing users receive new optional fields (`v5_announcement_sent_at`, `agentic_drip_step`, `agentic_drip_next_at`, `first_chat_workflow_at`, `chat_workflow_count`, `powerup_milestone_sent_at`, `certification_complete_sent_at`, `role_segment`). No migration required — Beanie handles absent keys as defaults.
- **Validate your chat model first.** The agent selects tools, chains multi-step work, and follows a confirm-gate protocol. A model that produced acceptable v4 summaries may pick wrong tools or skip confirmations. Test against real multi-step prompts before rollout.
- **Check team membership.** Agentic mode activates only with both a user and a team context. Users without team membership — including admins who never joined one — silently get plain chat with no tools. Set `DEFAULT_TEAM_NAME` at bootstrap, or verify membership before announcing.
- **Budget for higher token usage.** Tool schemas ride along in every request and results accumulate. Compaction and prompt caching mitigate this, but per-conversation cost is above v4.
- **Rollout order recommended:**
  1. Deploy code, run a dry-run on the announcement blast to verify the eligible count.
  2. Run the drip backfill (admin panel) so existing users are enrolled.
  3. Send the announcement in batches (admin panel) until `sent == 0`.
- **Rollback:** Safe to revert the branch. New User fields are additive. Already-sent announcement emails are idempotently tracked per-user, so a re-run after revert-then-reapply won't double-send.

## Known gaps

- No recorded walkthrough / video on the landing page yet (visual is a stylized chat mock).
- The landing page is slated for a full redesign; treat its current copy as provisional.
- Existing users without `role_segment` receive default drip copy.
- Cross-field extraction rules can be evaluated from chat (`check_compliance`) but not authored there — that stays in the extraction editor.
- Automations created from chat support folder-watch and schedule triggers only; API and M365 intake triggers are configured in the Automations UI.
- `search_documents` content search is a full collection scan with no text index, and can time out on very large workspaces.
