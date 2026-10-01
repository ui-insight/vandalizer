# Vandalizer RA usability upgrade checklist

Bring every reviewed area to at least **8/10 for visual UI, 8/10 for UX and 8/10 for task usefulness**. This is the implementation and verification backlog derived from the [September 30 fresh review](reviews/2026-09-30-ra-ui-ux.html) and its [scorecard](reviews/2026-09-30-ra-ui-ux.json). The baseline is UI **7.3**, UX **6.7**, RA task fit **7.5** across 23 RA-facing areas, with two supporting-role overviews graded separately.

**Implementation authorized.** Track checkpoints and resume instructions in the [implementation progress log](ra-ui-ux-implementation-progress.md).

**100/108 items complete; 8 remain open.** Completion evidence is recorded in the implementation progress log and the [October 1 reassessment](reviews/2026-10-01-ra-ui-ux.html); baseline grades remain unchanged. The eight remaining items require model execution or actual assistive-technology/user observation. The list covers all 25 assessed areas, shared defects, gaps in the original sampling and final acceptance. The older [169-item checklist](ui-ux-upgrade-checklist.md) remains the historical record for issue #964; this is a new pass and does not reopen or rewrite that record.

## How to use this checklist

**Fix** means a defect observed in the fresh review. **Improve** is a proposed design change. **Verify** means evidence is missing or behavior must be preserved; inspect the existing implementation first and repair only what the check shows is necessary. Existing working behavior can satisfy an item without a new feature.

**P1** covers access failures, critical task integrity and release gates. **P2** covers the remaining improvements and verification required to justify the target. Each checkbox names a bounded work item and its completion condition. Mark it complete only with a change or verification reference; implementation alone does not establish a grade.

For specialist surfaces, usefulness means helping that role support RA work and giving ordinary RAs a clear path to the right assistance. Technical controls can remain technical when their intended user needs them. Merely hiding a low-scoring screen does not raise its usefulness grade.

## Execution order

1. Preserve file/tool composition and resolve P1 keyboard, naming, contrast and mobile-shell defects.
2. Apply shared styles and improve navigation, resumption, titles and status visibility.
3. Improve task guidance, evidence inspection, reuse, collaboration and specialist workflows.
4. Fill the coverage gaps, validate actual execution and observe representative users.
5. Regrade each area and publish the evidence. A completed checklist does not automatically earn 8/10.

The current file-panel control and cross-pane behavior are required constraints from the user's navigation corrections. Shared shell work should be reused across Admin and examiner pages. Shared labels, contrast and styles should be fixed once rather than separately in each feature. Do not add unrelated integrations, a new grant-management system, a permission redesign or a backend rewrite to satisfy this list. Any additional operational data must come from real system state.

## Coverage and baseline grades

Each surface section below contributes to the all-surface target. UI, UX and RA columns are the original review grades, not predicted outcomes. The two supporting-role grades remain provisional until their populated workflows are exercised.

| Area | UI | UX | RA | Checklist |
| --- | ---: | ---: | ---: | --- |
| Workspace navigation | 7.5 | 6.5 | 7.5 | R8-NAV |
| Public entry and sign-in | 8 | 7.5 | 7 | R8-ENTRY |
| First-session guidance | 8 | 7.5 | 7.5 | R8-START |
| Chat and document/KB scope | 8 | 8 | 8 | R8-CHAT |
| Agent approvals and recovery | 8 | 7.5 | 8 | R8-AGENT |
| Files and document-to-tool work | 8 | 8 | 8.5 | R8-FILES |
| Projects and collaboration | 7.5 | 6.5 | 7.5 | R8-PROJECT |
| Library organization | 7.5 | 7 | 8 | R8-LIBRARY |
| Explore and shared tool detail | 8 | 7 | 7.5 | R8-EXPLORE |
| Workflow design, input and output | 7 | 5.5 | 8 | R8-WORKFLOW |
| Extraction design, results and evidence | 7.5 | 7 | 8.5 | R8-EXTRACT |
| Automations: list, setup and history | 7.5 | 7.5 | 8.5 | R8-AUTO |
| Knowledge bases and source health | 8 | 7.5 | 8.5 | R8-KNOWLEDGE |
| Validation and quality improvement | 7 | 6.5 | 7.5 | R8-VALIDATE |
| Activity and resuming work | 7 | 5.5 | 7 | R8-ACTIVITY |
| Human review queue and decision | 7 | 6 | 8.5 | R8-REVIEW |
| Account and team management | 7.5 | 7 | 7.5 | R8-TEAM |
| Credentials and integrations | 7 | 6 | 5.5 | R8-CREDENTIAL |
| Support panel | 7 | 6.5 | 7 | R8-SUPPORT |
| Certification and learning | 7 | 6.5 | 7 | R8-LEARN |
| Docs and self-service help | 6.5 | 5.5 | 5.5 | R8-DOCS |
| Team Admin overview | 5.5 | 4.5 | 6.5 | R8-ADMIN |
| Tuning suggestions | 7 | 6.5 | 6.5 | R8-TUNE |
| Examiner / Shared items | 5.5 | 4.5 | 6.5 | R8-EXAMINER |
| Support-staff queue | 7 | 7 | 6.5 | R8-STAFF |

## Shared foundations

Every surface uses the same dependable interaction and visual rules.

- [x] **R8-BASE-01 · P1 · Verify: Preserve the document and tool workspace.** Opening Files, Library, a workflow, extraction, project or assistant must preserve the intended document, selection, draft and result. The Files icon remains the file-panel control. Do not reintroduce exclusive full-screen sections or a duplicate split toggle.
- [x] **R8-BASE-02 · P2 · Improve: Extend the existing visual system.** Apply the established typography, spacing, borders, action hierarchy and semantic status styles to Reviews, Support, learning, account/team pages and specialist tools. Preserve meaningful diagram structure; remove decoration that competes with task content.
- [x] **R8-BASE-03 · P2 · Improve: Standardize forms and action states.** Use consistent labels, required/optional hints, inline errors, pending feedback and safe retry behavior. Primary and destructive actions must be recognizable in every reviewed surface, with no double submission.
- [x] **R8-BASE-04 · P1 · Fix: Name the known inaccessible controls.** Associate the Reviews status label with its select, label the artifact-edit textarea, name the Support close button and name the Docs mobile menu. Check adjacent controls for the same defect. Each must expose the correct name and role in the accessibility tree.
- [x] **R8-BASE-05 · P1 · Fix: Resolve measured contrast failures.** Repair the recorded failures in Reviews, Teams, Docs, Certification, Tuning, Admin and empty workflow/extraction histories. Use readable shared color roles, including selected tabs, disabled states and status text; rerun the affected checks.
- [x] **R8-BASE-06 · P1 · Verify: Check nested overflow and short screens.** Inspect both page width and nested scroll containers at 320, 390, 768, 1024 and 1440px, including short viewports. Ordinary forms, cards and navigation must fit; deliberate wide-data scrolling must remain contained and clearly usable.
- [ ] **R8-BASE-07 · P1 · Verify: Audit keyboard and assistive technology paths.** Exercise row opening, card editing, menus, tabs, source links and recovery with the keyboard, then spot-check names, order and announcements with a screen reader. Automated scans do not close this item by themselves.
- [x] **R8-BASE-08 · P1 · Verify: Verify dialog and overlay focus.** Dialogs and nested pickers must focus meaningful content, retain focus when modal, close the correct layer and restore the trigger. Nonmodal Support and learning panels must allow a predictable return to the workspace.
- [x] **R8-BASE-09 · P2 · Verify: Use representative review data.** Add bounded examples with long names, many documents/tools, multiple roles, partial source health, pending reviews, failed runs and long outputs. Keep success, empty, loading, denied-access and recoverable-error states distinct; do not grade only sparse happy paths.
- [x] **R8-BASE-10 · P2 · Verify: Check enlargement and reduced motion.** Critical reading and actions must remain usable at actual 200% browser zoom and enlarged text. Device pixel ratio alone is not zoom evidence. Reduced motion must preserve status meaning and usable focus.
- [x] **R8-BASE-11 · P2 · Improve: Make terminology and status consistent.** Reconcile shared, checked, validated, available, completed and approved across marketing, workspace, catalog, reviews and docs. Explain what each state establishes using actual system data; preserve distinctions between successful execution and correct output.

## Workspace navigation

Baseline UI 7.5 / UX 6.5 / RA 7.5. **Target: at least 8 in all three dimensions.**

An RA finds the right place and keeps work in context.

- [x] **R8-NAV-01 · P2 · Improve: Expose readable navigation labels.** Offer persistent or expandable labels for Projects, Chat, Files, Automations and Knowledge. The selected section remains clear on desktop, keyboard focus and touch, without adding another file-panel control.
- [x] **R8-NAV-02 · P2 · Fix: Keep workflow section labels visible.** Design, Input, Validate, Advanced and History remain readable at the default split width. Use compact text, wrapping or a clearly accessible tab overflow pattern instead of an unexplained icon strip.
- [x] **R8-NAV-03 · P2 · Verify: Make navigation reversible.** Check Back, forward, refresh, deep links, project entry/exit and source/tool switching. Returning restores the intended location and scroll position; a new task cannot silently inherit stale scope.

## Public entry and sign in

Baseline UI 8 / UX 7.5 / RA 7. **Target: at least 8 in all three dimensions.**

A visitor understands an RA outcome and can reliably enter the app.

- [x] **R8-ENTRY-01 · P2 · Improve: Lead with a concrete RA example.** Show an accurate proposal-review or budget-check example with its input, result and source inspection. Keep the existing clear sign-in path and make the primary call to action match what happens next.
- [x] **R8-ENTRY-02 · P2 · Improve: Align public promises with product behavior.** Replace ambiguous verified-workflow claims with the terminology and evidence actually used in the app. Distinguish sample/demo output from real execution.
- [x] **R8-ENTRY-03 · P2 · Verify: Exercise entry and recovery states.** Test sign-in success/failure, password reset, session expiry, permitted SSO paths and return to an intended deep link in an isolated test environment. A failed attempt must preserve useful input and offer a clear next step.

## First session guidance

Baseline UI 8 / UX 7.5 / RA 7.5. **Target: at least 8 in all three dimensions.**

A newcomer completes one useful task before learning the product taxonomy.

- [x] **R8-START-01 · P2 · Improve: Provide a short first-task path.** Guide upload or sample selection → ask an RA question → inspect evidence → save or reuse the result. Reuse the existing onboarding path where it meets this outcome.
- [x] **R8-START-02 · P2 · Improve: Explain tools at the point of use.** Introduce workflow, extraction and knowledge-base concepts through the task they solve. Offer clear example questions; keep training and the tour optional and easy to revisit.
- [x] **R8-START-03 · P2 · Verify: Support interruption and return.** Confirm skip, resume, dismissed-tour behavior, upload errors and returning-user guidance. Do not present a newcomer setup wall to a user with active work.

## Chat and document and knowledge base scope

Baseline UI 8 / UX 8 / RA 8. **Target: at least 8 in all three dimensions.**

An RA understands the answer scope and can inspect its supporting evidence.

- [x] **R8-CHAT-01 · P2 · Verify: Validate answer scope on real-shaped cases.** Exercise a document, multiple documents, folders, project scope and partially ready knowledge bases. Outgoing requests and visible scope must agree; switching context must not leave an unnoticed stale source.
- [ ] **R8-CHAT-02 · P2 · Verify: Check grounding and evidence navigation.** Use a manually checked set of sponsor/policy questions, including missing or conflicting information. Check deadline and budget claims against the cited passages; source inspection must preserve the conversation and reading position.
- [x] **R8-CHAT-03 · P2 · Verify: Check long answers and handoff.** Exercise long answers, tables, citations, interrupted responses, retry and conversation export. Exported output must preserve useful source references and scope; fix any loss or unreadable formatting found.

## Agent approvals and recovery

Baseline UI 8 / UX 7.5 / RA 8. **Target: at least 8 in all three dimensions.**

Approvals and tool results clearly show what happened and what to do next.

- [x] **R8-AGENT-01 · P2 · Improve: Resolve historical approval state.** After approval, cancellation or completion, the original approval card becomes a concise historical record with accurate status. It must never remain actionable or imply another approval is still needed.
- [x] **R8-AGENT-02 · P2 · Improve: Make completion and recovery actionable.** Summarize the completed action, affected item and available Open/Inspect result action. On failure, preserve inputs and show a relevant recovery action without suggesting that an uncompleted change succeeded.
- [ ] **R8-AGENT-03 · P2 · Verify: Exercise actual tool lifecycle transitions.** In isolated test execution, cover approval, cancellation, permission denial, interrupted streaming and retry. Confirm one accepted action produces one intended effect, including when the user refreshes or resends.

## Files and document to tool work

Baseline UI 8 / UX 8 / RA 8.5. **Target: at least 8 in all three dimensions.**

Users can read realistic documents and use tools without losing them.

- [x] **R8-FILES-01 · P2 · Verify: Inspect representative document formats.** Check a multipage text PDF, scanned PDF, table-heavy document, DOCX and spreadsheet where supported. Verify zoom, search, source highlighting and the transition between original and extracted text.
- [x] **R8-FILES-02 · P2 · Improve: Expose document readiness where it matters.** Use existing processing and readability signals to identify unavailable or incomplete inputs before use. Missing or partial text must be actionable and must not look like a ready, fully read document.
- [x] **R8-FILES-03 · P1 · Verify: Retain the proven file-to-tool journey.** Repeat open → Library → workflow/extraction → run → failure/retry → inspect output → return at the five review widths. Both opened and checkbox-selected document paths must submit the correct IDs and preserve context.

## Projects and collaboration

Baseline UI 7.5 / UX 6.5 / RA 7.5. **Target: at least 8 in all three dimensions.**

A project is a practical place to resume RA work.

- [x] **R8-PROJECT-01 · P2 · Improve: Show a compact project overview.** Expose the existing lifecycle state, useful contents and pinned work in context. Make files and reusable tools reachable without first interpreting Manage project as the main work destination.
- [x] **R8-PROJECT-02 · P2 · Improve: Separate project work from management.** Make routine Open files, Ask about project and Run pinned tool actions distinct from member management, sharing and deletion. Keep source and tool panes available.
- [x] **R8-PROJECT-03 · P2 · Improve: Clarify collaboration scope.** Show who can view, chat, edit or manage using existing permissions. Explain PI read-only invitations and team sharing at the action that grants access; do not redesign the permission model.
- [x] **R8-PROJECT-04 · P2 · Verify: Exercise real collaboration states.** Verify owner/editor/viewer views, invitation acceptance/expiry, a removed member, unavailable project content and project switching with drafts. Test permissions with controlled accounts and record backend enforcement separately from hidden UI.

## Library organization

Baseline UI 7.5 / UX 7 / RA 8. **Target: at least 8 in all three dimensions.**

Users select a reusable tool by the work they need done.

- [x] **R8-LIBRARY-01 · P2 · Improve: Add task-oriented discovery.** Provide concise entry points or examples for reviewing requirements, extracting budget details and summarizing award conditions alongside the existing types. Reuse available tools; avoid a second competing library structure.
- [x] **R8-LIBRARY-02 · P2 · Improve: Make ownership and reuse legible.** Keep Mine, Team and Explore clear; distinguish saved, owned and shared items and clarify what changes when a user edits, copies or saves an item.
- [x] **R8-LIBRARY-03 · P2 · Verify: Check realistic library density.** Exercise search, type filters, folders, favorites/pins and return position with a representative large library and long titles. Empty results must offer a useful recovery without resetting unrelated filters.

## Explore and shared tool detail

Baseline UI 8 / UX 7 / RA 7.5. **Target: at least 8 in all three dimensions.**

An RA can judge whether a shared item fits the task before running it.

- [x] **R8-EXPLORE-01 · P2 · Improve: Add meaningful publication guidance.** Prompt authors for intended task, required input, expected deliverable and a small example. Surface that information before Save/Open; do not invent it for existing catalog items.
- [x] **R8-EXPLORE-02 · P2 · Improve: Handle incomplete metadata honestly.** For older items without descriptions, provide a useful inspection path and an explicit limitation. A quality badge must not substitute for a description of what the item does.
- [x] **R8-EXPLORE-03 · P2 · Improve: Keep quality evidence understandable.** Present sample size, test date, metric meaning and applicability together. Explain that recorded test performance does not establish correctness on the user’s documents.
- [x] **R8-EXPLORE-04 · P2 · Verify: Exercise adoption and maintenance.** Test save/open/share/copy with team and personal libraries, view-only items, unavailable sources and failed saves. Verify where the saved item appears and how updates affect a reused item.

## Workflow design input and output

Baseline UI 7 / UX 5.5 / RA 8. **Target: at least 8 in all three dimensions.**

An RA can understand, edit and run a reusable workflow with a keyboard or pointer.

- [x] **R8-WORKFLOW-01 · P1 · Fix: Make step and task editing keyboard-operable.** Provide named focusable primary actions for opening steps and tasks, with Enter/Space activation. Keep reorder/delete actions separate; restore focus after closing an editor and avoid nested interactive controls.
- [x] **R8-WORKFLOW-02 · P2 · Improve: Explain the step and task hierarchy.** Make the current editing level, inherited input and whether tasks run together or sequentially clear. An RA must be able to predict where output goes without reading implementation terminology.
- [x] **R8-WORKFLOW-03 · P2 · Improve: Give existing workflows a clear run path.** Before running, summarize actual inputs, intended deliverable and any required approval. Keep advanced configuration available without making model selection or canvas editing a prerequisite for routine reuse.
- [x] **R8-WORKFLOW-04 · P2 · Verify: Exercise representative design and output flows.** Cover multiple steps, task editing, missing inputs, approval pauses, failed runs, history, download and Save to folder. Include keyboard operation and realistic long output, preserving the document beside the tool.

## Extraction design results and evidence

Baseline UI 7.5 / UX 7 / RA 8.5. **Target: at least 8 in all three dimensions.**

Users can compare extracted values with evidence and hand off usable results.

- [x] **R8-EXTRACT-01 · P2 · Improve: Separate inspect and copy actions.** Make viewing a source and copying a value distinct, clearly labeled actions. Inspecting evidence must not create an unexpected clipboard side effect; both paths remain keyboard-accessible.
- [x] **R8-EXTRACT-02 · P2 · Improve: Make multiple results easy to inspect.** Keep document identity, field name, value and source support visible in multi-document results. Support efficient comparison using the existing result model and show missing/unconfirmed values clearly.
- [x] **R8-EXTRACT-03 · P2 · Verify: Check evidence and uncertainty states.** Test located and missing quotes, approximate pages, unsupported values, partial input text and conflicting fields. Labels must describe the measured evidence accurately without overstating automatic checks.
- [x] **R8-EXTRACT-04 · P2 · Verify: Verify result export fidelity.** Compare displayed and exported values for a representative multi-document extraction, including dates, money, missing values and document names. Preserve supported source references or clearly disclose their absence.

## Automations list setup and history

Baseline UI 7.5 / UX 7.5 / RA 8.5. **Target: at least 8 in all three dimensions.**

An RA can configure, monitor and recover an automation without guessing its effects.

- [x] **R8-AUTO-01 · P2 · Fix: Give the editor title enough space.** Place title/identity and action controls on responsive rows when needed. Ordinary titles remain readable in the default split and at laptop/mobile widths; run, enable, privacy and close controls stay reachable.
- [x] **R8-AUTO-02 · P2 · Verify: Retain the clear setup recap.** Confirm trigger, inputs, filters, action, destination and activation are understandable before saving. Save disabled and Create & enable must have distinct, accurate effects, including recovery from a failed save.
- [x] **R8-AUTO-03 · P2 · Improve: Emphasize operational outcomes.** Make last outcome, current enabled state and any required user action easy to scan. History detail should lead with status and usable output; keep technical run IDs available as secondary metadata.
- [x] **R8-AUTO-04 · P2 · Verify: Exercise trigger and delivery behavior.** In a controlled environment, test folder/schedule/manual paths, timezone display, duplicate prevention, missing input, unavailable worker and result delivery. A queued request must not be presented as a completed run.

## Knowledge bases and source health

Baseline UI 8 / UX 7.5 / RA 8.5. **Target: at least 8 in all three dimensions.**

An RA can use a policy collection and quickly identify sources needing attention.

- [x] **R8-KNOWLEDGE-01 · P2 · Improve: Make source health manageable at scale.** Provide a compact summary and a clear way to focus on sources needing attention. Keep source names, state, freshness when known and relevant retry/open actions readable in a large collection.
- [x] **R8-KNOWLEDGE-02 · P2 · Improve: Keep readiness and answer quality distinct.** Explain partial availability at the point of chat and source use. Ready source counts, ingestion state and measured answer quality must remain separate claims.
- [x] **R8-KNOWLEDGE-03 · P2 · Verify: Exercise realistic source intake and recovery.** Cover document/URL intake, inaccessible URLs, processing failures, retry, removal, refresh and shared collections. Check that source changes update the chat scope and validation context appropriately.

## Validation and quality improvement

Baseline UI 7 / UX 6.5 / RA 7.5. **Target: at least 8 in all three dimensions.**

Users can run a representative check and understand its practical consequence.

- [x] **R8-VALIDATE-01 · P2 · Improve: Make the default sequence task based.** Lead with choose representative questions/examples → supply expected results → run a check → inspect problems. Reduce repeated explanation and tab nesting; reuse current controls where they already support this path.
- [x] **R8-VALIDATE-02 · P2 · Improve: Separate routine checking from expert tuning.** Keep grader/model selection, retrieval parameters and tuning budgets in clearly labeled advanced sections. Explain the existing defaults, cost limits and actual effect of each advanced operation.
- [x] **R8-VALIDATE-03 · P2 · Improve: Summarize actionable results.** Show what was tested, important failures, available evidence and the next review action before detailed metrics. Distinguish a saved proposal from applied settings and expose regressions alongside improvements.
- [ ] **R8-VALIDATE-04 · P2 · Verify: Cover all three validation domains.** Test KB, workflow and extraction validation with real-shaped cases, missing references, cancellation, refresh/resumption, history and apply/revert. Manually compare selected results with expected answers; fixture scores alone cannot close this item.

## Activity and resuming work

Baseline UI 7 / UX 5.5 / RA 7. **Target: at least 8 in all three dimensions.**

Recent work is easy to resume and failures are obvious.

- [x] **R8-ACTIVITY-01 · P1 · Fix: Make activity items proper keyboard actions.** Expose named focusable open/resume actions with Enter/Space support. Keep deletion separate and restore focus when the user returns from the selected item.
- [x] **R8-ACTIVITY-02 · P2 · Fix: Separate failure status from deletion.** Use persistent status text and a concise reason or recovery link. The delete button must not cover the status icon or become the most prominent signal of a failed run.
- [x] **R8-ACTIVITY-03 · P2 · Verify: Check a mixed populated activity list.** Exercise conversations, workflows, extractions, pending approvals, failed/cancelled/stale runs and many items. Verify loading, refresh, open/resume and deletion without accidental reruns or loss of unrelated work.

## Human review queue and decision

Baseline UI 7 / UX 6 / RA 8.5. **Target: at least 8 in all three dimensions.**

A colleague can make an informed decision and the workflow resumes correctly.

- [x] **R8-REVIEW-01 · P2 · Improve: Strengthen the queue hierarchy.** Make task, requester, due/expiry state, assignment and pending status easy to scan. Keep My reviews and Team queue distinct with readable filter and selected-tab states.
- [x] **R8-REVIEW-02 · P2 · Improve: Support evidence-led decisions.** Keep instructions, source documents, output and reviewer comments together. Make changes to the proposed artifact clear before approval; distinguish approval of output from publication or compliance certification.
- [x] **R8-REVIEW-03 · P1 · Verify: Exercise decision and resume behavior.** Test approve, reject, edited approval, duplicate submission, expiration, reassignment and insufficient access with controlled accounts. Exactly one accepted decision should drive the intended next workflow state.
- [x] **R8-REVIEW-04 · P2 · Verify: Check all artifact renderers.** Inspect text, markdown, structured JSON and extraction tables, including long content and mobile layouts. Source inspection and editing must preserve unsaved reviewer input and accessible control names.

## Account and team management

Baseline UI 7.5 / UX 7 / RA 7.5. **Target: at least 8 in all three dimensions.**

An RA understands identity, team roles and the effects of sharing.

- [x] **R8-TEAM-01 · P2 · Improve: Distinguish global and team roles.** Label account-level access separately from the role in the current team. Explain why the same person can be a global Member and a team Owner without suggesting inconsistent permissions.
- [x] **R8-TEAM-02 · P2 · Improve: Prioritize everyday team work.** Group members and invitations ahead of ownership transfer and deletion. Keep destructive actions distinct without adding confirmation steps to ordinary reversible edits.
- [x] **R8-TEAM-03 · P2 · Verify: Check profile and preference recovery.** Exercise profile/email edits, SSO-managed fields, memory settings and failed preference saves. Show actionable errors and restore the last saved state correctly.
- [x] **R8-TEAM-04 · P2 · Verify: Check membership and invitation lifecycle.** Test role changes, team switching, invite links, expiry/revocation and controlled ownership transfer. Explain the affected team and users before consequential actions; verify return to the correct workspace.

## Credentials and integrations

Baseline UI 7 / UX 6 / RA 5.5. **Target: at least 8 in all three dimensions.**

Integration setup serves the specialist while ordinary RAs can understand connection readiness.

- [x] **R8-CREDENTIAL-01 · P2 · Improve: Explain purpose and intended audience.** Describe credentials as connections used by workflow integrations, with a concrete example. Make it clear when setup belongs to a team/integration administrator and when an RA can use an existing connection.
- [x] **R8-CREDENTIAL-02 · P2 · Improve: Make setup and testing understandable.** Explain required fields and test effects in task language. Keep connection name, type, scope, test result and the next action clear; never expose stored secrets as a convenience.
- [x] **R8-CREDENTIAL-03 · P2 · Verify: Exercise connection lifecycle safely.** Use a local/mock integration for creation, edit, test success/failure, missing access and deletion while referenced by a workflow. Verify helpful outcomes for both the maintainer and an RA running the dependent tool.

## Support panel

Baseline UI 7 / UX 6.5 / RA 7. **Target: at least 8 in all three dimensions.**

A user can report a problem and return to work with a clear record.

- [x] **R8-SUPPORT-01 · P2 · Improve: Lead with the problem description.** Prioritize subject and description; keep priority and classification simple with reasonable defaults. Explain what is submitted and where the user can find the response.
- [x] **R8-SUPPORT-02 · P2 · Improve: Align the panel with the app.** Use shared typography, controls and action styling. Keep a named close/back path, usable mobile sizing and a draft that survives ordinary panel switching.
- [x] **R8-SUPPORT-03 · P2 · Verify: Exercise ticket and attachment recovery.** In a non-delivering test setup, check create, failed submission, retry, attachments, reopen and reply. A failed send must keep the user’s text and files; returning to work must not obscure ticket state.

## Certification and learning

Baseline UI 7 / UX 6.5 / RA 7. **Target: at least 8 in all three dimensions.**

Training helps users accomplish work without becoming a prerequisite.

- [x] **R8-LEARN-01 · P2 · Improve: Make task learning the primary entry.** Offer a short relevant lesson or task walkthrough before the full credential path. Show duration and next lesson plainly; keep XP, tiers and locked modules secondary.
- [x] **R8-LEARN-02 · P2 · Improve: Simplify panel positioning controls.** Use understandable position labels or a compact menu for float/dock/fullscreen choices. Keep returning to the workspace and resuming the lesson obvious without adding navigation clutter.
- [ ] **R8-LEARN-03 · P2 · Verify: Complete a representative learning path.** Exercise lesson progress, assessment feedback, interruption/resumption, module unlock and course completion states. Check keyboard, mobile, short viewports and saved progress using controlled test accounts.

## Docs and self service help

Baseline UI 6.5 / UX 5.5 / RA 5.5. **Target: at least 8 in all three dimensions.**

An RA reaches a useful answer without encountering deployment instructions first.

- [x] **R8-DOCS-01 · P2 · Improve: Create an RA-first help entry.** Provide a visible quickstart for upload → question → inspect source → reusable review → handoff. Keep installation and self-hosting documentation under the existing technical topics.
- [x] **R8-DOCS-02 · P2 · Improve: Connect help to the current task.** Link relevant in-app help to worked examples for project scope, Library tools, validation, reviews and source failures. Use current labels and screenshots/examples that match the actual workflow.
- [x] **R8-DOCS-03 · P2 · Verify: Check docs usability and accuracy.** Repair mobile navigation, code-region focus and contrast; verify headings, anchors and back-to-app routes. Walk through instructions against the app so the RA guide does not promise absent behavior.

## Team Admin overview

Baseline UI 5.5 / UX 4.5 / RA 6.5. **Target: at least 8 in all three dimensions.**

A team owner can understand adoption and investigate failures on any supported screen.

- [x] **R8-ADMIN-01 · P1 · Fix: Make the administration shell responsive.** Replace the fixed sidebar layout on narrow screens with a labeled switcher or collapsing navigation. Stack metric and chart grids so all values, filters and export controls are reachable without unintended horizontal scrolling.
- [x] **R8-ADMIN-02 · P2 · Improve: Connect usage to useful work.** Explain the existing completion/failure and usage measures in RA terms and link to relevant work where supported. Distinguish missing metrics from zero; do not invent time-saved or successful-submission measures.
- [x] **R8-ADMIN-03 · P2 · Verify: Inspect the team-owner administration tabs.** Exercise Usage, Users and Workflows with realistic populated and empty data, long labels, filters, export and denied access. Check drilldowns and error recovery, not only the landing overview.

## Tuning suggestions

Baseline UI 7 / UX 6.5 / RA 6.5. **Target: at least 8 in all three dimensions.**

A maintainer can decide whether a proposed change is worth applying.

- [x] **R8-TUNE-01 · P2 · Improve: Explain the recommendation and its limits.** Lead with affected item, why it was flagged, measured improvement/regressions and what changes if applied. Keep specialist detail available and ordinary RAs out of unnecessary configuration work.
- [x] **R8-TUNE-02 · P2 · Improve: Make lifecycle states unambiguous.** Present needs review, failed, running, applied, dismissed and no-change states distinctly. Correct contrast and show which configuration is currently live using actual data.
- [x] **R8-TUNE-03 · P2 · Verify: Exercise a populated recommendation lifecycle.** Check comparison, apply, dismissal, failure/retry, restore/revert and permission restrictions. Verify the configured item reflects the accepted action and subsequent history remains understandable.

## Examiner and Shared items

Baseline UI 5.5 / UX 4.5 / RA 6.5. **Target: at least 8 in all three dimensions.**

A reviewer can evaluate a shared item and communicate a useful decision.

- [x] **R8-EXAMINER-01 · P1 · Fix: Make the examiner shell responsive.** Collapse or replace the fixed-width sidebar at narrow widths. Keep the explanatory text, search, queue filters and decision controls readable at 320/390px.
- [x] **R8-EXAMINER-02 · P2 · Improve: Make review readiness easy to scan.** Present task description, author, input/output examples, available validation evidence and requested help clearly. Keep usefulness, measured quality and eligibility for sharing separate judgments.
- [x] **R8-EXAMINER-03 · P2 · Verify: Exercise the populated submission lifecycle.** Cover request detail, claim/release, review notes, send-back, sharing/approval and rejected access with controlled data. Authors must be able to understand and act on the resulting feedback.
- [x] **R8-EXAMINER-04 · P2 · Verify: Review the remaining examiner views.** Inspect Catalog, Coverage and Collections, plus examiner management for an authorized admin. Check populated states, search, empty/error recovery and keyboard/mobile actions; record any newly found work.

## Support staff queue

Baseline UI 7 / UX 7 / RA 6.5. **Target: at least 8 in all three dimensions.**

Support staff can resolve an RA’s problem without losing context.

- [x] **R8-STAFF-01 · P2 · Improve: Make actionable tickets easy to find.** Keep status, priority, requester, assignment and latest activity readable in a populated queue. Search and filters must retain state when opening a conversation and returning.
- [x] **R8-STAFF-02 · P2 · Verify: Exercise ticket work and visibility.** Cover assignment, internal notes versus user-visible replies, attachments, status changes, watcher behavior and failed sends in a controlled non-delivering environment. Preserve drafts and make the intended audience clear.
- [x] **R8-STAFF-03 · P2 · Verify: Check dense and mobile staff workflows.** Inspect long conversations, many tickets, narrow screens and keyboard operation. Verify the What’s Working view and transitions back to triage; avoid grading the empty desktop queue as the full surface.

## Coverage beyond the initial samples

An all-app quality claim includes explicitly reviewed specialist and exceptional states.

- [x] **R8-COVER-01 · P2 · Verify: Complete the route and role inventory.** Map each route and major tab to intended roles, supported devices and a representative task. Include shared/invited viewer entry, notifications, first-run and expired-session paths. Mark disabled or retired features explicitly rather than implying they were tested.
- [x] **R8-COVER-02 · P2 · Verify: Review people and content administration.** Inspect staff/global-admin Teams, Organizations, Knowledge Bases and Certifications tabs, including populated tables, detail/edit paths, errors and mobile layout. Keep permission rules unchanged; record remediation as scoped follow-up items.
- [x] **R8-COVER-03 · P2 · Verify: Review quality and governance administration.** Inspect Quality, Optimizer, Compliance and Audit Log tabs with realistic records. Verify the user can understand what each metric/event establishes, locate the affected item and recover from failed reads or changes.
- [x] **R8-COVER-04 · P2 · Verify: Review configuration and distribution administration.** Inspect API Keys, Catalog and Config tabs, including important edit/confirmation paths and authentication/model configuration presentation. Use controlled fixtures/test resources and avoid production configuration changes during QA.
- [x] **R8-COVER-05 · P2 · Verify: Review conditional and public supporting flows.** When enabled, inspect Demo, Email and Telemetry administration; trial signup/end/feedback/resend pages; and presentation entry/navigation. Distinguish role-specific usefulness from daily RA tasks. Check public links and invitation outcomes without contacting real users.
- [x] **R8-COVER-06 · P2 · Verify: Close findings from newly covered states.** Add newly observed defects with a reproduction, affected surface and acceptance condition. An unreviewed surface or unresolved finding prevents an all-app 8/10 claim even if the original list is finished.

## Final acceptance and regrading

Completion means demonstrated quality on each surface, not a higher average or a checked list.

- [x] **R8-GATE-01 · P1 · Verify: Pass the critical journey suite.** Exercise proposal upload and source checking; file → Library → run → recovery → return; project sharing; extraction evidence/export; human review and workflow resume; automation setup and recorded output. Confirm scope and saved state throughout.
- [x] **R8-GATE-02 · P1 · Verify: Close accessibility and responsive blockers.** No unresolved P1 task blockers, serious/critical automated findings in scoped states, unnamed essential controls or missing keyboard paths. Verify focus, touch, actual enlargement and nested overflow manually as well as automatically.
- [ ] **R8-GATE-03 · P2 · Verify: Check real execution separately from fixtures.** Run representative flows against an isolated backend and controlled accounts, with non-delivering external-service stubs where needed. Record ingestion, persistence, worker/retry behavior, permission enforcement and model-answer spot checks separately from visual evidence.
- [ ] **R8-GATE-04 · P2 · Verify: Validate RA usefulness with representative users.** Use a proposed acceptance study of at least five representative RAs performing five tasks: find a deadline, check a budget requirement, verify an extracted value, run a reusable review, and hand off a result. At least four of five users should complete each task unaided, with no unnoticed wrong-source or unintended-approval error. Record time, errors, evidence checks and handoff usability; this is a formative gate, not a statistical guarantee.
- [ ] **R8-GATE-05 · P2 · Verify: Validate specialist task fit with the right roles.** Observe a team owner investigating a failed run, an integration maintainer repairing a connection, an examiner reviewing a submission and support staff responding to a ticket. Ordinary RAs must also be able to identify when they need these roles and where to request help.
- [x] **R8-GATE-06 · P1 · Verify: Regrade every assessed area independently.** Reassess UI, UX and usefulness with the original rubric after implementation. Each area must reach at least 8/10 in each applicable dimension, with desktop and mobile assessed separately; no averaging away a weak surface. Use the same rubric and explain evidence for every score change.
- [x] **R8-GATE-07 · P2 · Verify: Publish a compact completion record.** Record item status, implementation references, representative evidence, test results, residual limitations and fresh grades. Keep a portable report with selected embedded screenshots; avoid another sprawling collection of duplicate captures. Link backend/user-study results separately and distinguish local completion from deployment.

## Links to the review findings

| Fresh review finding | Main checklist items |
| --- | --- |
| RA-01 Keyboard access | R8-WORKFLOW-01, R8-ACTIVITY-01, R8-BASE-07, R8-BASE-08 |
| RA-02 Mobile Admin and examiner layouts | R8-ADMIN-01, R8-EXAMINER-01, R8-BASE-06 |
| RA-03 Names and contrast | R8-BASE-04, R8-BASE-05, R8-REVIEW-04, R8-DOCS-03 |
| RA-04 Failure visibility | R8-ACTIVITY-02, R8-ACTIVITY-03 |
| RA-05 Navigation labels | R8-NAV-01, R8-NAV-02 |
| RA-06 Project resumption | R8-PROJECT-01, R8-PROJECT-02 |
| RA-07 Automation header | R8-AUTO-01 |
| RA-08 RA help and entry | R8-START-01, R8-START-02, R8-DOCS-01, R8-DOCS-02 |
| RA-09 Validation and tool suitability | R8-VALIDATE-01 through R8-VALIDATE-04, R8-EXPLORE-01 through R8-EXPLORE-04 |
| RA-10 Visual consistency | R8-BASE-02, R8-BASE-03, R8-SUPPORT-02 |

## Completion evidence

Maintain a short dated progress entry with item IDs, what changed, how it was checked and any limitation. Keep the original review as the baseline. New findings require explicit tracking; they must not be silently dismissed to preserve the original item count.

A final grade needs visual inspection and task evidence, including populated and failure states. For surfaces already at 8, preserve the behavior and close the verification gaps. User-study and live-execution work remains open until it actually happens; synthetic screenshots cannot substitute for it.
