# UX upgrade implementation progress

Tracking issue: [#964](https://github.com/ui-insight/vandalizer/issues/964).

**120/169 items are implemented locally**, including VAL-12 in the September 28 task lifecycle pass, VAL-15 in the history pass and WIZ-04/05/06/10/12 in the wizard pass. This implementation is included in the local checkpoint commit; it is not deployed. Every reviewed section now has a working **8/8 UI/UX grade**, with reviewed mobile states at **8/10**. The unchecked acceptance backlog remains open; grades cover exercised frontend states.

- [Before/after gallery and working grades](../artifacts/visual-review/upgrade-review/index.html)
- [Full report and evidence limits](../artifacts/visual-review/upgrade-review/report.md)
- [Machine-readable results and provenance](../artifacts/visual-review/upgrade-review/review-summary.json)
- [Remaining checklist](ui-ux-upgrade-checklist.md)

## Local checkpoint — September 28

The first checkpoint records the implementation, regression tests, browser review scripts and progress documentation accumulated for #964. Earlier entries below describe the uncommitted state at the time of those reviews. This is a partial implementation checkpoint, not completion of the issue or a deployment.

The latest Files recovery changes are included: failed folder loads and content searches retry; rename/create/move errors preserve drafts and targets; partial moves retry only failed files; revisiting moved-to folders refreshes their cached contents; returning from a document preserves list search, sort and selection. The focused run passed 37 tests across six files, and the production build passed. The 33-state Files browser run completed, but its final visual review and checklist update remain pending.

Checkpoint verification: 190 frontend tests across 32 changed test files and 216 backend tests across seven selected regression files pass. TypeScript and the production build pass. Backend deprecation warnings and existing Vite chunk/dynamic-import warnings remain. These checks do not certify live infrastructure.

The unfinished follow-up edits in `ProjectsPanel.tsx` and `useProjects.ts` remain outside this checkpoint. Generated screenshots and diagnostics remain local in `artifacts/visual-review/`; the review recipes and report sources are committed separately from generated media. No changes have been pushed or deployed by this checkpoint.

## Implementation progress — September 28, chat reading and source navigation

**120/169 checklist items implemented locally (CHAT-06/07/09 and CKB-04/05/06 completed in this pass).** Changes are uncommitted and not deployed.

- Drafts survive Assistant/Library/Files switches. Multi-KB plus document attachments, detachment, replacement from the KB list and deliberate new conversations submit the expected identifiers. The KB picker retries failed loading without discarding search/selection; New chat is keyboard-accessible.
- Incoming response content preserves a reader's position. Return to latest runs after layout and respects reduced motion. Long responses, lists, links, tables and code fit narrow views; tables/code have keyboard scroll targets. The composer wraps memory/export/send controls. Copy failures report an error, and IME confirmation Enter does not send prematurely.
- Citation menus support keyboard movement and preserve estimated page labels. Opening a cited document preserves attachment scope and restores the conversation position on return (within 8px for menu/layout changes). URL citations open the exact intended URL in a separate tab. Unlinked citations identify missing originals and a recovery route.
- Missing, inaccessible, failed and unavailable source previews have distinct recovery. Extraction retry retains its error, prevents duplicate submission and stops polling/applying results after a document switch. Retry controls use readable contrast; saved citation text is identified as potentially older than the original.
- Validation: 54 frontend tests across 9 files pass, including late extraction acceptance after navigation. Production build/TypeScript pass. Touched-file lint has zero errors and four existing hook-dependency warnings. 33 reading/source and 18 scope browser states at 320/768/1440px have zero axe findings, page overflow, page errors or unmatched requests. Screenshots inspected directly; earlier clipping and contrast failures are retained and superseded.
- Evidence: `2026-09-28-chat-navigation-evidence` and `2026-09-28-chat-scope-final`. Selected gallery: 492 states / 584 captures.
- Limits: browser APIs, external URL content and streamed responses are synthetic. No real model, retrieval, document processing, file access permissions or clipboard integration was certified. Broader model-selection, assistive-technology, role/theme/zoom and remaining acceptance items stay open.

## Implementation progress — September 28, catalog filters and evidence

**114/169 checklist items implemented locally (EXP-06/07 completed in this pass).** Changes are uncommitted and not deployed.

- Both catalog surfaces combine search, kind, quality and sorting predictably. Clearing restores the full population (the KB catalog retains its KB scope). Failed queries show unavailable results instead of a false empty result. Collections have their own retry.
- Older requests cannot overwrite newer filters; pending pagination cannot append to a different query. Duplicate pagination is blocked. Failed pagination preserves current results and retries the same offset.
- Details show rating origin, sample count, validation date, recorded runs and relevant limitations. Missing quality is distinct from a measured zero; author-provided ratings and pending regressions remain explicit. Cards show recorded validation dates, quality labels wrap, and collection counts respect visible items.
- Validation: 26 frontend tests across 4 files, production build/TypeScript and touched-file ESLint pass. 36 filter/recovery and 12 quality-evidence production browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. Representative screenshots inspected directly.
- Evidence: `2026-09-28-catalog-filters-evidence` and `2026-09-28-catalog-evidence-review`. Selected gallery: 441 states / 533 captures. Earlier blocked locator diagnostics are retained and excluded.
- Limits: browser APIs use fixtures. Broader catalog permission/scope variants and item input/output descriptions remain open; recorded quality does not establish performance on the user's own material.

## Implementation progress — September 28, sources and uploads

**112/169 checklist items implemented locally (FILE-03, KB-08/09/10, UP-04–08, QA-05/06 completed in this pass).** Changes are uncommitted and not deployed.

- Source rows identify type, readiness and recorded freshness. Refresh, reprocess, rename, inspect and remove preserve errors for retry, block duplicate requests and update only the intended KB. Late responses cannot reopen or overwrite a different KB. Viewers receive read-only provenance.
- Source intake preserves selected documents, folders, URLs and crawl settings on failure. Mixed processing outcomes and duplicate URLs have accurate feedback. Narrow dialogs keep titles and final actions visible. Backend document registration validates the entire selection before inserting sources, preventing a missing later document from leaving earlier sources undispatched.
- Files, chat and document pickers read the same server upload policy. Unsupported and oversized files fail independently; successful siblings and message drafts survive. Transfer blocks sending, processing explains the queued question, and cancellation/removal suppress delayed reattachment. Picker and drop paths are exercised.
- Validation scope switching now has dedicated browser assertions: leaving one running KB for another and returning restores the original task and question subset without starting another check.
- Validation: 72 source/upload frontend tests across 10 files, followed by 30 intake tests across 3 files (overlapping suites, not additive); 28 file-route backend tests and 109 registration/knowledge-route tests pass. Production build/TypeScript and touched-file Ruff pass; lint has no errors and one existing ChatPanel dependency warning. Backend output includes HTTPX cookie deprecations.
- Evidence: `2026-09-28-sources-release` (35), `2026-09-28-uploads-evidence` (28), `2026-09-28-validation-scope` (6), and `2026-09-28-source-intake-final` (24): 93 additional production captures at 320/768/1440px, zero axe findings, page overflow, page errors or unmatched requests. Representative screenshots inspected directly. Selected gallery: 393 states / 485 captures.
- Limits: browser APIs are synthetic and backend tests use mocks. Live upload/indexing, source retrieval, Mongo/Redis/worker behavior and model execution remain unverified. Catalog, broader roles/themes/zoom and the unchecked acceptance backlog remain open.

## Validation setup and resumption

**101/169 checklist items implemented locally (VAL-03/05/06/07/08 completed in this pass).** Changes are uncommitted and not deployed.

- Quick checks and tuning previews show full questions, expected answers and source expectations. Preflight explains no-KB comparison versus answer/retrieval grading, missing expected answers, sample limits, grader, approximate duration and available token/cost information without promising improvement.
- Server-backed discovery restores queued checks and completed results after reopening/reload. A per-user/KB active-task index makes competing windows resume one accepted task. Discovery failures keep new submissions locked; recovery retains the task mode and selected question IDs. Unconfirmed dispatch is never automatically re-enqueued.
- Add/edit/delete failures preserve question drafts or selection. Successful additions clear stale filters; partial batch deletion retains the remaining selection. Large sets initially render 50 questions while select-all covers the full filtered set. Imports validate CSV/XLSX and the server's 5 MB limit, preserve the file on failure, expose partial row/source errors and prevent resubmitting a completed import.
- The tuning wizard keeps its title and final action visible while content scrolls. Step labels wrap at word boundaries on narrow screens; imports fit 320px and short viewports.
- Validation: 45 frontend tests across 5 files; 128 lifecycle/knowledge-route backend tests and 56 import/ID backend tests pass. Production build/TypeScript, touched-file ESLint/Ruff pass. 29 recovery/setup and 23 question-management browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. Large-set selection covers 251 questions in the browser and partial deletion covers 2,001 questions in component tests.
- Evidence: `artifacts/visual-review/2026-09-28-resumption-final` and `artifacts/visual-review/2026-09-28-questions-final`. Selected gallery: 300 states / 392 captures. Earlier diagnostics are retained and superseded. Representative screenshots were inspected directly.
- Limits: coordinated frontend/API/worker release required. Browser responses are synthetic; backend tests use mocks. Live Mongo index creation, Redis/broker/worker delivery and model execution remain unverified. Cross-KB navigation now passes the dedicated source/upload review. Broader role/theme/zoom/source/catalog acceptance remains open.

The task lifecycle pass correlates the requested task to its saved result. Queued/running/delayed/retrying/failed/completed states survive supported tab switches; a lost response or status outage can reconnect without duplicating the start. Unconfirmed outcomes retain the run lock, while a confirmed failure permits a deliberate new check. Durable receipts enforce ownership and request identity; a sparse unique result index limits each task to one saved result. Status remains available for persisted results after Celery result expiry. Question-list text contrast and wrapping were improved after visual QA.

The setup/resumption pass adds server-owned recovery after reload/reopening and competing-window task reuse. Cross-KB navigation now passes the dedicated source/upload review. The frontend/API/worker changes require a coordinated release. An uncertain dispatch is not automatically re-enqueued. No live Mongo index creation, Redis/worker delivery, or model execution was verified.

The history pass exposes all 30 saved runs, readable comparison details, missing-score labels, and exact saved-result reopening. History and export errors are retryable; loaded rows survive refresh failure. Saved grader/mode labels are separated from next-check settings, and narrow controls fit.

The wizard pass adds required-field guidance and consistent selection styles, preserves trigger drafts, makes picker failures retryable, isolates nested Escape, and fixes the default workflow output format. Schedule previews no longer show stale results and offer retry. Long action names, final controls, and code examples are usable at narrow widths; API examples support keyboard scrolling. The folder/API/schedule wizard checklist is complete for the reviewed configuration. M365 setup and live execution remain unverified.

The September 26 recovery pass clarifies catalog save destinations, errors, already-saved state and useful next actions. KB adoption preserves errors and browsing context. Long details and apply controls remain reachable at 320px, tablet and desktop widths. Validation apply/revert refreshes its summary and requires fresh regression acknowledgment; composite quality is clearly separated from answer accuracy and from application state. Stopped or interrupted chat preserves unfinished calls and completed artifacts, including through retry.

Selected evidence contains **492 distinct states / 584 production captures**, including **26 final lifecycle captures**, **18 final history captures** and **72 wizard/API captures covering 53 states**. The latest selected capture for every state has zero axe findings, page errors, unmatched API requests or page-level overflow. Representative screenshots were inspected directly. Earlier blocked and contrast-failing captures are preserved.

Latest lifecycle tests: **32 frontend tests across 4 files; 207 backend tests across 5 files pass**. Backend test output includes HTTPX cookie deprecations and an AsyncMock coroutine warning. Production build/TypeScript, changed-file ESLint/Ruff and diff checks pass. Final evidence is `2026-09-28-lifecycle-evidence`; earlier locator/contrast diagnostics and the capture with inconsistent fixture summary are superseded. Assertions cover exact task identity, unchanged request/options after a lost start response, no duplicate start on status reconnect, and deliberate restart after confirmed failure.

Latest history tests: **19 passed across 5 files**; production build/TypeScript and touched-file lint pass. Browser assertions confirm the oldest run opens by keyboard and exports CSV/Excel/JSON with its exact UUID without launching validation. Final evidence is in `2026-09-28-history-verified`; the initial history capture set is superseded.

Latest wizard tests: **12 passed across 3 files**; touched-file ESLint, TypeScript, and the production build pass. September 26 results remain recorded separately: **55 frontend tests passed across 11 files; 131 knowledge/optimization backend tests passed**. TypeScript/production build pass. Changed-file lint has no errors and eight existing hook-dependency warnings in the expanded set; final touched-file lint is clean. `git diff --check` passes. Earlier 56/32-test frontend and 58-test automation-backend runs remain recorded separately, without adding overlapping counts. The earlier full frontend run had 961 passes and three signup failures reproduced on unchanged baseline HEAD.

Remaining acceptance work includes live worker integration, catalog filter/role/scope variants, source repair and full document navigation, other upload paths, large lists, alternate themes/roles, and 200% zoom. Failed automation saves after navigating away still need persistent recovery. All browser interaction results use synthetic API responses; no live model, ingestion, optimizer or automation execution was verified.
