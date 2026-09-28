# Vandalizer UX upgrade — implementation progress

September 28, 2026 · [Tracking issue #964](https://github.com/ui-insight/vandalizer/issues/964)

**Implemented locally: 128/169 checklist items. Every reviewed section now has a working UI/UX grade of 8/8; exhaustive acceptance remains open.** These are working grades of reviewed frontend states, not completion certificates. Implementation is checkpointed locally and has not been deployed. Earlier dated entries describe their state at the time of review. All A1–A14 have implementation in this pass; their broader acceptance checks remain part of the unchecked backlog.

The first pass fixes upload scope loss, wizard Enter dismissal, the StrictMode validation lifecycle, mobile overflow and Library row clipping. It adds the approved project search/sort, automation outcome summaries, upload retry/cancel, artifact links, draft confirmation, shorter validation wizard, Sources/Validation views, guided first-task cues, contextual assistant launcher, explicit activation choices, final recap, attached-KB health and structured approvals.

The September 26 recovery pass adds catalog save/adoption feedback, honest optimization metric/provenance labels, deliberate apply/revert with inline retry, and retained partial agent output through stop and retry. Long dialogs and actions are exercised at 320px, tablet and desktop widths.

The follow-up reduces Knowledge/Library mobile density, synchronizes validation summaries, exposes saved expected answers, makes citation previews readable, preserves failed bulk deletions for retry, and serializes automation saves with explicit failure recovery. New journeys exercise source inspection, onboarding, cancellation and keyboard saved views.

The September 28 wizard pass completes WIZ-04/05/06/10/12. It preserves folder settings across trigger switches while submitting only the active configuration, fixes an unsupported default workflow output format, adds required-field guidance, and makes action-picker errors recoverable. Escape closes only the nested picker. Schedule previews hide stale results, recover from failures and handle an empty upcoming-run list honestly. Long selections and final actions fit narrow/short screens, and API examples support keyboard scrolling. Selected controls use consistent accents with checked contrast; mobile checkboxes retain their size.

The September 28 history pass completes VAL-15 for recorded KB runs. All 30 timeline entries are accessible, with question-set changes, scoring mode, model attribution, source, date and run ID readable without hover. Missing scores are labeled unavailable. Open results uses the selected persisted snapshot and keeps exports tied to that UUID. History and export failures have explicit retry; previously loaded rows survive a refresh failure. Saved-run grading details are separate from next-run settings, and the scoring-mode control fits 320px screens. This history pass was followed by the task lifecycle work below.

The September 28 task lifecycle pass completes VAL-12 for supported Sources/Validation/Test questions/History switches. Status follows the requested task instead of inferring completion from a new history row. Queued, running, delayed, retrying, failed and completed states remain visible across tabs. Start requests use a durable ownership/idempotency receipt; reconnect after a lost response reuses the same request and options. Unconfirmed outcomes keep another check disabled, while confirmed failure permits an explicit new check. Workers attach task identity to saved results and skip already-persisted checks on retry; a sparse unique index limits each task to one saved result. Status reads check current KB access and task ownership, return sanitized failure messages, and can recover a saved result after Celery result expiry. Question-list text contrast/size and toolbar wrapping were corrected after browser review.

This backend/worker/frontend change is local only and requires a coordinated release. Server-backed discovery now restores checks and results after reload/reopening; competing windows resume the active task. Dedicated cross-KB navigation now restores the original run without another start. An unconfirmed dispatch stays blocked until status can be confirmed; it is never automatically re-enqueued. Browser results are synthetic and backend tests use mocks; no live Mongo index creation, Redis broker, worker delivery or LLM check was exercised.

## Implementation progress — September 28, validation setup and resumption

**101/169 checklist items implemented locally (VAL-03/05/06/07/08 completed in this pass).** Changes are uncommitted and not deployed.

- Quick checks and tuning previews show full questions, expected answers and source expectations. Preflight explains no-KB comparison versus answer/retrieval grading, missing expected answers, sample limits, grader, approximate duration and available token/cost information without promising improvement.
- Server-backed discovery restores queued checks and completed results after reopening/reload. A per-user/KB active-task index makes competing windows resume one accepted task. Discovery failures keep new submissions locked; recovery retains the task mode and selected question IDs. Unconfirmed dispatch is never automatically re-enqueued.
- Add/edit/delete failures preserve question drafts or selection. Successful additions clear stale filters; partial batch deletion retains the remaining selection. Large sets initially render 50 questions while select-all covers the full filtered set. Imports validate CSV/XLSX and the server's 5 MB limit, preserve the file on failure, expose partial row/source errors and prevent resubmitting a completed import.
- The tuning wizard keeps its title and final action visible while content scrolls. Step labels wrap at word boundaries on narrow screens; imports fit 320px and short viewports.
- Validation: 45 frontend tests across 5 files; 128 lifecycle/knowledge-route backend tests and 56 import/ID backend tests pass. Production build/TypeScript, touched-file ESLint/Ruff pass. 29 recovery/setup and 23 question-management browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. Large-set selection covers 251 questions in the browser and partial deletion covers 2,001 questions in component tests.
- Evidence: `artifacts/visual-review/2026-09-28-resumption-final` and `artifacts/visual-review/2026-09-28-questions-final`. Selected gallery: 300 states / 392 captures. Earlier diagnostics are retained and superseded. Representative screenshots were inspected directly.
- Limits: coordinated frontend/API/worker release required. Browser responses are synthetic; backend tests use mocks. Live Mongo index creation, Redis/broker/worker delivery and model execution remain unverified. Dedicated cross-KB navigation now restores the original run without another start. Broader role/theme/zoom/source/catalog acceptance remains open.

## Automation filtering and recovery — September 28

**128/169 checklist items implemented locally.** AUTO-07 is complete; broader automation acceptance remains open. These changes are not deployed.

- Search trims whitespace and combines with trigger filters. Clearing resets search and type while retaining the current project scope. Counts reflect that scope, filters expose their selected state, and existing M365 items remain filterable even when new M365 creation is disabled.
- Unavailable lists and project pins have an explicit retry rather than a false empty state. Refresh failures preserve loaded rows and filters; the error banner scrolls with the list so retained rows remain reachable on short screens. Earlier list/pin requests and late pin mutations cannot overwrite a newer response or another project's pins.
- Automation cards expose separate open and pin controls, avoiding nested interactive controls.
- Verification: 14 focused list/pin tests across four files, TypeScript, Vite production build and touched-file ESLint pass. The 27 production browser states at 320/768/1440px cover combined filters, empty results, clearing, M365 filtering, list and pin failures/retry, retained rows, project counts and a truly empty list. All have zero axe findings, page overflow, page errors or unmatched fixture requests; representative screenshots were inspected directly.
- Evidence: `2026-09-28-automation-filters-final`; recipe: `frontend/scripts/visual-review/automation-filters.mjs`. The preceding manual-run recovery commit is `fd7ba849`, with 18 focused tests and 21 browser states. AUTO-08/09 stay open for broader lifecycle/history work. All browser APIs and execution are synthetic; live permissions and worker delivery remain unverified.


## Automation manual-run recovery — September 28

Progress toward AUTO-08/09; the broader automation acceptance items remain open. The completed checklist count stays at 127/169.

Document search now distinguishes loading, failure/retry and no results, retains its query on failure, ignores stale responses and supports keyboard selection. Pending/accepted runs lock their document selection and block duplicate starts. Status requests run sequentially; a failed status read explicitly explains that the accepted run may still finish and offers a retry of that same event. Late responses cannot update another automation. Collapsing and reopening Run now preserves its accepted run; previous output remains clearly labeled if a new launch fails.

Verification: 18 focused manual-run/autosave tests, TypeScript, Vite production build and touched-file ESLint pass. The production browser journey covers keyboard document choice, search failure/empty state, start failure, status retry without relaunch, panel close/reopen, failed/completed outcomes and retained output at 320/768/1440px. All 21 captured states have zero axe findings, page overflow, uncaught page errors or unmatched fixture requests. Representative screenshots were inspected directly.

Evidence: `2026-09-28-automation-run-evidence`; recipe: `frontend/scripts/visual-review/automation-run-recovery.mjs`. API responses and execution are synthetic. Accepted-run recovery after leaving the editor/reloading, ambiguous launch failures, full history and live worker/output delivery remain unverified; this pass does not close AUTO-08/09.

## Files and Projects recovery — September 28

**127/169 checklist items implemented locally.** This pass completes FILE-08/09/10 and PROJ-04/06/07/08; it is not deployed.

- Files retain folder location, search, sorting and selection when returning from a document. Failed loads/searches retry; rename/create/move failures preserve their target and draft. Partial moves retry only failed files and refresh the destination. Prior upload and deletion evidence covers processing and partial-delete recovery.
- Projects show readable titles, descriptions, state, role and counts, with search across large lists and incremental display. Creation and detail loading have retry; failed title, description and status edits retain changes. Empty projects explain what belongs there and offer files/chat actions; viewers see read-only details.
- Project entry and exit update file, chat and KB scope together. Late lookups or refreshes cannot restore an old project. Initial team loading no longer clears a newly opened project, and opening Projects outside a project preserves general-work attachments.
- Verification: 50 focused Projects/navigation tests pass. The earlier Files suite passed 37 tests across six files. TypeScript and production build pass; touched Projects files have no lint errors and one existing hook-dependency warning. The restored layout passes 39 Projects and 33 Files browser states at 320/768/1440px, with zero axe findings, page overflow, page errors or unmatched fixture requests. Representative screenshots were inspected directly.
- Evidence: `2026-09-28-projects-restored-layout` and `2026-09-28-files-restored-layout`. The separate file → Library → workflow navigation journey remains selected.
- Limits: browser APIs, execution and permissions are fixtures; live backend/model behavior is not certified. The remaining acceptance checklist stays open.

## Navigation correction — September 28

The user reported that the full-width section layout broke opening a file and running a Library item on it. This was a regression in the earlier visual refresh. Desktop sections now retain the document/section pane beside Assistant and Library, including while a workflow or extraction is open. Compact screens expose explicit pane controls and preserve both the file and tool while switching. Clicking the active Chat navigation item no longer resets the conversation or attachments.

Verification: 22 tests across four layout/navigation/Library files, TypeScript and the production build pass. The production browser journey covers open file → Library → workflow → failed run → retry → output → return at 320, 390, 768, 1024 and 1440px. Both run attempts must submit exactly the opened document UUID. All 30 captured states have zero axe findings, page overflow, page errors or unmatched fixture requests. Representative screenshots were inspected directly. The workflow editor's drag handle now uses its existing keyboard move controls as the accessible alternative, and completion text has readable contrast.

Evidence: `2026-09-28-file-library-evidence`; recipe: `frontend/scripts/visual-review/file-library-workflow.mjs`. API execution and results are synthetic; this establishes the frontend journey and request targeting, not live workflow/model execution. Earlier section grades do not establish cross-pane task coverage. The broader acceptance checklist remains open, with no new items marked complete in this correction.

## Working grades

UI/UX, out of 10. The original rubric is unchanged: 8 is strong, 7 is usable with polish needed. Scores are authored judgments from screenshot inspection and exercised frontend behavior; untested journeys remain explicitly open.

| Area | Baseline UI/UX | Current UI/UX | Evidence |
|---|---:|---:|---|
| File browser | 6/6 | 8/8 | [files-return-from-document-1440](../2026-09-28-files-restored-layout/files-return-from-document-1440.png) |
| Projects | 6.5/6.5 | 8/8 | [projects-empty-detail-768](../2026-09-28-projects-restored-layout/projects-empty-detail-768.png) |
| Automations screen and editor | 6/6 | 8/8 | [automation-save-failed](../upgrade-polish-final-journeys/automation-save-failed.png) |
| Automation creation wizard | 7.5/5.5 | 8/8 | [wizard-schedule-review-320](../2026-09-28-wizard-mobile-final/wizard-schedule-review-320.png) |
| Knowledge bases | 6/5.5 | 8/8 | [knowledge-sources-mobile](../upgrade-followup-responsive/knowledge-sources-mobile.png) |
| KB validation system | 6.5/6.5 | 8/8 | [validation-history-run-card-320](../2026-09-28-history-verified/validation-history-run-card-320.png) |
| Explore / shared catalog | 7/6.5 | 8/8 | [catalog-save-success](../2026-09-26-recovery-verified/catalog-save-success.png) |
| Library | 5.5/5.5 | 8/8 | [library-320](../upgrade-followup-responsive/library-320.png) |
| Chat workspace | 6.5/6 | 8/8 | [chat-home](../upgrade-polish-final-context/chat-home.png) |
| Basic chat onboarding | 7/6.5 | 8/8 | [onboarding-evidence-checked-mobile](../upgrade-polish-final-journeys/onboarding-evidence-checked-mobile.png) |
| Chat uploads | 6/3 | 8/8 | [chat-upload-error](../upgrade-final/chat-upload-error.png) |
| Chat knowledge-base interactions | 7/7 | 8/8 | [chat-citation-preview-mobile](../upgrade-polish-final-journeys/chat-citation-preview-mobile.png) |
| Agentic chat UI | 7/6.5 | 8/8 | [agent-partial-completion-mobile](../2026-09-26-recovery-verified/agent-partial-completion-mobile.png) |

**Mobile working grade: 8/10, up from 3/10.** The reviewed layouts, Library filtering, source inspection, onboarding, approvals and validation drilldowns now meet the strong/usably polished bar. This is a judgment of the exercised frontend states, not coverage of every mobile subflow. All section working grades now reach 8. The unchecked acceptance backlog remains open; these grades do not imply every workflow has been verified.

## Verification

- Production build and TypeScript: pass. Existing bundle-size and mixed static/dynamic import warnings remain.
- Latest lifecycle tests: 32 frontend tests across 4 files and 207 backend tests across 5 files pass. Backend tests report HTTPX cookie deprecations and an AsyncMock coroutine warning. Production build/TypeScript, changed-file ESLint/Ruff and diff checks pass. 26 final browser states at 320/768/1440px have zero axe findings, page overflow, page errors or unmatched requests.
- Latest history tests: 19 pass across 5 files. Production build/TypeScript and touched-file ESLint pass; 18 final browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. The oldest run opens by keyboard and exports CSV/Excel/JSON with its exact UUID without starting a validation.
- Latest wizard tests: 12 pass across 3 files. Touched-file ESLint has no findings; TypeScript and production build pass. The 53 new wizard/API states have 72 captures across the main, API, and final mobile runs. Failed diagnostic runs are preserved and excluded from the selected gallery.
- September 26 focused frontend tests: 55 pass across 11 files, covering catalog saves, interrupted streams/retry, apply review, score semantics, citations and existing catalog/trust/progress behavior. Prior 56-test autosave/validation/UI and 32-test upload/wizard passes remain recorded separately; counts overlap and are not cumulative.
- Knowledge backend: 131 tests pass, including score metric/provenance regressions and existing knowledge/optimization routes. Composite quality is no longer subtracted from raw AI-only answer accuracy; scoring and execution are unchanged.
- Broader frontend run before the final copy/layout refinements: 961 passed, 3 failed. All three are landing-page signup tests. The same three failures reproduce in an isolated archive of the unchanged baseline HEAD (1 passed / 3 failed), so they are pre-existing.
- Automation backend tests: 58 pass, including persisted latest-event resolution, authorized-ID query scoping, API serialization, and existing automation routes. These use mocks; no live database or automation runs were used.
- Changed TypeScript files: ESLint has zero errors and eight existing hook-dependency warnings in the expanded changed-file set. `git diff --check` passes.
- Final evidence: 642 distinct states / 734 capture executions across the recorded production passes. Later targeted captures supersede the same IDs from earlier passes. Manifests retain each source/fixture fingerprint; later targeted checks supersede the same state from earlier builds. The latest context pass also verifies the upload-ready contrast fix.
- No unmatched API requests or uncaught page errors in the included runs. No page-level horizontal overflow in selected captures. Zero axe violations in the latest selected evidence for every state (earlier failing captures are retained, not deleted).
- All six main screens were captured at 320, 390, 768, 1280 and 1440px. The mobile validation final action was scrolled into view and captured. The automation editor was opened and closed on mobile.
- Upload → next request and Enter → exactly one wizard step are failing assertions. Agent completion checks require an artifact link and removal of actionable approval; a later failed turn must not retain the old completed plan.
- The validation completion regression also passed on the development server with StrictMode enabled in `upgrade-validation-refined`.

## Coverage labels and limitations

**Visually inspected:** representative before/after screens, mobile layouts, final wizard review, source health, approval cards and editor actions. All captured states have snapshots and axe output, but a screenshot's presence does not mean every hidden or scrolled interaction was manually inspected.

**Frontend interaction tested, with fixtures:** selection/upload scope, upload retry, wizard keyboard progression, validation setup/results/history/drilldowns, summary refresh across tab changes, automation save failure/retry, partial bulk deletion/retry, agent approval/cancellation, first-session upload-to-evidence, valid citation previews, catalog save/adoption and already-saved behavior, optimizer apply/error/retry/revert, interrupted streams and partial-artifact retry, long details at 320/768/1440px, project no-results recovery, contextual assistant open/close, mobile saved-view keyboard selection and narrow dialogs. Scores, source lists and chat/tool output are synthetic. The follow-up fixture returns the persisted answer-accuracy/baseline/lift contract after validation. Browser and component assertions confirm that the parent summary refetches without leaving Validation. Scores remain synthetic.

**Unit/API tested, with mocks:** transfer abort and late-response suppression; partial upload recovery; wizard saved-draft retry; event-history aggregation and route serialization.

**Live integration verified:** none. No real model, retrieval, upload ingestion, source refresh, optimizer apply/revert or autonomous tool execution was run. Citation fixtures do not establish grounding quality. Alternate roles, white-label colors, 200% zoom, large data sets, cross-browser behavior M365 setup, live API authentication and actual scheduled execution remain open.

## Sources and uploads

**112/169 checklist items implemented locally (FILE-03, KB-08/09/10, UP-04–08, QA-05/06 completed in this pass).** Changes are uncommitted and not deployed.

- Source rows identify type, readiness and recorded freshness. Refresh, reprocess, rename, inspect and remove preserve errors for retry, block duplicate requests and update only the intended KB. Late responses cannot reopen or overwrite a different KB. Viewers receive read-only provenance.
- Source intake preserves selected documents, folders, URLs and crawl settings on failure. Mixed processing outcomes and duplicate URLs have accurate feedback. Narrow dialogs keep titles and final actions visible. Backend document registration validates the entire selection before inserting sources, preventing a missing later document from leaving earlier sources undispatched.
- Files, chat and document pickers read the same server upload policy. Unsupported and oversized files fail independently; successful siblings and message drafts survive. Transfer blocks sending, processing explains the queued question, and cancellation/removal suppress delayed reattachment. Picker and drop paths are exercised.
- Validation scope switching now has dedicated browser assertions: leaving one running KB for another and returning restores the original task and question subset without starting another check.
- Validation: 72 source/upload frontend tests across 10 files, followed by 30 intake tests across 3 files (overlapping suites, not additive); 28 file-route backend tests and 109 registration/knowledge-route tests pass. Production build/TypeScript and touched-file Ruff pass; lint has no errors and one existing ChatPanel dependency warning. Backend output includes HTTPX cookie deprecations.
- Evidence: `2026-09-28-sources-release` (35), `2026-09-28-uploads-evidence` (28), `2026-09-28-validation-scope` (6), and `2026-09-28-source-intake-final` (24): 93 additional production captures at 320/768/1440px, zero axe findings, page overflow, page errors or unmatched requests. Representative screenshots inspected directly. Selected gallery: 393 states / 485 captures.
- Limits: browser APIs are synthetic and backend tests use mocks. Live upload/indexing, source retrieval, Mongo/Redis/worker behavior and model execution remain unverified. Catalog, broader roles/themes/zoom and the unchecked acceptance backlog remain open.

## Implementation progress — September 28, catalog filters and evidence

**114/169 checklist items implemented locally (EXP-06/07 completed in this pass).** Changes are uncommitted and not deployed.

- Both catalog surfaces combine search, kind, quality and sorting predictably. Clearing restores the full population (the KB catalog retains its KB scope). Failed queries show unavailable results instead of a false empty result. Collections have their own retry.
- Older requests cannot overwrite newer filters; pending pagination cannot append to a different query. Duplicate pagination is blocked. Failed pagination preserves current results and retries the same offset.
- Details show rating origin, sample count, validation date, recorded runs and relevant limitations. Missing quality is distinct from a measured zero; author-provided ratings and pending regressions remain explicit. Cards show recorded validation dates, quality labels wrap, and collection counts respect visible items.
- Validation: 26 frontend tests across 4 files, production build/TypeScript and touched-file ESLint pass. 36 filter/recovery and 12 quality-evidence production browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. Representative screenshots inspected directly.
- Evidence: `2026-09-28-catalog-filters-evidence` and `2026-09-28-catalog-evidence-review`. Selected gallery: 441 states / 533 captures. Earlier blocked locator diagnostics are retained and excluded.
- Limits: browser APIs use fixtures. Broader catalog permission/scope variants and item input/output descriptions remain open; recorded quality does not establish performance on the user's own material.

## Implementation progress — September 28, chat reading and source navigation

**120/169 checklist items implemented locally (CHAT-06/07/09 and CKB-04/05/06 completed in this pass).** Changes are uncommitted and not deployed.

- Drafts survive Assistant/Library/Files switches. Multi-KB plus document attachments, detachment, replacement from the KB list and deliberate new conversations submit the expected identifiers. The KB picker retries failed loading without discarding search/selection; New chat is keyboard-accessible.
- Incoming response content preserves a reader's position. Return to latest runs after layout and respects reduced motion. Long responses, lists, links, tables and code fit narrow views; tables/code have keyboard scroll targets. The composer wraps memory/export/send controls. Copy failures report an error, and IME confirmation Enter does not send prematurely.
- Citation menus support keyboard movement and preserve estimated page labels. Opening a cited document preserves attachment scope and restores the conversation position on return (within 8px for menu/layout changes). URL citations open the exact intended URL in a separate tab. Unlinked citations identify missing originals and a recovery route.
- Missing, inaccessible, failed and unavailable source previews have distinct recovery. Extraction retry retains its error, prevents duplicate submission and stops polling/applying results after a document switch. Retry controls use readable contrast; saved citation text is identified as potentially older than the original.
- Validation: 54 frontend tests across 9 files pass, including late extraction acceptance after navigation. Production build/TypeScript pass. Touched-file lint has zero errors and four existing hook-dependency warnings. 33 reading/source and 18 scope browser states at 320/768/1440px have zero axe findings, page overflow, page errors or unmatched requests. Screenshots inspected directly; earlier clipping and contrast failures are retained and superseded.
- Evidence: `2026-09-28-chat-navigation-evidence` and `2026-09-28-chat-scope-final`. Selected gallery: 492 states / 584 captures.
- Limits: browser APIs, external URL content and streamed responses are synthetic. No real model, retrieval, document processing, file access permissions or clipboard integration was certified. Broader model-selection, assistive-technology, role/theme/zoom and remaining acceptance items stay open.

## Remaining acceptance work

1. Exercise validation with a live worker/broker; reload, reopen, cross-KB and competing-window fixture checks pass. Catalog filter combinations now pass; alternate role/scope variants remain open.
2. Extend agent failure protocols; source repair/intake, citation document/URL navigation and scope fixture checks pass.
3. Extend automation run failure and scope-switching recovery. A failed save after navigating away still needs a persistent draft recovery policy; in-editor retry and close-before-save are covered.
4. Cover long content, larger lists, restricted roles, full keyboard focus journeys and 200% zoom. Regrade each section and mobile independently.

## Evidence manifests

- [upgrade-final](../upgrade-final/manifest.json): 54 states; source `dd97377f8d68b289a4bfa6fc142134425cc1bd303662f11e2ea1531a47ad3c01`; fixture `3a45c0b61f02d9cda2c100cd955c6fe741fe7ae9512c271b95b051c4b12a266a`; production; Chromium 148.0.7778.96.
- [upgrade-final-responsive](../upgrade-final-responsive/manifest.json): 42 states; source `dd97377f8d68b289a4bfa6fc142134425cc1bd303662f11e2ea1531a47ad3c01`; fixture `3a45c0b61f02d9cda2c100cd955c6fe741fe7ae9512c271b95b051c4b12a266a`; production; Chromium 148.0.7778.96.
- [upgrade-final-recheck](../upgrade-final-recheck/manifest.json): 5 states; source `304d137cccd76f6956e0ca368c694dce7adc6ca79e8fd432a9f11f7782875bf3`; fixture `3a45c0b61f02d9cda2c100cd955c6fe741fe7ae9512c271b95b051c4b12a266a`; production; Chromium 148.0.7778.96.
- [upgrade-final-detail-recheck](../upgrade-final-detail-recheck/manifest.json): 4 states; source `06167a9590da5eb885507e212eefdd88b64fbea43556cb92205022c7ec9f2485`; fixture `3a45c0b61f02d9cda2c100cd955c6fe741fe7ae9512c271b95b051c4b12a266a`; production; Chromium 148.0.7778.96.
- [upgrade-followup-detail](../upgrade-followup-detail/manifest.json): 10 states; source `98bde3d6bdbad939babaa660a75d5c470ce390fa4fa99a18f878d64743bf36e3`; fixture `53a27c54064cbf13704959896ae49be19fcb9d0c27a2ccc72592e5eedf043b8e`; production; Chromium 148.0.7778.96.
- [upgrade-followup-responsive](../upgrade-followup-responsive/manifest.json): 42 states; source `98bde3d6bdbad939babaa660a75d5c470ce390fa4fa99a18f878d64743bf36e3`; fixture `53a27c54064cbf13704959896ae49be19fcb9d0c27a2ccc72592e5eedf043b8e`; production; Chromium 148.0.7778.96.
- [upgrade-polish-final-journeys](../upgrade-polish-final-journeys/manifest.json): 20 states; source `9ab263840ad82724fa144c3beb66a8c16db8cd3a43f2530f5b61b6c75eb7c4ee`; fixture `53a27c54064cbf13704959896ae49be19fcb9d0c27a2ccc72592e5eedf043b8e`; production; Chromium 148.0.7778.96.
- [upgrade-polish-final-context](../upgrade-polish-final-context/manifest.json): 9 states; source `9ab263840ad82724fa144c3beb66a8c16db8cd3a43f2530f5b61b6c75eb7c4ee`; fixture `53a27c54064cbf13704959896ae49be19fcb9d0c27a2ccc72592e5eedf043b8e`; production; Chromium 148.0.7778.96.
- [upgrade-folder-recheck](../upgrade-folder-recheck/manifest.json): 4 states; source `5e854ebdf031d0fa2e1424949bf71dbd7f7248f0bbb2df85c6ac242700c46d5f`; fixture `53a27c54064cbf13704959896ae49be19fcb9d0c27a2ccc72592e5eedf043b8e`; production; Chromium 148.0.7778.96.
- [2026-09-26-recovery-verified](../2026-09-26-recovery-verified/manifest.json): 19 states; source `3c00786581d88931b877b28c65d41aa2ad4a92e611fc8ee309eb15dec9b4ffa3`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-26-recovery-layout-verified](../2026-09-26-recovery-layout-verified/manifest.json): 15 states; source `3c00786581d88931b877b28c65d41aa2ad4a92e611fc8ee309eb15dec9b4ffa3`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-flow-verified](../2026-09-28-wizard-flow-verified/manifest.json): 47 states; source `9a42756239009c55d3d59e059e33d4452ea55e2b696f57b228f7e5f5f63a37cb`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-api-verified](../2026-09-28-wizard-api-verified/manifest.json): 6 states; source `9a42756239009c55d3d59e059e33d4452ea55e2b696f57b228f7e5f5f63a37cb`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-28-wizard-mobile-final](../2026-09-28-wizard-mobile-final/manifest.json): 19 states; source `be4c40d793ccabbd831e13cb533f6604ab2bd16d99be7ecb6af993c30bf83f8e`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-28-history-verified](../2026-09-28-history-verified/manifest.json): 18 states; source `691246b33adf6c00811fd024a89c91da63d67b31246959928584a5c31fbcddc5`; fixture `ed5abe7b3f06435d0f7d6602d79e060d65e438a66c60bed518f12a8535b1c4a8`; production; Chromium 148.0.7778.96.
- [2026-09-28-lifecycle-evidence](../2026-09-28-lifecycle-evidence/manifest.json): 26 states; source `ccf31953e99a4257dc277b95973ba60f96cc790737fceafa1f99ab63eb91aaee`; fixture `3e79b1ab5c6ea0d06d8fd8bb450835f9f31ad843e64b385477cb677a9ee9ae58`; production; Chromium 148.0.7778.96.
- [2026-09-28-resumption-final](../2026-09-28-resumption-final/manifest.json): 29 states; source `1dc1511f27c2bca121dfed5144eb2e17ac867e58dc332d1d9c3ec7a43e13d6a3`; fixture `649209ffd0f792f0117eb1792d0a879d1de1ea0f691cd4e02aa7ba84fae2db2d`; production; Chromium 148.0.7778.96.
- [2026-09-28-questions-final](../2026-09-28-questions-final/manifest.json): 23 states; source `33696a54bf11c43a13127b84baf221dc9a32d93814e4e2be63242ae42909def9`; fixture `649209ffd0f792f0117eb1792d0a879d1de1ea0f691cd4e02aa7ba84fae2db2d`; production; Chromium 148.0.7778.96.
- [2026-09-28-sources-release](../2026-09-28-sources-release/manifest.json): 35 states; source `88784712f6ca5613e5562b741d603851dc533f0b440311c29b60091689662f1a`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-uploads-evidence](../2026-09-28-uploads-evidence/manifest.json): 28 states; source `88784712f6ca5613e5562b741d603851dc533f0b440311c29b60091689662f1a`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-validation-scope](../2026-09-28-validation-scope/manifest.json): 6 states; source `47b6255d507987555499ba43f1d4cef662cbba5543c71204b43a8691322c1eb4`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-source-intake-final](../2026-09-28-source-intake-final/manifest.json): 24 states; source `ccdd847c12e77c2248899f2defdd46ee0c52975de787607c134680e5d422f3dd`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-catalog-filters-evidence](../2026-09-28-catalog-filters-evidence/manifest.json): 36 states; source `221c0fac50789b334450a39bcea7b5c927200af55a4c1bb7b55a72054ede2e75`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-catalog-evidence-review](../2026-09-28-catalog-evidence-review/manifest.json): 12 states; source `0f510ea9363a67e62430ce5ca6a56a95ab94f8229599477faf8808d423d85304`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-chat-navigation-evidence](../2026-09-28-chat-navigation-evidence/manifest.json): 33 states; source `ca314d9152a391559bf3638c5b66be73042bfc5668971015eccf25da196dc867`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-chat-scope-final](../2026-09-28-chat-scope-final/manifest.json): 18 states; source `71171ed99d62616b58ffef0ead6ea65ea60b1dbdd8432d941609f4af478a1a9d`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-file-library-evidence](../2026-09-28-file-library-evidence/manifest.json): 30 states; source `7a42314934b1b90e86fb59a116253f54e851ec074509436c370b165d0c41368b`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-projects-restored-layout](../2026-09-28-projects-restored-layout/manifest.json): 39 states; source `dbfff5c474499b27dd914e221843a04bfb912042947b4511c356b97e4387ed92`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-files-restored-layout](../2026-09-28-files-restored-layout/manifest.json): 33 states; source `449342649e3042a4729bded577766c57e4f4a6e01a6384e91bd6517e0655e7cd`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-run-evidence](../2026-09-28-automation-run-evidence/manifest.json): 21 states; source `23a01df2593e624f9ae9f8090d4774ed49d1df4a57c2a7ff0e56ae726e980f09`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.
- [2026-09-28-automation-filters-final](../2026-09-28-automation-filters-final/manifest.json): 27 states; source `6a74bcfc7d73502fb4a87f5ea0d58d2adb635911a72590d9d899cbe6ea106ee0`; fixture `9a5aac13801517e9ff72b27abb599e50599e903c7783bb15a5361837290197af`; production; Chromium 148.0.7778.96.

## Section notes

**File browser:** Returning from a document preserves folder, search, sorting and selection. Load/search, rename/create/move and partial-delete failures have actionable retry; partial moves retry only failed files and refresh destination contents. Verified with the restored desktop source and Library panes.

**Projects:** Large lists, long titles, roles and counts remain readable. Creation, detail loading and edits recover without losing drafts. Empty/read-only details explain the next action. Scope transitions and stale-response guards pass fixture and component checks; live permissions remain unverified.

**Automations screen and editor:** The editor has its own canvas and explicit autosave state. Serialized saves preserve quick edits, failures keep edits for retry, and unsaved configuration cannot run. Combined search/type filters, clearing within project scope, list/pin retries and retained rows pass. Manual-run status retry checks the accepted event without relaunching; prior output survives a failed new start. Recovery after leaving the editor and broader history remain open.

**Automation creation wizard:** The reviewed folder/API/schedule wizard checklist is complete: required-field guidance, retained trigger drafts, readable picker selections and retry, current schedule previews, nested Escape isolation, consistent controls and short-screen review. API examples are keyboard-scrollable. M365, real credentials and actual execution remain unverified.

**Knowledge bases:** Sources/Validation precede source controls. Tags and technical metadata are behind Manage; web refresh settings collapse. Source health and measured quality remain distinct.

**KB validation system:** Saved history shows comparable question sets, scoring mode, grader and answer model, keeps all 30 rows accessible, and opens/exports the intended saved result. History/export errors are retryable. Manual apply/revert now retains errors in the review, resets acknowledgment, refreshes the summary and fits short screens. Composite quality, AI-only accuracy and proposed/applied/reverted settings are distinct. Task-correlated status and recovery are verified across supported tabs; reload and competing-window resumption now pass fixture checks; cross-KB restoration passes fixture checks; live worker behavior remains unverified.

**Explore / shared catalog:** Destination, checking, failure/retry, saved and already-saved states lead to an Open action. KB adoption preserves errors and browsing context; long details remain usable at 320px, tablet and desktop widths. Combined filters, clearing, empty/error states and pagination recovery pass. Rating origin, date, samples and limitations are explicit. Scope/role variants remain open.

**Library:** Mobile type and sort controls share one row. Saved views are keyboard buttons, show the selected view, close after selection and explain favorites, pins, folders and project scope. Broader folder operations remain open.

**Chat workspace:** A compact task launcher and shorter composer establish a clear primary action. Stopped/interrupted responses preserve partial output, and retry retains completed artifacts. Long response/table/code reading, retained scroll position, latest-response navigation, draft retention and narrow composer controls pass fixture checks. Model-selection and broader assistive-technology journeys remain open.

**Basic chat onboarding:** A mobile first session now exercises upload → scoped question → source preview. One progress guide stays visible, with concise contextual guidance. Full guided-tour coexistence remains open.

**Chat uploads:** Successful siblings survive failures, transfer retry/cancel are explicit, and scope preservation is asserted. Live ingestion and all supported intake paths remain unverified.

**Chat knowledge-base interactions:** Readable citation chips open a passage preview beside the answer; the submitted KB UUID is asserted. Missing/inaccessible/failed source recovery, full document/URL navigation, return position and multi-KB/document scope combinations pass fixture checks. Live retrieval and permissions remain unverified.

**Agentic chat UI:** Approvals and artifact shortcuts are clear. Stopped or interrupted tool calls show completion not confirmed, ended plans stop spinning, and retries retain prior work. Live execution, all protocol failures and broader assistive-technology journeys remain open.
