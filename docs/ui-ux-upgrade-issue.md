## Outcome

Bring every reviewed Vandalizer surface to **at least 8/10 for visual UI and 8/10 for UX**, with mobile independently reaching the same bar. Fix task failures first, establish a coherent visual hierarchy, and make existing behavior easier to understand. Each section must meet the target individually; the target is not an average.

This is the **single tracking issue** for the complete 169-item implementation/verification checklist and all 14 explicitly approved additions below. The additions map into the checklist; they are not a separate duplicate backlog. No product implementation is claimed complete by opening this issue.

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

Committed locally as `c107773b` (not pushed or deployed).

The user reported that the full-width section layout broke opening a file and running a Library item on it. This was a regression in the earlier visual refresh. Desktop sections now retain the document/section pane beside Assistant and Library, including while a workflow or extraction is open. Compact screens expose explicit pane controls and preserve both the file and tool while switching. Clicking the active Chat navigation item no longer resets the conversation or attachments.

Verification: 22 tests across four layout/navigation/Library files, TypeScript and the production build pass. The production browser journey covers open file → Library → workflow → failed run → retry → output → return at 320, 390, 768, 1024 and 1440px. Both run attempts must submit exactly the opened document UUID. All 30 captured states have zero axe findings, page overflow, page errors or unmatched fixture requests. Representative screenshots were inspected directly. The workflow editor's drag handle now uses its existing keyboard move controls as the accessible alternative, and completion text has readable contrast.

Evidence: `2026-09-28-file-library-evidence`; recipe: `frontend/scripts/visual-review/file-library-workflow.mjs`. API execution and results are synthetic; this establishes the frontend journey and request targeting, not live workflow/model execution. Earlier section grades do not establish cross-pane task coverage. The broader acceptance checklist remains open, with no new items marked complete in this correction.

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

## Implementation progress — September 28, validation setup and resumption

**101/169 checklist items implemented locally (VAL-03/05/06/07/08 completed in this pass).** Changes are uncommitted and not deployed.

- Quick checks and tuning previews show full questions, expected answers and source expectations. Preflight explains no-KB comparison versus answer/retrieval grading, missing expected answers, sample limits, grader, approximate duration and available token/cost information without promising improvement.
- Server-backed discovery restores queued checks and completed results after reopening/reload. A per-user/KB active-task index makes competing windows resume one accepted task. Discovery failures keep new submissions locked; recovery retains the task mode and selected question IDs. Unconfirmed dispatch is never automatically re-enqueued.
- Add/edit/delete failures preserve question drafts or selection. Successful additions clear stale filters; partial batch deletion retains the remaining selection. Large sets initially render 50 questions while select-all covers the full filtered set. Imports validate CSV/XLSX and the server's 5 MB limit, preserve the file on failure, expose partial row/source errors and prevent resubmitting a completed import.
- The tuning wizard keeps its title and final action visible while content scrolls. Step labels wrap at word boundaries on narrow screens; imports fit 320px and short viewports.
- Validation: 45 frontend tests across 5 files; 128 lifecycle/knowledge-route backend tests and 56 import/ID backend tests pass. Production build/TypeScript, touched-file ESLint/Ruff pass. 29 recovery/setup and 23 question-management browser states at 320/768/1440px have zero axe findings, overflow, page errors or unmatched requests. Large-set selection covers 251 questions in the browser and partial deletion covers 2,001 questions in component tests.
- Evidence: `artifacts/visual-review/2026-09-28-resumption-final` and `artifacts/visual-review/2026-09-28-questions-final`. Selected gallery: 300 states / 392 captures. Earlier diagnostics are retained and superseded. Representative screenshots were inspected directly.
- Limits: coordinated frontend/API/worker release required. Browser responses are synthetic; backend tests use mocks. Live Mongo index creation, Redis/broker/worker delivery and model execution remain unverified. Cross-KB navigation still needs dedicated acceptance coverage. Broader role/theme/zoom/source/catalog acceptance remains open.

## Implementation progress — September 28, validation task recovery

**96/169 checklist items implemented locally (VAL-12 completed for supported tab switches in this pass).** Changes are uncommitted and not deployed.

- Queued, running, delayed, retrying, failed and completed states follow the requested task across Sources, Validation, Test questions and History. Unrelated history cannot complete that task. Status reconnects do not submit new checks; confirmed failure permits a deliberate new check.
- A durable backend ownership/idempotency receipt is created before dispatch. Lost start responses reuse the same request ID/options. The status endpoint checks KB access and task ownership; failures are sanitized. Persisted task-correlated results survive Celery result expiry, and worker retries skip already-saved checks. A sparse unique index limits each task to one saved result.
- Unknown outcomes keep another check disabled while status is unresolved; uncertain dispatch is never automatically re-enqueued. The Test questions view now uses readable contrast/type and wraps its action toolbar.
- Validation: 32 frontend tests across 4 files; 207 backend tests across 5 files; production build/TypeScript, changed-file ESLint/Ruff and diff checks pass. Backend test output includes cookie deprecations and an AsyncMock coroutine warning. 26 final browser states at 320/768/1440px have zero axe findings, page overflow, page errors or unmatched requests.
- Evidence: `artifacts/visual-review/2026-09-28-lifecycle-evidence`. Selected gallery totals 248 states / 340 captures. Earlier diagnostics are preserved and superseded. Backend tests use mocks; browser responses are synthetic.
- Limits: coordinated frontend/API/worker release required. Full reload, closing/reopening a KB, cross-KB navigation and multi-window resumption remain unimplemented by this panel-owned hook. Live Mongo index creation, Redis/broker/worker delivery and model execution remain unverified. Broader acceptance backlog remains open.

## Implementation progress — September 28, validation history

**95/169 checklist items implemented locally (VAL-15 completed in this pass).** Changes remain uncommitted and not deployed.

- All 30 saved timeline rows are accessible with readable question-set differences, scoring mode, grader/answer model, source, date and run ID. Missing scores are labeled unavailable.
- Open results displays the selected persisted snapshot. CSV/Excel/JSON exports retain that exact run UUID. Saved-run provenance is separate from settings for the next check.
- History and export failures provide retry; background refresh failures preserve loaded rows. Narrow scoring-mode controls fit the result view.
- Validation: 19 focused tests across 5 files; touched-file ESLint, TypeScript, production build and diff checks pass. 18 final browser states at 320/768/1440px have zero axe findings, page overflow, page errors or unmatched API requests. The oldest run is opened by keyboard and exported in all three formats without a validation POST.
- Evidence: `artifacts/visual-review/2026-09-28-history-verified`; selected gallery totals 222 states / 314 captures. Synthetic responses only; no live model or backend execution. Initial history captures are superseded by the final build.
- VAL-12 remains open: delayed/failed-run recovery needs reliable server-side task correlation. Broader catalog/source/upload/role/theme/zoom acceptance remains open.

## Implementation progress — September 28, wizard review

**94/169 checklist items implemented locally (5 more in this pass: WIZ-04, WIZ-05, WIZ-06, WIZ-10, WIZ-12).** Changes remain uncommitted and not deployed. The folder/API/schedule wizard checklist is complete for the reviewed configuration; the wider acceptance backlog remains open.

- Required-field guidance now explains what is missing beside name, input, action, destination and recipient controls. Trigger drafts survive switching, while only the active trigger configuration is submitted. Workflow output defaults to a supported format.
- Action selections wrap at narrow widths. Picker load failures have a retry action and stay distinct from empty search results. Escape closes only the nested action picker, without opening the parent draft-discard prompt.
- Schedule previews immediately hide stale results when timing changes, offer retry after failure, and handle an empty upcoming-run list. Mobile checkboxes retain their size next to wrapped text.
- Wizard selections use consistent accents with verified contrast. Final controls remain reachable on short screens. API endpoint/key guidance and Python/cURL examples were reviewed; horizontally scrolling examples now support keyboard focus and scrolling.
- **12 focused tests pass across 3 files.** TypeScript, production build, touched-file ESLint and `git diff --check` pass. Existing bundle-size/mixed-import build warnings remain.
- **53 wizard/API states, 72 production captures** across 320×568, 390×844, 768×600 and 1440×900, including the final mobile recheck. No axe findings, page-level overflow, unmatched API requests or uncaught page errors in the successful runs. Injected HTTP 503 responses exercise recovery. Earlier failed diagnostics are preserved.
- Combined selected evidence is now **204 distinct states / 296 captures**. Representative screenshots were inspected directly. Working grades remain unchanged; this pass does not regrade unrelated surfaces.

Local report: `artifacts/visual-review/upgrade-review/index.html`; progress: `docs/ui-ux-implementation-progress.md`. These working-tree artifacts are not published GitHub attachments. All API responses in the browser review are synthetic; M365 setup, real credentials, scheduled execution and other live integrations remain unverified.

## Implementation progress — September 26, recovery review

**89/169 checklist items implemented and checked below (5 more in this pass). All reviewed sections now have working UI/UX grades of 8/8; the unchecked acceptance backlog remains open.** Changes are local, uncommitted and not deployed. All A1–A14 have implementation; broader acceptance checks are still tracked below.

- Catalog saving now shows the destination, checking/pending/error/retry, saved and already-saved states, plus an Open action. KB adoption keeps errors visible and prevents repeat submissions while pending. Long detail dialogs preserve search context and keep actions reachable at 320px, tablet and desktop widths.
- Validation apply/revert preserves inline errors, requires fresh regression acknowledgment, refreshes the parent summary, and works on short screens. Composite quality is no longer presented as answer accuracy or subtracted from raw AI-only accuracy. Summary labels distinguish proposed, applied-in-run, reverted and default settings. Existing scoring and execution are unchanged.
- Stopped/interrupted chat retains partial responses and unfinished calls; unresolved actions say completion is not confirmed and ended plans stop spinning. Retry now preserves completed artifacts and prior output. The harness opens a retained artifact after retry.
- Previous improvements remain: clearer Knowledge/Library mobile controls; validation summary refresh and saved expected-answer drilldowns; partial deletion retry; serialized automation saves; citation previews; first-session upload → question → evidence; and action-specific agent approvals.
- Latest selected evidence: **151 distinct states / 224 production captures**, including 34 new captures in this pass. No page-level overflow, unmatched API requests, uncaught page errors or axe findings in the selected evidence. Earlier blocked and contrast-failing captures remain preserved.
- Latest focused frontend tests: **55 passed across 11 files**. Knowledge/optimization backend: **131 passed**, including new score/provenance regressions. TypeScript/build pass. Changed-file lint: zero errors and eight existing hook-dependency warnings in the expanded changed-file set; final touched-file lint is clean. Earlier 56/32-test frontend and 58-test automation-backend runs remain recorded separately; counts overlap. The earlier broad frontend run had 961 passes and three signup failures reproduced on unchanged baseline HEAD.
- Working UI/UX grades: Files 8/8, Projects 8/8, Automations 8/8, Wizard 8/8, Knowledge 8/8, Validation 8/8, Catalog 8/8, Library 8/8, Chat 8/8, Onboarding 8/8, Uploads 8/8, Chat-KB 8/8, Agent 8/8. **Reviewed mobile states: 8/10.** These are authored judgments of exercised frontend states, not exhaustive live-integration certification.
- Remaining priorities: comparable validation history and delayed/failed-run recovery; catalog filter/scope/role variants; source repair and full document navigation; other upload intake paths; automation recovery after navigation; long content, large lists, alternate roles/themes and 200% zoom. The unchecked items below remain the acceptance backlog.

Evidence is fixture-backed: no live model, retrieval, ingestion, optimizer changes or autonomous execution was performed. Local review: `docs/ui-ux-implementation-progress.md` and `artifacts/visual-review/upgrade-review/index.html`. Artifacts are in the working tree, not published GitHub attachments; baseline screenshots and grades remain unchanged.

## Scope and constraints

- Covers Files, Projects, Automations and its wizard, Knowledge and validation, Explore/catalog, Library, Chat, onboarding, uploads, KB interactions and agentic functionality.
- All A1–A14 are approved. Keep the additions bounded to their descriptions; reuse existing functionality and controls where appropriate.
- A verification task does not imply that an untested flow is broken or authorize unrelated feature development.
- Preserve user data, existing permissions and operation semantics except for the explicitly approved changes and confirmed defect repairs. No unrelated backend rewrite, integration, model tuning or production deployment.
- Display actual operational state; never invent success, progress, timing, cost or quality values. Aborting an upload must not be presented as cancellation/rollback of server work that already started.
- Use one issue with task lists and acceptance criteria. Keep follow-up implementation progress and review evidence here.

## Baseline and evidence limits

Reviewed commit: [`560ccd5`](https://github.com/ui-insight/vandalizer/commit/560ccd5decc8d01df8fd3fa68a96d0c617f1a3f9), September 25, 2026. The Playwright harness captured **55 distinct states / 61 capture executions**: 53 development captures plus 8 production-preview captures, including repeated critical interaction checks and two additional validation states. Desktop: 1440×1000; mobile: 390×844. Baseline desktop aggregate: **6.2/10**; mobile: **3/10**.

The real frontend ran against synthetic authenticated API fixtures. Grades are authored from screenshot inspection and exercised interactions, not generated by axe or an automatic design metric. This does not establish live retrieval accuracy, model quality, backend ingestion or agent execution reliability. The two successful capture runs had no unconfigured API calls or uncaught page errors; product defects and accessibility findings were still present.

Original screenshots, manifests and the runnable harness currently exist in the working tree under `artifacts/visual-review/2026-09-25/`, `artifacts/visual-review/2026-09-25-production/` and `frontend/scripts/visual-review/`. They are not yet committed/uploaded and are not presented as accessible GitHub attachments. The issue includes the findings and reproduction steps needed to begin; preserve and publish before/after evidence during implementation.

| Area | Visual UI /10 | UX /10 |
|---|---:|---:|
| File browser | 6 | 6 |
| Projects | 6.5 | 6.5 |
| Automations screen and editor | 6 | 6 |
| Automation creation wizard | 7.5 | 5.5 |
| Knowledge bases | 6 | 5.5 |
| KB validation system | 6.5 | 6.5 |
| Explore / shared catalog | 7 | 6.5 |
| Library | 5.5 | 5.5 |
| Chat workspace | 6.5 | 6 |
| Basic chat onboarding | 7 | 6.5 |
| Chat uploads | 6 | 3 |
| Chat knowledge-base interactions | 7 | 7 |
| Agentic chat UI | 7 | 6.5 |

## Confirmed defects to fix first

1. **Chat upload loses source scope.** Add → Add Document; upload a fixture document whose response is complete and whose UUID appears in the refreshed Files list; send a question about that upload. The submitted chat request has `document_uuids: []` instead of the uploaded UUID. Reproduced in development and the fresh production build. Inspect selection synchronization in `FileBrowser.tsx`, `LeftPanel.tsx` and `ChatPanel.tsx`. Acceptance: the visible attachment and the next request retain the intended UUID across refresh/processing updates.
2. **Enter dismisses the automation wizard.** Open New Automation, enter name and description, press Enter while the description input has focus. The dialog disappears instead of advancing visibly. Reproduced in development and production. Inspect the window-level Enter handler and focus transitions in `AutomationCreationWizard.tsx`; the exact cause was not established by the audit. Acceptance: advance exactly once, retain values, and never activate Close accidentally.
3. **Mobile overflow and cramped content.** The six main screens render a 521px-wide document at a 390px viewport. Header controls overflow, Library keeps a desktop sidebar, and ordinary filenames/item names become nearly unreadable. Acceptance: no unintended page overflow, readable content, reachable controls at 320px and 390px.
4. **Library clips the first item.** At initial scroll position the first title is partly hidden beneath the Name header. Acceptance: full first-row content and consistent header/row geometry at all reviewed widths.
5. **Development-only validation lifecycle issue.** Validation can remain loading under React StrictMode; inspection points to `KBValidationPanel` clearing `mountedRef` during cleanup without resetting it on setup. The same fixture completes in the production build. Verify the cause, repair lifecycle handling, and cover both build modes.

## Approved additions

| ID | Approved addition | Scope | Status | Checklist references |
|---|---|---|---|---|
| A1 | Project search and sorting | New controls for finding/reordering the Projects list. The current list does not expose these. | Approved | PROJ-03 |
| A2 | Last-run outcome in automation list | New summary information on list cards, potentially requiring a data lookup; existing scheduled next-run text already exists and only needs presentation review. No new monitoring backend is proposed. | Approved | AUTO-03, AUTO-09 |
| A3 | Per-file upload retry | A new retry action for a failed upload, distinct from the existing chat-response retry. | Approved | UP-05 |
| A4 | Cancel an active upload | A new action that actually aborts an in-flight upload. Removing an existing attached file and cancelling an already-supported queued message are separate existing behaviors. | Approved | UP-06 |
| A5 | Open created artifact from agent completion | A new shortcut such as Open workflow on creation results. Existing source inspection, workflow progress/output and verification links are already present. | Approved | AGT-06 |
| A6 | Unsaved-draft discard confirmation | A new Keep editing / Discard prompt when closing a partially completed automation wizard. | Approved | WIZ-09 |
| A7 | Shorter validation wizard | Merge/reorder existing screens and put advanced settings behind an optional control. Computation stays the same, but the user's sequence changes. | Approved | VAL-04 |
| A8 | Separate primary Sources / Validation views | Introduce new primary tabs or navigation in KB detail instead of the existing stacked sections. | Approved | KB-06, VAL-02 |
| A9 | Guided first-task onboarding | A prescribed upload → question → inspect-evidence sequence beyond the existing upload/demo actions. | Approved | ONB-03 |
| A10 | Dedicated assistant launcher | A new launcher/control for opening contextual chat. Resizing existing panels, simplifying welcome content and using current navigation/collapse controls do not require this addition. | Approved | SYS-02 |
| A11 | Separate Save disabled / Create & enable buttons | Replace the current Enable immediately checkbox plus Create Automation button with two final actions. Creating enabled/disabled automations is already supported; the controls would change. | Approved | WIZ-08 |
| A12 | Read-only automation configuration recap | Show the selected trigger, folder/filters, action, output and activation together on the existing final wizard screen. No extra step, setting or execution behavior. | Approved | WIZ-07 |
| A13 | Source-health summary beside attached KB | Display existing ready/failed-source information beside the KB in chat. No refresh/retry control or new source-health service. | Approved | CKB-02 |
| A14 | Structured agent approval summary | Format the existing proposed action, target and supplied arguments as a readable summary before the existing confirmation. No new approval gate or tool behavior. | Approved | AGT-02 |

Implementation clarifications:

- A2 supplements existing scheduled next-run text; it does not require a new monitoring subsystem.
- A3/A4 are upload actions, distinct from existing response retry, detaching a file or cancelling an already-supported queued message.
- A7 keeps validation computation intact while simplifying its presentation/sequence. Preserve review, budget and deliberate application decisions.
- A11/A12 share the existing final automation screen: complete recap and explicit activation actions, without an extra step.
- A13/A14 present available information; do not infer missing source-health or tool arguments as facts.

## Detailed implementation and verification checklist



- **Fix**: a defect or usability problem observed in the baseline.
- **Improve**: a proposed change to reach the quality target.
- **Verify**: a flow or state that needs evidence; repair it if verification fails.
- **P1**: core task failure or broad inability to access the UI. Fix first.
- **P2**: necessary usability, clarity, consistency or accessibility improvement.

Unchecked items remain open; checked items refer to local implementation, not a deployed release. Reuse good existing behavior and avoid adding duplicate controls or unnecessary backend features. Display operational information only when real data supports it. Do not invent success, progress, cost, quality or timing values.

## 1. Shared workspace and navigation

- [x] **SYS-01 · P2 · Fix:** Give the selected workspace the primary canvas. Stop the large returning-user chat welcome panel from competing with Files, Projects, Automations and Knowledge.
- [x] **SYS-02 · P2 · Improve:** Make the assistant a compact, clearly labeled contextual panel that users can open and expand without losing their current task.
- [x] **SYS-03 · P2 · Fix:** Collapse an empty Activity rail by default; keep an obvious way to open activity, notifications and run history.
- [ ] **SYS-04 · P2 · Improve:** Preserve useful panel choices during a session without restoring layouts that do not fit the current viewport.
- [ ] **SYS-05 · P2 · Improve:** Make the active section and current project context unmistakable, including when opening an item from chat or the Library.
- [ ] **SYS-06 · P2 · Improve:** Use consistent placement for the page title, description, primary action, search, filters and secondary actions.
- [ ] **SYS-07 · P2 · Improve:** Establish one coherent vocabulary for Files, Projects, Automations, Knowledge, Library and Explore; distinguish location from ownership/sharing scope.
- [ ] **SYS-08 · P2 · Verify:** Back navigation, section switches and opening/closing contextual panels preserve the intended selection, draft and scroll position.

Acceptance: the active task owns the visual hierarchy; supporting panels are discoverable without dominating; navigation never silently discards work.

## 2. Shared visual system

- [ ] **VIS-01 · P2 · Fix:** Reconcile the light file/project/editor surfaces, dark automation/KB surfaces, blue wizard controls and purple validation controls into a consistent theme hierarchy.
- [ ] **VIS-02 · P2 · Improve:** Standardize page, section, card and metadata typography. Increase essential metadata that is currently too small to scan.
- [ ] **VIS-03 · P2 · Improve:** Use shared spacing, padding, row heights, border radii, borders and elevation across lists, cards and dialogs.
- [ ] **VIS-04 · P2 · Improve:** Standardize primary, secondary, quiet and destructive action styles, including disabled, hover, focus and loading states.
- [ ] **VIS-05 · P2 · Improve:** Standardize form labels, optional/required indicators, help text, validation messages and error placement.
- [ ] **VIS-06 · P2 · Fix:** Give important names and task content more space than decoration, promotional copy and low-value metadata.
- [ ] **VIS-07 · P2 · Improve:** Use consistent status badges with text and appropriate icons; reserve color for meaning rather than decoration.
- [ ] **VIS-08 · P2 · Verify:** Long names, multiline descriptions and translated/browser-enlarged text wrap sensibly without hiding actions.

Acceptance: screens look like parts of one product, with consistent hierarchy and readable information at normal zoom and enlarged text.

## 3. Responsive behavior and accessibility

- [x] **ACC-01 · P1 · Fix:** Remove the 521px document width at a 390px viewport by making the header, brand, support and account controls responsive.
- [x] **ACC-02 · P1 · Fix:** Replace desktop-only sidebar/list arrangements with usable narrow-screen layouts, particularly Library and Files.
- [x] **ACC-03 · P2 · Improve:** Make workspace panels stack, collapse or switch predictably on small screens while keeping the active task reachable.
- [x] **ACC-04 · P2 · Verify:** No unintended page-level horizontal scrolling at 320, 390, 768, 1280 and 1440px. Explicitly contained wide data may scroll when appropriate.
- [ ] **ACC-05 · P2 · Verify:** Dialogs and pickers fit short and narrow viewports; their titles, content and final actions remain reachable.
- [x] **ACC-06 · P2 · Fix:** Add descriptive accessible names to the Projects create button, KB sort select and any other unnamed controls identified by the harness.
- [x] **ACC-07 · P2 · Fix:** Remove nested interactive structures in KB cards and source rows; make row opening and secondary actions separate keyboard targets.
- [x] **ACC-08 · P2 · Fix:** Correct measured low contrast in timestamps, counts, tags and secondary metadata. Target 4.5:1 for normal text and 3:1 for large text and essential UI graphics.
- [ ] **ACC-09 · P2 · Verify:** Keyboard focus is visible and follows a logical order through navigation, tables, cards, menus, tabs and dialogs.
- [ ] **ACC-10 · P2 · Verify:** Dialogs set focus appropriately, contain focus while open, close with Escape when appropriate and restore focus to their trigger.
- [ ] **ACC-11 · P2 · Improve:** Make row actions usable without hover, and make small controls practical touch targets without crowding their neighbors.
- [ ] **ACC-12 · P2 · Verify:** Upload, processing, validation and tool-state changes are announced appropriately without flooding assistive technology.
- [ ] **ACC-13 · P2 · Verify:** Essential tasks remain usable at 200% zoom and with reduced motion; loading indicators do not rely exclusively on animation.

Acceptance: the six main mobile screens and their critical flows independently earn 8/10; no unresolved serious or critical automated accessibility findings in the reviewed states; keyboard and focus checks pass. Automated checks alone do not establish accessibility conformance.

## 4. File browser

- [x] **FILE-01 · P2 · Fix:** Rename the PDFs heading to Files and align the copy with supported document types.
- [x] **FILE-02 · P2 · Fix:** Reduce the oversized upload area on populated screens; retain a clear upload action and useful drag-and-drop affordance.
- [x] **FILE-03 · P2 · Improve:** Present actual file type and size constraints near upload; use the same rules for validation and explanatory copy.
- [x] **FILE-04 · P2 · Fix:** Allocate responsive width to filenames and keep type/status/actions readable instead of shrinking names to a few characters.
- [x] **FILE-05 · P2 · Fix:** Increase timestamp and file-type contrast and normalize metadata styling.
- [x] **FILE-06 · P2 · Fix:** Make the row action menu persistently discoverable and accessible with touch and keyboard.
- [x] **FILE-07 · P2 · Improve:** Show selected count, clear selection and applicable bulk actions together, with a clear distinction between selection and opening a file.
- [x] **FILE-08 · P2 · Verify:** Folder navigation, breadcrumbs, search, sorting and returning from a document preserve the correct location and selection.
- [x] **FILE-09 · P2 · Verify:** Empty folder, no search results, loading, processing, failed processing and retry states are distinct and actionable.
- [x] **FILE-10 · P2 · Verify:** Existing move, rename, delete and other bulk/context actions explain their target and recover from failure without losing selection.

Acceptance: upload → locate → select → inspect/use a file is understandable and reliable on desktop and mobile, including error recovery.

## 5. Projects

- [x] **PROJ-01 · P2 · Fix:** Replace the unlabeled plus with a named, prominent New project action.
- [x] **PROJ-02 · P2 · Fix:** Replace or supplement cryptic icon/count pairs with readable labels for the most useful project contents.
- [x] **PROJ-03 · P2 · Improve:** Add a project search and useful sorting without overloading a short list.
- [x] **PROJ-04 · P2 · Improve:** Make project title, description, state and relevant activity readable within a consistent card/list hierarchy.
- [x] **PROJ-05 · P2 · Fix:** Shorten the empty-state explanation and place a direct create action beside it.
- [x] **PROJ-06 · P2 · Improve:** Make the project detail page clearly answer what belongs here and what the user should do next.
- [x] **PROJ-07 · P2 · Verify:** Entering and leaving a project updates the visible chat/file/KB context consistently; no stale project scope leaks into unrelated work.
- [x] **PROJ-08 · P2 · Verify:** Creation errors, empty contents, long titles, many projects and restricted access have usable states.

Acceptance: users can create, find, open and work within the correct project without interpreting unlabeled icons or losing context.

## 6. Automations screen and editor

- [x] **AUTO-01 · P2 · Fix:** Replace color-only state dots with explicit Enabled/Paused labels.
- [ ] **AUTO-02 · P2 · Improve:** Present trigger, input location, action and output in a concise readable summary.
- [x] **AUTO-03 · P2 · Improve:** Show last outcome and next scheduled run when the API supplies them; clearly distinguish no history, unavailable data and a failed run.
- [x] **AUTO-04 · P2 · Fix:** Give the editor sufficient width so normal titles and configuration fields do not wrap unnecessarily.
- [ ] **AUTO-05 · P2 · Fix:** Unify list and editor visual styles using the shared theme and control patterns.
- [x] **AUTO-06 · P2 · Improve:** Keep enabled state, ownership/sharing, Save and Run now easy to distinguish; communicate unsaved edits.
- [x] **AUTO-07 · P2 · Verify:** Search/filter combinations, empty results and clearing filters work predictably.
- [ ] **AUTO-08 · P2 · Verify:** Enable, pause, edit and manual-run actions provide accurate pending, success and failure feedback and prevent accidental duplicate submission.
- [x] **AUTO-09 · P2 · Verify:** Available execution history, failed-run details and recovery actions are reachable from the relevant automation.

Acceptance: the list explains what will run and its operational state; configuration changes and manual execution have clear consequences and feedback.

## 7. Automation creation wizard

- [x] **WIZ-01 · P1 · Fix:** Stop Enter in the description input from dismissing the wizard. Advance exactly once where appropriate, preserve data and move focus deliberately.
- [x] **WIZ-02 · P1 · Verify:** Add a focused regression check for the keyboard failure, including returning to the prior step with the entered values intact.
- [x] **WIZ-03 · P2 · Improve:** Give numbered steps descriptive names and distinguish completed, current and upcoming steps.
- [x] **WIZ-04 · P2 · Improve:** Explain missing requirements beside their fields rather than relying only on a disabled Next button.
- [x] **WIZ-05 · P2 · Verify:** Back/Next preserves all values and changing the trigger handles incompatible selections explicitly.
- [x] **WIZ-06 · P2 · Improve:** Give the workflow/action picker clear search, selected state, empty results and a readable selection summary.
- [x] **WIZ-07 · P2 · Fix:** Add a final review containing name, trigger, input folder/filter, action, output and activation state.
- [x] **WIZ-08 · P2 · Fix:** Make Save disabled and Create & enable explicit choices; the final action must accurately state whether execution is being enabled.
- [x] **WIZ-09 · P2 · Verify:** Close/Escape/cancel behavior is consistent and protects a meaningful unsaved draft without adding prompts to an untouched form.
- [x] **WIZ-10 · P2 · Verify:** Review schedule and API-trigger branches, including timezone, configuration errors and relevant endpoint/secret presentation; these were outside the initial capture path.
- [x] **WIZ-11 · P2 · Verify:** Creation failure preserves the draft; submission cannot accidentally create duplicates; success leads to the created automation.
- [x] **WIZ-12 · P2 · Fix:** Apply the shared visual system and verify every step, picker and final review on mobile.

Acceptance: the full folder-watch path and supported alternate trigger paths can be completed with mouse, keyboard and touch; the final review makes activation unambiguous.

## 8. Knowledge-base list and detail

- [x] **KB-01 · P2 · Fix:** Separate retrieval availability, source completeness and measured quality instead of allowing a generic Ready badge to imply all three.
- [x] **KB-02 · P2 · Fix:** Lead with an actionable source summary such as 2 of 3 sources ready — 1 needs attention.
- [x] **KB-03 · P2 · Fix:** Make source/chunk counts and quality metadata readable, with useful explanations for technical counts.
- [x] **KB-04 · P2 · Fix:** Remove nested controls from list cards and source rows; provide clearly separated open/chat/edit/menu actions.
- [x] **KB-05 · P2 · Fix:** Name the sort control and make search, ownership filters and current sort clear.
- [x] **KB-06 · P2 · Improve:** Put source management and validation in clearly labeled primary views, with quality work reachable without scrolling through all source controls.
- [x] **KB-07 · P2 · Fix:** Move secondary export, clone, sharing and management actions out of the crowded primary action row while preserving discoverability.
- [x] **KB-08 · P2 · Improve:** Standardize source rows around source identity, type, readiness, freshness and a relevant recovery action.
- [x] **KB-09 · P2 · Verify:** Adding documents and URLs gives clear progress and success/failure feedback, including mixed-success batches and unavailable sources.
- [x] **KB-10 · P2 · Verify:** Inspect, refresh, reprocess, retry and remove actions update the correct source and summarize their result accurately.
- [ ] **KB-11 · P2 · Verify:** Sharing/ownership controls reflect actual permissions, and list/detail/chat source scope remains consistent after navigation.
- [ ] **KB-12 · P2 · Verify:** Empty, building, partially ready, all-failed and validated KBs have distinct, usable presentations.

Acceptance: users can tell what information is usable, what needs repair and what has actually been evaluated, then act on each without guessing.

## 9. Knowledge validation and improvement

- [x] **VAL-01 · P2 · Fix:** Separate the primary jobs into plain-language actions: Check answer quality and Improve retrieval.
- [x] **VAL-02 · P2 · Fix:** Make both actions visible near the KB summary rather than burying validation below source management.
- [x] **VAL-03 · P2 · Improve:** Explain evaluation questions and expected answers before asking users to choose technical settings.
- [x] **VAL-04 · P2 · Improve:** Shorten the six-step wizard by combining low-decision screens where useful; keep advanced controls optional.
- [x] **VAL-05 · P2 · Improve:** Preserve and improve the preview of selected questions, expected answers and source expectations.
- [x] **VAL-06 · P2 · Verify:** Creating, editing, importing, selecting and removing test questions gives clear validation and preserves intended scope.
- [x] **VAL-07 · P2 · Improve:** Explain the no-KB comparison and its purpose in plain language, and distinguish it from retrieval-only or answer-only grading.
- [x] **VAL-08 · P2 · Improve:** Summarize evaluation scope, question count, sample limitations, grader, expected time and available budget/cost information before starting.
- [x] **VAL-09 · P2 · Fix:** Qualify budget/time recommendations and small-sample results; do not imply that a larger sample guarantees the current measured score.
- [x] **VAL-10 · P2 · Fix:** Remove disabled coming-in-v2 controls from the primary decision path.
- [x] **VAL-11 · P2 · Fix:** Repair the development StrictMode lifecycle problem that can leave validation waiting indefinitely despite a completed response.
- [x] **VAL-12 · P2 · Verify:** Pending, running, delayed, failed and completed states survive supported tab switches and provide appropriate recovery without duplicate runs.
- [x] **VAL-13 · P2 · Improve:** Keep composite quality, answer accuracy, source health, coverage and improvement clearly distinct; preserve the score formula and sample explanation.
- [x] **VAL-14 · P2 · Verify:** Per-question results expose expected answer, actual answer, supporting source and failure reason without requiring users to interpret raw data.
- [x] **VAL-15 · P2 · Verify:** History can identify comparable runs, show configuration/provenance and open/export the intended result accurately.
- [x] **VAL-16 · P2 · Verify:** Manual apply remains the deliberate default; review the proposed change, apply result and available revert behavior. The initial review did not exercise these operations.
- [ ] **VAL-17 · P2 · Verify:** All validation views and wizard actions remain usable on narrow and short screens, with no hidden primary action.

Acceptance: a user can set up a meaningful check, understand what it costs and measures, interpret the result and deliberately choose whether to apply an improvement. Fixture scores do not establish real model accuracy.

## 10. Explore / catalog

- [x] **EXP-01 · P2 · Fix:** Use Explore consistently for discovery; describe public/team/personal scope separately from navigation labels.
- [x] **EXP-02 · P2 · Fix:** Use one contextual catalog search instead of displaying competing Library and catalog search fields.
- [x] **EXP-03 · P2 · Fix:** Collapse or remove the wide single-option All Knowledge Bases sidebar.
- [x] **EXP-04 · P2 · Fix:** Standardize Checked/Verified terminology and explain what each trust indicator actually establishes.
- [ ] **EXP-05 · P2 · Improve:** Prioritize item purpose, type, required inputs and intended output in cards and details.
- [x] **EXP-06 · P2 · Improve:** Make quality, sample count, validation recency, provenance and available limitations legible; distinguish unmeasured quality from low quality.
- [x] **EXP-07 · P2 · Verify:** Search, kind filters, quality filters, sorting, clearing filters and no-results recovery work together.
- [x] **EXP-08 · P2 · Verify:** Save to Library clearly indicates destination, pending/error state and already-saved state, then offers a useful next action.
- [x] **EXP-09 · P2 · Verify:** Detail dialogs preserve browsing context and remain usable with long descriptions and narrow viewports.

Acceptance: users can find an appropriate item, understand its fit and trust evidence, save it once and find it again.

## 11. Library

- [x] **LIB-01 · P2 · Fix:** Correct header/row geometry so the first item name is fully visible at scroll position zero.
- [x] **LIB-02 · P1 · Fix:** Replace the fixed mobile sidebar and cramped columns with a full-width item layout and accessible saved-view navigation.
- [x] **LIB-03 · P2 · Fix:** Increase contrast and readability of timestamps, item types, tags and quality metadata.
- [x] **LIB-04 · P2 · Improve:** Reduce stacked scope/filter/sidebar controls and group personal/team ownership, item type and saved views coherently.
- [x] **LIB-05 · P2 · Improve:** Explain the practical distinction between favorites, pins, folders and project membership; avoid presenting all as equal first-use decisions.
- [ ] **LIB-06 · P2 · Improve:** Make search and useful recent/pinned work prominent, with consistent create and browse actions.
- [ ] **LIB-07 · P2 · Verify:** Item opening, type filters, sorting, favorites, pins and folder actions target the correct item and provide visible feedback.
- [ ] **LIB-08 · P2 · Verify:** Empty Library, empty folder, no results, unavailable item and large populated lists have clear, efficient states.
- [ ] **LIB-09 · P2 · Verify:** Long names and mixed workflow/extraction/prompt items remain readable with reliable row actions on desktop and mobile.

Acceptance: users can find, organize and open an item quickly; no item is clipped and mobile retains the essential desktop capabilities.

## 12. Chat workspace

- [x] **CHAT-01 · P2 · Fix:** Replace the large returning-user promotional hero with a compact task launcher and relevant recent work.
- [x] **CHAT-02 · P2 · Fix:** Remove duplicate Ask about current work actions and competing layers of suggestion cards.
- [x] **CHAT-03 · P2 · Fix:** Move certification and promotional guidance below the primary task hierarchy.
- [x] **CHAT-04 · P2 · Fix:** Reduce composer height on mobile while retaining attachment, model, send and relevant stop controls.
- [x] **CHAT-05 · P2 · Improve:** Make document, KB and project scope readable near the composer, with explicit removal/switching behavior.
- [x] **CHAT-06 · P2 · Verify:** Drafts and intended attachments survive relevant panel switches; a deliberate new conversation starts with the advertised scope.
- [x] **CHAT-07 · P2 · Verify:** Long answers, lists, tables, links and code have readable wrapping and usable copy/source actions.
- [x] **CHAT-08 · P2 · Verify:** Streaming, stop, interruption, retry and connection failure preserve the conversation and show accurate state.
- [x] **CHAT-09 · P2 · Verify:** Auto-scroll respects a user reading earlier messages and provides a clear way to return to the latest response.
- [ ] **CHAT-10 · P2 · Verify:** Send-button state, Enter/Shift+Enter, model selection and errors remain understandable with keyboard, touch and assistive technology.

Acceptance: composing, sending, reading, interrupting and recovering from a conversation feel predictable, and the source scope is always clear.

## 13. Basic chat onboarding

- [x] **ONB-01 · P2 · Fix:** Focus the first session on two clear starts: upload a document or try the sample demo.
- [x] **ONB-02 · P2 · Fix:** Remove marketing/design-strategy paragraphs that delay the first useful action.
- [x] **ONB-03 · P2 · Improve:** Guide one complete first success: choose a source → ask a suggested question → inspect the supporting evidence.
- [x] **ONB-04 · P2 · Fix:** Replace the unconditional promise that every answer links to sources with accurate language about source-grounded tasks.
- [x] **ONB-05 · P2 · Improve:** Keep sample content visibly identified as a demo and provide a clear transition into the user's own work.
- [ ] **ONB-06 · P2 · Verify:** First visit, dismissed onboarding, returning user and the optional guided-tour overlay coexist without trapping focus or repeatedly interrupting work.
- [ ] **ONB-07 · P2 · Verify:** The first useful action and demo evidence are reachable on mobile without excessive scrolling.

Acceptance: a new user can understand what to do, complete one useful task and identify where the answer came from without reading a landing page.

## 14. Chat uploads

- [x] **UP-01 · P1 · Fix:** Preserve uploaded document selection across file-list refreshes; make the intended chat source selection authoritative.
- [x] **UP-02 · P1 · Verify:** Add a regression assertion that the next chat request contains the uploaded document UUID after refresh and processing updates.
- [x] **UP-03 · P2 · Improve:** Show a persistent attachment chip with uploading, processing, ready and failed states rather than relying on a transient toast.
- [x] **UP-04 · P2 · Improve:** Communicate when an attachment can be used and what happens if the user sends while processing is incomplete.
- [x] **UP-05 · P2 · Verify:** Failure and retry preserve the message draft and other successful attachments, and expose an actionable error.
- [x] **UP-06 · P2 · Verify:** Remove/cancel actions affect the intended attachment and cannot reattach it when a delayed response arrives.
- [x] **UP-07 · P2 · Verify:** Multiple files, partial failure, unsupported type, size limit and duplicate selection produce comprehensible outcomes.
- [x] **UP-08 · P2 · Verify:** Picker, drag/drop and other supported intake methods converge on the same attachment behavior on desktop and mobile.

Acceptance: upload → ready attachment → ask sends the intended source IDs reliably; failures do not silently change what the question is about.

## 15. Chat knowledge-base interactions

- [x] **CKB-01 · P2 · Fix:** Let the attached KB name use available width, with an accessible full-name affordance when truncation is unavoidable.
- [x] **CKB-02 · P2 · Improve:** Show relevant readiness and incomplete-source coverage near the attached KB without implying validation establishes certainty.
- [x] **CKB-03 · P2 · Improve:** Make answer evidence and source inspection readable and discoverable near the claim or source reference.
- [x] **CKB-04 · P2 · Verify:** Chat from KB and attach from chat produce the same intended scope; detach, replace and supported multi-source combinations submit the correct identifiers.
- [x] **CKB-05 · P2 · Verify:** Inspecting evidence opens the intended document/passage or URL and lets the user return to the conversation without losing position.
- [x] **CKB-06 · P2 · Verify:** Missing, stale, failed or inaccessible sources have an honest visible state and a useful recovery route.
- [x] **CKB-07 · P2 · Verify:** Use representative valid citation payloads for UI testing; separately label any live grounding check so mocked source chips are never treated as retrieval evidence.

Acceptance: the user knows which KB is attached, what its coverage limitations are and how to inspect the evidence for an answer.

## 16. Agentic chat functionality

- [x] **AGT-01 · P2 · Fix:** Replace generic Confirm wording with an action-specific approval label when the operation and target are known.
- [x] **AGT-02 · P2 · Improve:** Present a structured preview of the proposed action, target and meaningful consequences, visually separated from ordinary assistant prose.
- [x] **AGT-03 · P2 · Fix:** Associate each plan/progress display with its operation or turn so a prior completed plan cannot appear to describe a later failure.
- [ ] **AGT-04 · P2 · Improve:** Clearly distinguish awaiting approval, queued/running, failed, cancelled and completed states when those states are supported by the event protocol.
- [x] **AGT-05 · P2 · Verify:** Confirm, cancel and repeated clicks do not leave stale approvals or submit unintended duplicate actions.
- [x] **AGT-06 · P2 · Improve:** Show a concise completion summary and a direct Open workflow/View result action when a valid artifact reference is available.
- [ ] **AGT-07 · P2 · Verify:** Tool failure identifies the failed step and an appropriate recovery action while preserving any completed work and the user's context.
- [x] **AGT-08 · P2 · Verify:** Multiple tool calls, partial completion, interrupted streams and supported retry/cancel flows maintain accurate operation status.
- [ ] **AGT-09 · P2 · Verify:** Approval previews, progress, errors and result actions remain accessible on mobile and with keyboard/screen-reader navigation.

Acceptance: users can tell what is proposed, what was approved, what is running, what failed and where the outcome is. Frontend grading does not certify autonomous execution safety or model correctness.

## 17. Harness, regression checks and regrading

- [x] **QA-01 · P1 · Improve:** Convert the two recorded critical interaction observations into failing regression assertions for upload scope and wizard keyboard progression.
- [x] **QA-02 · P2 · Improve:** Preserve baseline screenshots and scores; write post-change evidence to a separate run directory.
- [x] **QA-03 · P2 · Improve:** Record commit, relevant working-tree changes, runtime/build mode, browser version, viewport and fixture version so uncommitted UI changes are distinguishable from the baseline commit.
- [ ] **QA-04 · P2 · Verify:** Re-capture all 55 baseline states and update locators only to reflect intended UI changes, never to conceal a failing task.
- [x] **QA-05 · P2 · Improve:** Add coverage for final automation review, alternate wizard branches, narrow dialogs, source recovery, validation result drilldown and supported apply/revert states.
- [x] **QA-06 · P2 · Improve:** Add scope-switching, upload partial failure, agent cancellation/interruption and valid citation-inspection scenarios.
- [ ] **QA-07 · P2 · Verify:** Cover the viewport matrix, essential keyboard journeys, 200% zoom, long content and realistic larger lists.
- [x] **QA-08 · P2 · Verify:** Re-run axe; resolve serious/critical findings and review remaining contrast, naming and interaction-structure findings individually.
- [x] **QA-09 · P2 · Verify:** Run appropriate component/browser regression checks, frontend typecheck/lint and a production build; identify pre-existing failures separately from new regressions.
- [x] **QA-10 · P2 · Verify:** Use the production build for the final screenshot pass; verify the specific StrictMode lifecycle repair in development as well.
- [x] **QA-11 · P2 · Improve:** Maintain explicit coverage labels: visually inspected, frontend interaction tested, fixture-backed, and live integration verified where actually exercised.
- [ ] **QA-12 · P2 · Verify:** Inspect screenshots directly and regrade every area against the original rubric; do not automatically award 8 because a checklist item was implemented.
- [ ] **QA-13 · P2 · Verify:** Publish before/after scores, evidence, resolved findings and remaining limitations in the updated report; verify all report links and gallery behavior.

Acceptance: every reviewed section independently reaches at least 8 for both UI and UX, mobile reaches at least 8, no P1 remains, and no serious/critical accessibility finding remains unexplained and unresolved in the graded states. If any section falls short, iterate on it rather than averaging the shortfall away.

## Implementation order

1. **Reliable foundations:** upload scope, wizard keyboard handling, responsive header/Library, clipped rows and validation lifecycle.
2. **Shared experience:** workspace hierarchy, contextual assistant/activity, shared visual system and accessibility patterns.
3. **Core screens:** Files, Projects, Automations/editor, Library and Explore.
4. **Knowledge workflows:** KB source/status management, validation setup/results/history and improvement review.
5. **Conversation workflows:** chat home/composer, onboarding, attachment feedback, source inspection and agent progress/approval/results.
6. **Evidence and iteration:** expanded regression coverage, fresh production captures, visual inspection and section-by-section regrading until the target is met.

## Boundaries

This backlog covers the requested frontend visual and UX scope. It does not silently expand into a backend rewrite, model tuning, production deployment, permission redesign or new integrations. Existing backend contracts may need small supporting changes when necessary for a verified flow; any operational UI must remain honest about data the current system actually provides. Broad live-model reliability and retrieval accuracy require their own evaluation.
