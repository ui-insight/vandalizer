# UX upgrade implementation progress

Tracking issue: [#964](https://github.com/ui-insight/vandalizer/issues/964).

**139/169 items are implemented locally**, including VAL-12 in the September 28 task lifecycle pass, VAL-15 in the history pass and WIZ-04/05/06/10/12 in the wizard pass. This implementation is included in the local checkpoint commit; it is not deployed. Every reviewed section now has a working **8/8 UI/UX grade**, with reviewed mobile states at **8/10**. The unchecked acceptance backlog remains open; grades cover exercised frontend states.

- [Before/after gallery and working grades](../artifacts/visual-review/upgrade-review/index.html)
- [Full report and evidence limits](../artifacts/visual-review/upgrade-review/report.md)
- [Machine-readable results and provenance](../artifacts/visual-review/upgrade-review/review-summary.json)
- [Remaining checklist](ui-ux-upgrade-checklist.md)




## Chat composer and model recovery — September 29

**139/169 checklist items implemented locally.** CHAT-10 is complete for the reviewed composer flows; changes are not deployed.

- The model picker distinguishes loading, failure and an empty configured list, offers retry, fits short screens, contains focus and returns it on Escape or selection. Radio options support arrow/Home/End keys; long model names and metadata remain readable. Retry no longer dismisses the picker when its content changes.
- A selected model applies to this chat immediately. Default saves are serialized, a late preference read cannot overwrite a deliberate choice, and save failures keep the selected model with explicit retry. Context-window metadata follows the loaded model list.
- Whitespace cannot send; Enter sends, Shift+Enter adds a line and IME confirmation does not submit. Touch users can Queue while Stop remains available. Pending submissions prevent duplicates and preserve any newly typed draft; a queue failure keeps the attempted message and does not mark the active response failed.
- The accepted conversation/activity IDs are captured from response headers before streaming finishes, so the first response supports queueing and Stop retains the identity for the next turn.
- Verification: 23 frontend/API tests across six files, TypeScript and production build pass. ESLint has zero errors and one existing ChatPanel dependency warning. All 26 browser states at 320/768-short/1440px have zero axe findings, page overflow, uncaught errors or unmatched requests. Focus containment/return, selected-model request payloads, first-turn queueing and post-Stop activity identity are asserted; representative screenshots inspected directly.
- Evidence: `2026-09-29-chat-composer-evidence`; recipe: `frontend/scripts/visual-review/chat-composer.mjs`. APIs and streams use fixtures. Live model execution, queue consumption, ambiguous server-side queue acceptance and assistive-technology device behavior are not certified; broader agent/accessibility acceptance stays open.

## Knowledge ownership, sharing and availability — September 29

**138/169 checklist items implemented locally.** KB-11/12 are complete for the reviewed Knowledge flows; changes are not deployed.

- Read-only cards omit Edit/Delete, and bookmarks open and chat with the same canonical KB. Lists are cached separately by account/team; changing either clears an open detail. Failed list/project-pin reads show retry instead of an empty workspace. Building lists refresh while processing continues.
- Sharing sends an explicit desired state, so retrying a lost acknowledgement does not reverse the setting. The dialog retains its note after failure and prevents duplicate submissions or dismissal while saving. API responses include the owning team; first sharing assigns a real team destination. Team-owned KBs cannot be unshared and lost from both Mine and Team. Legacy clients may still use toggle semantics.
- Pagination counts organization-visible KBs before applying offsets. Bookmarks occupy only their page slots, search uses their displayed catalog name, and local project filtering/sorting includes later pages. Empty, building, partial, all-failed and validated states distinguish indexed availability from measured answer quality; empty and team badge contrast was corrected.
- Verification: 39 frontend tests across four files and 114 backend tests across two files pass. TypeScript, production build, touched-file ESLint/Ruff and diff checks pass. Forty-six browser states at 320/768/1440px cover list recovery, all five availability states, lost-share response/retry, sharing/ownership permissions, canonical bookmark detail/chat a 205-row list, and failed project pins recovering the pinned KB from the second page. The narrow project context bar wraps its title and actions into readable rows. No axe findings, page overflow, uncaught errors or unmatched requests in the selected run; representative screenshots inspected directly.
- Evidence: `2026-09-29-knowledge-states-evidence` and `2026-09-29-knowledge-project-final`; recipe: `frontend/scripts/visual-review/knowledge-sharing.mjs`. Browser APIs are fixtures and backend persistence is mocked. Live team notification delivery, Mongo behavior, ingestion and model execution are not certified. Explicit sharing retries preserve the state; concurrent independent administrators are not an exactly-once notification guarantee. The wider shared-theme and accessibility acceptance items remain open.

## Library recovery and item opening — September 28

**136/169 checklist items implemented locally.** LIB-06/07/08/09 are complete for the reviewed Library flows; changes are not deployed.

- Search includes matching tools stored in folders, trims whitespace and combines with type filters. Recent, pinned and favorite work remains reachable through the saved views, with create and catalog entry points retained. Folder-only, genuinely empty and no-result states explain the next action.
- Item/folder/library failures are visible and retryable. Loaded rows survive refresh failures; late searches, old scopes and mutations cannot replace another scope. Favorite, pin, copy and move actions expose pending/success/failure feedback and keep the exact failed target for retry. Folder create/rename errors preserve names, Enter submits once, and deletion failures retain the folder and its contents. Successful folder deletion returns its items to the root.
- Folder navigation and actions are separate keyboard controls. Item menus use an inline folder choice that fits narrow screens, close with Escape and restore focus. Long names wrap, metadata retains contrast on hover, and 120-item mixed lists stay accessible. Older extraction entries without a type label or separate UUID open correctly.
- Workflow/extraction load failures distinguish unavailable content and offer retry. Editor instances are keyed to the item while the Library and file pane remain in place. Prompt content failures disable use/edit until a successful retry; stale reads cannot replace another preview. Long previews fit short screens, contain keyboard focus, allow keyboard scrolling and return focus on Escape.
- Verification: 48 frontend regression tests across six files, TypeScript, production build and touched-file lint pass (four existing editor hook-dependency warnings, no lint errors). The final browser set covers 51 Library recovery states, 21 opening/long-content states at 320/768/1440px, and 30 repeated file → Library → run-on-the-selected-file states at 320/390/768/1024/1440px. All have zero axe findings, page overflow, uncaught errors or unmatched fixture requests; representative screenshots inspected directly.
- Evidence: `2026-09-28-library-recovery-evidence`, `2026-09-28-library-opening-evidence`, and `2026-09-28-file-library-regression`. APIs and execution use fixtures; live permissions and backend/model execution remain unverified. Broader shared theme, zoom and cross-surface acceptance remain open.


## Automation edit and launch recovery — September 28

**132/169 checklist items implemented locally.** AUTO-08 is complete for the reviewed editor and manual-run flows; changes are not deployed.

- Failed edits survive panel navigation in a user/automation-scoped save queue. Exact retries, pause/re-enable, description clearing, rename cancellation, IME Enter and duplicate-submit prevention pass. Unsaved configuration cannot launch. Drafts remain in tab memory and are discarded on reload, as the error message explains.
- Manual launches carry a stable request ID, reserved in a durable server receipt before dispatch. Reconnect repeats the same identity and document selection; a competing reservation returns the existing run. Lost responses can recover the owned event, while uncertain dispatch is never automatically queued again. Manage permission is checked before receipt access. Confirmed validation rejection permits corrected input; an uncertain outcome keeps the original intent locked.
- The browser retains launch IDs across editor switches and tab reloads. Accepted status failures retry only that event, and a deliberate run after completion receives a new ID. Completion no longer claims that every output destination received delivery.
- Verification: 24 frontend tests across two files and 93 backend tests across five files pass. TypeScript, production build, touched-file ESLint/Ruff and diff checks pass. The 18 edit states plus 18 launch states and 21 repeated manual-run states at 320/768/1440px have zero axe findings, page overflow, uncaught errors or unmatched requests. Representative screenshots inspected directly.
- Evidence: `2026-09-28-automation-save-review`, `2026-09-28-automation-launch-evidence`, and `2026-09-28-automation-run-reconnect`. Browser APIs use fixtures and backend persistence is mocked. The frontend/API update and new unique Mongo receipt index need coordinated release; live broker delivery, model execution and output destinations are unverified. A reservation without a recoverable event remains locked for investigation rather than risking duplicate effects. Earlier clients without request IDs retain their existing behavior.


## Automation edit recovery — September 28

**131/169 checklist items implemented locally.** AUTO-08 remains open for ambiguous manual-run launch recovery.

- Save queues now survive editor navigation in tab memory, scoped by user and automation. Failed writes retain their exact patches and require explicit retry; reopened editors overlay the draft and cannot race an earlier write or stale initial read. Read-only loads retain their current permissions. Drafts are not written to browser storage because output settings may include credentials; reloading the tab discards unsaved edits, as the error message explains.
- Description edits debounce as they are typed, including an empty string that actually clears the server field. Rename has explicit Save/Cancel controls, ignores IME Enter, and prevents duplicate submission. Completed run wording no longer claims all output deliveries succeeded.
- Verification: 21 frontend tests across two files, TypeScript, production build and touched-file ESLint pass. All 18 production browser states at 320/768/1440px have zero axe findings, page overflow, uncaught errors or unmatched requests. Checks cover canceled/IME rename, pending submission, failed drafts across editor switches, exact retry, description clearing, failed pause, retry and re-enable. Mobile screenshots were inspected directly.
- Evidence: `2026-09-28-automation-save-review`; recipe: `frontend/scripts/visual-review/automation-save-recovery.mjs`. API writes are fixtures; live server/worker behavior remains unverified. Work continues on preventing duplicate runs after a lost launch response.

## Automation summaries and shared surfaces — September 28

**131/169 checklist items implemented locally.** AUTO-02 and AUTO-05 are complete; changes are not deployed.

- Cards and editors share a readable Trigger / Input / Action / Output summary. It resolves source/destination folder paths, distinguishes scheduled selections from API or Microsoft 365 intake, names the chosen action and reports configured storage, notifications, webhooks and follow-up delivery without exposing endpoint credentials. Missing names or configuration remain explicit; folder-name failures retry, and old team responses cannot replace current names.
- Automation browsing and editing now use the same neutral surfaces, borders, readable metadata and brand selection treatment. Trigger labels are neutral; status keeps its own meaning. A concise empty state replaces the full promotional panel. Desktop file/section and Library/Assistant navigation is preserved.
- Verification: 20 frontend tests across four files, TypeScript, production build and touched-file ESLint pass. The 21 summary/theme states plus 27 repeated filter/scope recovery states at 320/768/1440px have zero axe findings, page overflow, uncaught errors or unmatched fixture requests. Long names, all trigger families, output destinations, folder-name failure/retry and empty content were inspected directly.
- Evidence: `2026-09-28-automation-summary-review` and `2026-09-28-automation-filter-light`; recipe: `frontend/scripts/visual-review/automation-summaries.mjs`. APIs and execution are fixtures. This completes the automation surface items, not the wider VIS checklist or live delivery verification.

## Automation history — September 28

**129/169 checklist items implemented locally.** AUTO-09 is complete; the issue remains open and changes are not deployed.

- Run history is reachable from each automation editor. It lists persisted workflow/task and extraction runs with status, timestamps, error details and recorded output. Older pages use a stable time/ID cursor; loading and pagination failures retry without discarding loaded entries.
- Opening a queued/running event polls that event sequentially. Failed detail reads retry the same ID, and late responses cannot replace another automation or selected run. Reopening the editor or reloading can reconnect through history without launching another run. Preparing a new run is an explicit separate action using the current configuration; read-only users can inspect results but cannot prepare a run.
- The new read endpoint authorizes the automation before either history query, uses existing scope/time/ID indexes, bounds each collection read, and fetches large outputs only through the authorized detail endpoint.
- Verification: 26 frontend tests across three files and 82 backend tests across five files pass. TypeScript, production build, touched-file ESLint and Ruff pass. All 30 browser states at 320/768/1440px have zero axe findings, page overflow, uncaught errors or unmatched fixture requests. Keyboard opening, focus return, 25-row pagination, failed details, editor reopen, reload, reader access and empty history are exercised; representative screenshots were inspected directly.
- Evidence: `2026-09-28-automation-history-final`; recipe: `frontend/scripts/visual-review/automation-history.mjs`. Browser APIs/execution are synthetic; backend tests use mocked persistence. Live Mongo/worker/output-delivery behavior and ambiguous launch failure handling are not certified. AUTO-08 remains open.

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

## Local checkpoint — September 28

The first checkpoint records the implementation, regression tests, browser review scripts and progress documentation accumulated for #964. Earlier entries below describe the uncommitted state at the time of those reviews. This is a partial implementation checkpoint, not completion of the issue or a deployment.

The latest Files recovery changes are included: failed folder loads and content searches retry; rename/create/move errors preserve drafts and targets; partial moves retry only failed files; revisiting moved-to folders refreshes their cached contents; returning from a document preserves list search, sort and selection. The focused run passed 37 tests across six files, and the production build passed. The Files browser review and checklist closure were subsequently completed against the restored navigation; see the Files and Projects entry above.

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

Remaining acceptance work includes live worker integration, catalog filter/role/scope variants, source repair and full document navigation, other upload paths, large lists, alternate themes/roles, and 200% zoom. Failed automation saves now survive panel navigation in tab memory; reload persistence is intentionally excluded for credential-bearing drafts. All browser interaction results use synthetic API responses; no live model, ingestion, optimizer or automation execution was verified.
