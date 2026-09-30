# Vandalizer: visual and UX upgrade checklist

Tracking issue: [GitHub issue #964](https://github.com/ui-insight/vandalizer/issues/964).

> **Approved scope:** All 169 checklist items and additions A1–A14 are in scope following explicit user approval. See [scope decisions](ui-ux-scope-decisions.md). Track the implementation in one consolidated GitHub issue.

Target: every reviewed area earns **at least 8/10 for visual UI and 8/10 for UX**, with mobile independently meeting the same bar. Each section must independently meet the target.

Baseline: review dated September 25, 2026, commit `560ccd5decc8d01df8fd3fa68a96d0c617f1a3f9`; 55 distinct captured states. [Baseline report](../artifacts/visual-review/2026-09-25/report.md).

This is the complete implementation and verification backlog for the reviewed scope. It is not a claim that every untested interaction is broken, nor an exhaustive audit of the backend. Local implementation and the visual/UX acceptance review are complete. All 169 items have evidence recorded in the final report and dated progress log; every reviewed area and mobile meet the 8/10 target. This does not certify live backend/model execution or deployment.

## How to read the list

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
- [x] **SYS-04 · P2 · Improve:** Preserve useful panel choices during a session without restoring layouts that do not fit the current viewport.
- [x] **SYS-05 · P2 · Improve:** Make the active section and current project context unmistakable, including when opening an item from chat or the Library.
- [x] **SYS-06 · P2 · Improve:** Use consistent placement for the page title, description, primary action, search, filters and secondary actions.
- [x] **SYS-07 · P2 · Improve:** Establish one coherent vocabulary for Files, Projects, Automations, Knowledge, Library and Explore; distinguish location from ownership/sharing scope.
- [x] **SYS-08 · P2 · Verify:** Back navigation, section switches and opening/closing contextual panels preserve the intended selection, draft and scroll position.

Acceptance: the active task owns the visual hierarchy; supporting panels are discoverable without dominating; navigation never silently discards work.

## 2. Shared visual system

- [x] **VIS-01 · P2 · Fix:** Reconcile the light file/project/editor surfaces, dark automation/KB surfaces, blue wizard controls and purple validation controls into a consistent theme hierarchy.
- [x] **VIS-02 · P2 · Improve:** Standardize page, section, card and metadata typography. Increase essential metadata that is currently too small to scan.
- [x] **VIS-03 · P2 · Improve:** Use shared spacing, padding, row heights, border radii, borders and elevation across lists, cards and dialogs.
- [x] **VIS-04 · P2 · Improve:** Standardize primary, secondary, quiet and destructive action styles, including disabled, hover, focus and loading states.
- [x] **VIS-05 · P2 · Improve:** Standardize form labels, optional/required indicators, help text, validation messages and error placement.
- [x] **VIS-06 · P2 · Fix:** Give important names and task content more space than decoration, promotional copy and low-value metadata.
- [x] **VIS-07 · P2 · Improve:** Use consistent status badges with text and appropriate icons; reserve color for meaning rather than decoration.
- [x] **VIS-08 · P2 · Verify:** Long names, multiline descriptions and translated/browser-enlarged text wrap sensibly without hiding actions.

Acceptance: screens look like parts of one product, with consistent hierarchy and readable information at normal zoom and enlarged text.

## 3. Responsive behavior and accessibility

- [x] **ACC-01 · P1 · Fix:** Remove the 521px document width at a 390px viewport by making the header, brand, support and account controls responsive.
- [x] **ACC-02 · P1 · Fix:** Replace desktop-only sidebar/list arrangements with usable narrow-screen layouts, particularly Library and Files.
- [x] **ACC-03 · P2 · Improve:** Make workspace panels stack, collapse or switch predictably on small screens while keeping the active task reachable.
- [x] **ACC-04 · P2 · Verify:** No unintended page-level horizontal scrolling at 320, 390, 768, 1280 and 1440px. Explicitly contained wide data may scroll when appropriate.
- [x] **ACC-05 · P2 · Verify:** Dialogs and pickers fit short and narrow viewports; their titles, content and final actions remain reachable.
- [x] **ACC-06 · P2 · Fix:** Add descriptive accessible names to the Projects create button, KB sort select and any other unnamed controls identified by the harness.
- [x] **ACC-07 · P2 · Fix:** Remove nested interactive structures in KB cards and source rows; make row opening and secondary actions separate keyboard targets.
- [x] **ACC-08 · P2 · Fix:** Correct measured low contrast in timestamps, counts, tags and secondary metadata. Target 4.5:1 for normal text and 3:1 for large text and essential UI graphics.
- [x] **ACC-09 · P2 · Verify:** Keyboard focus is visible and follows a logical order through navigation, tables, cards, menus, tabs and dialogs.
- [x] **ACC-10 · P2 · Verify:** Dialogs set focus appropriately, contain focus while open, close with Escape when appropriate and restore focus to their trigger.
- [x] **ACC-11 · P2 · Improve:** Make row actions usable without hover, and make small controls practical touch targets without crowding their neighbors.
- [x] **ACC-12 · P2 · Verify:** Upload, processing, validation and tool-state changes are announced appropriately without flooding assistive technology.
- [x] **ACC-13 · P2 · Verify:** Essential tasks remain usable at 200% zoom and with reduced motion; loading indicators do not rely exclusively on animation.

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
- [x] **AUTO-02 · P2 · Improve:** Present trigger, input location, action and output in a concise readable summary.
- [x] **AUTO-03 · P2 · Improve:** Show last outcome and next scheduled run when the API supplies them; clearly distinguish no history, unavailable data and a failed run.
- [x] **AUTO-04 · P2 · Fix:** Give the editor sufficient width so normal titles and configuration fields do not wrap unnecessarily.
- [x] **AUTO-05 · P2 · Fix:** Unify list and editor visual styles using the shared theme and control patterns.
- [x] **AUTO-06 · P2 · Improve:** Keep enabled state, ownership/sharing, Save and Run now easy to distinguish; communicate unsaved edits.
- [x] **AUTO-07 · P2 · Verify:** Search/filter combinations, empty results and clearing filters work predictably.
- [x] **AUTO-08 · P2 · Verify:** Enable, pause, edit and manual-run actions provide accurate pending, success and failure feedback and prevent accidental duplicate submission.
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
- [x] **KB-11 · P2 · Verify:** Sharing/ownership controls reflect actual permissions, and list/detail/chat source scope remains consistent after navigation.
- [x] **KB-12 · P2 · Verify:** Empty, building, partially ready, all-failed and validated KBs have distinct, usable presentations.

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
- [x] **VAL-17 · P2 · Verify:** All validation views and wizard actions remain usable on narrow and short screens, with no hidden primary action.

Acceptance: a user can set up a meaningful check, understand what it costs and measures, interpret the result and deliberately choose whether to apply an improvement. Fixture scores do not establish real model accuracy.

## 10. Explore / catalog

- [x] **EXP-01 · P2 · Fix:** Use Explore consistently for discovery; describe public/team/personal scope separately from navigation labels.
- [x] **EXP-02 · P2 · Fix:** Use one contextual catalog search instead of displaying competing Library and catalog search fields.
- [x] **EXP-03 · P2 · Fix:** Collapse or remove the wide single-option All Knowledge Bases sidebar.
- [x] **EXP-04 · P2 · Fix:** Standardize Checked/Verified terminology and explain what each trust indicator actually establishes.
- [x] **EXP-05 · P2 · Improve:** Prioritize item purpose, type, required inputs and intended output in cards and details.
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
- [x] **LIB-06 · P2 · Improve:** Make search and useful recent/pinned work prominent, with consistent create and browse actions.
- [x] **LIB-07 · P2 · Verify:** Item opening, type filters, sorting, favorites, pins and folder actions target the correct item and provide visible feedback.
- [x] **LIB-08 · P2 · Verify:** Empty Library, empty folder, no results, unavailable item and large populated lists have clear, efficient states.
- [x] **LIB-09 · P2 · Verify:** Long names and mixed workflow/extraction/prompt items remain readable with reliable row actions on desktop and mobile.

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
- [x] **CHAT-10 · P2 · Verify:** Send-button state, Enter/Shift+Enter, model selection and errors remain understandable with keyboard, touch and assistive technology.

Acceptance: composing, sending, reading, interrupting and recovering from a conversation feel predictable, and the source scope is always clear.

## 13. Basic chat onboarding

- [x] **ONB-01 · P2 · Fix:** Focus the first session on two clear starts: upload a document or try the sample demo.
- [x] **ONB-02 · P2 · Fix:** Remove marketing/design-strategy paragraphs that delay the first useful action.
- [x] **ONB-03 · P2 · Improve:** Guide one complete first success: choose a source → ask a suggested question → inspect the supporting evidence.
- [x] **ONB-04 · P2 · Fix:** Replace the unconditional promise that every answer links to sources with accurate language about source-grounded tasks.
- [x] **ONB-05 · P2 · Improve:** Keep sample content visibly identified as a demo and provide a clear transition into the user's own work.
- [x] **ONB-06 · P2 · Verify:** First visit, dismissed onboarding, returning user and the optional guided-tour overlay coexist without trapping focus or repeatedly interrupting work.
- [x] **ONB-07 · P2 · Verify:** The first useful action and demo evidence are reachable on mobile without excessive scrolling.

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
- [x] **AGT-04 · P2 · Improve:** Clearly distinguish awaiting approval, queued/running, failed, cancelled and completed states when those states are supported by the event protocol.
- [x] **AGT-05 · P2 · Verify:** Confirm, cancel and repeated clicks do not leave stale approvals or submit unintended duplicate actions.
- [x] **AGT-06 · P2 · Improve:** Show a concise completion summary and a direct Open workflow/View result action when a valid artifact reference is available.
- [x] **AGT-07 · P2 · Verify:** Tool failure identifies the failed step and an appropriate recovery action while preserving any completed work and the user's context.
- [x] **AGT-08 · P2 · Verify:** Multiple tool calls, partial completion, interrupted streams and supported retry/cancel flows maintain accurate operation status.
- [x] **AGT-09 · P2 · Verify:** Approval previews, progress, errors and result actions remain accessible on mobile and with keyboard/screen-reader navigation.

Acceptance: users can tell what is proposed, what was approved, what is running, what failed and where the outcome is. Frontend grading does not certify autonomous execution safety or model correctness.

## 17. Harness, regression checks and regrading

- [x] **QA-01 · P1 · Improve:** Convert the two recorded critical interaction observations into failing regression assertions for upload scope and wizard keyboard progression.
- [x] **QA-02 · P2 · Improve:** Preserve baseline screenshots and scores; write post-change evidence to a separate run directory.
- [x] **QA-03 · P2 · Improve:** Record commit, relevant working-tree changes, runtime/build mode, browser version, viewport and fixture version so uncommitted UI changes are distinguishable from the baseline commit.
- [x] **QA-04 · P2 · Verify:** Re-capture all 55 baseline states and update locators only to reflect intended UI changes, never to conceal a failing task.
- [x] **QA-05 · P2 · Improve:** Add coverage for final automation review, alternate wizard branches, narrow dialogs, source recovery, validation result drilldown and supported apply/revert states.
- [x] **QA-06 · P2 · Improve:** Add scope-switching, upload partial failure, agent cancellation/interruption and valid citation-inspection scenarios.
- [x] **QA-07 · P2 · Verify:** Cover the viewport matrix, essential keyboard journeys, 200% zoom, long content and realistic larger lists.
- [x] **QA-08 · P2 · Verify:** Re-run axe; resolve serious/critical findings and review remaining contrast, naming and interaction-structure findings individually.
- [x] **QA-09 · P2 · Verify:** Run appropriate component/browser regression checks, frontend typecheck/lint and a production build; identify pre-existing failures separately from new regressions.
- [x] **QA-10 · P2 · Verify:** Use the production build for the final screenshot pass; verify the specific StrictMode lifecycle repair in development as well.
- [x] **QA-11 · P2 · Improve:** Maintain explicit coverage labels: visually inspected, frontend interaction tested, fixture-backed, and live integration verified where actually exercised.
- [x] **QA-12 · P2 · Verify:** Inspect screenshots directly and regrade every area against the original rubric; do not automatically award 8 because a checklist item was implemented.
- [x] **QA-13 · P2 · Verify:** Publish before/after scores, evidence, resolved findings and remaining limitations in the updated report; verify all report links and gallery behavior.

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
