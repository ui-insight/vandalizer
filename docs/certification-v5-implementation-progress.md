# Vandalizer certification implementation progress

Implement the [162-item upgrade checklist](certification-v5-upgrade-checklist.md) until every audited dimension and each module’s Vandalizer 5.0 alignment has evidence supporting at least 8/10. The [October 2 audit](reviews/certification-v5-audit.html) remains the unchanged baseline.

## Current checkpoint

- **Authorization:** the user requested that implementation begin on October 2, 2026.
- **Accepted items:** 74/162. **Remaining:** 88. C8-VIS-05 was reopened and revalidated after repairing the panel renderer; see checkpoint 11. Item count measures acceptance work, not percentage of engineering effort or achieved quality.
- **Current milestone:** correct supported teaching and reconcile acceptance evidence. Historical guidance and current copy are verified through 328; optional transfer and maintenance foundations remain locally verified through 301. Release verification and representative learner observations remain separate gates.
- **Last accepted checklist item:** C8-CONTENT-08 at checkpoint 328. Latest verified checkpoints are 20–328; the numbered log preserves earlier acceptances, implementation details and evidence.
- **Next task:** consolidate outstanding interaction acceptance against existing evidence, starting with modal and handoff focus. The historical star discrepancy is now disclosed; its equivalent-assessment gate remains open. The baseline QA-script fingerprint gap is recorded at 306; it does not block independent teaching work. Deployment configuration changes also need recorded compatibility review evidence. Production equivalence policy, bridge observation, actual cohort reconciliation and live grading calibration remain open; live calibration stays deferred.
- **Verified foundations:** immutable course/enrollment/credential history and fenced completion recovery; 74 unpublished lesson replacements across all eleven modules; 17 recognition scenarios covering all five scenario-choice outcomes; saved lab inputs and execution, authenticated learner decisions, automatic-review receipts and technical recovery; read-only course comparison, synthetic cohort inventory, saved-feedback delivery and applied execution settings. Details and evidence remain in the numbered checkpoints below.
- **Unfinished release gates:** release verification for all 33 outcomes, calibrated live grading, complete learner practical delivery, actual cohort reconciliation and rollout, full-course graduation with live providers, and full accessibility/learner observation. No 8/10 reassessment or release-ready claim has been made.
- **Current blockers:** no blocker for independent teaching/versioning work; the practical review policy is resolved as automatic-only with LLM assistance permitted and no staff queue. The user selected optional upgrades on October 2, 2026. Live-model calibration is deferred at the user’s request on October 5/6 so independent work can continue overnight. It remains a release gate; live deployment/model configuration has not been rechecked while calibration is deferred. Subsequent persistence work uses explicitly isolated QA MongoDB, not the application database. Do not keep requesting environment details while this gate is deferred. Independent work continues. Migration, screen-reader and learner-observation gates remain open.
- **Historical verification summary (October 7; subsequent work is in the numbered checkpoints):** All 74 draft lessons passed 370 native-zoom captures. Graduation, certificate focus and module-based completion were repaired and rechecked. Seven certification tool payload contracts passed 130 backend tests, 67 frontend tests and 52 normal/native-zoom browser captures with GET-only uncertain-response recovery. Panel bounds/focus and workspace preservation passed 33 tests and 42 captures; chat/panel certificate access passed 50 tests, 42 captures and 20 byte-verified downloads. Mobile reading-width and retained-state checks passed 8 tests and 51 normal/native/enlarged-text captures. Saved-result consistency passed 179 unit and 156 persistence checks. Direct navigation passed 53 targeted frontend tests and 70 browser captures; cross-browser resume/handoff passed 40 overlapping frontend tests, three persistence checks and nine connected captures. Course semantics and readable status alternatives passed 46 tests and 61 browser captures. Additional WebKit verification passed 103 captures and 12 byte-verified downloads; Firefox launch remains unverified. XP milestones passed 17 tests and 66 final normal/native/enlarged-text captures. Explicit combined draft outcomes passed 10 persistence cases and one authenticated HTTP case without credit or staff review. Foundations draft assignment consistency passed 35 unit/catalog cases, nine scope persistence cases, 52 frontend tests and 54 browser captures. Counts are 27/162 accepted, 33 draft mechanisms implemented, zero release-verified.
- **Evidence ledger:** [Search retained browser runs](reviews/certification-v5-evidence-ledger.html) or inspect the [machine-readable coverage and provenance](reviews/certification-v5-evidence-ledger.json). Regenerate with `python3 scripts/build_certification_qa_ledger.py`. Capture counts include repeats and failures; checklist acceptance remains authoritative.
- **Working state:** local certification checkpoint commits are recorded on `major/agentic-chat` at the user’s October 9 request. Content: `54a7892f`; backend: `98dc6db1`; frontend: `9cc91de6`; QA/tracker: `82673dc8`; the visual follow-up is checkpoint 300. The preceding shared HEAD was `af6311a1eead3531fbe7cf7f62fc366cbfb98f3a`. Unrelated work remains outside this task. The inbox was separately committed as `a43a06f0`; knowledge-base and panel-refresh changes remain separate from the certification batch. These are development checkpoints, not release acceptance. No push, deployment, learner migration, course publication or external communication has occurred.
- **GitHub reconciliation, October 5:** Repository searches found no open certification issues. The six issues matching certification are closed: [#434](https://github.com/ui-insight/vandalizer/issues/434), [#488](https://github.com/ui-insight/vandalizer/issues/488), [#912](https://github.com/ui-insight/vandalizer/issues/912), [#914](https://github.com/ui-insight/vandalizer/issues/914), [#956](https://github.com/ui-insight/vandalizer/issues/956) and [#964](https://github.com/ui-insight/vandalizer/issues/964). #964 is the earlier 169-item workspace UI/UX project, not this 162-item certification upgrade. The repository's two open issues are [#926 starter-example contributions](https://github.com/ui-insight/vandalizer/issues/926) and [#861 injection-detector revival criteria](https://github.com/ui-insight/vandalizer/issues/861). Their status does not complete this certification checklist. No GitHub issue was changed. The user confirmed continuing this separate certification checklist after this reconciliation; unrelated open GitHub issues are outside this task.

- **GitHub reconciliation, October 9:** fresh read-only searches returned 15 open repository issues and no dedicated open certification issue. Several open product issues already have implementation commits on this shared branch; an open label is not proof that implementation is missing. The certification work continues in this local 162-item tracker. No issue was closed, commented on or changed. The October 5 reconciliation above is retained as historical context, not the current open-issue count.

## Delivery scope confirmed October 9

The user explicitly retained the upgrade bridge, fair credit transfer, focused course-health reporting, maintenance checks and useful administration. Do not remove these outcomes to make the backlog smaller. Consolidate implementation and verification into learner journeys; avoid repeated full-course captures for a local copy change. The 162-item audit remains the acceptance ledger, not 162 separate development projects.

1. **Current corrections:** source/approval/recovery teaching and historical guidance (305–317), with batch/output/governance follow-up at 319; introductory correction is verified at 320; process mapping, workflow design and advanced-node corrections are verified at 321; validation wording is verified at 322; original lab controls are verified at 323; module-level objectives/tips are verified at 324 and exercise directions/legacy grading limits at 326.
2. **Existing-learner upgrade:** optional bridge and explicit outcome-equivalence rules; retained original credentials/progress; automatic grading; no routine staff queue. Unknown legacy history must not become inferred 5.0 credit. Separate read-only eligibility from authorized, durable credit application.
3. **Operational maintenance:** use existing administration surfaces and focused version-specific failure reporting; product changes trigger course compatibility checks.
4. **Consolidated release verification:** complete learner journeys, actual practical outputs, grading rejection cases, accessibility, publication/recovery and actual-cohort reconciliation. Deferred live calibration remains a stated gate, not replaced by fixture evidence.

No new completion date is claimed. Report delivered behavior and concrete remaining blockers at each batch, rather than screenshot totals as progress.

## Tracking rules

The checklist is the authoritative list of acceptance items. This log records the current checkpoint, evidence, dependencies and decisions. The baseline audit and later reassessments record quality; their scores are not inferred from the number of checked boxes.

Use five states in checkpoint notes: **Not started**, **In progress**, **Awaiting verification**, **Complete**, and **Blocked**. Only Complete gets a checked box. An implemented change awaiting an actual backend run, browser inspection or learner observation remains unchecked. For a Blocked item, name the precise missing dependency and the next action; continue independent work.

Work in small batches with a named set of checklist IDs. At each checkpoint:

1. Inspect current source and reproduce the relevant failure or establish the starting behavior.
2. Make the bounded change while preserving existing learner data and unrelated workspace behavior.
3. Run verification appropriate to the claim: contract tests, persistence checks, browser captures, model execution or observed learner work.
4. Record source references, commands/results, evidence paths and remaining limits here. Mark only fully satisfied items complete in the checklist.
5. Update the accepted count and the exact next task. Keep working-tree/commit and publication state explicit.

Use small reviewable commits as implementation checkpoints are prepared for version control; record actual commit IDs here once created. Do not use commits or test counts as substitutes for acceptance evidence. Keep previous capture directories and failures as historical evidence rather than overwriting them with fixed states.

## Milestones

| Milestone | Work and dependency | Exit evidence | State |
| --- | --- | --- | --- |
| 1 Immediate reliability and usability | Progress contract, live-result synchronization, mobile layout, contrast and inaccurate card feedback/copy. Do not change assessed requirements yet. | Relevant regressions pass and changed UI states are inspected at the affected widths. Real course entry is tracked separately from the repaired serializer/tool contract. | In progress |
| 2 Protect course identity and earned work | Snapshot current teaching, exercises and rubric; define the shared outcome contract; implement versioned enrollments, lesson position and credential issuance. | Supported old/new enrollments coexist with stable identities and reproducible requirements. | In progress: immutable release lifecycle verified; explicit enrollment and conditional chat/panel delivery implemented; rollout remains disabled |
| 3 Upgrade teaching and assessment | Shared lesson interactions, eleven module updates and evidence-bound grading against a draft version. | Every outcome has an assessment and invalid evidence is rejected; actual labs execute successfully. | In progress: all 74 teaching drafts and all five recognition outcomes have local evidence; complete practical assessment, live calibration and release remain open |
| 4 Prepare existing learner transition | Cohort inventory, explicit credit equivalence, bridge, administrative controls and reversible migration. | Dry-run reconciliation, mid-attempt protection, restart and rollback evidence. | In progress: optional upgrade/return/resume and synthetic migration rehearsal verified; actual cohorts, equivalence, bridge and rollout remain open |
| 5 Validate and regrade | Complete responsive, accessibility, persistence, model, lifecycle and learner-observation gates. | All six dimensions and all eleven modules independently grade at least 8; unresolved required evidence stays visible. | Not started |

Dependencies determine sequence; milestone labels do not override individual checklist requirements. Visual fixes can proceed alongside versioning work when they do not change course requirements.

## Immediate work queue

This is the current queue, replacing the October 2 sequence. Checked items do not return to the queue merely because their original milestone is unfinished. Consolidate checks by learner journey; reuse retained evidence when source and behavior are unchanged.

| Order | Items | Concrete remaining work and dependency |
| --- | --- | --- |
| 1 | Related M05-04 and VERSION-06 | Copy audit accepted at 328. Historical star mismatch is disclosed but needs a separately reviewed equivalent-assessment/support decision; a notice does not close it. |
| 2 | Open CHAT/VIS/A11Y interaction items and QA-08/10 | Reconcile existing state coverage, then exercise only missing or changed interactions. Keep real persistence, mobile keyboard and actual assistive-technology evidence distinct from fixture rendering. |
| 3 | MIGRATE-02/03/06/08/09/10; VERSION-06/11/12; OPS-01/02/03/06/07 | Reuse implemented continuation/transfer/operations checks. Remaining acceptance needs actual cohort reconciliation, reviewed equivalence/support policy, operational evidence and coherent release configuration. No automatic reset, routine staff grading or publication is authorized. |
| 4 | Practical module outcomes; GRADE-04/09/10/12; QA-04/05/06 | Execute and inspect actual course work and calibrate automatic review when the user resumes the deferred live-model gate. Mocked engine success and synthetic grading cannot close these items. Continue independent work while deferred. |
| 5 | QA-07/09/11/12/13/14 and associated accessibility requirements | Complete release-wide coverage, actual screen-reader/learner observations, issued downloads and operational rehearsal; then regrade all six dimensions and eleven modules. Do not infer 8/10 from the acceptance count. |

The checklist retains all 89 open acceptance requirements. These groups consolidate work; they do not defer or remove valuable scope. Ask for missing access, decisions or observations only when the dependent work is concrete and independent work cannot progress.

## Completed checkpoints

### Checkpoint 1 Progress contract on October 2 2026

**Accepted:** C8-CHAT-01. **Status:** Complete. **Related but still open:** C8-CHAT-03 and C8-QA-02 through C8-QA-04.

**Problem:** `get_certification_progress` read `streak_days` even though the real `get_progress_dict` response no longer contains it. Existing mock responses supplied the retired field and hid the failure.

**Change:** removed the obsolete read and the streak promise from the tool description. Updated the shared test fixture to match the service contract, including the Boolean unlock flag. Added six regression cases: new, active and certified progress, each with and without a legacy stored streak. These call the actual service serializer and actual chat tool, mocking only record retrieval.

**Source:** [chat tool](../backend/app/services/chat_tools.py), [regression tests](../backend/tests/test_chat_cert_tools.py). The progress model, serializer, learner records, lessons, rubric and course requirements were not changed.

**Verification:** all six new cases failed with `KeyError: streak_days` before the fix. After the fix, 50 focused certification tests passed, including the six contract cases and existing chat-tool, governance, extraction-field and output-delivery coverage. Targeted Ruff and whitespace checks are recorded with the checkpoint evidence.

Run from `backend`:

```bash
.venv/bin/python -m pytest tests/test_chat_cert_tools.py tests/test_certification_governance.py tests/test_certification_extraction_fields.py tests/test_certification_output_delivery.py -q --disable-warnings --junitxml=../artifacts/visual-review/certification-upgrade-2026-10-02-contract/pytest.xml
.venv/bin/ruff check app/services/chat_tools.py tests/test_chat_cert_tools.py
```

**Evidence:** [JUnit results](../artifacts/visual-review/certification-upgrade-2026-10-02-contract/pytest.xml) and [checkpoint manifest](../artifacts/visual-review/certification-upgrade-2026-10-02-contract/checkpoint.json). Captures and generated test evidence are local artifacts; the source tests and this result summary remain reproducible from the repository.

**Limits:** this proves the tool/serializer contract, not a live database enrollment or full model-driven start/resume/graduation. It does not fix buffered completion refresh, mobile rendering, grading validity or course versioning. Baseline grades remain unchanged.


### Checkpoint 2 Live refresh and readable cards on October 2 2026

**Accepted:** C8-CHAT-04, C8-CHAT-06, C8-VIS-01, C8-VIS-05, C8-VIS-06. **Still open:** full synchronization (migration does not exist), complete responsive/accessibility coverage, and formal regrade.

Live `tool_result` events now trigger successful certification-write refresh directly from `useChat`; loading history never triggers that callback. Duplicate events within a response are deduplicated. Progress reads reject stale responses and preserve the last successful state. Chat and panel expose a shared failure notice with a GET-only retry after a saved action. Tests cover buffered/incremental delivery, replay/remount, failed/malformed write classification, racing reads and retry recovery.

Lesson headings stack title and position; cards shed one nested mobile indent, wrap buttons and field labels, and use darker text tokens. Module overview/instructions use sanitized Markdown and ordered procedures show numbers. Check cards no longer say “All checks passed” when their individual checks disagree; this does not repair weak grading. Certificate banner values now come from actual progress rather than a fixed 1850 XP claim (verification pending with the next capture batch).

**Evidence:** 51 focused frontend tests passed before shared-practice work. TypeScript passed. Targeted ESLint passed with two existing dependency warnings. Production build passed with existing bundle/import warnings. [28 rendered states](../artifacts/visual-review/certification-upgrade-2026-10-02-ui/manifest.json) include all eleven module actions at 390px, long lesson top/bottom at 320/390/768/1440, and completion refresh. [Recovery capture set](../artifacts/visual-review/certification-upgrade-2026-10-02-recovery/manifest.json) demonstrates a deliberately failed progress read and exactly one GET retry, with no repeated write. Screenshots at 320px and the saved-state recovery notice were inspected. The initial UI batch has one remaining panel contrast failure, repaired in source and awaiting recapture. Model/backend responses in browser runs are synthetic.

### Checkpoint 3 Preserve the pre-upgrade course on October 2 2026

**Accepted:** C8-VERSION-01. [Preservation package](../backend/certification-releases/legacy-snapshot-2026-10-02/README.md) contains course assets, all application source dependencies, lockfiles, the original validators and certificate code from the audit baseline commit. [Snapshot utility](../scripts/snapshot_certification.py) verifies the archive digest and every source hash and extracts only to a new destination. All 928 files verified. The extracted original backend passed 54 archived certification tests, including rubric and PDF tests. No live records were read or migrated.

The package is a reproducible repository snapshot, not a historical course-version assertion for existing learners. Old data still has unknown historical provenance. Enrollment pinning, migration, immutable credentials and version-aware delivery remain open.

### Checkpoint 4 Shared lesson interactions and contrast on October 2 2026

**Accepted:** C8-JOURNEY-04, C8-JOURNEY-05 and C8-A11Y-01. **Still open:** overall accessibility, server-side answer/cursor persistence, payload schemas, full responsive reflow and versioned teaching publication.

Chat and panel share all eight diagrams and formative knowledge checks. Practice uses labeled native radio controls, explicit checking, announced feedback and correction; it does not award assessed credit. Wide diagrams and example tables use a named keyboard-focusable scrolling region with a visible text explanation. Mobile course bubbles and practice controls have less nested padding. The exporter includes diagram references and rejects stale data in both `make frontend-ci` and npm CI.

The browser found a capture-phase state update that reset native radios before their change events. `ChatPanel` now records reading position without rendering in click/key capture; its ordinary scroll handler retains navigation-state updates. Dedicated browser checks verified pointer and keyboard selection. The expanded interaction run verified wrong-answer feedback, correction and shared panel rendering. The initial failed run and later load-related timeout remain in separate evidence directories.

**Final evidence:** [22-state acceptance capture](../artifacts/visual-review/certification-upgrade-2026-10-02-accepted/manifest.json) has zero axe violations. It includes all eight diagrams at 320px, practice/feedback, panel teaching, chat and panel certified states, actual certificate-banner XP, successful completion refresh and a deliberately failed read followed by exactly one read-only retry. Narrow table/diagram screenshots were inspected after repair. Earlier 28-state evidence covers all eleven module actions at 390px and lesson layouts at 320/390/768/1440. Browser responses remain synthetic; these captures do not prove live grading or model behavior.

**Verification:** 159 chat/certification frontend tests passed with `--maxWorkers=2`. The initial default-worker run hit 14 timeouts under heavy machine load; it is not counted as passing. TypeScript and production builds passed after the final frontend changes. Targeted ESLint passed with the existing ChatPanel dependency warning; Ruff passed. The real lesson export/tool test covers all 74 identities, eight diagrams and 18 practice checks. All 64 focused backend tests passed; [JUnit output](../artifacts/visual-review/certification-upgrade-2026-10-02-accepted/backend-tests.xml) and a [source/build checkpoint manifest](../artifacts/visual-review/certification-upgrade-2026-10-02-accepted/checkpoint.json) are recorded in the acceptance evidence directory. No original lesson text or practice answers changed; the JSON additions are authored IDs/revisions and diagram references.

### Checkpoint 5 Immutable releases and staged enrollment delivery on October 5 2026

**Accepted:** C8-VERSION-02. **In progress:** C8-VERSION-03/04/05/06/09/11/12 and optional transition infrastructure. No overall quality score has been raised.

Published course manifests pin teaching, exercises, reflection questions, panel definitions, level/tier structure, sample PDFs and the installed preserved rubric by digest. Draft, published, retired and existing-learner support states are validated separately. Local authoring uses a lock and atomic registry replacement; publication requires the reviewed digest and never selects a default. CI checks packages and rejects changes/removal of previously published definitions. The 11-module, 74-lesson continuation package is still **draft**, with no configured enrollment defaults; its manifest SHA-256 is `54f74731d64f6c92b94252a3ff4e3cb60f5955c6a0029118842132a9cd7e0195`.

Explicit enrollments reference one progress record and course definition. Restartable initialization preserves legacy records and marks their historical version unknown. Duplicate, missing, cross-user and inconsistent records fail closed. A separate selection controls the active course. Serialized writes persist their course/rubric identity, reject stale submissions and block internal activation during work. An interrupted cleanup stays blocked for reconciliation; this is not a completed attempt journal or recovery mechanism.

The conditional runtime pins chat tools and certification API/service calls to the same package. The frontend fetches matching progress and course definitions, uses manifest totals and prerequisites, sends enrollment identity on writes and rejects mismatched delivery. Historical chat cards cannot submit against another selected course. Local lesson positions use lesson IDs scoped to enrollment and preserve old numeric keys. A browser-discovered authentication timing bug now restores the saved module once the user identity loads. Reflection saves no longer display unearned stars, and grading-card headers wrap at narrow widths.

**Verification:** 210 backend tests passed, including 24 isolated real-MongoDB integration cases and both live/preserved grading behavior. Tests cover concurrent initialization, interrupted initialization, source preservation, selection/write conflicts, actual HTTP/chat grading and reflection paths, concurrent course isolation and stale/missing request identities. 161 frontend tests passed across 28 files. TypeScript/production build, targeted ESLint/Ruff, lesson-export parity, release checks and whitespace checks passed. Existing frontend test warnings and production bundle/import warnings remain.

**Evidence:** Ten browser states passed with zero axe violations; the narrow grading header, resumed lesson and saved-reflection screenshots were inspected. [backend JUnit](../artifacts/visual-review/certification-versioning-2026-10-05/backend-tests.xml), [frontend JUnit](../artifacts/visual-review/certification-versioning-2026-10-05/frontend-tests.xml), and [browser capture manifest](../artifacts/visual-review/certification-versioning-2026-10-05-ui-attempt8/manifest.json). Browser evidence uses synthetic API responses with the real built frontend; backend persistence tests use disposable databases. Earlier failed capture attempts are retained, including the actual resume defect. No live model or actual learner migration was exercised.

**Rollout remains disabled:** `certification_versioning_enabled=False`; no publication, deployment, existing-learner transition or notification occurred. The internal activation primitive has no public endpoint. Credit preview/equivalence, immutable credentials, durable attempts/recovery, server resume, remaining user-only supporting readers/writers, complete lab execution, cohort reconciliation and rollback are still open. Disabling the flag after versioned enrollment begins is not a verified rollback. The preserved rubric retains known weak assessment rules; this work does not establish 5.0 competence.

### Checkpoint 6 Server lesson positions on October 5 2026

**In progress:** C8-JOURNEY-01/02/03 and C8-VERSION-04. Accepted count remains **11/162**; live-model, complete cross-device/browser and legacy-cursor transition evidence are still open.

Versioned progress now stores a stable module/lesson identity, authored revision, content digest and save timestamp, separately from credit. A position revision rejects stale writes from another session. Panel navigation and an explicit “Save this place” control use the pinned API; failed saves remain visible with a GET-only refresh. Fresh versioned panels restore the server module and lesson even after local course storage is cleared. Reading alone does not award XP, stars or completion, and a resumed lesson does not mark the first lesson viewed.

Chat progress exposes the same cursor. The lesson tool accepts its stable identity, and a navigation-only save tool records the viewed lesson with the expected revision. Coaching instructions use the saved position and returned course totals. Historic chat replay remains read-only; live successful navigation saves refresh shared progress.

**Verification:** 54 backend persistence/chat tests passed, including an actual HTTP-to-chat-to-HTTP resume, stale-tab conflict, invalid lesson/revision rejection, and preservation of prior credit, reflections and lab references. 73 LLM-service tests passed. 32 focused frontend tests passed, including server-over-local restoration, failed-save recovery without a repeated write, current revision use, live-write classification and authentication arriving after server progress. Production build/typecheck, targeted lint, export parity, endpoint-map/release and whitespace checks passed.

**Evidence:** [12 browser states](../artifacts/visual-review/certification-position-2026-10-05-ui-attempt2/manifest.json), [backend results](../artifacts/visual-review/certification-position-2026-10-05/backend-tests.xml), [frontend results](../artifacts/visual-review/certification-position-2026-10-05/frontend-tests.xml), and [source/build checkpoint](../artifacts/visual-review/certification-position-2026-10-05/checkpoint.json). Captures include storage-cleared resume, a deliberately rejected stale save, read-only refresh and explicit recovery. Zero axe violations were recorded; desktop resume/conflict screenshots were inspected. Browser responses are synthetic; server persistence is verified separately with disposable MongoDB. Existing tests report dependency deprecations; the first unprivileged Mongo run could not connect through the sandbox and was interrupted, then rerun with local access successfully.

The old local numeric cursor remains untouched. Practice attempts and reflection drafts are not yet persisted by this navigation work. Rollout is still disabled and no existing learner data has been changed.

### Checkpoint 7 Supporting readers and administrator writes on October 5 2026

**In progress:** C8-VERSION-03/09/12 and C8-MIGRATE-04/12. Accepted count remains **11/162**.

Home and feedback now recognize any preserved earned certification instead of whichever user-only progress row happens to be returned first. This is an earned-status Boolean, not an assertion about historical version or 5.0 competency. Background course reads honor the explicit selection without enrolling an untouched user; orphaned or duplicate records require reconciliation. The old fixed onboarding email sequence defers versioned enrollments without advancing its once-per-user cursor. A reviewed version-specific notification sequence remains a rollout gate; no email was sent by this work.

Administrator rows identify the course, selected enrollment and preserved history, with manifest-based module totals and visible reconciliation errors. Search/export retain that identity. Debug unlock requires the reviewed active enrollment and takes the same write boundary as learner actions; it rejects missing/stale identities and in-flight writes, audits the targeted course and never awards credit. Preserved-history and inconsistent rows are read-only. Detail reads can explicitly select an enrollment instead of choosing an arbitrary user-only row.

**Verification so far:** 64 backend tests passed for enrollment/supporting-reader behavior and existing engagement/config/feedback routes; the final 28-test real-Mongo enrollment suite also passed after adding administrator list metadata and historical-row assertions. Six administrator frontend tests passed, including one user with both a historical and selected enrollment. Six tool-registration tests confirm the navigation tool is sequential. Lint, typecheck/build and endpoint-map/release checks passed. Inspection found cramped mobile table cells, repaired with a minimum table width inside the existing named scrolling region and readable action/date cells. The final four-state browser run at 390/1440px passed with zero axe violations; the mobile action view was inspected.

**Evidence:** [backend results](../artifacts/visual-review/certification-readers-2026-10-05/backend-tests.xml), [final enrollment tests](../artifacts/visual-review/certification-readers-2026-10-05/enrollment-tests.xml), [administrator frontend tests](../artifacts/visual-review/certification-readers-2026-10-05/frontend-tests.xml), and [final captures](../artifacts/visual-review/certification-readers-2026-10-05-ui-attempt3/manifest.json) and [source/build checkpoint](../artifacts/visual-review/certification-readers-2026-10-05/checkpoint.json). The earlier fixture failure due to missing authentication configuration is retained in attempt 1.

Immutable credentials, enrollment lifecycle transitions, version-specific completion notifications, interrupted-operation recovery, migration rehearsal and full rollback are still open. No live learner records were inspected or changed.

### Checkpoint 8 Preserved credentials and historical downloads on October 5 2026

**In progress:** C8-VERSION-07/08 and C8-MIGRATE-04/09. Accepted count remains **11/162**. This implements preservation mechanics; assessed 5.0 outcomes, supersession and cohort migration are still open.

Versioned graduation freezes an issuance payload with a deterministic unique identity, learner name, original date, course/manifest/rubric and stored module-credit references. The pending payload is saved with graduation before insert-only issuance. Retries before or after the insert preserve that payload and award no duplicate XP. Credential reads verify both digest and schema/identity, remain independent of the current catalog or selected progress, and require the authenticated owner. Malformed records require reconciliation rather than receiving an invented date or identity.

The explicit legacy-preservation primitive keeps original dates where available and labels unknown dates and historical versions honestly. It never runs as a side effect of a read. Course activation now holds the source write boundary while checking credential preservation and changing selection, preventing graduation from racing between those operations. A pending issuance or certified source without a preserved record blocks activation.

The panel and standalone course show earned-certificate history. Browser QA found that the fullscreen focus trap canceled temporary download links appended outside the dialog; links now stay inside the initiating dialog. PDF QA found missing Latin text in Poppler despite successful MuPDF rendering; embedding the bundled font repaired it. Normal, long-name and Vietnamese legacy samples were rendered and inspected after repair. Broader CJK rendering remains unverified.

**Verification:** 50 initial backend cases passed, followed by 31 enrollment cases after the transition guard. The final 46-case enrollment/PDF/completion run passed after closing the activation race and testing malformed credential data. These runs overlap and are not additive. 35 frontend cases passed. The production build and targeted lint/export/release/endpoint checks passed. Thirteen browser states passed with zero axe violations, including downloading the original certificate after a synthetic course change; the history screenshot was inspected. Browser fixtures are synthetic and persistence tests use disposable MongoDB. Existing dependency warnings remain.

**Evidence:** [final backend results](../artifacts/visual-review/certification-credentials-2026-10-05/final-backend-tests.xml), [frontend results](../artifacts/visual-review/certification-credentials-2026-10-05/frontend-tests.xml), [browser captures](../artifacts/visual-review/certification-credentials-2026-10-05-ui-attempt2/manifest.json) and [checkpoint manifest](../artifacts/visual-review/certification-credentials-2026-10-05/checkpoint.json). Failed browser attempt 1 and pre-font-fix PDF samples are retained separately.

**Limits:** immutable records preserve credential meaning; PDF bytes are rendered by the current template. Stored legacy module credit does not prove new supervision outcomes, so the outcome list is deliberately empty. Supersession, legacy cohort backfill, complete attempt/job reconciliation and durable version-specific completion notifications remain open. An interrupted graduation retry can still miss its completion notification. The flag remains off, all repository packages remain draft, and no live learner data, course publication or notification was changed.

### Checkpoint 9 Batched administrator history reads on October 5 2026

**In progress:** C8-VERSION-03/12. Accepted count remains **11/162**.

Administrator metadata now uses two bulk reads and verifies each distinct course package once per request. It reuses the progress set already loaded for sorting instead of querying and hashing packages for each row. Detail reads use the same validation rules. These are display snapshots; administrator writes still recheck the live selected enrollment under its write boundary.

**Verification:** the mixed 11-row regression requires exactly two metadata queries, no extra progress query and one package verification. Missing selection targets, invalid identities, bad manifest hashes and malformed enrollment records remain read-only without hiding valid learners. The full 33-case enrollment run passed 32 cases and exposed a misplaced assertion in the new test; that assertion was repaired, and all three administrator cases passed on rerun. Ruff and whitespace checks passed. No UI contract or layout changed, so checkpoint 7 remains the relevant browser evidence. This removes the added per-row overhead; it does not claim production-scale pagination or load testing.

**Evidence:** [initial results](../artifacts/visual-review/certification-admin-reads-2026-10-05/backend-tests.xml), [final administrator results](../artifacts/visual-review/certification-admin-reads-2026-10-05/final-admin-tests.xml) and [source checkpoint](../artifacts/visual-review/certification-admin-reads-2026-10-05/checkpoint.json). No live records were used.

### Checkpoint 10 Durable completion attempts on October 5 2026

**In progress:** C8-VERSION-05 and C8-GRADE-02, with C8-MIGRATE-07/09 still open. Accepted count remains **11/162**.

Versioned completion now creates a durable attempt containing the enrollment, module, course/manifest/rubric, all packaged asset digests and a snapshot of prior credit and submitted reflection answers. The journal distinguishes evaluation, saved grade, awarded credit, rejected assessment and execution failure. Saved judgments and results have integrity digests; module credit links back to its attempt, and new credential evidence retains that reference.

A completion receipt is saved in the same progress write as the XP award. Recovery after a lost progress-save response or journal update reuses the original grade/result instead of grading today's mutable workspace again. Changed answers or earned progress prevent applying an older uncommitted judgment. Requests can supply a stable ID; reuse returns the original result, while a new submission after a definite failure receives a new ID. HTTP and chat share those records. The browser retains an uncertain request ID through a panel remount/reload in session storage, with an in-memory fallback when storage is unavailable.

Course activation rejects an unresolved source or target attempt. Interrupted evaluation and lost write-boundary cleanup still fail closed; no timeout assumes a worker stopped. Explicit operational reconciliation/fencing remains a rollout requirement. The journal pins the completion submission, not the beginning of external lab jobs. It preserves reflection answers and grade output, but does not yet freeze every workspace artifact/run revision or establish new 5.0 outcomes. Completion notifications remain a separate unfinished durable-delivery task.

**Verification so far:** eight focused interruption/issuance tests passed, followed by 114 backend course/enrollment/credential/chat/release tests. Twenty frontend tests passed, including retaining retry identity across remount and creating a new identity after a definite failed assessment. The UI no longer labels an uncertain server response as failed requirements or automatically regrades it. The final 41-case enrollment run passed after adding answer snapshots and attempt-to-credential references. A separate recovery regression also passed after excluding navigation-only module state from the saved assessment digest. Typecheck/production build, targeted lint and release/endpoint checks passed. The first outdated build was stopped during heavy memory pressure, then the final source was built successfully. The final 15-state browser run passed with zero axe violations and no unmatched API requests or page errors. It verified the same completion request ID after a 503, page reload, explicit module reopen and successful retry; the uncertainty notice and recovered-completion screenshots were inspected. Earlier runs missed the synthetic lab setup step, timed out during navigation, or incorrectly expected module restoration without a saved lesson position; all are retained. An automatic approval review timed out before launch, then the permitted retry was approved. With no saved lesson position, the panel still opens the curriculum; an unresolved-attempt resume affordance remains open.

**Evidence:** [backend results](../artifacts/visual-review/certification-attempts-2026-10-05/backend-tests.xml), [focused recovery tests](../artifacts/visual-review/certification-attempts-2026-10-05/attempt-tests.xml) and [frontend results](../artifacts/visual-review/certification-attempts-2026-10-05/final-frontend-tests.xml). [Final enrollment tests](../artifacts/visual-review/certification-attempts-2026-10-05/final-enrollment-tests.xml), [navigation recovery regression](../artifacts/visual-review/certification-attempts-2026-10-05/navigation-recovery-tests.xml), [final browser evidence](../artifacts/visual-review/certification-attempts-2026-10-05-ui-attempt4/manifest.json) and [source checkpoint](../artifacts/visual-review/certification-attempts-2026-10-05/checkpoint.json) are recorded. Browser responses remain synthetic; the database tests verify persistence separately. No publication, live migration or external notification occurred.

### Checkpoint 11 Panel exercise formatting and procedure numbers on October 5 2026

**Revalidated:** C8-VIS-05. **Related:** C8-VIS-06. Accepted count returns to **11/162**; no new overall grade is claimed.

Visual inspection found a gap in the earlier formatting acceptance: chat instructions used sanitized Markdown, but the panel still used partial HTML substitutions. Authored italic text showed literal markers, and that path did not sanitize arbitrary HTML. The item was reopened while the panel overview and instructions were moved to the same safe Markdown renderer as lesson text. Supported emphasis, links, code and nested lists now retain their meaning; executable markup and embedded action controls are stripped. Shared styles restore ordered/unordered list markers and visible links.

Procedure numbers now remain visible after module completion instead of turning every step into a checkmark. A legacy module result does not establish that every displayed instruction was individually verified, and the procedure remains useful for later review.

**Verification:** 17 frontend cases passed, including a renderer regression preserving emphasis/code/links/lists while rejecting script, event handlers and JavaScript links. Typecheck/production build, targeted lint and whitespace checks passed. The final 18-state browser run passed with zero axe violations, no unmatched API requests and no page errors. Mobile exercise instructions at 390px and the completed desktop procedure were inspected. The run also retained history downloads, server-position conflict recovery and the same completion request after reload. The first run's final assertion expected Continue to stay on the completed module; the actual UI advances to the next module, so the corrected scenario explicitly reopens the completed module. The failed run is retained.

**Evidence:** [frontend tests](../artifacts/visual-review/certification-markdown-2026-10-05/frontend-tests.xml), [final browser captures](../artifacts/visual-review/certification-markdown-2026-10-05-ui-attempt2/manifest.json), and [source checkpoint](../artifacts/visual-review/certification-markdown-2026-10-05/checkpoint.json). Browser API responses are synthetic. Assessed requirements and packaged lesson/exercise bytes did not change; release/export checks remain separate from display behavior. Broader mobile reflow, actual assistive-technology checks and the formal 8/10 regrade remain open.

### Checkpoint 12 Fenced completion recovery on October 5 2026

**In progress:** C8-VERSION-05 and C8-MIGRATE-07/09. Accepted count remains **11/162**.

Staged progress saves now compare a private database ownership token in the same atomic write. Completion, reflections, lab references, administrator unlock and lesson navigation use that boundary. Closing it leaves a permanent new token; a delayed acquisition or copied old task context cannot overwrite later progress. Attempt binding uses the exact write identity, and pending journal updates compare their owner. The preserved rubric and unversioned fallback remain unchanged.

Internal completion recovery requires the exact reviewed write, selection revision and a recorded reason. It revokes the old worker before reconciling its attempt. Saved credit/results remain intact; an uncommitted saved grade can be retried with its original request; an interrupted evaluation becomes an explicit failed execution with no award. Attempt intent is saved before insertion, covering death between those operations. Recovery itself can restart after failure, and the old worker’s cleanup cannot clear a replacement boundary. A changed marker during review is rejected rather than dropping newly bound attempt intent.

**Verification so far:** the first 53 database/service tests passed after two repairs: the old rubric-read assertion now excludes only the new internal fence metadata, and recovery timestamps now serialize consistently across MongoDB round trips. Failed runs remain in the evidence directory. An initial sandboxed test run could not connect to disposable MongoDB and was stopped; the permitted local-service run succeeded. The final expanded suite passed all 163 affected backend cases, including the two added marker/cursor races. Ruff, release verification and whitespace checks passed. No frontend behavior changed in this checkpoint.

**Evidence:** [final backend results](../artifacts/visual-review/certification-recovery-2026-10-05/backend-tests.xml), [earlier 53-case run](../artifacts/visual-review/certification-recovery-2026-10-05/recovery-tests-attempt2.xml) and [source checkpoint](../artifacts/visual-review/certification-recovery-2026-10-05/checkpoint.json).

**Limits:** internal completion-only recovery is not a complete operational recovery interface. Provisioning/external jobs, pre-fence workers, full recovery audit history, pending-issuance notifications, live cohort rehearsal and rollback remain open. No timeout clears work. No live learner data, rollout flag, course publication or notification was changed.

### Checkpoint 13 Resume unresolved completion on October 5 2026

**In progress:** C8-JOURNEY-09 and C8-VERSION-05. Accepted count remains **11/162**.

Progress and chat reads now expose enrollment-scoped pending completion status without grading or recovering anything. The panel shows the affected module and an explicit saved-result action after an uncertain response, including after reload with no saved lesson cursor. It preserves the original request identity and can use a saved server attempt on another device. In-flight evaluation offers status refresh; interrupted evaluation requires review instead of silently rerunning the grader. The notice remains available when an uncertain request already earned credit and the ordinary Complete Module button is hidden.

Reconciled execution failures carry a stable error code through HTTP and the frontend. They show the execution failure instead of claiming the learner failed the requirements or automatically validating again. A definite terminal result clears the browser’s retry identity; uncertainty retains it. The inactive standalone page source shares the notice, but the actual `/certification` route redirects into the panel.

**Verification:** 82 backend enrollment/chat cases and 49 frontend API/hook/panel cases passed. A frontend test initially inherited an earlier mock rejection; the fixture now resets implementations and supplies the intended saved result. Production build, targeted lint, release/export and whitespace checks passed. The final 23-state browser run passed with zero axe violations, no unmatched requests and no page errors. Resume, in-flight and needs-review states at 390px and resume at 1440px were inspected. The same submission ID survived uncertain response/reload/retry. The capture named `standalone-saved-grade-resume-390` actually verifies the bookmark redirect into the panel, not an independent standalone route. No standalone browser claim is made. Browser responses remain synthetic; separate real-Mongo tests verify persistence. In-app browser connection was unavailable, so the isolated local Playwright harness was used.

**Evidence:** [backend results](../artifacts/visual-review/certification-resume-2026-10-05/final-backend-tests.xml), [frontend results](../artifacts/visual-review/certification-resume-2026-10-05/final-frontend-tests.xml), [browser captures](../artifacts/visual-review/certification-resume-2026-10-05-ui-attempt2/manifest.json) and [source checkpoint](../artifacts/visual-review/certification-resume-2026-10-05/checkpoint.json).

**Limits:** review is an honest blocked state; a learner/admin recovery UI and complete support handoff still need implementation. This does not resolve every failed-grade remediation, saved draft, external job or course-transfer requirement. Rollout remains disabled, all packages remain draft and no live data or notification was changed.

### Checkpoint 14 Truthful grade summaries and course navigation on October 5 2026

**In progress:** C8-GRADE-03 and C8-JOURNEY-01/09. Accepted count remains **11/162**.

Panel/page grade feedback now shares one renderer. “All checks passed” appears only for a nonempty set in which every listed check passed. A preserved course that permits completion with an unmet check instead says “Module requirements met” and keeps the unmet check and explanation visible. The display does not invent required/advisory roles or change the grading rule. Check text wraps at narrow widths; met/not-met text and an accessible star label supplement color/icons.

Course and module labels no longer promise a save simply from leaving. Versioned lessons point to the existing Save this place control; legacy copy identifies browser-local reading position. The curriculum map now receives the selected course’s tier ordering and module membership instead of silently using the old global tier list.

**Verification:** 25 frontend cases passed, including mixed/empty/all-passing feedback and a course with reordered tier membership. Two older assertions were updated for the intentional heading punctuation change. Production build, targeted lint, export and whitespace checks passed. Initial browser inspection found a prohibited label on a generic span; the star group now has an image role. The final 26-state browser run passed, including mixed results at 320/390/1440px, with zero axe violations and no unmatched requests or page errors. The harness now fails on any recorded axe violation. The 320px and desktop mixed-result views were inspected before the semantic-role repair; the final captures retain that layout. Failed accessibility captures remain separate.

**Evidence:** [frontend results](../artifacts/visual-review/certification-feedback-2026-10-05/final-frontend-tests.xml), [final browser captures](../artifacts/visual-review/certification-feedback-2026-10-05-ui-attempt2/manifest.json) and [source checkpoint](../artifacts/visual-review/certification-feedback-2026-10-05/checkpoint.json).

**Limits:** explicit rubric roles, improved assessed requirements, actual screen-reader testing and a formal regrade remain open. Browser API responses are synthetic. No assessed content, rubric, live data, publication or rollout flag changed.

### Checkpoint 15 Reviewed administrator recovery on October 5 2026

**In progress:** C8-VERSION-12 and C8-MIGRATE-07/09. Accepted count remains **11/162**.

The administrator workflow reads one explicit enrollment, shows the affected course/module/attempt and earned progress, and requires a reviewed snapshot, reason and explicit action. Staff inspection is read-only; only a full administrator can apply recovery. Every action stores durable operator intent before revoking anything, followed by an immutable terminal receipt. Repeating the same request returns that receipt. Changed reviews fail closed; if the reviewed worker finishes before revocation, the receipt states that no recovery was applied. No replacement worker is targeted.

A lost recovery response retains the original request, review and reason. Recent history allows its original operator to resume an interrupted request after reopening the screen. Cleanup interrupted inside reconciliation can also recover and restart. Preserved enrollments expose read-only recovery history. The record collection is registered for application initialization and learner account deletion.

**Verification so far:** 171 affected backend cases passed, followed by the final 61-case real-Mongo enrollment suite after adding historical read-only inspection. Twelve database/account-deletion lifecycle cases and 54 frontend cases passed. These test sets overlap. The first build found a missing required email field in a test fixture; that fixture was repaired. Final production build, lint, export/release and endpoint-map checks passed. Ten administrator browser states at 390/1440px passed with zero axe violations, no unmatched requests and no page errors. Mobile/desktop review and mobile history were inspected. The scenario retained the same action after a lost response, produced one receipt with unchanged XP, and restored focus to the initiating row after closing. The initial ten administrator UI tests also passed.

**Evidence:** [affected backend results](../artifacts/visual-review/certification-admin-recovery-2026-10-05/final-backend-tests.xml), [final enrollment tests](../artifacts/visual-review/certification-admin-recovery-2026-10-05/final-enrollment-tests.xml), [lifecycle checks](../artifacts/visual-review/certification-admin-recovery-2026-10-05/lifecycle-tests.xml), [frontend results](../artifacts/visual-review/certification-admin-recovery-2026-10-05/final-frontend-tests.xml), [browser captures](../artifacts/visual-review/certification-admin-recovery-2026-10-05-ui-attempt1/manifest.json) and [source checkpoint](../artifacts/visual-review/certification-admin-recovery-2026-10-05/checkpoint.json). Browser data and responses are synthetic; persistence/permission checks are separate.

**Limits:** this workflow reconciles fenced completion and its own reconciliation operations. It does not recover provisioning or external jobs, invent missing legacy evidence, issue transfer credit or enable optional course activation. Live cohort rehearsal, full external-job recovery and version-specific notification delivery remain open. No live learner data was inspected or changed.

### Additional preservation groundwork

All 74 lessons have explicit authored IDs and revisions, preserved by the exporter and lesson tool. Keep an ID when its meaning remains stable; do not regenerate it after renaming or reordering. Saved numeric positions have not been migrated, so C8-VERSION-04 and server-side resume remain open.

Star upgrades and repeat completion now preserve the module’s first-earned completion date. Unknown legacy dates remain unknown. Three actual-service regression cases cover known/missing dates, XP on an upgrade versus retry, and a reflection save preserving the module completion date while dating its own answers. A lint finding caught an accidental change to the separate reflection timestamp; it was corrected and the real reflection-save regression added before acceptance. This bounded repair does not establish cross-tab idempotency or immutable credential issuance.

The [proposed transition policy](certification-v5-transition-policy.md) defines the credential promise, eleven-module outcome/evidence matrix, patch boundaries and concrete behavior for each pending transition choice. These are draft policy and requirements, not implemented assessment gates. The user selected optional upgrades on October 2, 2026. Existing earned credit and credentials are not migrated by this work.

## Decisions and constraints

- **Confirmed transition policy:** optional upgrades. Retain the supported current course and existing credentials; require an explicit credit-and-requirements preview and learner choice before activating 5.0.

- Preserve the existing document/tool/chat composition and current navigation rules.
- Keep the current published course requirements unchanged while preparing version protection. Existing earned credit and original credential dates are preserved.
- No course-version identity may be invented for legacy records whose historical provenance is unknown.
- The checklist’s proposed bridge, migration and progression details still require concrete implementation/policy records; planning prose alone is not an implemented policy.
- Keep audit evidence separate from implementation evidence. Never regenerate the baseline report against a new source build and present it as the old observation.
- Routine reversible implementation work proceeds within the user’s instruction to work through the checklist. Record consequential course-policy choices and rollout effects explicitly; do not manufacture approval gates for ordinary repairs.

## Resume instructions

1. Read this checkpoint and the relevant checklist sections, then inspect `git status` and existing diffs before editing.
2. Preserve the prior audit/checklist/harness files and current product changes; they are part of this work, even if untracked or uncommitted.
3. Continue the current task above. Live result refresh now belongs to `useChat` stream events and the shared certification context; the old mount-based sync hook was removed.
4. Reuse the focused stream, progress, practice and browser regressions. Preserve existing capture directories; record any new build in a fresh directory.
5. Update this log and checklist only for the scope actually verified. C8-QA-02 covers more than the initial progress regression and remains open.
6. Report the accepted count, concrete changes, verification and next task after each batch. Do not announce an 8/10 score until the formal regrade has evidence.


### Checkpoint 16 Learner assessment support draft on October 5 2026

**Status:** Verified within the scope below. **Related and still open:** C8-GRADE-11, C8-OPS-05/08 and C8-QA-02/04. Accepted count remains 11/162; corrected the checklist introduction’s stale count to match its checked items.

A completion that needs review now offers **Prepare support request**. The fullscreen course closes and the existing support panel opens an editable draft containing the selected course/version, enrollment, module and assessment reference. This action neither submits a ticket nor retries grading. Existing text, attachments and ticket options survive; repeated opening does not duplicate the same context. Context arriving during an outgoing ticket request waits for that request to settle before changing the draft. Existing support draft persistence remains limited to the mounted application session; browser-reload persistence is not claimed.

**Verification:** 15 focused component tests passed; production TypeScript/Vite build and targeted ESLint passed. The initial test run had a selector mismatch against the empty-ticket list and is retained. The corrected 28-state production browser review passed with zero axe violations, unexpected API requests or application errors. It asserts exact course/enrollment/assessment references, closed certification dialog, editable/reopened text, no extra certification writes and zero support submissions. Inspected 390px draft and 1440px edited draft screenshots. Browser APIs are synthetic; no real ticket/message, live learner change, migration or publication occurred.

**Evidence:** `artifacts/visual-review/certification-support-2026-10-05/checkpoint.json`, `final-frontend-tests.xml`, and `artifacts/visual-review/certification-support-2026-10-05-ui-attempt1/`. Source hashes are in the checkpoint. New support context helper: `frontend/src/lib/certificationSupport.ts`; shared notice and existing SupportChatPanel own the UI. The original baseline scores remain unchanged.


### Checkpoint 17 Outcome contract and read-only transition preparation on October 5 2026

**Status:** Design contract and preparation primitive verified, not a completed curriculum or migration feature. **Related and still open:** C8-DEF-01/02/04/05, C8-GRADE-01/02/08/09/10, C8-MIGRATE-02/05/06 and module acceptance items. Accepted count remains 11/162; baseline grades are unchanged.

Authored [33 required outcomes across all eleven modules](../backend/certification-data/drafts/v5.0/README.md), with stable identities, existing teaching references needing revision, practice tasks, evidence requirements, passing conditions, critical failures and 66 positive/negative calibration examples. Each outcome explicitly records teaching revision required and assessment not implemented. The examples are design expectations, not executed grader evidence. Structured-review outcomes still require a calibrated reviewer mechanism; agent prose, keyword presence, XP and legacy titles cannot establish learner competence.

Added a strict outcome-contract validator. Unknown or cross-module teaching references, incomplete evidence, duplicate identities, missing negative calibration and unverified release-candidate claims fail validation. Course packages may carry an outcome contract only under the same rubric identity. Catalog reads reject an unverified contract on a published package, and the publication operation now checks readiness before changing the registry.

Added internal `TransitionPreview.inspect`: a read-only preparation view for an existing selected enrollment and an explicitly named target package. It separates preserved source XP/module credit/credential identity from the new required outcomes, conservatively transfers zero outcomes without a verified equivalence rule, and reports pending assessments, in-flight writes, unfinished reflection answers and missing credential preservation. A retained write fence detects an operation that both starts and finishes during the read. Unknown legacy provenance is preserved; private reflection text is not included. It creates no enrollment, changes no selection, awards no credit and exposes no activation endpoint. External-job reconciliation and equivalence are always reported as unresolved prerequisites.

**Verification:** 35 contract/catalog/release-authoring tests and six real-Mongo transition cases passed, using disposable synthetic databases. Tests cover untouched/foreign users, historical credit preservation, draft targets, pending work, absent outcome requirements, intervening writes and publication refusal. The first contract run took unusually long while the local host was unresponsive; it eventually passed. Later final tests passed normally. Targeted Ruff, whitespace and current release checks passed. Existing legacy package bytes, registry defaults and disabled rollout remain unchanged.

**Evidence:** `artifacts/visual-review/certification-outcomes-2026-10-05/checkpoint.json`, `final-contracts-tests.xml` and `transition-tests.xml`. Source hashes are recorded. No browser claim applies: this checkpoint adds design data and internal backend preparation, not a learner transition UI.


### Checkpoint 18 Immutable assigned lab inputs on October 5 2026

**Status:** Internal input-capture foundation verified; execution and grading integration remain open. **Related:** C8-GRADE-01/02/07, C8-VERSION-05, C8-MIGRATE-05. Accepted count remains 11/162.

Added insert-only `CertificationLabInput` records and a server-side extraction input capture primitive. It requires the enrollment write boundary, explicit owned extraction identity, the complete assigned document IDs in the enrollment lab, completed readable ingestion and source file bytes matching the package’s SHA-256. Matching filenames cannot substitute for assigned evidence. The snapshot preserves source identity, text and location markers, field definitions, authored and optimizer configuration, exercise/course/rubric identity and an artifact digest. It detects documents or fields changing during preparation, limits payload size, verifies stored receipts and returns the original snapshot on an identical request even after workspace edits/deletion. Shared-artifact evidence is deliberately not supported by this primitive.

Snapshot creation performs no extraction or grading and records no learner decisions or outcomes. No current course tool/API calls it yet. Future execution must consume the persisted payload and bind its result; merely creating a snapshot does not prove competence. Prepared evidence currently blocks the internal activation primitive until a disposition is implemented and appears by reference in transition preparation without exposing source text. Account deletion includes the new collection.

**Verification:** 13 initial capture cases passed, followed by a final 85-case real-Mongo enrollment/recovery/credential/transition/input suite, including five additional capture and transition checks. Twelve database/account-deletion-summary tests passed; these do not constitute a destructive account-deletion integration test. Ruff and whitespace checks passed. Storage bytes and ingestion text are fixtures; real storage ingestion and model execution remain open. The interrupted first full run produced no completion report. The restored MongoDB then exhausted its default file limit; that failure is retained. Restarted only the disposable service with `ulimit -n 8192`; the third full run passed in 115.51 seconds.

**Evidence:** `artifacts/visual-review/certification-lab-inputs-2026-10-05/checkpoint.json`, `final-enrollment-tests-attempt3.xml`, `enrollment-attempt3.log`, `lifecycle-tests.xml` and the retained `mongodb-attempt2-failure.log`. The official test archive and checksum source is [MongoDB Community releases](https://www.mongodb.com/try/download/community-edition/releases). No application database or live learner record was changed.

### Checkpoint 19 Draft AI Literacy teaching and recognition grading on October 5 2026

**Status:** Unpublished content draft and grading kernel verified; learner delivery and submission persistence remain open. **Related:** C8-M00 items, C8-DEF-05, C8-GRADE-03/08/10. Accepted count remains 11/162; no baseline grade is raised.

Authored two lesson replacements at explicit revision 2 and nine assessed recognition scenarios covering unsupported claims, wrong sources/workspaces, embedded document instructions, changed release scope, institutional authority and credential limits. The current course files and frozen continuation package are unchanged. Each lesson includes formative feedback; the scenarios have choice-specific remediation.

Added a deterministic scenario kernel with required checks and per-outcome results. Every required scenario must pass; success elsewhere cannot offset a critical wrong decision. Missing answers remain incomplete. Unknown identities and a changed bank digest are rejected. The learner-facing definition excludes answer keys and feedback until grading. Bank coverage must match the contract’s recognition outcomes and rubric. The kernel explicitly awards no credit and does not claim practical competency from recognition answers.

**Verification:** 41 focused scenario/outcome tests passed, including every one of the 18 wrong choices, missing answers, stale bank identity, invalid bank structures, public answer-key exclusion, outcome/rubric mismatches and known teaching replacement IDs/revisions. Ruff passed. Draft teaching has not yet been rendered in the browser or observed with learners. Evidence: `artifacts/visual-review/certification-scenarios-2026-10-05/checkpoint.json` and `final-scenario-tests.xml`.


### Checkpoint 20 Authenticated scenario submissions on October 5 2026

**Status:** Staged persistence and public delivery verified; no course is enabled. **Related and still open:** C8-M00-03, C8-GRADE-01/03/08, C8-VERSION-05 and C8-MIGRATE-05. Accepted count remains 11/162.

Added authenticated, enrollment-pinned scenario submission and owner-only historical reads. Each insert-only receipt preserves exact choices, bank/course/manifest identity, rubric result, request digest and previous result reference. The receipt is saved before linking progress. Retrying an interrupted link returns the same record, changed answers cannot reuse its request ID, and an old retry cannot replace a newer result. Scenario results never award XP, complete a module or issue a credential. Historical reads survive catalog unavailability and reject corrupted records.

Course delivery now includes only public questions and choices for packaged scenario banks. It suppresses the legacy reflection assessment for that module. Catalog validation rejects invalid bank keys, module identity and rubric/outcome mismatches before delivery. The preserved legacy runner explicitly rejects packages claiming new competency outcomes. No supported V5 credit runner exists yet.

The internal transition boundary conservatively blocks any saved scenario receipt, including a receipt whose progress link was interrupted. Read-only preparation lists references without answer text and includes them in its consistency check. An explicit evidence disposition remains required before this restriction can be relaxed. Fenced writes prevent a revoked worker from linking progress; a cross-collection transaction is not claimed, and an orphan immutable receipt can remain. Recovery from process death while a scenario write marker is held remains open.

**Verification:** Eleven real-Mongo cases passed against disposable synthetic databases; 66 contract/kernel/release tests passed before the final catalog guard and were included in the subsequent lifecycle regression run. HTTP tests cover authenticated ownership, missing/stale enrollment, stale bank digest, forbidden award flags and key-free delivery. Initial transition tests had fixture setup failures (duplicate temporary release path, then invalid temporary defaults); retained reports distinguish them from final success. The existing 85-case persistence suite is the checkpoint-18 baseline; it was not rerun for this checkpoint. Targeted Ruff, endpoint mapping and preserved-release checks passed.

**Evidence:** `artifacts/visual-review/certification-scenario-submissions-2026-10-05/checkpoint-20.json`, `final-submission-tests.xml`, `contracts.xml` and retained earlier attempts. Frontend scenario delivery is tracked separately in checkpoint 21. No production database, published course, enrollment selection or historical credit changed.


### Checkpoint 21 Learner scenario delivery and responsive recovery on October 5 2026

**Status:** Staged learner interface verified with synthetic browser APIs and separate backend persistence evidence. **Related and still open:** C8-M00-01/03/04, C8-VIS-02/03, C8-A11Y-02 and C8-VERSION-05. Accepted count remains 11/162; no broad acceptance item or baseline grade is changed.

The pinned course can deliver an explicit nine-question recognition assessment with native radio groups, answered count, required submission, choice-specific feedback and a durable submission reference. Unsubmitted choices are isolated by enrollment/module/bank in browser-tab session storage. An uncertain request locks its exact choices and preserves its request identity across reload; no submission occurs until the learner clicks. Browser storage failure prevents dispatch. History loads never replace unsent edits, foreign requirement identities are rejected, and an old retry is labeled without claiming it displaced newer work. The scenario challenge suppresses legacy reflection/completion controls and says that recognition results do not award module credit or XP.

Visual inspection found clipped progress stars at 320px despite zero automated axe violations. The shared progress row now wraps, with an explicit browser overflow assertion. Desktop question content uses a bounded reading width. Inspected the 320px header and choices, 390px revised teaching and resumed request, 320px feedback and 1440px question layout. The full two-lesson rewrite and nine-scenario draft are still outside the course registry; other AI Literacy teaching remains under review.

**Verification:** 31 frontend regression tests, 78 backend contract/catalog/kernel/lifecycle tests, production build, targeted ESLint/Ruff, endpoint mapping, generated-content and frozen-release checks passed. The final 13-state production browser pass has zero axe violations, unexpected API calls or page errors. It exercises native keyboard selection, all wrong answers, a synthetic response lost after save, mobile reload via the activity drawer, identical retry, corrected answers under a new request and zero credit writes. “Start the certification course” is a chat kickoff; the direct mobile panel control lives in Activity. Earlier harness attempts assumed the desktop control was visible, then mistook the chat kickoff for a direct opener; their blocked captures are retained. The first capture attempt was interrupted by local disk exhaustion. Removed only this task’s extracted Mongo download archive and unused temporary mongos binary, preserving evidence and project data.

**Evidence:** `artifacts/visual-review/certification-scenario-submissions-2026-10-05/checkpoint-21.json`, `final-frontend-tests.xml`, `final-contracts-lifecycle.xml`, `production-build.log`, and `artifacts/visual-review/certification-v5-scenarios-2026-10-05-ui-attempt5/`. Browser IAB was unavailable; the isolated Playwright fallback used a production build and synthetic data. No live model, user enrollment, course publication, ticket or external message was involved. Screen-reader use and learner observation remain unverified.


### Checkpoint 22 Saved-input extraction execution on October 5 2026

**Status:** Internal execution adapter and persistence verified with a stubbed provider. **Related and still open:** C8-GRADE-01/02/07, C8-VERSION-05/07 and C8-MIGRATE-05. Accepted count remains 11/162.

Added a saved-text extraction runner that consumes only the persisted document text, location metadata and field definitions from checkpoint 18. It records the input digest, effective extraction settings, configured model identities, implementation and provider-SDK fingerprints before dispatch. A changed input, model setting or implementation prevents a prepared run from silently changing requirements. Image-mode inputs, unconfigured pass models and duplicate field names are rejected. Credential rotation does not change the runtime fingerprint; credentials and raw provider errors are excluded from receipts.

Dispatch claims a prepared record atomically, so concurrent duplicate calls do not repeat the provider invocation. Completed output, source sidecars, usage and document references are preserved in an integrity-checked terminal record. Workspace deletion does not change the saved inputs. A failed execution is not a failed learner assessment. Timeout/cancellation is recorded as uncertain because the underlying provider thread may continue; the same request never silently retries. Failed terminal persistence leaves an executing intent for future reviewed recovery. That recovery workflow and learner-facing dispatch are not implemented. The existing captured-input restriction continues to block course activation. Cross-collection transactional dispatch and provider-output reproducibility are not claimed.

**Verification:** All 112 persistence cases passed in four bounded batches: 28 in the initial bounded-cache batch, then the remaining 84 using a tracked foreground MongoDB service. The 16 focused execution cases cover immutable inputs after deletion, original-result replay, changed settings/code, provider failure, timeout, invalid/oversized output, interrupted receipt save, duplicate concurrent dispatch, revoked ownership, cancellation, credential rotation and owner-only integrity-checked history. Twelve registration/account-deletion-summary tests passed. No live provider call occurred. Targeted Ruff and whitespace checks passed. The first focused run could not connect after disk exhaustion; the next identified the installed SDK’s actual distribution name (`pydantic-ai-slim`), which was corrected. Detached service exits interrupted broader runs; their reports/logs are retained. The foreground service completed the remaining tests. Existing dependency deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-lab-execution-2026-10-05/checkpoint.json`, `execution-tests-attempt3.xml`, `lifecycle-tests.xml`, `persistence-batch-1.xml`, `persistence-batch-2-foreground.xml`, `persistence-batch-3-foreground.xml`, `persistence-batch-4-foreground.xml`, and retained failure logs. No live learner, production database, publication, grade or credential changed.

### Checkpoint 23 Selected-course home continuation on October 5 2026

**Status:** Verified within scope. **Related and still open:** C8-JOURNEY-01/02 and C8-VERSION-03. Accepted count remains 11/162.

The Assistant home’s continuation count now uses the selected course’s module membership and total. Historical or unrelated module keys cannot inflate its numerator. Saved lesson position, reflection/lab work, a pending completion or a scenario receipt offers continuation even before the learner earns the first module. Unversioned continuation retains its eleven-module fallback. The button still starts the established chat flow; it does not change enrollment or automatically submit work.

**Verification:** 15 component tests passed, including selected-course membership/count and three forms of unfinished work. Production build and targeted ESLint passed. Four production browser states at 320px and 1440px passed with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow selected-credit state. The first browser attempt omitted the panel’s background exercise-read fixture and is retained; no product failure was inferred from that missing mock. Existing first-session tests emit React act warnings. Source changes and evidence are recorded in `artifacts/visual-review/certification-home-resume-2026-10-05/checkpoint.json`, `home-tests.xml`, `production-build.log`, and `artifacts/visual-review/certification-home-resume-2026-10-05-ui-attempt2/`.


### Checkpoint 24 Complete AI Literacy teaching draft and lesson layout on October 5 2026

**Status:** Nine unpublished teaching replacements and bounded shared UI repairs verified. **Related and still open:** C8-M00-01/02/03/04, C8-VIS-02/03/04/12 and C8-A11Y-02. Accepted count remains 11/162; no baseline grade changes.

All nine AI Literacy lessons now teach source support, task scope, operation-specific approval, missing information, human authority and review before expanding a task. Each retains its original identity at revision 2 and includes a formative question with explanatory feedback. Local capability review corrected an overbroad approval claim: creating an extraction and running a saved workflow use confirmation previews, while running an existing extraction may execute directly. The draft distinguishes generated fields available after creation from the creation preview itself. The first real scoped file exercise, final assessment integration and learner observation remain open.

Numbered lesson controls now wrap in the card, name viewed status and identify the current step accessibly. Mobile padding provides more reading room. The desktop module card and lesson body have bounded, centered widths. Scenario radios use native required semantics. A dark accent audit found a fixed dark text color on an Assistant home action behind the panel; it now uses the theme’s contrast-aware text token.

**Verification:** 42 backend scenario/outcome/teaching contract cases and 33 focused frontend tests passed. Production build, targeted ESLint, frozen-release/outcome checks and whitespace checks passed. The final production browser pass captured 50 states with a dark purple accent, including every lesson’s reading/practice states at 390px and 1440px and scenario/retry states at 320px, 390px and 1440px. All have zero axe violations, horizontal page overflow, unexpected API calls or page errors. Inspected the centered desktop worked example, narrow practice and wrapped current/viewed navigation. Earlier default-theme captures passed automated checks but revealed manual layout defects; earlier purple captures isolated the home-action contrast failure. Those artifacts remain available. A transient all-lessons-viewed toast appears in some captures; permanent overlap and screen-reader behavior are not inferred from these screenshots.

**Evidence:** `artifacts/visual-review/certification-ai-literacy-rewrite-2026-10-05/checkpoint.json`, `final-all-teaching-contract-tests.xml`, `final-frontend-tests.xml`, `final-position-tests.xml`, `production-build.log`, and `artifacts/visual-review/certification-ai-literacy-rewrite-2026-10-05-ui-centered/`. Browser APIs are synthetic; real scenario persistence was verified separately in checkpoints 20 and 22. No course publication, live learner change, model call or earned credit occurred.


### Checkpoint 25 Foundations teaching draft on October 5 2026

**Status:** Six unpublished replacements verified for teaching presentation and formative practice. **Related and still open:** C8-M01-01/02/03/04. Accepted count remains 11/162.

Replaced inconsistent three-versus-five-field instructions and the assumption that every extraction requires a workflow with a single coherent sequence: scope the task, inspect the assigned source, review creation, inspect generated fields, explicitly request execution and check all five values. The teaching distinguishes a preview, saved configuration, completed run and verified result. It explains missing or unreadable input, source context, operation-specific confirmation and repair followed by re-execution. A fictional budget subtotal mismatch provides a concrete practice case. Legacy field-count stars and expected answers are not presented as proof of V5 competence.

**Verification:** The shared teaching/scenario/outcome suite passed with both AI Literacy and Foundations drafts (42 cases); the subsequent three-module run adds Process Mapping. All 42 Foundations browser states passed at 320px, 390px and 1440px, including a wrong answer followed by corrected feedback for each lesson. Zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow ordered procedure, visible correction feedback and bounded desktop reading layout. The first harness attempt incorrectly expected POST for the PUT position API; retained artifacts identify the fixture error. A second pass verified all states, and the final pass scrolls feedback into view for readable screenshots.

**Evidence:** `artifacts/visual-review/certification-foundations-teaching-2026-10-05/checkpoint.json` and `artifacts/visual-review/certification-foundations-teaching-2026-10-05-ui-feedback/`. These are synthetic teaching-only fixtures; provisioning, real extraction, durable learner decisions, practical grading, truthful enrichment criteria and learner observations remain required. Original lesson IDs are retained at revision 2. The draft remains outside the catalog and cannot enroll a learner.


### Checkpoint 26 Process Mapping teaching and narrow breadcrumb on October 5 2026

**Status:** Seven unpublished replacements and narrow module-name wrapping verified. **Related and still open:** C8-M02-01/02/03/04 and C8-VIS-01/03. Accepted count remains 11/162.

Replaced unsupported 80/20 and 70/30 efficiency claims, workflow-by-default framing and automatic release examples with explicit method choice, bounded source/output scope, meaningful reviewer checkpoints and exception paths. Each lesson includes formative feedback. The worked progress-report example ends with an internal brief and a named review decision; it does not silently authorize a sponsor submission. Teaching distinguishes a diagrammed checkpoint from an implemented pause and requires evidence before expanding automation.

Manual inspection found the long module name truncated in the 320px breadcrumb. The panel now wraps its full name beneath the Curriculum control on narrow screens and allows wrapping in constrained wider panes. The final harness asserts actual breadcrumb bounds as well as page and lesson bounds.

**Verification:** 43 shared backend contract cases, seven panel tests, production build and targeted ESLint passed. The final 49-state production browser pass covers seven lessons at 320px, 390px and 1440px and corrected feedback at 390px, with zero axe violations, horizontal page overflow, unexpected calls or page errors. Inspected the narrow full module name, ordered intake map, release-boundary feedback and desktop method lesson. An earlier pass identified the visual truncation despite passing axe; the first recapture used an ambiguous locator matching both breadcrumb and module heading, then was corrected to target the breadcrumb span. Prior captures are retained.

**Evidence:** `artifacts/visual-review/certification-process-mapping-teaching-2026-10-05/checkpoint.json`, `teaching-contract-tests.xml`, `panel-tests.xml`, `production-build.log`, and `artifacts/visual-review/certification-process-mapping-teaching-2026-10-05-ui-wrapped-attempt2/`. This proves draft presentation and practice behavior, not structured assessment, actual process execution or a publication-ready module.


### Checkpoint 27 Execution-aware optional-upgrade preparation on October 5 2026

**Status:** Internal read-only inventory and course-selection protection verified. **Related and still open:** C8-MIGRATE-05/06 and C8-VERSION-05/07. Accepted count remains 11/162. This backend checkpoint completed while checkpoint 26’s final visual pass was running.

Upgrade preparation now lists the learner’s saved lab run references, modules, captured-input references and current execution states. Prepared, executing, completed, failed and uncertain records all require an explicit future disposition. The view excludes model configuration, result contents and worker identity. It remains read-only and transfers zero outcomes. Run state, plan/result digests and membership are part of the snapshot consistency check, so a provider result arriving independently of a progress write invalidates an in-flight preview.

Course activation checks execution records directly for both source and target enrollments. A missing input reference cannot hide an unresolved execution or permit an automatic retry/discard. This supplements existing captured-input and scenario protection; it does not implement recovery or upgrade activation for learners.

**Verification:** 18 targeted real-Mongo cases and 22 affected activation/execution regression cases passed; these sets overlap. Eleven new cases cover all five states, foreign-user/enrollment exclusion, read-only behavior, state/result changes, insertion/deletion during preview and source/target runs with unavailable inputs. Actual execution behavior remains covered with a stubbed provider. Targeted Ruff, preserved-release and whitespace checks passed. Existing dependency deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-transition-executions-2026-10-05/checkpoint.json`, `persistence-tests.xml` and `activation-execution-regression.xml`. The inventory is metadata for reconciliation, not an integrity-verified grade. No live learner selection, course publication, model execution or credit changed.


### Checkpoint 28 Workflow Design teaching draft on October 5 2026

**Status:** Eight unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M03-01/02/03/04. Accepted count remains 11/162.

The draft now traces configured input sources, intermediate evidence and output requirements. It distinguishes creation confirmation, run confirmation and an actual Approval node; it explains reviewer assignment, timeout behavior and the need to verify pause/resume/rejection before relying on a boundary. Source review confirmed that the current chat builder supports specified operation types and linear wiring, while its creation preview summarizes names/types rather than all prompts, sources or reviewer settings. Learners are instructed to inspect the saved configuration before running. Unsupported claims about guaranteed reliability, one-glance review and time saved were removed. Worked examples require correction of missing comparison inputs and out-of-scope delivery.

**Verification:** 44 shared backend scenario/outcome/teaching contract cases passed. All 56 production browser states passed with a dark purple accent at 320px, 390px and 1440px, including wrong-to-correct formative feedback for each lesson. Zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected mobile source-wiring text, approval-timeout feedback and desktop saved-configuration guidance. Shared renderer/build and breadcrumb regressions were verified in checkpoints 24 and 26.

**Evidence:** `artifacts/visual-review/certification-workflow-design-teaching-2026-10-05/checkpoint.json`, `teaching-contract-tests.xml`, and `artifacts/visual-review/certification-workflow-design-teaching-2026-10-05-ui/`. This does not verify real workflow dispatch or review behavior, record a learner’s corrected design, or satisfy practical assessment. The first four modules now have 30 drafted replacements with visual evidence; the remaining seven modules contain 44 lessons to revise. All remain outside publication and the readiness contract is unchanged.


### Checkpoint 29 Automatic-only review policy and staged judge on October 5 2026

**Status:** Policy and internal response/evidence boundaries verified; real-model semantic grading remains unverified. **Related and still open:** C8-GRADE-01/02/08/09/10 and practical module outcomes. Accepted count remains 11/162.

The user revised the initial choice to option 2: automatic grading, unclear evidence returned to the learner, no staff queue. They explicitly allowed an LLM while directing that staff not be burdened. Recorded the selected policy separately from institutional review duties taught by the course. No staff grading workflow was built.

Added a staged structured-review adapter using the existing configured model integration and strict structured output without action tools. Missing evidence kinds return authored revision guidance before model dispatch. Every requested structured outcome must be returned exactly once; supported outcomes must quote saved evidence for every required kind. Unknown outcomes, fabricated quotations, extra award fields and contradictory/incomplete verdicts become retryable grader errors rather than learner failures. Unclear or contradicted outcomes return concrete revision instructions. All results remain ineligible for module completion and award no credit. Deterministic outcomes are excluded from model judgment and still require their own trusted checks. Evidence, contract, policy, model routing, prompt, implementation and SDK identities are recorded in the result; credentials and provider error text are excluded.

Authored six synthetic Foundations calibration cases: corrected scope and verified values, late approval, wrong-document approval, unresolved source checking, reliance on agent assurance and hostile instructions inside source text. The measurement harness distinguishes false support from provider unavailability and never declares release readiness. An always-passing test judge produces five detected false supports; a fixture oracle can match the cases without claiming actual model quality.

**Verification:** 71 focused tests passed: 23 automatic-review boundaries (including the actual Pydantic-AI adapter with a local TestModel), four calibration-harness cases and 44 existing teaching/scenario/outcome contracts. Targeted Ruff, whitespace and frozen-release checks passed. The first test command used a wrong relative path and ran no tests; its report is retained separately. No external LLM call, live learner write, staff task or publication occurred.

**Evidence:** `artifacts/visual-review/certification-automatic-review-2026-10-05/checkpoint.json` and `verified-calibration-contract-tests.xml`. These tests establish mechanical boundaries, not semantic reliability or prompt-injection resistance of a real model. The adapter accepts only an internal caller’s verified evidence packet; authenticated evidence assembly, saved learner decisions, durable grading/retry and real-model calibration remain required before release.


### Checkpoint 30 Saved automatic reviews and technical retries on October 5 2026

**Status:** Internal persistence, explicit retry lineage and optional-upgrade protection verified. **Related and still open:** C8-VERSION-05/06, C8-MIGRATE-05/06 and practical outcome assessment. Accepted count remains 11/162.

The review repository saves the exact evidence, packaged outcome contract, automatic-only policy and model/runtime/code identity before dispatch. A conditional claim permits one grading call per attempt. Results are immutable and owner-scoped; duplicate requests return the original result, including after a lost response. Changed evidence cannot reuse a request identity. A missing terminal database write leaves an unfinished intent, never silently regrades. Integrity-checked history remains readable without the active catalog. No credit, completion or staff queue is created.

Provider failures and cancellation remain technical unavailability with no learner failure. An explicit retry creates a new linked attempt from the original saved evidence and requirements. A unique parent index prevents concurrent requests from branching the same failure. Each failed child may be retried in turn. Updated runtime configuration is recorded on the new attempt; the previous failure remains unchanged. Successful grades, revision guidance and unfinished attempts cannot use this technical-retry path. Automatic recovery of process death is still required before exposing grading to learners.

Read-only optional-upgrade preparation inventories saved reviews and detects concurrent changes without exposing evidence or model output. Course activation protects review records on either enrollment. The model is registered for database initialization and its records are included in account deletion.

**Verification:** 23 real-Mongo review cases passed, including concurrent dispatch/retry, changed evidence/configuration, credential rotation, missing evidence, provider failure, cancellation, interrupted result storage, ownership, corruption and source/target transition guards. Another 22 existing upgrade/activation cases and 83 shared policy, calibration, teaching, database and account-deletion cases passed. Targeted Ruff, release/outcome checks and whitespace checks passed. Existing Beanie/Pydantic deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-review-attempts-2026-10-05/checkpoint.json`, `persistence-and-retry-tests.xml`, `transition-regression.xml` and `contracts-and-registration.xml`. Providers were synthetic; no real-model calibration, learner-facing practical review, authenticated practical-decision capture, earned credit, live learner change or publication occurred. The internal repository trusts its future authenticated evidence producer; text claiming an actor is not provenance.


### Checkpoint 31 Authenticated practical decisions on October 5 2026

**Status:** Saved decision records and authenticated HTTP boundaries verified; learner interface and grading integration remain open. **Related and still open:** practical Foundations assessment, C8-VERSION-05 and C8-MIGRATE-05/06. Accepted count remains 11/162.

Two unpublished Foundations prompts separate scope review before execution from source checking after a completed run. Each receipt saves the actual authenticated actor, server timestamp, exact prompt/revision, explicit answers, input snapshot and execution-plan identity. Completed-run decisions also bind the result digest. Assigned lab snapshots now retain their lab-folder identity. Before-run decisions cannot first be submitted after execution; replay of an already-saved decision preserves its original timestamp. Five source checks are required for the Foundations value-review prompt, with explicit supported, unsupported or unresolved answers. Literal quotes must exist in the captured assigned text. These checks validate references and capture judgment; they do not prove that the source supports the value or award a grade.

The HTTP write requires the selected enrollment and rejects client-supplied actors, timestamps and grade metadata. No chat tool submits these decisions. Duplicate requests preserve the original receipt, including after a lost response; changed answers require a new request. Owner-scoped history is independent of the catalog. New prompts are validated against packaged outcomes at course load. Decisions are registered for database initialization/account deletion and protected during optional course changes; previews list metadata and detect concurrent changes without exposing answers.

**Verification:** 94 real-Mongo integration cases passed: 16 new decision cases plus affected saved-input, execution, review and transition regressions. Another 119 prompt, catalog, authoring, policy, calibration, teaching and registration/deletion cases passed. Targeted Ruff, release/outcome checks and whitespace checks passed. Existing Beanie/Pydantic deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-learner-decisions-2026-10-05/checkpoint.json`, `persistence-and-regression.xml` and `contracts-and-registration.xml`. HTTP calls were exercised through ASGI against disposable MongoDB records; extraction/model output was synthetic. No learner interface, browser verification, real-model calibration or credit integration is claimed. A scope approval records a decision but does not yet gate execution; intentional-mismatch proposal capture, the evidence assembler, automatic grading recovery and full practical delivery remain required. No live learner or publication change occurred.


### Checkpoint 32 Practical review screen and self-service response recovery on October 5 2026

**Status:** Staged learner decision UI, saved-evidence reads and response recovery verified. **Related and still open:** Foundations practical assessment, agentic-chat evidence delivery, C8-VERSION-05 and accessibility acceptance. Accepted count remains 11/162; this is not an 8/10 reassessment.

A packaged practical-decision module now replaces the legacy challenge form with a saved-run review screen. Learners inspect the captured source, extraction fields and output, choose their own decision and record source checks. Scope and value-review stages remain separate. The UI lists the latest 50 owned course/module runs, reports older work and accepts a full run reference. Reads verify saved input/run identity and return the applicable prompt and most recent decision. Later workspace edits cannot replace this evidence.

Browser drafts and pending request IDs are isolated by enrollment, run and prompt digest. Submission first preserves the exact answers locally. A lost response locks those answers; an explicit check reads the original receipt before considering a retry. A confirmed saved receipt resolves without another POST. Unknown history failures never silently dispatch again. Definite source-reference validation failures return HTTP 422 before insertion and keep answers editable. Unsupported and unresolved checks remain explicit learner statements, without implying a pass, failed performance or staff review. Saved history displays the recorded choice, explanation and source checks separately from unsent edits.

Visual inspection found clipped source-check options at 320px. The selected option now uses a short label with a wrapping explanation below. A wrapping selected-source title also remains readable when a native select clips a long filename. A slower run-list response cannot erase a source-context error.

**Verification:** 19 real-Mongo/ASGI cases passed for decision persistence and review reads, including ownership, pinned requirements, original source preservation, bounded run listing and editable quote rejection. 62 prompt/catalog/scenario cases and 26 frontend cases passed; the final source-label adjustment also passed all 11 practical-review component cases. Production build, targeted Ruff/ESLint and release/outcome/whitespace checks passed. All 13 final production browser states passed at 320px, 390px and 1440px with a dark purple accent, zero axe violations, page errors, unmatched requests or horizontal page overflow. Inspected narrow source-check controls, saved unresolved values and desktop source evidence. Existing build chunk/import and Beanie/Pydantic warnings remain.

**Evidence:** `artifacts/visual-review/certification-practical-review-ui-2026-10-05/checkpoint.json`, `http-and-persistence.xml`, `prompt-catalog-tests.xml`, `frontend-tests-mobile-fix.xml`, `form-tests-source-label.xml`, `production-build-source-label.log` and `artifacts/visual-review/certification-practical-review-ui-2026-10-05-browser-readable-source/`. Earlier harness failures are retained: exact label-text selectors included native form content, and reload required reopening the learning panel. The final harness uses the observed semantic control names. Expected synthetic HTTP 503/422 console messages exercise recovery and rejection; no unexpected browser errors occurred.

**Limits:** The browser uses synthetic saved runs and receipts; ASGI tests separately exercise real persistence. No live model or real execution was used. This screen saves evidence, not a grade; scope approval does not yet authorize dispatch. Intentional-mismatch proposal evidence, trusted grading packets, deterministic outcome integration, automatic interrupted-grading recovery, model calibration and full practical provisioning/execution remain required. There is no routine staff queue. No course publication, deployment or live learner change occurred.


### Checkpoint 33 Saved scope approval gates execution on October 5 2026

**Status:** Internal execution authorization and immutable consent receipts verified. **Related and still open:** Foundations scoped proposal and executed extraction, C8-VERSION-05 and C8-MIGRATE-05/06. Accepted count remains 11/162.

The unpublished scope prompt now declares its explicit approval choice. A prepared run pins that requirement. Execution reads the currently linked learner decision for that exact run and input snapshot; missing approval, revise and decline block the provider call. A newer decline supersedes an earlier approval, and replaying an older request cannot restore it. An interrupted receipt-to-run link remains non-authorizing until the original request safely resumes. A conditional execution claim detects consent changes between checking and dispatch.

The execution record freezes the complete authenticated approval and its digest before calling the provider. Completed, failed and uncertain results retain that identity. History can still verify the frozen consent after the separate decision record becomes unavailable. Optional-upgrade inspection now detects changes to consent pointers and authorization digests even when the run state is unchanged. Course loading rejects ambiguous multiple approval prompts. Existing packages without a declared approval requirement retain their prior behavior.

**Verification:** 47 real-Mongo integration cases passed, including 11 new cases for missing/negative consent, superseded approvals, cross-run borrowing, interrupted linking, changed consent at dispatch, receipt corruption and failed execution without automatic rerun. Another 82 prompt/catalog/authoring/scenario/outcome contract cases passed. Targeted Ruff, preserved-release, outcome and whitespace checks passed. The earlier 35-case regression report is retained; it overlaps the final regression. Existing Beanie/Pydantic dependency warnings remain.

**Evidence:** `artifacts/visual-review/certification-scope-authorization-2026-10-05/checkpoint.json`, `authorization-and-regression.xml` and `contracts.xml`. Providers are synthetic; no new browser behavior is claimed. This enforces permission to run, not proof that the learner corrected an intentional mismatch or verified the output. Trusted grading evidence, proposal capture, deterministic outcome integration, automatic grading recovery, model calibration and full practical delivery remain required. No grade, staff task, publication, deployment or live learner change occurred.


### Checkpoint 34 Owned-record practical evidence assembly on October 5 2026

**Status:** Internal Foundations collector verified. **Related and still open:** Foundations practical assessment and C8-GRADE evidence validity. Accepted count remains 11/162.

The collector accepts an authenticated owned run reference under the enrollment write boundary and builds evidence from integrity-checked saved inputs, frozen execution consent, terminal output and the latest saved value review. It checks course/rubric, source asset and ingestion-text hashes, actual executed document IDs, extraction revision, prompt revision and decision/result links. It never reads current workspace content or lets a caller select an older favorable value review. Sources remain available after workspace deletion; the dispatch receipt preserves the original consent independently of the decision collection.

Long source text is included in ordered, identified chunks without shortening it. Item and total-packet limits produce technical unavailability rather than a failed learner grade. Unresolved checks remain unresolved. Source text asserting that an agent approved or checked values does not substitute for an authenticated decision. The collector reports the still-missing intentional-mismatch proposal; a completed approved run is not relabeled as that proposal. It makes no review attempt, model call, award or staff task.

**Verification:** 47 real-Mongo assembly/approval/review cases passed, including 13 new collector cases for original evidence after deletion, latest decisions, absent value checks, hostile source prose, complete Unicode source chunking, oversized packets, corruption, ownership/write fences, incomplete execution and rehashed records with broken cross-record links. Targeted Ruff, preserved-release and whitespace checks passed. Existing Beanie/Pydantic warnings remain.

**Evidence:** `artifacts/visual-review/certification-practical-evidence-2026-10-05/checkpoint.json`, `assembly-and-regression.xml` and the earlier overlapping 10-case `initial-assembly.xml`. Providers are synthetic. Proposal capture, durable trusted-review handoff, deterministic outcome integration, automatic interrupted-grading recovery, real-model calibration and learner-facing practical execution remain required. No course publication, deployment or live learner change occurred.


### Checkpoint 35 Intentional source mismatch and explicit learner correction on October 5 2026

**Status:** Unpublished Foundations proposal, execution guard and learner controls verified. **Related and still open:** Foundations scoped proposal, C8-GRADE evidence validity and practical delivery. Accepted count remains 11/162.

A packaged authored case intentionally proposes the NIH document for the assigned NSF task. Preparing a run freezes that original proposal, course-source hash, assigned-input snapshot, extraction revision and lab workspace into the immutable plan. The learner sees the original proposal and task, explicitly selects a source and explains the decision. Nothing is preselected. Approval with the unrelated source is saved as the learner's answer but cannot dispatch the provider. A later explicit correction can authorize the exact assigned run; both decisions remain preserved. Changed answers need a new request, and a correction cannot first be submitted after execution.

The evidence collector now includes the actual original proposal and linked authorized selection when available. It verifies the case against the pinned package rather than inventing a proposal from agent text or a completed run. Invalid cases using an assigned source as the deliberate mismatch, missing assets, an unrelated prompt or the wrong module are rejected at course load. The review UI preserves proposal selection through pending-response recovery, verifies it in returned receipts and displays the recorded source separately from unsent changes. Full selected-source labels wrap beneath native selects on narrow screens.

**Verification:** 45 real-Mongo proposal/evidence/decision/authorization cases plus four additional malformed-package cases passed; nine new cases cover the proposal behavior. 72 shared backend contracts and all 13 practical-review component tests passed. Production build, targeted Ruff/ESLint and release/outcome/whitespace checks passed. All 19 final production browser states at 320px, 390px and 1440px passed with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the full 320px proposal, source correction controls, desktop evidence and saved-source confirmation. The first capture pass left the lower proposal text outside the screenshot; the final pass scrolls the entire proposal into view. Both sets are retained. Expected synthetic 503/422 responses test recovery and editable rejection. Existing build/dependency warnings remain.

**Evidence:** `artifacts/visual-review/certification-scope-proposal-2026-10-05/checkpoint.json`, `proposal-and-regression.xml`, `catalog-rejection.xml`, `shared-contracts.xml`, `form-tests.xml`, `production-build.log` and `artifacts/visual-review/certification-scope-proposal-2026-10-05-browser-readable-proposal/`. The in-app browser connection was unavailable after bootstrap; isolated Playwright ran against the local production build. Browser APIs and extraction output are synthetic; database tests separately verify persistence. This establishes explicit source correction and its authorization link, not real-model grading quality. Trusted grading handoff, deterministic outcome integration, automatic grading recovery, live calibration and full practical execution delivery remain required. No staff queue, publication, deployment or live learner change occurred.


### Checkpoint 36 Durable automatic review from saved practical records on October 5 2026

**Status:** Internal trusted-evidence handoff and original-packet retry verified. **Related and still open:** Foundations assessment, C8-GRADE validity and durable assessed attempts. Accepted count remains 11/162.

The review repository now has a saved-run entry point that accepts an authenticated run reference and request identity, assembles owned evidence itself and saves the complete packet with source/run/decision/proposal digests and collector implementation identity. A caller cannot pass grading prose through this path. Missing proposal or value-review evidence prevents assessment creation and records no learner failure. Existing internal raw-evidence fixtures cannot be relabeled as trusted saved-record submissions.

Replaying an existing request preserves its original packet even when the learner later saves a new value review or source records become unavailable. Assessing revised work uses a new request. Technical retries copy both the original packet and its provenance; changed lineage is rejected. A model-supported structured result still cannot award credit or declare module completion. Deterministic outcomes and calibrated release requirements remain separate.

**Verification:** 32 real-Mongo handoff/retry cases passed, including nine new cases covering original evidence, later edits, history after source removal, exactly-once evaluation, technical retry provenance, missing collection, cross-run/model/learner reuse and raw-evidence relabeling. Another 27 automatic-review/calibration contracts passed. Targeted Ruff, preserved-release and whitespace checks passed; existing dependency warnings remain.

**Evidence:** `artifacts/visual-review/certification-trusted-review-2026-10-05/checkpoint.json`, `handoff-and-retry.xml` and `review-contracts.xml`. Model responses are synthetic and demonstrate mechanical boundaries only. No HTTP/chat grading endpoint, automatic interrupted-worker recovery, live-model calibration, deterministic outcome integration or earned credit is claimed. No staff task, course publication, deployment or live learner change occurred.


### Checkpoint 37 Automatic reconciliation of interrupted grading on October 5 2026

**Status:** Internal request-driven recovery and stale-worker protection verified. **Related and still open:** C8-VERSION-05/07/08, automatic practical delivery and recovery UX. Accepted count remains 11/162.

The saved-review orchestrator binds the attempt to its own enrollment write before dispatch and records a five-minute recovery deadline. A subsequent internal request preserves an unexpired worker; after expiry it reconciles only recognized tool-free automatic grading. A durable recovery marker precedes revoking the old progress fence. The original review becomes technical unavailability with `passed: null` and an explicit linked retry remains available. Recovery itself never calls the model or creates a new attempt. It does not claim the original provider call was cancelled.

A terminal result that wins the conditional-write race remains intact. A later provider result cannot overwrite recovered unavailability, and an old worker's cleanup cannot release a newer learner write. Prepared-to-evaluating races, interrupted fencing/result/cleanup and concurrent recovery are restartable. Normal cleanup may already have released the enrollment; in that case record-only reconciliation leaves an unrelated active writer untouched. External execution, provisioning and unknown operations cannot use this recovery path. No staff grading task is created.

**Verification:** The complete real-Mongo certification integration suite passed: 218 cases, including 11 new automatic-recovery cases. The earlier 41-case review/recovery subset is retained and overlaps the full run. 109 shared automatic-review, calibration, prompt, catalog, authoring, scenario and outcome contracts passed before the subsequent Extraction Engine draft added its teaching case. Targeted Ruff and preserved-release/outcome/whitespace checks passed. Existing Beanie/Pydantic and PDF dependency deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-automatic-review-recovery-2026-10-05/checkpoint.json`, `full-persistence.xml`, `recovery-and-regression.xml` and `contracts.xml`. Process interruption and provider responses are synthetic; tests use disposable databases. Recovery runs when the internal orchestrator is requested, not through a deployed scheduler or HTTP endpoint. Learner-facing delivery, deterministic practical grading, real-model calibration and earned-credit integration remain required. No deployment, course publication or live learner change occurred.


### Checkpoint 38 Extraction Engine teaching draft on October 5 2026

**Status:** Six unpublished lesson replacements verified for presentation and formative practice. **Related and still open:** C8-M04-01/02/03/04 and full module assessment. Accepted count remains 11/162.

Replaced guaranteed-accuracy claims with evidence-based configuration choice, precise field meanings and explicit missing-value treatment. The lessons explain that two-pass refinement can use different configured models and can return the first-pass draft after refinement failure. Current consensus starts with two attempts and can add a tiebreak attempt; its cost and correctness are not fixed guarantees. Field grouping requires an enabled setting, rather than automatically appearing at a field-count threshold. Optionality, allowed categories and structured output do not establish source-supported values.

The procedure now follows chat proposal, saved configuration inspection, exact assigned execution, source checking and a preserved repair/re-execution comparison. The worked example demonstrates the reasoning needed to establish a repair without inventing a successful output. Guided test-case verification is distinguished from opening a session and from certification credit. Source behavior was checked in `extraction_engine.py`, `models/system_config.py` and the chat `propose_test_case` implementation.

**Verification:** 45 shared teaching/scenario/outcome contracts passed. All 42 production browser states at 320px, 390px and 1440px passed, including incorrect-to-correct feedback in all six lessons. Zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow numbered procedure, source-support feedback and desktop terms/verification explanation. Existing production build and shared rendering were verified in checkpoint 35; this checkpoint changes only the separate teaching draft and its contract-test coverage. Preserved-release/outcome/whitespace checks passed.

**Evidence:** `artifacts/visual-review/certification-extraction-engine-teaching-2026-10-05/checkpoint.json`, `teaching-contracts.xml` and `artifacts/visual-review/certification-extraction-engine-teaching-2026-10-05-browser/`. Browser delivery is synthetic and awards no assessed credit. Thirty-six lessons across five modules now have draft visual evidence; 38 lessons across six modules remain. All draft outcome readiness statuses remain unchanged. Actual NIH practical assessment, calibrated review and course publication remain open.


### Checkpoint 39 Deterministic execution evidence stays separate from model judgment on October 5 2026

**Status:** Internal Foundations execution check and saved-result integration verified. **Related and still open:** Foundations executed extraction and complete practical grading. Accepted count remains 11/162.

The trusted collector now saves a deterministic result for `foundations.executed_extraction`: the completed run must bind the reviewed extraction revision, exact assigned inputs and preserved before-run authorization. The checker pins the assessed requirement's identity and meaning; changed requirements require an explicitly reviewed checker rather than silently reusing this one. Source assignment/ownership and packaged hashes are verified by the collector before the check.

Model review continues to cover only the two structured outcomes. Its verdict cannot replace or overwrite the execution check. Saved assessment results expose the deterministic evidence separately, including when semantic review requires revision or the provider is unavailable. Technical recovery and linked retries preserve that same original check. A supported execution result does not imply that extracted values are correct or that the learner's explanation is adequate, and none of these draft results award credit or permit module completion.

**Verification:** 42 real-Mongo practical/review/recovery cases passed, including nine new cases covering separate outcome coverage, unclear semantic results, technical recovery/retry and broken source/artifact/approval/result links or changed requirements. Another 38 automatic-review/calibration/outcome contracts passed. Targeted Ruff, preserved-release and whitespace checks passed. Existing dependency warnings remain.

**Evidence:** `artifacts/visual-review/certification-practical-checks-2026-10-05/checkpoint.json`, `checks-and-regression.xml` and `review-contracts.xml`. Providers are synthetic. Full learner-facing practical delivery, real-model calibration, release readiness and earned-credit integration remain open. The user has been asked for the environment to use for live-model calibration; independent curriculum work continues. No staff task, publication, deployment or live learner change occurred.


### Checkpoint 40 Multi-Step teaching draft on October 5 2026

**Status:** Six unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M05-01/02/03/04 and connected practical assessment. Accepted count remains 11/162.

The lessons now teach inspection of actual configured sources, combined source context, step-level inputs and task overrides. They distinguish source-supported terms from interpretations and unresolved questions. The assigned procedure requires one saved revision, actual execution, intermediate-output inspection and a traceable repair. More stages are not presented as an automatic quality improvement, and an instructional checkpoint is distinguished from an implemented approval pause.

The worked example identifies unsupported deadline and institutional-policy claims instead of inventing a correct date or comparison. Formatter and post-process model transformations require meaning and uncertainty checks. Source behavior was verified in `workflow_engine.py` input resolution, Prompt/Formatter processing and saved step-output/error handling.

**Verification:** 46 shared teaching/scenario/outcome contracts passed. All 42 production browser states passed at 320px, 390px and 1440px, including wrong-to-correct feedback for each lesson, with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow numbered procedure, unsupported-inference feedback and desktop input-source lesson. Shared production renderer/build evidence remains checkpoint 35. Whitespace checks passed; published teaching remains untouched.

**Evidence:** `artifacts/visual-review/certification-multi-step-teaching-2026-10-05/checkpoint.json`, `teaching-contracts.xml` and `artifacts/visual-review/certification-multi-step-teaching-2026-10-05-browser/`. Delivery is synthetic and proves presentation/practice, not real connected execution or calibrated assessment. Forty-two lessons across six modules now have draft visual evidence; 32 lessons across five modules remain. No course publication, deployment or live learner change occurred.


### Checkpoint 41 Advanced Nodes teaching draft on October 5 2026

**Status:** Six unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M06-01/02/03/04 and advanced practical assessment. Accepted count remains 11/162.

The lessons separate model-based Deep Analysis from deterministic calculation evidence. They require source-linked inputs, units, formula and a checked result, without requiring standard learners to obtain Code Node privileges. Restricted runtime behavior is no longer presented as a blanket correctness or isolation guarantee. Method choice starts with the required evidence rather than a fixed node count or an advanced label.

Parallel tasks are limited to independent work. The teaching explains configured step inputs/task overrides, listed-order output collection and the need to inspect combined output meaning. Dependent conclusions and releases wait for their prerequisite evidence and required approval. A failed sibling does not prove an external effect was undone, so recovery requires checking actual status. The worked calculation uses explicitly illustrative values and does not claim a successful run on the assigned document. Source behavior was checked in the workflow engine, Code Node authorization boundary, editor palette and restricted code runner.

**Verification:** 47 shared teaching/scenario/outcome contracts passed. All 42 production browser states passed at 320px, 390px and 1440px, including wrong-to-correct feedback for each lesson, with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected narrow procedures, dependent-action feedback and the desktop calculation/permission lesson. Preserved-release/outcome/whitespace checks passed. Shared production renderer/build evidence remains checkpoint 35.

**Evidence:** `artifacts/visual-review/certification-advanced-nodes-teaching-2026-10-05/checkpoint.json`, `teaching-contracts.xml` and `artifacts/visual-review/certification-advanced-nodes-teaching-2026-10-05-browser/`. These are synthetic teaching fixtures, not executed calculation or parallel-work assessment. Forty-eight lessons across seven modules now have draft visual evidence; 26 lessons across four modules remain. No staff task, publication, deployment or live learner change occurred.


### Checkpoint 42 Output Delivery teaching draft on October 5 2026

**Status:** Five unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M07-01/02/03/04 and artifact/release assessment. Accepted count remains 11/162.

The lessons now name the formats actually supported by Document Renderer and Data Export, explain the CSV text fallback and require opening the generated files. Form filling requires usable template fields and inspection of missing/unsupported values. Generation, release authorization and confirmed handoff are distinct evidence; a filename or download link does not prove usable content or delivery.

The worked example supplies a concrete input route for separate CSV and narrative outputs. A later Prompt reads the assigned Workflow Documents rather than treating the preceding download payload as source text. Marked output steps can be bundled in a ZIP; the unavailable Package Builder palette entry is not required. Invented report figures and unsupported format guarantees were removed. Behavior was checked in the workflow engine, output settings and result-download bundling code.

**Verification:** 48 shared teaching/scenario/outcome contracts passed. All 35 production browser states passed at 320px, 390px and 1440px, including each lesson's wrong-to-correct feedback, with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow procedure, exact-release feedback and final desktop input-routing example. Shared production renderer/build evidence remains checkpoint 35.

**Evidence:** `artifacts/visual-review/certification-output-delivery-teaching-2026-10-05/checkpoint.json`, `final-teaching-contracts.xml` and `artifacts/visual-review/certification-output-delivery-teaching-2026-10-05-browser-input-routing/`. These fixtures prove teaching presentation, not actual generated artifacts or delivery. Fifty-three lessons across eight modules now have draft visual evidence; 21 lessons across three modules remain. No publication, deployment or live learner change occurred.


### Checkpoint 43 Validation & QA teaching draft on October 5 2026

**Status:** Eight unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M08-01/02/03/04 and real validation/repair assessment. Accepted count remains 11/162.

The lessons distinguish source accuracy, output shape, repeated agreement and scoped quality measurements. They require representative cases with checked expectations, explicitly missing/ambiguous cases and held-out regression evidence. Saved checks do not guard every future execution. Workflow validation currently evaluates recent completed runs, so a repair requires new execution and inspection of which results were actually graded. Workflow checks include model judgment; an unavailable or skipped check is not a pass.

Guided verification now explains field approval/correction, skipped-field coverage gaps and actual finalization. The worked example is explicitly illustrative and no longer fabricates a passing run history. Fixed test-count guarantees and the unsupported claim that the assistant cannot see scores were removed. Behavior was checked in workflow validation, extraction metrics, quality scoring and verification-session finalization code.

**Verification:** 49 shared teaching/scenario/outcome contracts passed. The first browser pass exposed unsupported lesson variants causing a renderer error; corrected variants and an added contract assertion address that failure. The final 56 production browser states passed at 320px, 390px and 1440px with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected narrow run/retest instructions, guided-verification feedback and desktop quality-signal teaching.

**Evidence:** `artifacts/visual-review/certification-validation-qa-teaching-2026-10-05/checkpoint.json`, `final-teaching-contracts.xml` and `artifacts/visual-review/certification-validation-qa-teaching-2026-10-05-browser-corrected-variants/`. The first failed browser capture is retained. These fixtures prove presentation and formative feedback, not real validation execution or calibrated assessment. Sixty-one lessons across nine modules now have draft visual evidence; 13 lessons across two modules remain. No staff task, publication, deployment or live learner change occurred.


### Checkpoint 44 Batch Processing teaching draft on October 5 2026

**Status:** Six unpublished replacements verified for presentation and formative practice. **Related and still open:** C8-M09-01/02/03/04 and assigned batch/recovery assessment. Accepted count remains 11/162.

Batch teaching now requires exact assigned-input reconciliation, per-item source checking and explicit exception records. It removes the claim that all jobs execute sequentially. The aggregate completed state can include failed items, and the downloaded bundle can omit failed or unfinished results. Neither counts nor completion labels establish correct coverage.

The recovery example preserves successful work, checks actual repaired source text and requires checking uncertain external effects before any retry. Model and batch choices use representative pilot evidence with recorded quality/resource tradeoffs. Fixed success assumptions and automatic improvement from re-uploading a scan were removed. Source behavior was verified in batch dispatch/status/cancellation, download bundling and model resolution.

**Verification:** 50 shared teaching/scenario/outcome contracts passed. All 42 production browser states passed at 320px, 390px and 1440px, with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected the narrow assigned-batch procedure, mixed-result recovery feedback and desktop bad-source example.

**Evidence:** `artifacts/visual-review/certification-batch-processing-teaching-2026-10-05/checkpoint.json`, `teaching-contracts.xml` and `artifacts/visual-review/certification-batch-processing-teaching-2026-10-05-browser/`. These fixtures prove presentation and formative feedback; real input coverage, pilot quality and targeted recovery assessment remain open. Sixty-seven lessons across ten modules now have draft visual evidence; Governance's seven lessons remain. No staff task, publication, deployment or live learner change occurred.


### Checkpoint 45 Governance teaching draft and full teaching-pass coverage on October 5 2026

**Status:** Seven unpublished replacements verified for presentation and formative practice. All 74 lessons across eleven modules now have draft replacements with browser evidence. **Related and still open:** C8-M10-01/02/03/04, capstone assessment and release readiness. Accepted count remains 11/162.

Governance now requires an accountable internal handoff with ownership, intended use, exact tested revision, evidence, limitations and a change/review route. It distinguishes access, library review, certification and operational authority. Broad publication and examiner availability are not certification requirements. The final lesson no longer declares the learner certified merely for reaching it.

Export/import teaching explains embedded content, portability warnings and dependency repair/retesting. The two-office example requires actual learner decisions about scope, an unsupported value, uncertain delivery recovery and release. Later changes need new evidence without rewriting original achievement. Optional course upgrades preserve earned history and require an explicit choice; the teaching does not imply that the rollout is already implemented. Source behavior was checked in export/import, library review and the agreed transition policy.

**Verification:** 51 shared teaching/scenario/outcome contracts passed. All 49 production browser states passed at 320px, 390px and 1440px with zero axe violations, horizontal page overflow, unexpected requests or page errors. Inspected narrow handoff instructions, earned-history feedback and the desktop supervision example. Preserved-release, outcome-design and whitespace checks passed.

**Evidence:** `artifacts/visual-review/certification-governance-teaching-2026-10-05/checkpoint.json`, `teaching-contracts.xml` and `artifacts/visual-review/certification-governance-teaching-2026-10-05-browser/`. Full teaching-pass coverage is not course release readiness: connected labs, complete outcome assessment, real-model calibration, transitions and learner/accessibility observation remain open. Outcome readiness statuses remain conservative; no 8/10 reassessment or new accepted checklist item is claimed. No staff task, publication, deployment or live learner change occurred.


### Checkpoint 46 Validation & QA and Governance recognition assessments on October 5 2026

**Status:** Eight new unpublished scenarios verified through deterministic grading, authenticated persistence and responsive delivery. **Related and still open:** C8-M08-01, C8-M10-01/03 and complete assessed course integration. Accepted count remains 11/162.

The three draft banks now contain 17 scenarios covering all five declared recognition outcomes. Validation & QA adds cases for consistent wrong values, historical score scope, validation of an old execution after a prompt change and skipped-field coverage. Governance adds cases for pending library review, later artifact changes, explicit optional upgrades and unsupported claims of learner review. These cases assess recognition only; they do not demonstrate the mixed modules' practical outcomes.

The design checker requires exactly one bank for each module with scenario-choice requirements and verifies its exact contract coverage. Every new wrong choice fails the relevant outcome even if the other choices are correct. Public definitions omit answer keys/feedback. The browser harness now accepts the selected module rather than being hard-coded to AI Literacy. Shared fixture packages include all three banks so delivery and persistence can be checked under the same pinned-course rules.

**Verification:** 70 teaching/scenario/outcome contracts passed, including 19 new recognition cases. All 38 affected real-Mongo scenario/decision/trusted-review cases passed, including two new mixed-module persistence cases that preserve zero XP and incomplete practical outcomes. Both new browser flows passed all 14 states each at 320px, 390px and 1440px: explicit choices, keyboard navigation, lost-response recovery with stable request identity, wrong feedback and a corrected new submission. Zero axe violations, horizontal page overflow, unexpected writes/requests or page errors. The intentional synthetic HTTP 503 is the recovery trigger, not an unresolved failure. Inspected narrow choices, corrective feedback, pending recovery and successful recognition. Targeted Ruff, browser-script syntax, outcome-design and whitespace checks passed. Existing dependency deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-remaining-scenarios-2026-10-05/checkpoint.json`, `contracts.xml`, `persistence.xml`, `artifacts/visual-review/certification-validation-qa-scenarios-2026-10-05-browser/` and `artifacts/visual-review/certification-governance-scenarios-2026-10-05-browser/`. Browser grading/persistence is synthetic; durable receipts are checked separately against disposable MongoDB. No model call, earned credit, staff task, course publication or live learner change occurred. Live-model calibration awaits the requested configured environment; connected practical delivery and optional upgrade acceptance remain open.


### Checkpoint 47 Optional course comparison on October 6 2026

**Status:** Learner-facing read-only comparison verified. **Related and still open:** C8-MIGRATE-02/03/04/06 and optional activation. Accepted count remains 11/162.

The authenticated comparison reads an existing owned enrollment without initializing one. A validated registry mapping explicitly offers source/target pairs; only published targets with an outcome contract appear. Draft, retired, unoffered and withdrawn targets are unavailable. Source changes and withdrawn offers invalidate a comparison. No offer is configured in the real registry.

The panel shows original earned XP, completed-module history, unknown legacy provenance, saved-place and credential preservation, target outcomes and saved-work counts. All target outcomes still require assessment because no equivalence is verified. Unfinished answers and raw evidence stay private. Learners can close the comparison and continue their current course; closing does not save a permanent decline. Activation remains unavailable. Late responses, mismatched identity and failed refreshes cannot display another course's preview.

Screenshot inspection also found a negative remaining-XP label when the saved level lagged behind earned XP. The next threshold now follows earned XP, clamps animation widths and labels the highest threshold without implying certification. Four regression cases cover stale levels, an exact threshold and the highest threshold.

**Verification:** 32 catalog/release contracts, 22 affected real-Mongo cases and 22 frontend cases passed. The production build and targeted ESLint/Ruff passed. All 19 final browser states passed with zero axe violations, page overflow, unexpected requests/writes or page errors. Coverage includes the comparison at 320px, 390px and 1440px, no-offer, server/conflict recovery and the highest-XP display. The initial highest-XP extension needed a corrected harness route because reloading the workspace closes the panel, and the progress details must be expanded before capturing the XP bar; earlier captures are retained. The intentional 503/409 responses exercise recovery. Preserved-release and whitespace checks passed. No model call, staff task, earned-credit change, publication or live learner migration occurred.

**Evidence:** `artifacts/visual-review/certification-upgrade-comparison-2026-10-05/` contains catalog/persistence evidence and the checkpoint manifest. Final browser evidence is `artifacts/visual-review/certification-upgrade-comparison-2026-10-06-browser-expanded/`; the final highest-XP capture after the count reaches 1800 is in `artifacts/visual-review/certification-upgrade-comparison-2026-10-06-browser-final-xp/`. The browser uses synthetic offered-course responses; persistence uses disposable MongoDB. These establish comparison behavior, not migration readiness or real-model calibration. Live calibration is deferred at the user's request; independent overnight work continues.


### Checkpoint 48 Read-only cohort inventory tooling on October 6 2026

**Status:** Aggregate inventory verified with synthetic records. **Related and still open:** C8-MIGRATE-01 and actual cohort rehearsal. Accepted count remains 11/162.

The explicit inventory command reads certification metadata directly without application startup, index creation, enrollment initialization or writes. It requires its own connection environment variable and an explicit database. Database projections exclude names, answer text, credential payloads, model evidence and decision content; the output also excludes learner and record IDs. Record limits fail the operation instead of emitting partial totals. Connection failures do not echo URI/provider details.

Counts distinguish unstarted records, active selected courses, completed selected courses and inconsistencies. Overlapping flags preserve earlier completion, unknown provenance, prerequisite overrides, unfinished answers, pending issuance, unresolved assessments/runs/reviews/recovery and in-flight writes. Duplicate selections/legacy progress, missing or unowned references, shared progress, mismatched identities, invalid saved values and unknown work states remain visible. Historical assessment records do not turn a fresh selected enrollment into an active course. Missing owners are counted separately. The tool does not count registered people with no certification record.

Two matching metadata reads are required, with observation times and a digest. This detects some concurrent changes; it is explicitly not a transactional snapshot, a credential-integrity check or authorization to migrate. Catalog verification and external-job reconciliation remain separate gates.

**Verification:** 35 classifier/concurrent-read contracts and two real-Mongo projection/command cases passed. The latter check sensitive-content exclusion, malformed modules, exact cohort classification, explicit connection requirements, bounded reads and unchanged database records/collections. Targeted Ruff passed. All data was synthetic in disposable databases. No production counts are claimed and C8-MIGRATE-01 remains open until an authorized actual-cohort inventory is reviewed.

**Evidence:** `artifacts/visual-review/certification-cohort-inventory-2026-10-06/checkpoint.json`, `contracts.xml` and `final-persistence.xml`. No staff queue, model call, publication or learner change occurred.


### Checkpoint 49 Read-only saved automatic-assessment feedback on October 6 2026

**Status:** Owned saved-result delivery verified; subsequent enlarged-text refinements are tracked in checkpoint 51. **Related and still open:** connected practical assessment and earned-credit integration. Accepted count remains 11/162.

Learners can list recent saved assessments and open older ones by reference. The authenticated reads require an explicit owned enrollment, validate the pinned course and saved receipt, and expose bounded feedback and cited evidence as plain text. They remain readable after the selected enrollment changes or course delivery is disabled. Internal evidence packets and provider details are excluded. Reading does not initialize an enrollment, run a model, recover or retry grading, create a staff task, or change earned credit.

Feedback distinguishes revisions, supported draft requirements, pending results and technical unavailability. A technical failure does not count as a failed learner attempt or erase a separately saved execution check. Late responses and identity mismatches cannot replace the displayed result. This is draft feedback: supported requirements do not yet complete a module.

**Verification:** 32 frontend cases and 17 production browser states passed before the enlarged-text refinements. The normal-width states cover 320px, 390px and 1440px, revision/citations, technical failure, supported/pending results, read failure and empty history, with zero axe violations, page overflow, unexpected requests/writes or page errors. A 27-case saved-review/recovery MongoDB regression passed; the subsequent 37-case affected regression also verifies the final delivery-disabled HTTP behavior. The production build and targeted lint passed before checkpoint 51. Model calls are stubbed and databases disposable.

**Evidence:** `artifacts/visual-review/certification-saved-reviews-2026-10-06/checkpoint.json`, its persistence XML files, `artifacts/visual-review/certification-saved-reviews-2026-10-06-browser/`, and the final HTTP regression in `artifacts/visual-review/certification-execution-config-2026-10-06/persistence.xml`. The later 200% text check found nested clipping despite normal-width checks passing; that repair is not claimed verified here. No publication or live learner change occurred.


### Checkpoint 50 Captured applied extraction settings on October 6 2026

**Status:** Applied configuration and frozen dispatch verified. **Related and still open:** complete practical delivery and real-model calibration. Accepted count remains 11/162.

The assessed execution planner previously captured optimizer overrides but ignored them when selecting extraction settings. It now uses the same effective-configuration resolver as the workspace. The prepared plan and model identity follow the captured applied settings; later optimizer edits cannot replace those frozen inputs. Unsupported applied modes are rejected rather than silently ignored. The resolver implementation is included in the dispatch identity so a changed implementation requires a newly prepared plan before execution.

**Verification:** The reproducer failed five of seven configuration contracts before the fix; all seven pass after it. All 37 affected MongoDB execution, practical-check, trusted-review and saved-result HTTP cases pass. New persistence cases prove that changing the live optimizer settings leaves the captured dispatch unchanged, replay does not execute twice, and changing the resolver implementation blocks dispatch. Existing dependency deprecation warnings remain. The database run took almost 56 minutes under heavy host load but finished with no failures. Targeted Ruff passed.

**Evidence:** `artifacts/visual-review/certification-execution-config-2026-10-06/checkpoint.json`, `before-fix.xml`, `contracts.xml` and `persistence.xml`. Provider execution was stubbed. No model cost, staff task, credit change, publication or live learner update occurred.


### Checkpoint 51 Enlarged-text feedback, comparison and panel controls on October 6 2026

**Status:** Bounded layout and keyboard repairs verified. **Related and still open:** full C8-A11Y coverage and complete course visual acceptance. Accepted count remains 11/162.

At 200% text size, nested padding squeezed the saved-feedback heading and prose beyond their containers. Feedback and comparison now use more available mobile width, controls wrap, and assessment dates help identify saved results. Long references remain available in expandable details. Closing either view returns keyboard focus to its opening button, with late callbacks fenced against a subsequent action.

The position selector no longer truncates its selected value at enlarged text. The floating panel's title was also squeezed into fragments by controls sharing its row, so the position controls now occupy a separate row. Browser assertions cover nested text overflow, expanded references, focus restoration and the floating title. Error captures preserve the primary failure rather than masking it with another region lookup.

**Verification:** All 41 affected frontend cases pass across four files with the original Vitest runner and default test timeouts (9.56 seconds). The full TypeScript/production build and targeted ESLint pass. The final browser matrix passes 80 states: 21 saved-feedback states and 19 comparison states each at normal and 200% root text size, covering 320px, 390px and 1440px plus the floating header. Zero axe violations, horizontal page overflow, unexpected requests/writes or page errors. Enlarged-text nested overflow and close-focus assertions pass. Inspected the narrow feedback/reference display, narrow comparison and repaired floating title. Intentional 503/409 responses exercise error recovery.

Heavy host load initially caused three worker-startup failures. A temporary startup allowance then ran 41 cases with 21 five-second timeouts; a later longer-deadline diagnostic passed 17 cases but could not start two other files. Both temporary runner changes were restored byte-for-byte. Once the host recovered, the unchanged runner completed the clean 41-case regression. Earlier failures remain recorded. No simulator or other application was stopped. A failed first comparison capture predates the final matrix and is retained.

**Evidence:** `artifacts/visual-review/certification-enlarged-text-2026-10-06/checkpoint.json`, `final-frontend-tests.json`, diagnostic logs/runner receipts, and the four sibling `-comparison-text`, `-feedback-text`, `-feedback-normal`, `-comparison-normal` capture directories. The final browser action deadline was 120 seconds to tolerate host load; this is functional evidence, not a performance benchmark. Doubled root text size is not full browser zoom, and it does not complete screen-reader or learner-observation gates. No model call, staff task, credit change, publication or live learner migration occurred.


### Checkpoint 52 Authenticated practical preparation and recoverable receipts on October 6 2026

**Status:** Preparation HTTP boundary and receipt recovery verified. **Related and still open:** complete learner-facing practical assessment and C8-GRADE/C8-VERSION evidence. Accepted count remains 11/162.

Preparation requires an explicitly selected existing owned enrollment, an owned extraction, assigned provisioned documents and a pinned Foundations outcome/decision/proposal package. Legacy courses and unsupported modules do not offer this action. The server captures fields, applied settings and verified source inputs, then prepares a run with the same request identity. It does not dispatch a model, create global settings, initialize an enrollment or award credit. Course delivery advertises the capability only for the supported pinned package.

Identical retries return the original preparation even after the live extraction/source is removed or runtime settings become unavailable. If capture succeeded but planning was interrupted, the read-only receipt reports saved inputs; an explicit retry finishes from those same inputs. Missing inputs for an existing run are never reconstructed from current workspace data. Concurrent or reused references cannot create duplicate work or borrow another run. Public responses select learner-facing fields and omit provider credentials/routing and raw source text. Owned reads remain available after selection changes and while delivery is disabled.

A confirmed capture rejection with no saved record and a still-valid write lease returns an editable 422. Existing captures, lost leases and planning failures retain the original request for recovery. Authentication, explicit enrollment, unsupported-module, actor-forgery and cross-owner boundaries are checked at HTTP level.

**Verification:** Seven initial preparation cases, a 30-case affected input/review regression and twelve final preparation/capability cases passed against disposable MongoDB. A real SystemConfig-shape test then reproduced a serialization failure from database IDs/timestamps. The adapter now emits JSON settings without record/edit metadata; nine runtime/configuration contracts pass, including credential rotation without requirement changes, genuine setting changes invalidating the fingerprint, and missing configuration remaining uninitialized. The failing reproducer is retained. Targeted Ruff passed. Cases include frozen retry after deletion, partial capture/recovery, missing-original preservation, reference collision, concurrent requests, no automatic enrollment, legacy/foreign/unassigned rejection, capability gating, disabled-delivery reads and the distinction between 422 rejection and 503 partial planning failure. Provider dispatch was asserted absent; no live model was used.

**Evidence:** `artifacts/visual-review/certification-practical-preparation-2026-10-06/checkpoint.json`, `persistence.xml`, `final-persistence.xml` and `final-preparation.xml`, `runtime-before-fix.xml` and `runtime-contracts.xml`. Learner presentation remains separately tracked in checkpoint 53. No staff task, publication or live learner change occurred.


### Checkpoint 53 Recoverable learner preparation and scope handoff on October 6 2026

**Status:** Learner preparation delivery verified. **Related and still open:** full practical assessment and accessibility acceptance. Accepted count remains 11/162.

The draft-capable Foundations module now offers an owned-extraction picker, saves a stable request reference before transmission, and displays the frozen fields, assigned documents and planned models. Empty extractions cannot be selected. A definite unsaved rejection permits correction; an unconfirmed request retains its identity across remount. Recovery reads the original receipt before explicitly finishing missing preparation, and a failed history read cannot start replacement work. Scope review remains a separate learner action with no preselected source or approval.

Preparing refreshes the saved-run list immediately. The scope handoff moves keyboard focus into the saved source and learner review; closing preparation restores focus to its opening control. Late responses and mismatched identities cannot replace the displayed receipt.

**Verification:** The 23 preparation/review cases pass; the subsequent execution UI regression includes those cases and passes all 37 tests. Targeted ESLint and the production build pass. The final preparation matrix verifies 48 states: 24 normal and 24 at doubled root text size, spanning 320px, 390px and 1440px, rejected/partial/lost responses, unavailable history, recovery, reference display and scope handoff. Zero axe violations, page overflow, unexpected requests or page errors; enlarged-text nested overflow checks pass. The 320px ready state was visually inspected at both text sizes.

A browser navigation waiting for the full load event timed out after five successful final 320px captures, and its failure capture stalled. Only that isolated QA process was interrupted. Those five verified states plus nineteen remaining states from a successful run form the final normal matrix. The harness now waits for DOM readiness and the actual controls, and preserves a failure without trying another operation on a stalled renderer. All 24 enlarged-text states then passed. Earlier provisional captures remain separate. Text scaling is not full browser zoom or screen-reader acceptance.

**Evidence:** `artifacts/visual-review/certification-practical-preparation-2026-10-06/learner-ui-checkpoint.json` and sibling `-normal-final`, `-normal-rest`, `-text-final` capture directories. The tested preparation bundle was `index-CFMqDClJ.js`; source-tree fingerprints may include subsequent local work, so this bundle identity is recorded separately. Checkpoint 55 verifies the later execution UI bundle. No live model, staff work, publication or learner migration occurred.


### Checkpoint 54 Explicit approved practical execution boundary on October 6 2026

**Status:** Authenticated execution and read-only status verified with stubbed providers. **Related and still open:** connected automatic grading and calibrated practical assessment. Accepted count remains 11/162.

Execution requires an explicit existing selected enrollment, exact saved plan hash, exact linked scope-decision reference/hash and an explicit execution consent value. The server verifies the owned pinned Foundations package, corrected assigned source, original inputs and unchanged runtime/implementation before claiming the run. It repeats the displayed-approval comparison inside the dispatch boundary, and the conditional claim still rejects a concurrent approval change. A stale screen cannot silently authorize a different plan or decision.

Status reads validate ownership and saved integrity, explain readiness without acquiring a write lease, and expose only selected learner-facing metadata. They never initialize an enrollment, create global configuration or dispatch a provider. Owned history stays readable while delivery is disabled or a different course is selected. Readiness remains advisory; the explicit write rechecks every execution condition.

A replay of an already executing/completed/failed/uncertain run returns its saved state without loading configuration or repeating execution. Technical failure and uncertainty remain distinct from a failed assessment; neither awards credit nor creates a staff task. Provider details, raw exceptions and result entities are excluded from this status response; saved values remain available through the existing owned review context.

**Verification:** All ten new service/HTTP cases and all 65 affected MongoDB preparation, source-decision and execution regression cases pass. They cover missing/wrong-source approval, frozen source dispatch after workspace deletion, stale displayed identities, an approval changing across the dispatch boundary, unavailable/changed settings, technical failure/uncertainty, exact replay, authentication, forged metadata, explicit consent/enrollment, disabled delivery and preserved history. Targeted Ruff passes. All databases are disposable and provider calls are stubbed; no live-model result is claimed.

**Evidence:** `artifacts/visual-review/certification-practical-execution-2026-10-06/persistence.xml`, `regression.xml` and `checkpoint.json`. The learner execution controls remain under checkpoint 55 verification. No credit, credential, publication or live learner change occurred.


### Checkpoint 55 Explicit learner execution and saved-value handoff on October 6 2026

**Status:** Execution controls verified. **Related and still open:** automatic-assessment presentation and complete practical course acceptance. Accepted count remains 11/162.

Learners check the saved plan and approval, then explicitly run those inputs. Status checks never dispatch. The request records its exact plan/approval locally before transmission; unavailable storage prevents sending. Lost responses retain the run reference and require a read before another explicit action. A prepared recovered state does not automatically execute. In-flight, failed and uncertain states have no rerun control, and technical failure is not presented as a failed learner assessment. Completed runs offer an explicit handoff to checking their saved values.

Browser QA exposed a focus request that could run before the value-review region mounted. The handoff now focuses after DOM commit. An integration test also exposed duplicate React keys shared by preparation and saved feedback; those sections now have distinct keys. Both repairs are verified, including the absence of the duplicate-key warning in the final integration test.

**Verification:** All 38 affected frontend cases pass; the final 14-case review regression also passes after the key repair. The full TypeScript/production build and targeted ESLint pass. The final matrix passes 48 browser states: 24 each at normal and doubled root text size across 320px, 390px and 1440px, including missing approval, explicit source correction, completion, reference display, focus handoff, in-flight/failure/uncertainty, unavailable/mismatched status, lost response and stale approval. Zero axe violations, page overflow, unexpected requests or page errors; enlarged-text nested overflow checks pass. Narrow normal/enlarged execution and value handoff captures were inspected.

Earlier captures preserve a selector error, the reproduced focus failure, and an unavailable-preview failure. A host interruption also stopped the local preview/database and an earlier build; a frontend rerun failed to start its workers. Only disposable QA services were restarted. The final build has an explicit zero exit receipt and the final test run used the unmodified runner/default timeouts. No unrelated application was stopped.

**Evidence:** `artifacts/visual-review/certification-practical-execution-2026-10-06/learner-ui-checkpoint.json`, `verified-frontend-tests.json`, `final-review-tests.json`, `final-keys-build.json`/`.log`, and sibling `-normal-finalkeys`/`-text-finalkeys` directories. The manifest records the exact bundle hash. Browser responses are synthetic; no live model, credit, staff work, publication or learner migration occurred.


### Checkpoint 56 Learner-requested automatic assessment and technical retry on October 6 2026

**Status:** Automatic-assessment HTTP boundary verified with a stubbed judge. **Related and still open:** learner assessment controls, live calibration and earned-credit integration. Accepted count remains 11/162.

An explicit assessment request accepts only its stable identity and consent. Evidence is assembled from the owned saved run, preserved scope approval and latest saved value checks; clients cannot supply evidence text, actor metadata or a grading model. The adapter selects the configured system judge, then the application default/first configured model when no judge/default is specified. An explicitly configured missing or ambiguous judge fails closed rather than silently changing the assessment model. The selected model and requirements are frozen in the existing review receipt.

Interrupted prepared requests resume from their original evidence. In-flight or terminal replays do not reload settings or grade twice. Technical retry is a separate explicit action linked to the failed original assessment, preserves the original evidence/model requirements and cannot create multiple children from the same failure. No automatic retry or staff queue is introduced. Feedback uses the existing owned, bounded saved-result response; no action awards XP, completion or credentials.

**Verification:** Seven model-selection contracts, eight service/HTTP cases and one additional run/owner reference-isolation case pass. These cover trusted collection, missing source checks, unavailable judge, interrupted preparation, frozen replay after source deletion, concurrent identical requests, technical retry lineage, authentication, consent, forged evidence/model/actor fields, disabled delivery and readable saved feedback. Targeted Ruff passes. The first run had three incorrect expectations for the always-supporting stub and one missing test-catalog override; corrected fixtures pass. A separate rerun could not connect after the disposable database stopped; those setup errors remain recorded. All final persistence cases used a fresh disposable MongoDB directory and a stubbed judge. Supported fixture feedback is not actual grading-validity evidence.

**Evidence:** `artifacts/visual-review/certification-assessment-delivery-2026-10-06/checkpoint.json`, `model-selection.xml`, `verified-persistence.xml`, `reference-isolation.xml`, and retained diagnostic XML. Live-model calibration remains explicitly deferred. No model cost, staff task, publication or live learner change occurred.


### Checkpoint 57 Learner automatic-assessment controls and feedback handoff on October 6 2026

**Status:** Assessment request/retry presentation verified. **Related and still open:** live grading validity, earned credit and all-module practical delivery. Accepted count remains 11/162.

After reaching saved-value review, learners can explicitly request automatic assessment of their saved work. The request reference is stored before transmission. Checking an unconfirmed request only reads; a confirmed missing/prepared/in-flight receipt exposes a separate action to finish that same request. A failed history read cannot silently start or replace an assessment. Technical retry creates a new linked request using the original evidence, while assessing revised saved work creates a separate fresh assessment. Storage failure prevents transmission, and mismatched run/enrollment/parent or credit/staff flags are rejected.

The learner can open the resulting saved feedback directly without locating it in a history list. Feedback and close focus now wait for the corresponding DOM elements to mount. The handoff remains read-only and preserves the distinction between deterministic execution checks, model judgment, revision guidance and technical unavailability. Evidence quotations are rendered as text.

**Verification:** All 38 affected frontend cases pass, including 15 new request/recovery/retry cases and the direct-feedback focus case. Targeted ESLint and the full TypeScript/production build pass. All 54 browser states pass: 27 normal and 27 with doubled root text size at 320px, 390px and 1440px. The matrix includes saving honest unresolved source checks, explicit assessment, revision feedback/citations/details, supported/unavailable/prepared/evaluating states, original-evidence retry, finishing a prepared request, unavailable history, missing-receipt confirmation, lost main/retry responses and mismatched receipts. Zero axe violations, page overflow, unexpected requests or page errors. Enlarged-text nested overflow and both feedback/close focus checks pass. Narrow feedback and enlarged technical-unavailability views were inspected.

**Evidence:** `artifacts/visual-review/certification-assessment-controls-2026-10-06/checkpoint.json`, `frontend-tests.json`, `build.json`/`.log` and sibling `-normal`/`-text` capture directories. The exact bundle hash is recorded. Feedback is synthetic; these checks do not establish live grading accuracy, full browser zoom or screen-reader acceptance. No real model, staff task, credit, publication or learner migration occurred.


### Checkpoint 58 Owned practical history and keyboard-readable sources on October 6 2026

**Status:** Owned run/context history verified. **Related and still open:** prior-course history navigation and optional migration acceptance. Accepted count remains 11/162.

Run listings and decision context now require an explicit owned enrollment and read its original pinned package without initializing or selecting a course. Sources, extracted values, original proposals and saved decisions remain available after another course is selected, selection is missing, the enrollment is retired, or submissions are disabled. History reads do not acquire a write lease, reload live workspace evidence or call a provider. Missing or tampered saved inputs fail closed. New work remains subject to the selected-course write boundary.

The learner view explains read-only status and hides preparation, execution and assessment controls. Decision fields remain readable but cannot submit, including a locally pending draft. Mismatched list identities fail closed. Preparation can refresh the run list without unmounting its receipt or losing its scope handoff.

Enlarged-text browser QA found that long source text could scroll without a keyboard focus target. Saved source and extracted-output viewers now have named, focusable scroll regions. The repeated reason message also exposed an ambiguous browser-test locator; the test now scopes to the source-review region.

**Verification:** All 64 affected frontend cases pass; all 16 review cases pass again after the keyboard repair. Ten final MongoDB cases pass, covering current/changed/missing selection, disabled delivery, abandoned/transferred enrollments, authentication, ownership, no initialization, tampered evidence and unchanged collections. Targeted lint and both production builds pass. Final browser captures pass 20 history states (ten normal and ten doubled root text at 320px, 390px and 1440px) with zero axe violations, horizontal page overflow, unexpected requests or page errors. Enlarged-text nested text checks pass. Five preparation states verify receipt refresh and scope handoff. Narrow expanded original-output and enlarged source captures were inspected. Both saved-content regions were focused directly; an earlier capture had inadvertently collapsed the initially open output details, so the final matrix corrects that capture action.

An initial tampering test edited the wrong field; its corrected test passes. A subsequent sandboxed database run was denied localhost access; the permitted disposable-database rerun passes. Earlier selector and accessibility failures remain recorded. The preparation regression preceded the final focusability-only change. Synthetic browser responses and real disposable persistence are verified separately; no live grading validity is claimed.

**Evidence:** `artifacts/visual-review/certification-practical-history-2026-10-06/checkpoint.json`, frontend/keyboard test reports, `final-persistence.xml`, build receipts and sibling `-normal-expanded`, `-text-expanded` and `-preparation-regression` directories. The exact final bundle hash is recorded. Prior-course navigation still needs a learner entry point; transfer activation remains blocked. No staff task, credit, publication or learner migration occurred.


### Checkpoint 59 Learner navigation to owned original-course work on October 6 2026

**Status:** Prior-course practical history entry point verified. **Related and still open:** scenario history and optional transition activation. Accepted count remains 11/162.

Learners can browse their latest 50 saved enrollments or open an older enrollment by its full reference, then choose a practical module and inspect its original sources, values, decisions and automatic feedback. This entry point is available in the curriculum and when selected-course progress cannot load. It performs only reads and does not select, initialize, reactivate or upgrade a course. Even the currently selected course is read-only in this history view.

The server discovers only authenticated owned enrollment references and verifies the original package before exposing prompts. Unavailable or mismatched definitions remain discoverable by reference without substituting current requirements. Opening and closing restore useful keyboard focus after DOM commit. Stale requests cannot populate a closed/unmounted view; the panel keys history by account identity. Course errors clear previously displayed results. Original progress and credentials remain separate from this practical-history view.

**Verification:** Four MongoDB service/HTTP tests pass, including 53 owned enrollments, bounded listing/older-reference access, foreign-owner exclusion, unavailable/tampered definitions, missing selection, delivery disabled, authentication and unchanged collections. All 39 affected frontend tests pass. Targeted ESLint/Ruff and production builds pass. All 44 browser states pass across normal/doubled root text at 320px, 390px and 1440px, including source/output focus, disabled writes, feedback reads, empty/unavailable/mismatched/legacy-course states, a selected-progress outage and direct references. Zero axe violations, horizontal page overflow, unexpected requests or page errors; enlarged-text nested overflow and focus assertions pass. Narrow original-course and enlarged outage-history captures were inspected.

Initial component tests emitted act warnings; the corrected async test helper runs cleanly. The browser matrix preceded the final account-identity key; the final build and 39-case regression include that isolation change. No claim of full browser zoom, screen-reader acceptance or live grading validity is made.

**Evidence:** `artifacts/visual-review/certification-course-history-2026-10-06/checkpoint.json`, `persistence.xml`, `final-frontend-tests.json`, build receipts and sibling `-normal`/`-text` captures. Tested browser and final bundle identities are recorded separately. Saved recognition-scenario browsing remains separate work. No staff task, credit, activation, publication or learner migration occurred.


### Checkpoint 60 Preserved scenario choices and honest legacy history on October 6 2026

**Status:** Read-only recognition history verified. **Related and still open:** connected practical flow and optional transfer activation. Accepted count remains 11/162.

The original-course history view now includes recognition modules as well as practical reviews. Learners can list their last 50 scenario submissions or open an older reference, then read each original prompt, recorded choice and saved feedback. Unanswered cases remain explicitly unanswered. The server verifies ownership, course/manifest and bank identity, loads existing receipts and never invokes the grader. An interrupted progress-pointer update does not hide the preserved receipt. No answer controls, retry submission, credit award or course-selection action are introduced.

The frontend rejects mismatched identities, prompts, banks and credit flags, clears a previous result on lookup failure, ignores stale results after reload/unmount, and focuses the opened result after DOM commit. Feedback is text, including markup-like strings. Missing definitions are never substituted. Legacy enrollment history now explicitly explains that an unknown earlier version remains unknown; the retained continuation definition does not prove which lessons a learner previously completed.

**Verification:** Nine final MongoDB cases pass across course/scenario history, including unlinked receipts, selection changes, retired enrollments, 52 stored submissions, old-reference retrieval, unrecorded answers, mismatched banks, ownership, disabled delivery, authentication and unchanged legacy progress. All 51 affected frontend cases pass. Corrected async test helpers run without the earlier act warnings. Targeted ESLint/Ruff and both production builds pass. Forty scenario browser states pass at normal/doubled root text across 320px, 390px and 1440px; twelve final enlarged-text course-history states verify practical history and the legacy explanation. Zero axe violations, horizontal page overflow, unexpected requests or page errors; nested enlarged-text and result-focus checks pass. Narrow feedback, enlarged unanswered-result and legacy-history captures were inspected.

**Evidence:** `artifacts/visual-review/certification-scenario-history-2026-10-06/checkpoint.json`, `final-persistence.xml`, `final-frontend-tests.json`, build receipts and sibling `-normal`, `-text`, `-course-regression` captures. Scenario and final-build bundle identities are recorded separately because the legacy explanation was added after the scenario matrix. Doubled text is not full browser zoom or screen-reader acceptance. Browser fixtures and real persistence remain separately verified; end-to-end connection is next. No model call, staff task, credit, activation, publication or learner migration occurred.


### Checkpoint 61 Connected practical browser-to-persistence flow on October 6 2026

**Status:** Connected practical delivery verified with stubbed providers. **Related and still open:** live grading, all-module assessment and optional transition acceptance. Accepted count remains 11/162.

The production frontend now has an integration harness that sends certification requests through the real FastAPI router, repositories and a uniquely named disposable MongoDB database. A loopback-only QA server clears inherited environment credentials, runs from a temporary directory and blocks outbound connections except its test MongoDB. Authentication is a fixed test actor, extraction/judge calls are stubbed, and other workspace APIs remain UI fixtures. This verifies connected certification behavior, not production authentication or model accuracy. The synthetic course and prerequisite completion are explicitly test fixtures, not released requirements or learner achievement.

A browser prepared five saved fields, explicitly corrected the proposed source and approved scope, executed once, recorded five unresolved value checks and requested automatic assessment. The test interrupted the response after the server saved execution and again after it saved assessment. Both were recovered by reading the original receipt: exactly one extraction dispatch, one judge dispatch, one run, two decisions and one assessment exist. The frontend opened real saved feedback distinguishing the deterministic execution result from stubbed revision guidance. XP, credentials, certification and course selection stayed unchanged; no write lease remained in flight.

A separate browser session then opened those persisted decisions, extraction output and feedback through the course-history entry point at 320px, 390px and 1440px, at normal and doubled root text size. Every history request was GET and before/after persistence counters were identical.

**Verification:** All 18 connected browser captures pass (six flow states and twelve history states), with zero axe violations, horizontal page overflow, unexpected requests or page errors. Focus handoffs and lost-response recovery pass. Narrow actual saved feedback was visually inspected. Python/JavaScript syntax checks and diff whitespace checks pass. Production code did not need a repair during this flow. A successful stubbed response is not live calibration evidence; full browser zoom and screen-reader acceptance remain open.

**Evidence:** `artifacts/visual-review/certification-connected-flow-2026-10-06/checkpoint.json`, `persistence-proof.json`, its six captures and sibling `certification-connected-history-2026-10-06-normal`/`-text` proofs/captures. The temporary database was reused for checkpoint 62, then dropped on clean isolated-server shutdown. No real model, staff work, live learner change, publication or course activation occurred.


### Checkpoint 62 Connected recognition submission, replay and original history on October 6 2026

**Status:** Recognition submission/history connection verified. **Related and still open:** full module competency acceptance and optional migration. Accepted count remains 11/162.

The production browser submitted explicit synthetic choices to the real recognition endpoint. After the server saved the receipt, the harness lost the response. Checking again sent the identical request identity, bank and answers; the server returned the identical saved response and retained one submission. The learner then opened that original receipt through course history at 320px, 390px and 1440px, with every displayed choice matched against the submitted one. Feedback stayed read-only and no module credit was awarded.

**Verification:** Five final connected browser captures pass, with zero axe violations, horizontal overflow, unexpected requests or page errors. Submission/result focus passes. Before/after practical counters, provider calls, XP, certification, credentials and selection remained identical; the real scenario-history endpoint confirmed exactly one receipt. The narrow actual history view was inspected. An initial QA locator expected a numbered AI Literacy card; the seeded completed prerequisite shows a checkmark instead. A fresh loaded DOM snapshot established its actual label and the corrected run passes. This was a test-navigation correction, not an application change. Enlarged-text presentation is separately covered by checkpoint 60.

**Evidence:** `artifacts/visual-review/certification-connected-scenarios-2026-10-06-final/checkpoint.json`, `persistence-proof.json` and five captures. Earlier locator failure and entry snapshots are retained separately. The isolated server then exited cleanly and dropped `certification_qa_browser_44605881d2ea447bb6bd08ffbd80045f`; checkpoint 61's cleanup receipt was updated. Authentication remains a fixed synthetic actor and the course/prerequisite are fixtures. No production authentication, live grading or learner-observation claim is made. No staff task, live learner change, publication or course activation occurred.


### Checkpoint 63 Honest implementation and release-readiness reconciliation on October 6 2026

**Status:** Draft readiness metadata reconciled. Accepted count remains 11/162; no quality reassessment is implied.

The draft contract's original placeholders still called every teaching reference revision-required and every assessment unimplemented. They now distinguish the work that exists from release acceptance: all 33 outcomes reference authored replacements among the 74 lessons; five recognition outcomes plus Foundations' three outcomes have staged implemented assessment mechanisms; 25 outcomes still need assessment implementation. None is marked verified and all 33 release gates remain open.

The README now defines those stages explicitly. Implemented does not mean calibrated, credit-bearing, enrollable, release-approved or 8/10. It also corrects outdated statements that preparation/execution/review had no learner HTTP controls. The outcome checker reports counts and exact remaining outcome IDs, and verifies that every authored outcome actually references a draft replacement. No assessed requirement, rubric, calibration expectation or published package was changed; only draft readiness metadata and its reporting changed.

**Verification:** The 105-case outcome/scenario/review/calibration/release-authoring contract regression passes. All thirteen outcome tests pass after adding a publication-guard case in which every assessment is implemented but none verified. Authored teaching coverage verifies all 74 replacements. The outcome checker, release integrity checker, targeted Ruff and diff whitespace checks pass. The legacy manifest remains `54f74731d64f6c92b94252a3ff4e3cb60f5955c6a0029118842132a9cd7e0195`; the registry still has no published/default 5.0 release. No UI or live learner change occurred.

**Evidence:** `artifacts/visual-review/certification-readiness-reconciliation-2026-10-06/checkpoint.json`, `outcomes-report.json`, `contracts.xml` and `final-outcomes.xml`. Live-model calibration remains deferred, and no release/8/10 claim or new checklist acceptance was made.


### Checkpoint 64 Source-grounded Extraction Engine repair case on October 6 2026

**Status:** Authored case/source integrity verified; assessed delivery is not implemented. Accepted count remains 11/162.

Visual review of the assigned NIH PDF found a local Poppler font-substitution failure and, with MuPDF, genuinely misaligned personnel and budget table columns. A separate unpublished two-page draft now embeds fonts and uses fixed, wrapped table columns. Its builder reuses the original generator's NIH content without running any other document generator. Exact normalized source text is preserved, excluding the new synthetic-draft footer. Both new pages were rendered in Poppler and visually inspected; rebuilding is byte-identical. Existing source files, the pinned legacy package and registry were not modified. Tagged-PDF/screen-reader acceptance remains open.

The new repair case distinguishes full-project budget from first-year budget, an unnamed postdoc from a fabricated name, constrained human-subject categories and animal-use correctness. Its deliberately flawed baseline is explicitly an authored teaching specimen, never an execution receipt or learner evidence. Private expectations bind page-level source anchors to the exact new PDF bytes. Public task data excludes those expected answers. Two decision prompts require review of the revised field semantics before execution and all four source checks after a real revised run. An unresolved answer remains unresolved. Neither field counts nor a setting change alone demonstrates repair.

Strict schemas reject execution claims, injected run identities, missing/duplicate fields, error-free baselines, fabricated absence values, unsupported categories, wrong outcomes and incomplete prompt bindings. Package loading rejects old/mismatched sources and assignments. The outcome checker validates the new case against all three Extraction Engine outcomes and its actual source text. No outcome readiness status was advanced: eight mechanisms remain implemented, 25 unimplemented, all 33 unverified.

**Verification:** All 48 affected case/outcome/decision tests pass; targeted Ruff and the release-integrity checker pass. Source normalization and deterministic PDF rebuild checks pass. MuPDF emits existing SWIG deprecation warnings. The unchanged legacy manifest remains `54f74731d64f6c92b94252a3ff4e3cb60f5955c6a0029118842132a9cd7e0195`.

**Evidence:** `artifacts/visual-review/certification-extraction-repair-case-2026-10-06/` contains original/new rendered pages, `source-proof.json`, `contracts.xml`, `outcomes-report.json` and `checkpoint.json`. New content remains outside the registry. Real owned-run binding, collector, automated grading, learner controls and calibration are still required; no credit, staff work, activation or learner migration occurred.


### Checkpoint 65 Owned repair-example binding and authenticated decisions on October 6 2026

**Status:** Internal run/decision persistence verified. Learner preparation and assessment delivery for Extraction Engine remain unavailable. Accepted count remains 11/162.

Saved execution plans now bind the public authored repair specimen to the exact input snapshot, revised artifact and assigned source. The private expected answers are not included in run/decision context. Both pre-run and post-run decisions must reference the exact saved binding. Missing, foreign or injected references are rejected before a receipt is saved; scope authorization checks that binding again before provider dispatch. A decline or missing approval blocks execution. Package validation checks the source and decision requirements. Original snapshots, examples, decisions and output survive deletion of live workspace objects, and repeated requests preserve one provider dispatch.

A source-supported absent name can be recorded as an empty checked value with the actual TBD personnel row; fabricated quotations are rejected. These records do not assert a successful repair, award credit or turn the authored baseline into an execution. Existing Foundations decisions need no repair reference. The disabled delivery boundary is unchanged.

**Verification:** All 84 affected MongoDB regression cases pass, including nine repair cases plus execution, authorization, decisions, preparation and history. All 69 affected schema/catalog/configuration unit cases pass. Targeted Ruff and release-integrity checks pass. Four existing semicolon lint findings in the adjacent history tests were corrected without behavior changes. Dependency deprecation warnings remain.

The first broader database regression was interrupted when the disposable MongoDB process exhausted its open-file limit and terminated during diagnostic capture. It was restarted on the same isolated QA path with a process-only 8192 file limit; no global setting or application database changed. A readiness check found only admin/config/local databases, and the complete final regression passes. Earlier interrupted evidence remains retained.

**Evidence:** `artifacts/visual-review/certification-repair-run-binding-2026-10-06/final-persistence.xml`, `unit-tests.json`, `initial-run-interruption.json` and `checkpoint.json`. Provider behavior is stubbed. Extraction Engine collection, automatic review and learner UI remain subsequent work; no outcome readiness or checklist acceptance was advanced.


### Checkpoint 66 Trusted Extraction Engine repair assessment on October 6 2026

**Status:** Internal collection and automatic-assessment persistence verified with stubbed models. Learner delivery remains open. Accepted count remains 11/162.

The NIH collector reads only owned saved inputs, the actual revised execution, the original authorization and the latest authenticated value review. It preserves the authored flawed example and private source expectations as a distinct `repair_baseline`, the learner's actual field revision, complete saved source text, real output and source checks. It never substitutes current workspace state or an agent's account of learner behavior. The unpublished structured-outcome evidence requirements now explicitly include the baseline, assigned source and revised output so a positive judgment must cite those evidence kinds. No passing condition or legacy requirement changed.

A separate pinned deterministic checker confirms the approved assigned revision and exactly one result containing every requested field. Explicit null values are complete output slots, not proof of correctness. Empty, partial or split results require revision. Field meaning, absence handling and actual correctness remain structured-review questions. A model's positive result cannot override a failed deterministic check; feedback gives the incomplete-run correction. Provider failures retain `passed: null`, and technical retry reuses the original collected evidence and decisions even after later answers are saved. No staff fallback or credit is introduced.

**Verification:** All 77 affected unit/contract cases pass, including 15 completeness/provenance cases. Nine new real MongoDB collector/review cases and 34 Foundations trusted-review/feedback/assessment regressions pass. The tests distinguish authored from executed evidence, preserve actual source/output, select latest checks, reject missing reviews and rehashed unbound records, preserve replay/retry, and prevent a stubbed favorable judge from overriding incomplete execution. Targeted Ruff, outcome/release checkers and diff whitespace checks pass. Existing dependency warnings remain.

**Evidence:** `artifacts/visual-review/certification-repair-assessment-2026-10-06/{contracts.xml,persistence.xml,foundations-regression.xml,outcomes-report.json,checkpoint.json}`. These tests establish mechanisms and persistence, not live grading accuracy. Extraction Engine remains `not_implemented` in the readiness ledger until its authenticated learner path is complete; eight delivered mechanisms, 25 incomplete, 33 unverified. No publication, migration, credential or new checklist acceptance occurred.


### Checkpoint 67 Learner repair comparison and accurate absence history on October 6 2026

**Status:** Repair review presentation/recovery verified with synthetic HTTP responses. Accepted count remains 11/162.

The review view now distinguishes the authored flawed example, saved revised field definitions, optional/category settings, original source and actual saved output. Submitted and recovered decisions preserve the exact repair binding; a missing/mismatched case or receipt is rejected. Explicit source-supported absence is shown as an empty value recorded as supported absence, while unresolved empty values remain separate. Original-course history remains read-only. Saved-decision focus now waits for the committed DOM.

Enlarged-text QA found clipping in original-example labels and the new absence guidance at 320px. The corrected view inherits word wrapping and uses compact fixed small-screen padding inside the example, preserving reading width as text grows. Both failures and intermediate builds remain recorded. Screenshot inspection additionally prompted the final padding refinement to reduce awkward word breaks.

**Verification:** All 77 affected frontend tests pass; all 26 review cases pass again after the first layout repair. Targeted ESLint and production builds pass. The final matrix passes all 36 repair states at normal/doubled root text across 320px, 390px and 1440px, including flawed/revised comparisons, keyboard source access, lost-response recovery, source checks, saved absence, read-only history and mismatched source rejection. Ten enlarged-text Foundations history states pass on the preceding build; the final change only adjusts repair-example padding. Zero axe violations, page/nested horizontal overflow, unexpected requests or page errors. Narrow feedback and enlarged original-example/source-check views were visually inspected. Native selects may abbreviate visible options at extreme enlargement; adjacent full-text descriptions remain available.

**Evidence:** `artifacts/visual-review/certification-repair-ui-2026-10-06/checkpoint.json`, tests/build receipts, final sibling `-readable-normal`/`-readable-text` captures and `-foundations-history`. This is not full browser zoom, screen-reader or live-grading acceptance. The authenticated complete preparation/assessment flow and pre-preparation assignment entry point are next. No credit, staff task, publication or learner migration occurred.


### Checkpoint 68 Connected NIH repair delivery and consistent assignment on October 6 2026

**Status:** Complete staged learner path verified with isolated authentication and stubbed models. Accepted count remains 11/162. Related C8-M04-01–04 remain open for full acceptance.

The repair assignment is visible before preparing a run. Once work is selected, the view shows the original example captured with that run; history never substitutes today's assignment. The separate draft exercise replaces old field-count/star instructions with the four-field NIH repair and the explicit prepare, approve, execute, source-check and automatic-assessment steps. Chat reads the same pinned exercise. Package validation rejects old count criteria, exposed expected values and mismatched case references. Existing exercises, enrollments and registry offers remain unchanged.

Supported repair packages now expose the same authenticated preparation/execution/assessment controls as Foundations. The complete HTTP test prepares actual owned inputs, records scope approval, dispatches a stubbed extraction, saves four source checks, requests automatic review and retrieves the original feedback. It also covers technical grading retry without recollecting evidence, ownership rejection, disabled-write/readable-history behavior and unauthenticated access. The browser loses execution and grading replies after the real server saves them, then recovers each without a second provider dispatch. Progress, credentials and course selection remain unchanged.

**Verification:** 51 real disposable-MongoDB cases pass, including two complete HTTP flows and Foundations regressions. All 72 final backend contract cases and 67 frontend cases pass; targeted Ruff/ESLint, release/outcome checks, diff whitespace and production build pass. All 22 connected browser captures at normal/doubled root text pass across assignment/feedback widths 320, 390 and 1440 and the full 390px action flow. Zero axe violations, page/nested review text overflow, unexpected requests or page errors. Narrow assignment/feedback and enlarged assignment captures were inspected. This is not full browser zoom or screen-reader acceptance.

One frontend case initially exceeded its five-second timeout during heavy host load; the unchanged complete rerun passes. The readiness update exposed one old test assertion requiring `not_implemented`; it now correctly expects implemented delivery, with all outcomes still unverified. Initial/failed receipts remain retained. Dependency and existing build warnings remain.

The three Extraction Engine outcome mechanisms advance to `implemented`: 11 implemented, 22 not implemented, 0 verified. This is not grading calibration, earned credit or a release/8/10 judgment. Both browser databases were disposable and cleaned up. No learner migration, external communication, publication or staff task occurred. The legacy manifest remains `54f74731d64f6c92b94252a3ff4e3cb60f5955c6a0029118842132a9cd7e0195`.

**Evidence:** `artifacts/visual-review/certification-repair-delivery-2026-10-06/checkpoint.json`, persistence/contract/frontend receipts, build log and sibling `-normal`/`-text` captures. Next is the Thinking in Workflows case and evidence contract; live calibration remains deferred.


### Checkpoint 69 Supplied process-design case and rubric contract on October 6 2026

**Status:** Authored case/exercise contract verified; learner delivery is not implemented. Accepted count remains 11/162. Related C8-M02-02–04 remain open.

Thinking in Workflows now has a self-contained fictional monthly-review case. Three situations contrast a one-off question, repeated fixed-field intake and a review with multiple stages. The learner chooses and justifies a method, corrects an intentionally flawed proposal and saves an ordered process map plus bounded task brief. The proposed errors include unauthorized source expansion, guessed missing information, automatic institutional approval, release before review and discarded intermediate evidence. No personal example, real report, real execution, recipient contact or staff grading is required.

Private review guidance is bound to the case identity and exactly preserves each declared outcome's passing conditions and critical failures. It permits justified alternative methods rather than awarding correctness for a label, step count or nonempty prose. The public task excludes that guidance. A future exercise must bind the exact case and contain no legacy reflection/star credit or field-answer key. The stated handoff preserves the original approved map or permits a supplied example; actual handoff implementation remains subsequent work.

**Verification:** 67 case/outcome/repair contracts pass, including 29 new process-case tests. Negative cases cover duplicate/missing identities, changed response requirements, execution claims, rubric weakening, staff routing, presence credit, forced personal work and mismatched exercises. Case identity changes with public or private authored requirements. Targeted Ruff, outcome/release checks and diff whitespace pass. No UI change or browser acceptance is claimed for this authoring checkpoint.

**Evidence:** `artifacts/visual-review/certification-process-design-case-2026-10-06/{checkpoint.json,contracts.xml,outcomes-report.json}`. Eleven mechanisms remain implemented, 22 not implemented and all 33 unverified. This checkpoint neither grades learners nor advances the three process-mapping readiness statuses. No registry, legacy source, learner work, credit or staff queue changed.


### Checkpoint 70 Immutable process-design submissions and transition protection on October 6 2026

**Status:** Internal authenticated persistence verified; no learner delivery or grading is enabled. Accepted count remains 11/162.

A saved process submission freezes the public authored case, exact learner answers, explicit save consent and course identity. Revisions create new records with an owned predecessor; replay returns the original record and cannot replace later work. Acknowledging a design does not establish its quality: nonempty wrong answers are preserved without a pass, model dispatch or earned credit. Missing/stale case references, unknown questions, forged actors, reused request identities, unowned revisions and missing write boundaries fail closed. Saved history remains owned and independent of the currently selected course.

The new collection is registered in application startup and existing account-deletion cleanup. Upgrade planning includes only submission identities/module metadata and detects changes during inspection. Internal activation blocks on saved process designs on either course, including an unavailable original record, until an explicit disposition exists. Aggregate inventory reports their presence/ownership without reading answers. This protects work; it does not implement optional migration or transfer competence.

**Verification:** All 52 affected MongoDB submission/upgrade/history regressions pass, including 17 new process cases. Five final integrity cases pass after adding rejection of fabricated credit flags (one additional distinct case). All 106 affected unit/contract tests pass; targeted Ruff, release/outcome checks and diff whitespace pass. Concurrency preserves one receipt; original revisions, foreign ownership, preview races and target-side protection are covered. No HTTP/frontend delivery or visual acceptance is claimed.

**Evidence:** `artifacts/visual-review/certification-process-submissions-2026-10-06/{checkpoint.json,final-persistence.xml,final-integrity.xml,final-contracts.xml,outcomes-report.json}`. New runtime records exist only in disposable test databases, which were dropped by their fixtures. Eleven outcomes remain implemented, 22 not implemented, all 33 unverified; no registry, live learner, credential, publication or staff queue changed. Next is trusted collection and automatic review of the exact saved design.


### Checkpoint 71 Trusted process-design collection and automatic-review persistence on October 6 2026

**Status:** Internal evidence/review path verified with stubbed models; learner delivery remains open. Accepted count remains 11/162.

The collector binds an owned saved process submission to its original packaged case and rubric. It supplies the authored fictional scenario/private guidance separately from the exact learner map, task brief and three authenticated decisions. It neither invents a run nor requires an execution receipt for a design task. A changed case retaining its old hash is rejected. The saved packet carries the original submission identity, digest and collector identity under a distinct process-record channel.

Review replay never recollects newer answers. A technical retry retains the original map/case and works even after the live submission record is unavailable. Supported/contradicted/unclear judgments remain automatic structured-review results with no XP, completion or staff queue. Long answers are preserved verbatim; evidence beyond limits is rejected before preparing a review, without truncation or a learner failure.

**Verification:** All 42 affected MongoDB review/retry regressions pass, including nine new process cases. All 75 automatic-review/process-case/calibration/delivery unit contracts pass. Targeted Ruff, release checks and diff whitespace pass. Tests cover original versus later revisions, deleted originals, replay, technical retry, missing/foreign/unbound evidence, request reuse, full long answers, oversized evidence and negative feedback. Model verdicts are stubs and do not establish grading accuracy.

**Evidence:** `artifacts/visual-review/certification-process-review-2026-10-06/{checkpoint.json,final-persistence.xml,contracts.xml}`. Process results are not yet exposed by learner delivery. Eleven mechanisms remain implemented, 22 not implemented and all 33 unverified. No UI acceptance, live grading, credit, staff task, registry update or migration is claimed.


### Checkpoint 72 Authenticated process-design HTTP delivery and preserved feedback on October 6 2026

**Status:** HTTP save/history/assessment path verified with stubbed models; learner UI remains open. Accepted count remains 11/162.

Explicit enrollment-owned endpoints now list the original case/submissions, save a reviewed process design, retrieve its immutable receipt and request automatic review of that exact submission. Technical retry has explicit consent and one linked child per failed assessment. Shared saved-feedback reads distinguish a process submission from a practical run; no fake run identity is introduced. Client actor/credit/evidence/model assertions and incorrect consent are rejected. Reads never initialize an enrollment or dispatch a model.

Original maps and feedback remain available with delivery disabled or a different course selected. Testing caught a listing dependency on resolving the current selection; listing now reads only selection metadata after verifying the requested owned course, so missing unrelated selection data cannot hide preserved history. Writes still require the selected course and its write boundary.

**Verification:** All 19 affected real-MongoDB HTTP/feedback/assessment cases pass, including two complete process flows covering successful review and technical retry. All 71 affected unit contracts pass; targeted Ruff, release checks and diff whitespace pass. Saving/replaying creates one map; assessing/replaying dispatches one stubbed judge, with one additional call only for explicit technical retry. Foreign access, unauthenticated calls, disabled writes, unknown actors, original history, no XP/credentials and no extraction dispatch are covered. The initial history-list failure remains retained.

**Evidence:** `artifacts/visual-review/certification-process-http-2026-10-06/{checkpoint.json,final-persistence.xml,contracts.xml}`. This is fixed-test authentication through real HTTP handlers, not a production authentication acceptance claim. No frontend or visual acceptance is claimed yet. Process Mapping stays not implemented in the readiness record: 11 implemented, 22 not implemented, 33 unverified. No staff task, publication, migration or live learner change occurred.


### Checkpoint 73 Connected process-design learner delivery on October 6 2026

**Status:** Staged learner delivery verified with fixed test authentication and stubbed grading. Accepted count remains 11/162; related module acceptance and release gates remain open.

Thinking in Workflows exposes the fictional assignment before the three-answer form. Session drafts preserve unfinished answers; a request reference is saved before dispatch. A lost reply can be recovered by reading the original receipt, with explicit same-request completion only after confirmed absence. A saved design records the exact case, answers and course identity. Editing it creates a linked revision; original answers and feedback remain available in read-only course history. Receipt mismatches and unavailable local request storage fail closed. Saving does not grade or award credit; automatic assessment requires its own explicit action and binds the saved submission, without inventing an execution.

**Verification:** 83 component cases, eight HTTP/history persistence regressions and both connected browser matrices pass. Each matrix captures 18 states at 320, 390 and 1440 pixels; the second doubles root text size (not browser zoom). Across the 36 states there are no axe violations, page-width overflow, unexpected routes or page errors. Narrow original-history and enlarged form/history screenshots were visually inspected. The large-text narrow view requires vertical scrolling; this is not full accessibility or screen-reader acceptance. Each isolated database contains two linked designs and one review with one stubbed judge call, despite lost save and assessment replies. History uses GET only, with no additional model call, execution, XP, credential or selection change. Both disposable databases were confirmed dropped.

The initial browser run stopped because the test omitted opening the collapsed Course progress and credential section; the captured DOM identified the omission and corrected navigation passes from a fresh database. An initial build caught an unsupported test-query option; it was removed before the successful production build. These initial receipts remain retained. Targeted lint and whitespace checks pass; final outcome/review contracts and release checks are recorded with the checkpoint evidence.

The three process-mapping mechanisms advance to implemented: 14 implemented, 19 not implemented, none release-verified. This does not establish live grading accuracy, earned credit, an 8/10 score or safe release. Workflow Design handoff remains subsequent work. No existing learner, registry, legacy requirement, staff queue, publication or migration changed.

**Evidence:** `artifacts/visual-review/certification-process-ui-2026-10-06/` contains component/persistence/final-contract receipts, build log, cleanup verification and checkpoint summary; sibling `-final-normal` and `-final-text` directories contain captures and persistence proofs.


### Checkpoint 74 Workflow Design case and preserved-map contract on October 6 2026

**Status:** Authored assignment/rubric contract verified; artifact capture and learner delivery remain open. Accepted count remains 11/162.

The replacement for reflection-presence grading now has an authored case requiring one saved workflow revision and explicit learner decisions. It pins the exact Thinking in Workflows source case, inputs, exclusions and intended internal draft. Learners can choose their owned original saved map or a clearly authored example; choosing a map transfers no competence or credit. The flawed proposal intentionally disconnects source data, discards evidence and sends externally before approval. A corrected design ends at the internal draft and requires neither execution nor a real reviewer. Valid simpler designs remain possible: a suitable prompt does not need a gratuitous extraction step.

Private automatic-review guidance exactly preserves all three outcome rubrics and required evidence kinds. It requires inspection of actual input/output configuration, correction before approval and reviewable intermediate evidence. It distinguishes design intent from tested runtime behavior and never accepts agent prose, a diagram, step count or nonempty reflection as artifact evidence. The authored exercise has no legacy answer-presence or star credit.

**Verification:** 90 case/process/outcome contracts pass, including 36 new design-case cases. Negative cases reject fabricated run/artifact claims, staff routing, implicit approval, missing supplied alternatives, credit transfer, weaker rubrics, prose-only evidence and changed process scope. Changes to supplied maps, proposals or private guidance change the case identity. Targeted Ruff, outcome checks and diff whitespace pass. No learner UI, actual handoff, saved artifact or live grading acceptance is claimed.

**Evidence:** `artifacts/visual-review/certification-workflow-design-case-2026-10-06/{checkpoint.json,contracts.xml,outcomes-report.json}`. The three Workflow Design outcomes remain not implemented: 14 mechanisms implemented, 19 not implemented, none release-verified. Registry, legacy source, existing learner records, staff queues and release status remain unchanged.


### Checkpoint 75 Immutable workflow configuration and original-map capture on October 6 2026

**Status:** Internal configuration capture verified; referenced-resource collection and learner assessment delivery remain open. Accepted count remains 11/162.

An explicit authenticated request now captures one owned saved workflow, its ordered steps/tasks and the learner's chosen original process submission or supplied example. The authored case/exercise is verified against the course package. Original map content and identity are frozen with the configuration; replay survives edits or deletion without collecting newer work. A different request can capture a changed revision. Client artifact assertions, foreign actors/workflows/maps, ambiguous or missing references, changed request choices, racing edits, oversized records and lost write ownership are rejected. Workspace share tokens are omitted. Nonempty or poorly connected designs may be saved but gain no correctness claim, run, model dispatch, XP or completion.

The snapshots use existing immutable input storage and its transition protection. Upgrade previews include only snapshot/module references, not prompts or map content. Design snapshots are explicitly rejected by extraction preparation reads and execution planning/dispatch. The capture scope is recorded as workflow/step/task configuration only: attached documents, referenced extraction sets and external resources are not resolved here, and must not be treated as captured assessment evidence by the future collector. No Workflow Design HTTP/UI or automatic-review path is exposed yet.

**Verification:** 42 MongoDB capture/extraction-input/process-HTTP regressions pass, plus four additional execution-boundary cases. There are 23 new capture cases, covering both map choices, original history after deletion, no credit, identity conflicts, configuration races, integrity failures, size/lease guards, transition protection and dispatch rejection. Case/catalog/release tests pass (68); preparation/execution/case contracts pass (45, with overlapping case coverage). Targeted Ruff, outcome/release checks and diff whitespace pass. An initial test helper passed a keyword-only operation argument positionally; fixed before the successful reruns. The initial interrupted receipt is retained. Its confirmed empty database was identified from the local MongoDB creation log and removed; no QA databases remain.

**Evidence:** `artifacts/visual-review/certification-workflow-design-inputs-2026-10-06/{checkpoint.json,final-regression.xml,final-dispatch-boundary.xml,contracts.xml,final-boundary-contracts.xml,cleanup.json}`. Assessment readiness stays 14 implemented, 19 not implemented, none verified. The legacy manifest remains `54f74731d64f6c92b94252a3ff4e3cb60f5955c6a0029118842132a9cd7e0195`. No existing learner, registry, staff queue, publication or migration changed.


### Checkpoint 76 Owned referenced extraction definitions in saved workflow designs on October 6 2026

**Status:** Referenced extraction configuration capture verified; Workflow Design decisions, grading and UI remain open. Accepted count remains 11/162.

Workflow capture now resolves each Extraction task's template reference to an owned saved definition, preserving fields, optional/category settings, ordering, cross-field rules and base/override configuration alongside the workflow. The same reference used by multiple tasks has one captured definition. A later template edit changes the snapshot identity; replay after template deletion retains the original configuration. The second configuration read detects field changes during capture. Missing/foreign templates or fields, duplicate template identities, empty field definitions, ambiguous field names and malformed references fail before insertion.

This closes a configuration-reference gap; it does not capture source document contents, run a workflow or resolve other integrations. Those remain explicit limits for the future trusted collector. No learner interface or grader may infer execution, correctness or complete source evidence from this snapshot.

**Verification:** 32 workflow capture/reference persistence cases pass. After strengthening ambiguity checks, all 11 final referenced-template cases pass, including two additional duplicate-identity/field cases. Targeted Ruff, outcome/release checks and whitespace validation pass. Tests preserve original settings and category/optional constraints after edit/deletion, reject inaccessible definitions and detect races without saving partial evidence. No provider is invoked.

**Evidence:** `artifacts/visual-review/certification-workflow-design-references-2026-10-06/{checkpoint.json,persistence.xml,final-reference-integrity.xml,outcomes-report.json}`. Workflow Design remains not implemented in readiness: 14 mechanisms implemented, 19 not implemented, none release-verified. No registry, learner migration, staff task, publication or earned credit changed.


### Checkpoint 77 Authenticated approval of the captured workflow revision on October 6 2026

**Status:** Internal saved approval and preservation verified; Workflow Design grading and learner delivery remain open. Accepted count remains 11/162.

The learner explicitly approves a captured workflow revision for assessment and supplies the three required decisions. The request binds the full snapshot digest and case identity. The receipt embeds the original configuration and map; later answers use a new linked receipt. Replay survives deletion of live workflow, map and capture records. Client artifact assertions, missing/foreign revisions, incorrect hashes, wrong actors, reused request identities and ambiguous answers fail closed. Saving approval awards no credit and cannot authorize execution.

The new immutable collection is registered with application startup and account deletion. Source- and target-side activation guards preserve saved approvals independently of their original inputs. Upgrade previews and aggregate inventory use only identities/ownership metadata, not learner answers. Preview fingerprints include these approvals and detect changes during inspection.

**Verification:** 27 MongoDB approval/process-history/upgrade regressions pass, including 18 new approval cases. All 86 case/outcome/inventory contracts pass. Tests cover original evidence after deletion, linked revisions, replay, forged requests, corrupted inner bindings, no credit or execution, write-boundary enforcement and transition blocking after source records disappear. Targeted Ruff and diff whitespace pass. No HTTP/UI or live-grading claim is made.

**Evidence:** `artifacts/visual-review/certification-workflow-approval-2026-10-06/{checkpoint.json,final-regression.xml,contracts.xml}`. Readiness remains 14 implemented, 19 not implemented and none verified. No registry, existing learner, staff queue, publication or migration changed.


### Checkpoint 78 Trusted approved-design collection and automatic review on October 6 2026

**Status:** Internal collector/review path verified with a stubbed judge; learner HTTP/UI delivery remains open. Accepted count remains 11/162.

The Workflow Design collector derives evidence only from the authenticated approval of the exact captured revision. It separates the authored flawed proposal/private rubric, actual artifact configuration, original process-map choice and learner decisions. It creates no execution receipt and treats approval as permission for assessment only. The original case must match exactly. Inline Prompt/Formatter/Extraction configurations and captured owned extraction definitions are supported; unresolved documents, output resources, integrations or unknown task settings stop collection as technical unavailability, not a learner failure. Incorrect supported settings remain visible for rubric review rather than being treated as correct merely because they exist.

Review requests preserve a distinct workflow-design provenance channel and the original evidence packet. Replay does not recollect newer work, and an explicit technical retry survives deletion of the live approval. Per-evidence/packet limits reject oversized material without truncating it or producing a grade.

**Verification:** 16 process/workflow review persistence cases pass, including seven new workflow cases. All 41 review/calibration/dependency contracts pass, including 14 new collector-boundary cases. Tests verify exact configuration/map/answers, ownership, request reuse, missing or unsupported evidence, oversized answers, successful stubbed review and original-packet technical retry. No model runs before successful collection, and no XP, execution or staff task is created. Targeted Ruff passes. These are mechanism checks, not grading-accuracy evidence.

**Evidence:** `artifacts/visual-review/certification-workflow-review-2026-10-06/{checkpoint.json,persistence.xml,contracts.xml}`. Readiness remains 14 implemented, 19 not implemented, none verified; Workflow Design needs complete learner delivery before its mechanism statuses advance.


### Checkpoint 79 Authenticated Workflow Design capture, approval and assessment HTTP flow on October 6 2026

**Status:** HTTP flow verified with a stubbed judge; learner UI and connected visual verification remain open. Accepted count remains 11/162.

Enrollment-owned endpoints now list workflow/map choices, capture the selected configuration, preserve explicit learner approval/decisions, request automatic assessment and retry a technical failure. Capture responses expose a server-computed snapshot digest for the approval binding. Client-supplied artifacts, actors, model choices and evidence are rejected. Feedback explicitly identifies a workflow approval and has no invented run reference. Reads remain available after live workspace records disappear or delivery is disabled, and read-only listings do not consult current workspace choices.

The process and workflow assessment services share the same explicit request/replay/retry lifecycle while retaining separate module, provenance and reference checks. Saving or replaying either capture or approval makes no model call. Replaying an assessment dispatches no second judge; explicit technical retry produces one linked review of the original packet.

**Verification:** Four full real-MongoDB HTTP scenarios pass: two existing process flows and two Workflow Design flows covering normal and technical-retry results. All 44 delivery/review/dependency unit cases pass. Coverage includes owned-only choices, foreign artifact rejection, required consent/enrollment, strict request bodies, capture/approval/review replay, saved-feedback lists, original history after deletion, disabled writes and foreign history access. No workflow execution, XP, staff queue or credential is created. Targeted Ruff passes; production authentication and live grading validity are not claimed.

**Evidence:** `artifacts/visual-review/certification-workflow-http-2026-10-06/{checkpoint.json,persistence.xml,contracts.xml}`. Workflow Design readiness does not advance until its complete learner interface is verified. No existing learner, registry, publication or migration changed.


### Checkpoint 80 Workflow Design learner delivery and connected visual verification on October 6 2026

**Status:** Draft learner mechanism implemented and verified with synthetic authentication and grading; release acceptance remains open. Accepted count remains 11/162.

The panel now supports owned workflow selection, explicit original-map or supplied-example choice, immutable configuration capture, inspection of saved steps/tasks/referenced extraction settings, and authenticated approval of three decisions against the exact snapshot digest. An unresolved newer capture blocks approval of an older revision. Older workflows and maps remain selectable by reference. The case appears in the current course and original read-only history with the same identity. Saving, revising and viewing history do not execute workflows or award credit.

Capture, approval and automatic assessment each preserve their original request across lost replies. Recovery reads the existing receipt; only confirmed absence permits finishing the same request. Revised decisions create a linked approval and preserve the original configuration and answers. Feedback identifies a workflow approval rather than inventing an execution. History omits capture, revision and assessment controls even if a server listing says writable. Existing learners, the registry and live artifacts were not changed.

**Verification:** 59 distinct component cases pass across Workflow Design, shared assessment/feedback and course history. Four connected HTTP/persistence scenarios pass, including process regressions and workflow technical retry. All 93 outcome/case/review/delivery contracts pass. Final TypeScript, targeted ESLint/Ruff, production build, readiness/release checks and diff whitespace pass. Initial component runs retained two host-load timeouts and one obsolete copy assertion; corrected runs pass. The QA bootstrap model-name error and local browser timeouts were fixed in the harness; their evidence is retained. Existing build chunk warnings and test-library/deprecation warnings remain.

Two fresh disposable browser courses exercise 22 states each at 320, 390 and 1440 pixels: normal text with the supplied map, and doubled root-font text with the learner's original map. This is doubled text, not browser zoom. All 44 states have zero axe WCAG A/AA violations, horizontal page/text clipping, undersized visible controls, page errors or unmatched requests. Representative mobile/desktop and doubled-text screenshots were visually inspected. Each course ends with one capture, two linked approvals, one simulated assessment, zero executions/XP/credentials and unchanged enrollment selection. Lost replies cause no duplicate writes or grading; opening original history issues only GET requests and leaves persistence unchanged. Both browser databases and the failed bootstrap database were removed.

**Evidence:** `artifacts/visual-review/certification-workflow-ui-2026-10-06/` contains component reports, `http-regression.xml`, `contracts.xml`, final type/lint/build logs, outcome/release checks, cleanup confirmation, and `normal/` plus `text/` screenshots, accessibility reports, manifests and persistence proofs.

Workflow Design's three mechanisms advance to `implemented`: 17 implemented, 16 not implemented, none release-verified. This does not establish grading accuracy, chat/editor continuity, earned credit or an 8/10 score. Live calibration remains deferred. No staff queue, deployment, publication or learner migration was introduced.


### Checkpoint 81 Multi-Step Workflows source repair on October 6 2026

**Status:** Assigned-source visual repair verified; connected-run assessment remains open. Accepted count remains 11/162.

The original subaward handout had a budget heading stranded on page one and irregular, misaligned table cells on page two. `scripts/build_certification_subaward_draft.py` invokes only the original subaward generator through an embedded-font layout adapter. The separate unpublished draft keeps lists on separate lines, places the budget heading with its fixed five-column table, and preserves every substantive source word and value. It does not replace the legacy source or alter institutional/legal claims in that fictional training document.

Both final pages were rendered with Poppler and visually inspected. Full normalized-text comparison, text bounds, embedded fonts actually used, two-page structure and byte-identical deterministic rebuild pass. The original and packaged legacy subaward remain byte-identical at SHA-256 `a2083e8515fb0004290483248b437cf6ee55627a69b9dcc9f084560a6e7c8110`; the new draft is `ed54f2ebaaf1e1e312a32b67f615e3fce47302f0c3ae9878fe97ed12a0be122c`. An initial overbroad font assertion included an unused default Helvetica resource; checking the fonts used by actual text confirms all rendered text is embedded. Targeted Ruff and diff whitespace pass.

**Evidence:** `artifacts/visual-review/certification-multi-step-case-2026-10-06/` retains original/intermediate/final page renders, extracted text, reproducible `verify-source.py` and `source-verification.json`. The authored connected-run case, runtime, assessment and learner UI remain open. Readiness stays 17 implemented, 16 not implemented, none verified. No current learner, registry, staff task or release changed.


### Checkpoint 82 Authored Multi-Step Workflows connected-run and repair contract on October 6 2026

**Status:** Authored source/case/exercise contracts verified; runtime capture, execution, grading and learner delivery remain open. Accepted count remains 11/162.

`multi-step-case.json` binds the exact repaired subaward and all three outcome rubrics. It describes an intentionally incorrect Formatter connection that bypasses the reasoning result, and unsupported reasoning that conflates distinct reporting obligations with an invented institutional standard. The example is explicitly authored and cannot substitute for execution evidence. Private source anchors and assessment guidance are omitted from the public definition.

The exercise requires actual owned original and corrected runs, saved revisions and explicit approval before each run. The corrected run must connect extraction to reasoning and reasoning to formatting on the assigned source. Learners compare actual intermediate and final results and separate source facts, calculations and interpretation. If a stage fails, completed outputs are preserved; supported recovery targets the incomplete stage or a newly approved corrected revision. The case grants no permission to replay completed writes, perform external actions or request staff review. Extra task types, filled reflections and unrelated historical runs cannot establish competence.

**Verification:** 44 contracts pass, including 31 new connected-case cases and 13 outcome regressions. Negative cases cover fabricated executions, authored examples claimed as runs, missing/duplicate stages or links, unrelated-run aggregation, staff routing, scope expansion, unsafe retry policy, retrospective approval, mismatched decisions, weakened evidence/method/rubrics, stale source bytes/anchors and legacy count-based credit. Targeted Ruff, outcome/release checks and diff whitespace pass. The source rebuild and visual checks remain checkpoint 81 evidence.

**Evidence:** `artifacts/visual-review/certification-multi-step-case-2026-10-06/{contracts.xml,source-verification.json,outcome-readiness.json,release-integrity.txt}`. The case digest is `9c0e2f71ecd88e9d9cae946b916c9e3b02fa8cd90956e5e3e968b3fbcf424dfe`. Multi-Step Workflows remains `not_implemented`; overall readiness stays 17 implemented, 16 not implemented, none verified. The legacy registry, existing learners, publication state and staff workload are unchanged.


### Checkpoint 83 Immutable connected-workflow inputs and source binding on October 6 2026

**Status:** Internal capture verified; connected execution, assessment and learner delivery remain open. Accepted count remains 11/162.

The new capture contract freezes an owned workflow's ordered steps/tasks and referenced extraction definitions together with the assigned subaward's verified bytes identity and ingested text. It checks the authenticated actor, exact packaged case, enrollment lab folder, completed ingestion and source ownership. Double reads reject workspace or source changes during collection. The snapshot excludes the workflow sharing token and private grading anchors/guidance. Replay returns the original record after live source/workflow deletion. Capture grants neither execution authority nor credit.

The catalog now validates the connected case's source and exercise binding and rejects an exercise missing its original case. Existing extraction preparation and dispatch explicitly refuse connected-workflow inputs. Snapshots enter the existing upgrade evidence guard; metadata-only previews preserve their references without exposing source text or task settings. Oversized evidence and missing/revoked write boundaries fail before insertion.

**Verification:** 32 real-MongoDB persistence cases pass (29 new connected-input cases plus three extraction/design capture regressions). All 74 case/catalog/preparation/execution contracts pass, including nine additional strict request/dispatch boundaries. Coverage includes replay, deletion, ownership, malformed/partial ingestion, changing bytes/configuration, request reuse, rehashed inner corruption, no execution/credit, source/exercise/package substitution and transition preservation. Targeted Ruff and diff whitespace pass. Fixtures use disposable databases and synthetic catalog publication only.

**Evidence:** `artifacts/visual-review/certification-connected-inputs-2026-10-06/{persistence.xml,boundaries.xml,contracts.xml}`. Readiness stays 17 implemented, 16 not implemented, none verified. The next runtime adapter must preserve actual effective input choices, models and step results; it cannot silently normalize unsupported settings or combine unrelated runs. No learner migration, production publication or staff task occurred.


### Checkpoint 84 Multi-Step assignment aligned to actual runtime input controls on October 6 2026

**Status:** Runtime behavior characterized with stubbed providers; connected certification execution remains open. Accepted count remains 11/162.

The runtime audit established that input choices are Step Input (the immediately preceding output), Workflow Documents and Selected Document. The authored repair now uses the supported mistake: the Formatter re-reads Workflow Documents instead of consuming the reasoning result through Step Input. It also requires inspection of task-level overrides, which can supersede the step's input selection. This replaces the earlier wording that implied an arbitrary earlier-step connection. Revision 1 case/exercise files are archived with the evidence; the unpublished case is revision 2, digest `6216b0d1a34780620c356f86b3d8111aff25dfa584c31a52b28234b2e7f69e57`. No enrolled course was rewritten.

Four integration-style unit cases execute the real WorkflowEngine with simulated Extraction/Prompt/Formatter providers. They verify source-versus-reasoning context, the corrected input, step-level precedence over stale task settings, and explicit task override behavior. Every run produces real engine stage records while making only the expected three simulated provider calls. These are runtime wiring tests, not actual learner work or calibrated grading. The connected capture fixture now uses real input-source and task-setting keys.

**Verification:** 57 runtime/case/outcome contracts pass (four new runtime cases, 40 case/request boundaries, 13 outcome regressions). Targeted Ruff, readiness and diff whitespace checks pass. Evidence is `artifacts/visual-review/certification-connected-inputs-2026-10-06/runtime-alignment.xml` and archived revision-1 definitions. Readiness remains 17 implemented, 16 not implemented, none verified. Model calibration, bounded execution planning/approval, saved stage receipts, recovery and learner delivery remain open.


### Checkpoint 85 Bounded connected-workflow plan and real-engine parity on October 6 2026

**Status:** Complete for pure planning and simulated runtime parity; persistence, approval and assessed dispatch remain separate gates. Accepted count remains 11/162.

The planner consumes the frozen source/configuration and produces the three internal stages with explicit effective inputs, source identity, model choices, extraction settings, output keys and implementation/runtime digests. It makes no provider call and does not authorize execution or award credit. The incorrect original Formatter connection remains representable so learners can inspect and repair an actual result. Product step/task precedence and the selected assigned document are preserved.

The initial bounded executor supports one Extraction, Prompt and Formatter task in order. External resources/delivery, attachments, linked prompts, optimizer overrides, extra task types and unsupported extraction-template settings stop preparation as technical unavailability; they are not silently discarded or graded as learner failure. Saved extraction fields retain optional/enum metadata, and the plan distinguishes the requested task model from effective extraction pass models.

**Verification:** 59 checks pass: 41 planning boundaries, seven new real-engine adapter cases, four runtime precedence regressions and seven strict request-body cases. Engine cases cover the original/corrected connection, stale task settings, explicit override, selected source, captured template metadata and duplicate step names. The initial adapter assertions expected a list; the real engine unwraps one extracted entity to an object. The corrected assertions pass, and the original report is retained. Targeted Ruff and diff whitespace pass.

**Evidence:** `artifacts/visual-review/certification-connected-inputs-2026-10-06/{planning-initial.xml,planning-final.xml,planning-corrected.xml,plan-request.xml}`. Readiness remains 17 implemented, 16 not implemented, none verified. Live calibration stays deferred; no learner, staff queue, publication or migration changed.


### Checkpoint 86 Saved connected-run plans and explicit scope decisions on October 6 2026

**Status:** Complete for internal persistence and authorization; connected dispatch, learner delivery and grading remain open. Accepted count remains 11/162.

Prepared plans embed original captured inputs and require a separate authenticated scope decision against the exact plan/case digest. The learner may approve or hold. New decisions link to the previous choice; replaying an old approval cannot replace a newer hold. A lost decision-to-run link can be recovered without inserting another decision. Saving a plan or choice makes no provider call and awards no credit. Source/workflow/capture deletion does not erase the plan or approval history.

The existing execution and learner-decision collections preserve these records through course transitions and account lifecycle registration. Upgrade previews expose identities and states only, block activation while evidence needs preservation, and omit answers, source text and task instructions. The extraction dispatcher rejects connected plans; the new preparation service also refuses dispatch until its dedicated stage executor is implemented.

**Verification:** All 26 MongoDB persistence/transition/regression cases pass, including 24 new plan/scope cases and two existing extraction/approval regressions. All 67 planner/request/runtime unit checks pass, including six scope request boundaries and two effective-pass-model cases. Pass-model overrides now omit an unused base model from the list of models that actually execute, while retaining its resolved configuration separately. Targeted Ruff, release/outcome checks and whitespace checks pass. Readiness remains 17 implemented, 16 not implemented, none verified.

Six initial persistence cases passed before the disposable MongoDB stopped responding. That failed report is retained. The isolated service was restarted with a 256 MB cache; the full rerun passed, and the exact abandoned synthetic database was removed. Normal fixtures clean up their own databases. No production database or existing learner was accessed.

**Evidence:** `artifacts/visual-review/certification-connected-inputs-2026-10-06/{plan-persistence.xml,plan-scope-persistence.xml,plan-scope-regression.xml,plan-scope-contracts-final.xml,interrupted-plan-cleanup.json,plan-outcome-readiness.json,plan-release-integrity.txt}`. Live calibration remains deferred; no publication, migration, staff task or earned credit changed.


### Checkpoint 87 Approved stage execution and exact consumed-context receipts on October 6 2026

**Status:** Complete for the internal worker and synchronous checkpoint protocol; durable dispatch and recovery remain open. Accepted count remains 11/162.

The worker validates the claimed run, exact linked learner approval and current implementation/runtime against the saved plan before any provider call. It runs the real engine with synchronous stage-start/result checkpoints. Receipts preserve actual consumed contexts separately from engine display fields, link predecessor results and stage-start digests, retain extraction source sidecars and make no grading claim. Provider failures, explicit engine errors, cancellation and failed/oversized checkpoints stop successors; completed provider work is never automatically replayed.

An opt-in completeness check rejects assessed extractions that skipped the assigned source or returned an invalid entity structure. Ordinary workflow calls retain their existing default. Stage receipts describe the exact one-entity unwrapping and input precedence observed by the engine.

**Verification:** 199 focused worker/planner/extraction/engine regressions pass, including 24 new worker cases. The initial incomplete-extraction fixture lacked numeric token counters; that fixture was corrected. A broader run reached 146 passing cases before an unrelated image-node test needed DNS for `example.com`; the focused run covers all affected extraction and engine behavior without that network dependency. Targeted Ruff and whitespace checks pass. Reports are retained under `artifacts/visual-review/certification-connected-inputs-2026-10-06/`, including `stage-runtime-initial.xml`, `stage-runtime-regression.xml`, `stage-runtime-corrected.xml` and `stage-runtime-focused.xml`.

No learner endpoint invokes this worker yet, and checkpoint sinks in this verification are test-controlled. No live provider, staff task, publication, credit or learner migration occurred. Readiness remains 17 implemented, 16 not implemented, none verified.


### Checkpoint 88 Durable connected-workflow stage evidence on October 6 2026

**Status:** Complete for internal durable stage evidence; dispatch and recovery remain separate gates. Accepted count remains 11/162.

Stage checkpoints now form an append-only, integrity-checked log within the existing owned execution record. Each write checks the active enrollment lease, claimed worker, plan, authorization and previous log digest. Exact replay returns its existing checkpoint; conflicting or out-of-order evidence cannot replace it. Reads verify the full chain, recompute actual consumed contexts from the saved source/predecessor and reject rehashed inner substitutions. Completed runs require all six start/result receipts. No new collection or independent learner-data lifecycle was introduced.

Plan, checkpoint-log and terminal-result budgets reserve space below MongoDB's document limit. Oversized evidence stops the chain without truncation. Transition previews now fingerprint the checkpoint digest/count while exposing only existing summary identities and states.

**Verification:** 23 checkpoint contract cases and 11 real-MongoDB cases pass. Database checks prove the stage-start receipt is durable before each simulated provider runs, replay inserts no duplicate, and wrong workers, revoked leases, altered source evidence, missing predecessors and size violations are rejected. Two new transition-race cases detect changed stage digests/counts, and the original saved-plan replay regression passes. Targeted Ruff and whitespace checks pass.

**Evidence:** `artifacts/visual-review/certification-connected-inputs-2026-10-06/{stage-checkpoint-contracts.xml,stage-checkpoint-persistence.xml}`. No live provider, staff task, publication, earned credit or learner migration occurred. Readiness remains 17 implemented, 16 not implemented, none verified.


### Checkpoint 89 Once-only connected execution and interruption boundaries on October 6 2026

**Status:** Complete for internal approved dispatch and interruption handling; learner HTTP/UI, incomplete-stage recovery and assessment remain open. Accepted count remains 11/162.

The dedicated dispatcher atomically claims the exact prepared plan and latest scope approval, then runs the real engine through durable stage checkpoints. A hold saved between approval inspection and claim prevents dispatch. Terminal results bind the whole checkpoint log and exact final deliverable. Replaying any claimed run only reads its saved status and never repeats a provider. Completed inputs/results remain available after live workspace, capture and decision records disappear because the original plan and authorization are embedded.

Cancellation and timeout preserve an uncertain receipt and stop late successor stages. An interrupted terminal save leaves all durable checkpoints visible with the executing state; it does not fabricate completion or restart providers. Provider exception text is omitted from receipts. Technical failures award no grade, XP or credential.

**Verification:** All 14 real-MongoDB dispatch cases and 120 worker/planner/checkpoint/request contracts pass. Tests cover each failing provider stage, stale actor/plan/approval/runtime, revoked ownership, a concurrent hold, simultaneous duplicate dispatch, timeout, cancellation, late provider completion, deleted inputs, terminal corruption and lost final-save acknowledgement. Targeted Ruff and whitespace checks pass. Evidence is `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-dispatch-initial.xml,connected-dispatch-interruption.xml,connected-dispatch-contracts.xml}`.

These runs use synthetic learners and stubbed providers in disposable databases. No learner endpoint invokes this dispatcher yet. Readiness stays 17 implemented, 16 not implemented, none verified; no staff task, publication or migration occurred.


### Checkpoint 90 Finalize durable connected results without provider replay on October 6 2026

**Status:** Complete for finalizing fully saved, unsealed runs; incomplete-stage retry remains open. Accepted count remains 11/162.

An explicit learner request can seal an executing run only when all six successful stage checkpoints are already durable and match the exact original plan and approval. It invokes no provider, cannot execute incomplete work and does not overwrite an existing failed/uncertain terminal receipt. The recovered receipt records when it was finalized and leaves the unavailable original execution finish time unknown. Concurrent/repeated finalization returns the same saved receipt. Original inputs, authorization and results remain preserved after workspace and standalone input/decision records disappear.

**Verification:** Twelve persistence/regression cases pass, including ten new finalization cases and two checkpoint/dispatch regressions. Five strict request-body cases pass. Coverage includes exact plan/approval/log bindings, ownership, partial evidence, revoked leases, size limits, immutable terminal history, duplicate requests and rehashed inner receipt corruption. Targeted Ruff and whitespace pass. Evidence is `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-finalization.xml,finalization-regression.xml,finalization-request.xml}`. No model replay, staff work, credit, publication or migration occurred.


### Checkpoint 91 Connected-execution checker and actual repair comparison on October 6 2026

**Status:** Complete for internal deterministic checks and comparison binding; automatic quality review and learner delivery remain open. Accepted count remains 11/162.

The pinned deterministic checker verifies one approved execution with the required roles, exact source, durable intermediate/final receipts and actual predecessor connections. A bypassed connection or empty output requires revision. A valid connection does not establish source accuracy, interpretation quality, a correct learner comparison or credit. Changed assessed requirements reject the old checker instead of silently reusing it.

The comparison binds distinct original/corrected runs of the same owned workflow on the same assigned document and ingested text. It reports configuration, actual input and output differences. Reusing one run twice or combining independently valid runs from different learners, workflows, sources or ingestion revisions is rejected. Two real runs with identical configurations are visible as no configuration repair.

**Verification:** 35 checker/outcome contracts pass, including 22 new checker cases. One real-MongoDB scenario runs the actual engine twice with stubbed providers, preserves the original wrong Formatter input and corrected revision, then verifies both after workspace/capture deletion. It confirms the original chain fails the connection check, the corrected chain passes, and no grade or XP is awarded. Targeted Ruff passes. Evidence is `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-checker-initial.xml,connected-checker-final.xml,connected-checker-persistence.xml}`. Readiness remains 17 implemented, 16 not implemented, none verified.


### Checkpoint 92 Draft lesson terminology aligned and visually rechecked on October 6 2026

**Status:** Complete for the three unpublished lesson revisions; release acceptance remains open. Accepted count remains 11/162.

Two Multi-Step lessons and one Workflow Design lesson still called the editor choice “Previous Step Output.” They now use the actual “Step Input” label and explain that it means the immediately preceding output. Their draft lesson revisions advance from 2 to 3. The Multi-Step practice description now names the actual Formatter misconnection from the authored case. No enrolled/published lesson or assessed passing condition changed.

The teaching harness can select specific lessons and returns each selected lesson's real revision when simulating saved position. All 42 normal/doubled-text states pass at 320, 390 and 1440 pixels, including reading, practice and corrected feedback. There are zero axe WCAG A/AA violations, horizontal page overflow, undersized visible controls, page errors or unmatched requests. Representative normal and doubled-text screenshots were inspected. The global small-text diagnostic remains recorded in the manifests; it is not a claim that every text-size metric is zero. Doubled root text is not browser zoom or screen-reader verification.

The in-app browser was unavailable. The default Playwright binary was also absent; the installed Chromium 1223 binary ran the isolated fixture checks without an installation. All 82 affected teaching/case/checker/release-authoring contracts, targeted ESLint, and outcome/release integrity checks pass. Evidence is `artifacts/visual-review/certification-input-labels-2026-10-06/checkpoint.json` and four sibling capture folders; contract evidence is `artifacts/visual-review/certification-connected-inputs-2026-10-06/teaching-alignment-contracts.xml`. No live learner, model, staff queue, release or migration changed.


### Checkpoint 93 Preserve learner comparison decisions with both executions on October 6 2026

**Status:** Complete for internal result-review persistence. Authenticated result-review submissions bind two exact owned completed runs, the original case and both post-run answers. They preserve embedded execution records and actual comparison facts, support linked answer revisions after standalone execution deletion, and reuse the existing learner-decision lifecycle and transition protection. No grading or learner endpoint is exposed by this checkpoint.

**Verification:** Thirteen real-MongoDB cases pass, including twelve review cases and the original/corrected execution regression. Fifteen strict request cases pass. Checks cover deleted workspace and execution records, original replay and linked revisions, unrelated scope-record rejection, foreign actors, revoked leases, oversized evidence, request reuse, and rehashed inner corruption. Upgrade previews preserve decision identities without exposing answers or results. No provider is repeated and no XP is awarded. Evidence: `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-result-reviews.xml,connected-review-requests.xml}`.


### Checkpoint 94 Trusted connected evidence and automatic grading on October 6 2026

**Status:** Complete for trusted collection and internal automatic grading. The collector loads the authenticated saved comparison and both embedded executions, checks the pinned case/exercise/rubric, and preserves actual configurations, consumed stage contexts/results, assigned source, approvals and learner answers. Authored source context is explicitly distinguished from learner work. The deterministic connection result remains separate from the model quality review and cannot be overridden by a model pass. No live calibration or learner endpoint is included in this checkpoint.

**Verification:** Ten database assessment cases and 60 request/checker/automatic-review contracts pass. Coverage includes actual original/corrected receipts, a reversed comparison whose failed connection overrides a stub model pass, replay after deletion, explicit technical retry with unchanged evidence, actor and request isolation, per-item/packet limits and revoked ownership. The first run passed seven cases before a missing test-only import in the size fixture; the corrected bounded-schema fixture and remaining three cases pass. The initial report is retained. Targeted Ruff and whitespace checks pass. Evidence: `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-assessment-initial.xml,connected-assessment-limits.xml,connected-assessment-contracts.xml}`. No live provider, staff queue, XP, publication or migration changed.


### Checkpoint 95 Connected learner HTTP actions and preserved history on October 6 2026

**Status:** Complete for authenticated HTTP delivery. New endpoints expose explicit capture, plan, approve/hold, execution, saved-result finalization, original/corrected review and automatic grading/retry. Reads never execute or grade. Original course definitions, run/source/stage history and assessment feedback use the pinned enrollment. Rollout-disabled history stays readable while writes are disabled. The frontend interface remains a separate verification gate.

**Verification:** Thirteen HTTP/history cases pass: four connected journeys and nine affected saved-review, course-history and Workflow Design regressions. They cover actual engine runs with stubbed providers, normal grading and technical retry, stale approval after a hold, saved-stage finalization, once-only replay with unavailable settings, deleted workspace and standalone execution records, closed enrollment, foreign access, explicit enrollment and rejected client evidence/model/actor fields. The original scope record remains independently readable after a newer hold. Responses omit provider secrets, private authored guidance and internal engine plans. The initial HTTP report retains a missing test-only import failure reached after normal feedback passed; the corrected full journeys pass. Targeted Ruff, whitespace and outcome/release integrity checks pass. Evidence: `artifacts/visual-review/certification-connected-inputs-2026-10-06/{connected-http-initial.xml,connected-http-regression.xml,connected-http-scope-history.xml}`. No live provider, staff queue, earned credit, publication or migration changed.


### Checkpoint 96 Connected workflow learner interface on October 6 2026

**Status:** Complete for the connected-workflow interface and isolated learner journey. Multi-Step's three assessment mechanisms advance to implemented, bringing the draft to 20 implemented, 13 not implemented and none release-verified. Accepted checklist count remains 11/162. The failed-stage assessment exercise remains separate open work.

The chat panel and original-course history select a dedicated interface for capture, preparation, approve/hold, execution, finalization, original/corrected comparison and automatic assessment. It displays actual source and stage evidence, freezes pending request bodies across remounts, moves focus to opened evidence, supports linked answer revisions and preserves original read-only history. Malformed request storage blocks new submissions while saved server history remains readable. Lost replies recover through inspection without duplicate provider or judge calls. Incomplete runs preserve completed outputs without offering finalization, replay or completed-run selection.

**Visual repair:** Mobile inspection found escaped newlines in the JSON presentation of actual stage inputs/results. Text now renders directly; complete metadata and source details remain in nested disclosures. The earlier 29 normal-text states are retained as pre-repair evidence. Twelve read-only states verify repaired extraction/Formatter inputs and final results at 320, 390 and 1440 pixels with unchanged persistence/provider counts. A fresh doubled-text full journey adds 29 states on the repaired build. All 70 captures have zero axe A/AA violations, page overflow, undersized visible controls, page errors or unmatched requests; nested text overflow assertions also pass. Representative normal mobile evidence, desktop output, enlarged mobile approval/feedback and enlarged original history were inspected. The 320px doubled-text view remains dense with a tall stacked header; no full accessibility or 8/10 claim is made.

**Verification:** The 74-case affected frontend regression passed. Subsequent focused runs pass all 19 current connected-interface cases (16 interface/recovery cases plus three incomplete-prefix cases). Historical host-load timeouts and an ambiguous test-only metadata selector are retained with their passing rechecks. Targeted ESLint passes. The full TypeScript/production build passes; slow host execution also prompted a separate Vite bundle on loopback port 5294 so browser checks could proceed without the later build changing served files. Both full journeys persist exactly two runs, two captures, two scope choices, two linked comparisons and one automatic review, with two calls to each stage provider, one judge call and no credit. Read-only original history preserves the first answers. Both disposable databases were removed on normal shutdown.

The 60 affected outcome/case/release-authoring contracts initially reached 59 passes and one stale expectation that Multi-Step was not implemented. That test now checks implemented status without release verification; its focused case recheck passes. Outcome/release integrity and targeted Ruff pass. The legacy release remains draft, rollout stays disabled, and no current learner was migrated or had requirements changed.

**Evidence:** `artifacts/visual-review/certification-multi-step-ui-2026-10-06/checkpoint.json` records all three capture matrices, source/browser metadata, persistence proofs and manual inspection paths. Test/build evidence is in `artifacts/visual-review/certification-connected-inputs-2026-10-06/`, including `connected-ui-readable-evidence-recheck.xml`, `connected-ui-incomplete-prefix.xml`, `connected-readable-production-build.log`, `connected-readable-dist-sha256.json`, `connected-readiness-contracts.xml`, `connected-readiness-case-recheck.xml` and `connected-outcome-readiness.json`.

**Limits:** The actual workflow engine and real isolated HTTP/MongoDB were used with stubbed providers and a fixed synthetic learner. Live-model calibration remains deferred. Doubled root text is not browser zoom, screen-reader or learner-observation evidence. No staff queue, earned credit, publication, deployment or migration changed.


### Checkpoint 97 Controlled stopped-run recovery practice on October 6 2026

**Status:** Complete for the unpublished teaching exercise. Assessment of a learner's own failed-run recovery remains open; C8-M05-02 and the broader recovery acceptance items remain unchecked. Counts remain 11/162 accepted and 20/33 mechanisms implemented, none release-verified.

The stable `multi_step.glossary-review` lesson advances from revision 3 to 4. It retains the evidence vocabulary and adds an explicitly authored stopped-run example: Extraction completed, Reasoning failed, Formatter not started. Learners identify the first incomplete stage, preserve the successful output and original run, inspect the failed input/result and choose the currently supported separate capture/plan/approval route. The lesson explicitly limits repeated computation to this internal exercise without external actions. It distinguishes lost replies and unknown outcomes from a saved failure, explains GET-only request checking and saved-result finalization, and rejects assuming cancellation rolls back work. No in-place stage resume or staff review is promised.

**Verification:** All 20 outcome/release-authoring contracts pass. Fourteen browser states pass at 320, 390 and 1440 pixels with normal and doubled root text, including reading, practice and corrected feedback. Zero axe violations, page overflow, undersized visible controls, page errors or unmatched requests; no lab or credit writes occurred. Normal mobile feedback and doubled-text narrow practice were visually inspected. The narrow doubled-text layout remains dense, and this is not browser-zoom, screen-reader or observed-learner verification. Existing enrolled content, case requirements and earned work are unchanged.

**Evidence:** `artifacts/visual-review/certification-stopped-run-teaching-2026-10-06/checkpoint.json`, the two capture folders, `contracts.xml` and the archived original revision-3 lesson. No live model, release, deployment or migration changed.


### Checkpoint 98 Readable unpublished budget source on October 6 2026

**Status:** Complete for source presentation. The original budget used nonembedded fonts and irregular table boundaries. Poppler rendered no visible text in this environment; MuPDF showed the text and misaligned columns. The new draft embeds two fonts, aligns personnel/summary columns and deliberately keeps the original inconsistent amounts and policy statements. The original document and course package are unchanged.

The isolated builder invokes only the existing budget content generator and writes only `drafts/v5.0/documents/budget-justification.pdf`. Both rendered pages were inspected. Normalized substantive text is identical to the original; only layout and the synthetic-draft footer/page labels differ. Rebuilding produces identical bytes. Targeted Ruff and whitespace checks pass. Original SHA-256: `0599cd3b4d286300f5e3f3bb16c1a2b204e5ce4e3f8f756d5830142027218ea0`. Draft SHA-256: `5ce1ba24c588532002129a30a011041dec4e82382f498140950bf21560116240`.

**Evidence:** `artifacts/visual-review/certification-advanced-case-2026-10-06/source-checkpoint.json`, original Poppler/MuPDF renders and both `budget-draft-*.png` pages. No current learner's source changed.


### Checkpoint 99 Authored Advanced Nodes case and package boundaries on October 6 2026

**Status:** Complete for the authored case, strict definition validation and package binding. Learner calculation capture, actual owned execution collection, automatic assessment and UI delivery remain open. Advanced Nodes' three outcomes stay not implemented. Overall counts remain 11/162 accepted, 20 implemented, 13 not implemented and none release-verified.

The new assignment separates permitted interpretation methods from recorded deterministic or explicit learner arithmetic, allowing a supported route without enabling the restricted Code Node or requesting staff help. It requires exact source inputs, USD, operations, results and limits for Equipment, the seven listed direct categories and the full printed summary. Private checked sums are 45,000; 517,424; and 542,800 respectively. The matching summary addition does not resolve the narrative's direct-cost basis, indirect-rate inconsistency or period assumptions. Learners must preserve those limits in an internal exception memo.

The authored flawed proposal is explicitly not execution evidence. The case requires a saved owned revision, actual task inputs/results and dependency review: independent source-reading drafts may overlap, while synthesis waits for its required calculation and branch results. A justified sequential alternative is allowed. External actions, real budget approval, staff queues, node counts, unrelated histories and model arithmetic assurance cannot substitute for evidence.

Private amounts, calculation expectations, source issues and review guidance are excluded from the public definition. Validation binds the exact rubric/evidence kinds, source hash and page anchors, named operands, fixed-point finite amounts and exact decimal addition. It rejects duplicate or omitted operands and internally coherent arithmetic on altered source amounts. The catalog verifies optional Advanced Nodes case assets and rejects an exercise whose original case is absent.

**Verification:** 56 initial case/outcome/release-authoring contracts pass; the expanded 41-case Advanced Nodes suite also passes, including five full temporary catalog-package cases. These cover source substitution, missing/unknown case assets, changed exercise binding, weakened rubrics, fabricated execution fields, nonfinite/exponent/oversized values and unsafe scope/method policies. Outcome/release integrity, targeted Ruff and whitespace checks pass. No course was published or selected, and no provider or learner database was used.

**Evidence:** `artifacts/visual-review/certification-advanced-case-2026-10-06/{contracts.xml,package-contracts.xml,readiness.json}`. Authored case digest: `15c1f444f2e94f348f6a0c187762047bef655c2efdbd70cd623fc0a883ff0977`.


### Checkpoint 100 Exact source-bound arithmetic checker on October 6 2026

**Status:** Complete for the pure calculation checker and submission contract. Persistence, authenticated ownership, workflow evidence collection and learner delivery remain open. Readiness counts do not advance.

The checker accepts three explicit named addition records, with USD inputs, source pages/quotes, learner-reported method, recorded result and interpretation. It reads the exact SHA-bound assigned PDF itself, verifies source anchors, preserves the learner's values and recomputes with decimal arithmetic. Correct arithmetic on wrong source values requires revision rather than substituting the answer key. Unsupported quotes/pages also require revision. An explicitly unresolved input or missing result stays unresolved even when a proposed total matches. No expression evaluation, arbitrary code, model call or staff action is involved.

The returned facts distinguish source agreement, arithmetic agreement and learner-reported method. They explicitly require interpretation review and cannot establish period compatibility, institutional policy, actual workflow execution or credit. This function is not an authenticated or durable receipt; the trusted collector must bind it to owned work before assessment.

**Verification:** All 26 focused cases pass: both permitted methods, preserved incorrect values, correct sums on wrong inputs, wrong result, invented/different source quotes, wrong/missing page, unresolved inputs, absent results, duplicate/missing checks, altered PDF, malformed amounts, duplicate/reordered operands, arbitrary operations, wrong units, blank explanations and attempted client grade injection. Targeted Ruff and whitespace checks pass. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/calculation-contracts.xml`. No learner record, credit, provider, release or migration changed.


### Checkpoint 101 Authenticated source-bound calculation persistence on October 6 2026

**Status:** Complete for internal immutable calculation storage. Owned workflow capture/execution, learner delivery and grading remain open. Counts remain 11/162 accepted, 20 mechanisms implemented, 13 not implemented and none release-verified.

Authenticated submissions bind the exact assigned owned budget, pinned case and course, explicit consent and all three calculation records. Saved evidence retains the original PDF, separately identified ingestion text, learner inputs and versioned deterministic checks. Repeated requests return the original record; corrections create linked records without replacing incorrect answers. Linked corrections survive deletion of the live document. No arithmetic result grants execution authority or assessed credit. Calculation records cannot enter extraction preparation or dispatch.

**Verification:** All 19 initial persistence cases pass after restoring the disposable MongoDB runtime. The first attempt had 19 setup errors because that isolated service was unavailable; no implementation test ran in that attempt, and its report remains preserved. A further 35-case affected persistence regression passes, including four unrelated-parent/source/enrollment rejection cases and extraction preparation/execution checks. All 80 focused calculation, case and preparation contracts pass, including eleven request authority/consent boundaries. Targeted Ruff passes. Test databases are disposable and fixture-cleaned; no application database or current learner was used.

**Evidence:** `artifacts/visual-review/certification-advanced-case-2026-10-06/{calculation-persistence.xml,calculation-persistence-recheck.xml,calculation-persistence-regression.xml,calculation-contracts-recheck.xml}`. No live model, staff queue, release, deployment or migration changed.


### Checkpoint 102 Owned budget workflow and method capture on October 6 2026

**Status:** Complete for internal immutable capture. Planning, approved execution, review and learner delivery remain open; readiness counts do not advance.

The authenticated capture binds an owned saved workflow revision, the learner's pre-execution method explanation and the exact selected calculation snapshot. It embeds the original calculations/PDF so deletion of workspace objects or the standalone calculation cannot erase the evidence. Incorrect arithmetic remains incorrect evidence and can be captured for review. Capture omits workflow share tokens, never authorizes execution and never awards credit. A reused request cannot replace the original method answer.

**Verification:** All 19 disposable-MongoDB cases pass. Coverage includes deletion and exact replay, foreign ownership, changed source binding, workflow mutation during capture, client-fabricated evidence, blank decisions, changed consent, nested corruption with recomputed hashes, revoked writes, storage limits and rejection by extraction execution. Targeted Ruff passes. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/workflow-capture.xml`. No live learner, model, staff task, release or migration changed.


### Checkpoint 103 Budget planning and explicit scope decisions on October 6 2026

**Status:** Complete for internal planning, saved plans and approve/hold decisions. Durable task dispatch and learner delivery remain open; readiness counts do not advance.

The bounded executor supports one source-review prompt, or two independent prompts together, followed by one internal memo. This is a supported execution shape, not a task-count grading criterion. Plans preserve actual input precedence, task models, saved instructions and ordered references. Provider contexts identify original budget text and learner calculation evidence separately, exclude the private answer key, and retain incorrect arithmetic. The memo must explicitly receive previous results and saved source/calculations. Unavailable models, external delivery/resources, restricted code, optimizer overrides and unsupported settings stop preparation before execution.

Saved plans preserve the complete capture. A separate authenticated decision approves or holds the exact plan; replaying an older approval never replaces a newer hold. The existing connected scope protocol now has explicit module/request/preparation parameters; Advanced Nodes uses its own consent and scope question. Captures and sources may be deleted without erasing saved plans or decisions. Preparation still refuses dispatch until the dedicated task-receipt executor is available.

**Verification:** All 19 planner/actual-engine cases pass, including concurrent sibling reviews, a supported single-review alternative, memo consumption of both results and calculations, and failure before memo execution. The first run reached nine passes and a test-only incorrect assumption: the product intentionally maps first-step `step_input` to workflow documents, not sibling output. The corrected test preserves and verifies that behavior. All 39 plan/scope persistence and affected connected-workflow regressions pass. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/{workflow-plan.xml,workflow-plan-recheck.xml,workflow-plan-scope.xml}`. Providers were stubbed; no live learner, release, credit, staff queue or migration changed.


### Checkpoint 104 Actual per-task budget runtime evidence on October 6 2026

**Status:** Complete for the internal worker and synchronous checkpoint contract. Durable claim/log integration is being verified separately; no learner dispatch endpoint is exposed.

The worker validates the exact plan and linked approval, then uses the actual workflow engine with preserved settings. Each task records its actual consumed context, predecessor input and result separately. Parallel completions are retained independently; the memo waits until the engine joins every required review. Empty results, provider failures, receipt failures and cancellation stop dependent work. Provider exception text is excluded from failure receipts. Completed arithmetic remains separate from interpretation and does not award credit.

**Verification:** All ten real-engine/stub-provider cases pass, covering exact consumed contexts, complete branch inputs to the memo, missing results, provider exceptions, checkpoint failure, changed authorization/runtime and cancellation. The first run found a cancellation race where both sibling starts could be recorded after one triggered stop; the worker now checks cancellation again while holding the event-log lock before acknowledging another start. The passing rerun confirms no provider calls after that cancellation point. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/{workflow-runtime.xml,workflow-runtime-recheck.xml}`. The test claim envelope is synthetic; durable dispatch is not claimed by this checkpoint. No live learner, model, grade, staff queue, release or migration changed.


### Checkpoint 105 Durable budget task dispatch and saved-result recovery on October 6 2026

**Status:** Complete for internal authenticated dispatch, task-log persistence and explicit saved-result finalization. Result review, automatic assessment and learner delivery remain open; readiness counts do not advance.

An atomic claim binds the latest exact learner approval. Every task start/result is synchronously persisted with source/calculation context and chained log identity; the final memo cannot start until all required review results are durable. Saved results remain owner-only and survive source/capture deletion. Repeated requests inspect the original run without calling providers again. Failed or empty sibling results stop synthesis, preserve completed work and cannot become a learner grade. Pending task writes are fenced before terminal status is saved. Provider failures retain their type, not potentially sensitive exception text.

Explicit finalization can seal a still-executing run only when every required result is already saved. It invokes no providers, records the actual finalization time separately from the unknown execution finish time, and cannot replace failed/uncertain terminal receipts or invent missing results.

**Verification:** The initial durable-dispatch run passed ten cases and exposed a real cancellation race between an already queued sibling checkpoint and terminal receipt. Adding an atomic checkpoint-close fence fixes that race; all eleven dispatch cases pass. The full 62-case affected regression passes across planning, scope, runtime, dispatch and seven finalization cases, including forged contexts, missing branches, fabricated output, lost terminal writes and no-repeat recovery. Ruff and whitespace checks pass. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/{workflow-dispatch.xml,workflow-dispatch-recheck.xml,workflow-execution-recovery-regression.xml}`. All model responses are stubs and all databases disposable. No live learner, credit, staff queue, release or migration changed.


### Checkpoint 106 Budget result review and checked automatic assessment on October 6 2026

**Status:** Complete for internal authenticated result review and automatic grading. Learner interface verification and release calibration remain open; readiness counts do not advance.

Learners save calculation/dependency explanations against an exact completed owned run. The review embeds original source/calculation/workflow/task evidence and the earlier method decision; linked answer revisions survive standalone run deletion without replacing original work. The trusted collector supplies actual source text, configurations, consumed inputs, results and authenticated decisions. Private authored answer keys are excluded from the review packet.

An explicit supporting arithmetic check cannot be overridden by a model pass. Original model decisions remain preserved separately; incorrect or unresolved additions make both the final computation outcome and overall result require revision. The check never upgrades model uncertainty. Provider/schema failures remain technical unavailability and can be retried against identical evidence without repeating workflow execution or creating a staff queue.

**Verification:** All 12 budget review/assessment integration cases, 32 affected existing-review persistence cases and 80 review/calculation/outcome contracts pass. These cover a corrected linked calculation, wrong arithmetic despite a stub model pass, consistent public feedback, original replay after record deletion and exact technical retry. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/{workflow-assessment.xml,assessment-persistence-regression.xml,assessment-contract-regression.xml}`. No live calibration or earned credit is claimed.


### Checkpoint 107 Authenticated budget HTTP actions and original-course history on October 6 2026

**Status:** Complete for backend learner delivery. Frontend implementation and visual verification remain open; readiness counts do not advance.

Explicit endpoints support saved calculations, workflow/method capture, planning, approve/hold, once-only execution, saved-result finalization, result review, automatic assessment and technical retry. Reads never execute or grade. Calculation and workflow lists remain distinct in the shared immutable collection. Responses omit private authored keys, PDF encodings and internal executable plans while exposing the actual learner evidence. Course definitions and history use the pinned original case; disabled rollout keeps saved work readable and blocks writes.

**Verification:** Three full HTTP/security journeys pass, including the normal and technical-retry grading routes. A 24-case affected HTTP/review/course-history regression also passes, including existing connected workflows. Coverage verifies explicit enrollment, rejected client model/actor/grade fields, private-data omission, deleted live sources, replay without runtime settings, foreign-user denial and unchanged credit. Evidence: `artifacts/visual-review/certification-advanced-case-2026-10-06/{workflow-http.xml,workflow-http-regression.xml}`. Model responses were stubbed and databases disposable. No release, migration or staff task changed.


### Checkpoint 108 Advanced Nodes learner delivery and visual QA on October 7 2026

**Status:** Complete for the staged learner mechanism. Advanced Nodes' three outcomes advance to `implemented`, giving 23 implemented and ten unimplemented mechanisms; none is release-verified. Accepted checklist count remains 11/162.

The learner records source-bound USD additions, preserves a linked correction, captures an owned workflow and method decision, approves the exact internal run, inspects actual per-task inputs/results and submits calculation/dependency answers for automatic review. Failed or uncertain executions cannot become completed reviews. Pending request bodies survive remount; checking uses reads, and explicit finishing retains the original identity. Missing session storage prevents a send. Automatic grading cannot override incorrect arithmetic, and technical grading retry preserves the original evidence. Course history is read-only. Selecting calculations and revising work move focus to the corresponding form.

**Verification:** 85 affected frontend tests and 86 outcome/catalog/release-authoring contracts pass; targeted lint, release integrity, TypeScript and production build pass. A first 43-state normal browser journey, a final 43-state doubled-text journey and nine final normal-text focus checks cover 320, 390 and 1440px. Every capture has zero axe violations, page/nested overflow or undersized visible controls. Representative entry, scope, feedback, enlarged-text and focus screenshots were inspected. Each full journey preserves two calculation versions, two captures, two approved runs, two reviews and two assessments with exactly six stub task calls and two stub judge calls. Lost calculation/execution/review/grading replies recover without repeat writes. Original answers remain readable after correction, with no additional history writes. Both disposable databases were dropped at shutdown. An initial frontend recovery test had incorrect error-constructor arguments and clicked an earlier transient pending button; the corrected regression passes.

**Evidence:** `artifacts/visual-review/certification-budget-ui-2026-10-06/checkpoint.json` records all 95 states, source/build hashes, browser and persistence proofs. Test/build reports are in `artifacts/visual-review/certification-advanced-case-2026-10-06/`, including `budget-ui-final.xml`, `budget-readiness-contracts.xml`, `budget-readiness.json` and `budget-final-production-build.log`. The browser used installed Chrome after in-app browser discovery failed. Doubled text does not claim actual 200% browser zoom, screen-reader use or observed learner success. Live calibration, earned credit and publication remain open. No staff queue or real learner migration was added.

### Checkpoint 109 Readable progress-report source for Output and Delivery on October 7 2026

**Status:** Complete for a separate unpublished source repair. Output and Delivery assessment remains unimplemented.

The original source renders with blank text in Poppler and a misaligned budget table in MuPDF. `scripts/build_certification_progress_draft.py` reuses the original generator's substantive strings, embeds Vera fonts and supplies four fixed table columns. The new two-page source preserves every title, date, amount, publication status and milestone. Whitespace-normalized substantive text matches exactly. Both draft pages were rendered in Poppler and visually inspected; the original and legacy source hashes remain unchanged.

**Evidence:** `artifacts/visual-review/certification-output-case-2026-10-07/source-checkpoint.json`, original Poppler/MuPDF renders and `progress-draft-1.png` / `progress-draft-2.png`. Original source SHA-256: `08fbc619b12653288f435c0f7dd42e9427609961affa830445b7709c100632fa`; draft: `281bc78b3330ac0dc285677689448122f4147e063b5c6a68e35c1d94664999df`. No publication, assigned learner document or enrollment changed.


### Checkpoint 110 Authored artifact-inspection and private-handoff case on October 7 2026

**Status:** Complete for assignment authoring/contracts only. Output and Delivery's three mechanisms remain unimplemented.

The case binds the repaired progress report, a readable PDF and actual CSV with eleven required fields, inspection of every real bundle member, an explicit exact-file release decision and a contained learner-only training inbox. The first approved training write deliberately fails before destination mutation; the task calls for an explicit retry of only that failed handoff. This is labeled a delivery rehearsal, never a sponsor outage or external send. Private review guidance preserves all three existing outcome criteria. Source anchors distinguish Year 2/cumulative expenditure, reporting versus submission dates, nine students and publication statuses. No Package Builder, external credential, staff queue or configuration-count credit is required.

**Verification:** All 116 case/outcome/catalog/Advanced Nodes regression cases pass. The initial report contains one test-only attempt to mutate a frozen outcome model; reconstructing the altered test contract fixes it. Unknown/missing cases, changed source/exercise hashes, weakened evidence, omitted period fields, unsafe destination/audience changes and authority shortcuts are rejected. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/{case-contracts.xml,case-contracts-recheck.xml,readiness.json}`. Case SHA-256: `7c3f30a132367f7b86765163947698dc1f9b60c1daa7cb3e94e411a164ad3583`. No generated learner artifact, delivery or grade is claimed.

### Checkpoint 111 Actual generated-file inspection and portable report text on October 7 2026

**Status:** Complete for the internal file/bundle preservation kernel. Durable learner execution and delivery remain open.

The kernel consumes trusted completed output-node results, preserves exact PDF/CSV bytes and the actual product download ZIP, and verifies file/member hashes without regenerating the original timestamped bundle. Empty/malformed files, missing fields, inconsistent CSV rows and prose-to-text fallbacks remain repair evidence. Invalid encoding, unsafe/duplicate filenames and size-limit violations stop before download packaging. Parseability never means source correctness, visual approval, confirmed delivery or credit.

Visual inspection of the real Document Renderer output exposed another font-substitution failure: Poppler showed only the table grid although MuPDF extracted the text. Workflow report title/body/table/emphasis and list fonts now embed ReportLab's bundled Vera family with thread-safe registration. The same generated artifact was re-rendered and inspected successfully. This change is scoped to workflow report text styles; the separate AcroForm/extraction renderers and Courier code styles are unchanged.

**Verification:** All 35 artifact cases and the final 66-case PDF/artifact/legacy-delivery regression pass. A subsequent 21-case PDF run includes embedded list markers. The font test initially needed corrections for MuPDF's shortened font names and exact-versus-prefix matching; both failed reports are retained. Ruff and whitespace checks pass. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/`, including `artifact-contracts-recheck.xml`, `embedded-report-fonts-final.xml`, `embedded-report-fonts-lists.xml`, and original/fixed generated fixture PDFs, CSVs, ZIPs and renderings. These files use synthetic supplied records; no model, owned assessed run, learner decision or delivery receipt is claimed.

### Checkpoint 112 Immutable output workflow and assigned-source capture on October 7 2026

**Status:** Complete for internal capture; it grants no execution or release authority.

Authenticated capture preserves the exact owned workflow/steps/tasks, assigned PDF bytes and original ingested text, public/private case identity and course/rubric binding. Ingestion must be complete and the document must belong to this learner's assigned lab. Configuration/source races are rejected before save. Repeating the request returns its original record after source or workflow deletion. Public case data excludes review keys; execution and credit remain false, and extraction dispatch rejects the distinct snapshot kind.

**Verification:** All 20 disposable-MongoDB cases pass, including foreign actor/workflow/source, wrong folder or bytes, unfinished ingestion, missing assignment, racing edits, client evidence injection, rehashed nested corruption and reused request IDs. No provider or execution is called. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/workflow-capture.xml`. No release, migration, staff task or readiness count changed.


### Checkpoint 113 Exact output plan and saved generation scope on October 7 2026

**Status:** Complete for internal planning and explicit approve/hold decisions. No release authority or readiness credit.

The bounded plan resolves four real sequential stages: source-grounded report preparation, PDF rendering, independent source-grounded summary preparation and CSV export. Both preparation stages receive the original assigned report; file stages receive their preceding result. Actual step/task override precedence, effective settings, selected output steps, configured models and runtime/implementation hashes are preserved. Unsupported attachments, external effects, unsafe filenames and unresolved models stop preparation. Scope approval authorizes only this saved internal generation; a newer hold cannot be replaced by replaying an older approval. Plans and decisions remain readable after workspace deletion.

**Verification:** All 40 disposable-MongoDB planning/preparation tests pass. Two actual engine variants verify consumed contexts and generated PDF/CSV/ZIP bytes using stub providers; prose fallback remains invalid CSV evidence. An initial test incorrectly expected a stale task selection to override its step input; the corrected explicit-override case is rejected, while the separate precedence test confirms step settings win when overrides are disabled. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/{workflow-plan.xml,workflow-plan-scope.xml}`. Execution receipts, file release and delivery remain subsequent work.


### Checkpoint 114 Durable output generation and saved-file finalization on October 7 2026

**Status:** Complete for the internal approved generation service and explicit complete-result recovery. Learner file inspection, private delivery and grading remain open.

An authenticated claim runs the approved four-stage workflow once. Each source/file input and stage result receives durable acknowledgement before a successor starts. Actual PDF/CSV bytes and the product ZIP bind the terminal receipt; readback validates both file integrity and correspondence with the original output stages. Prose fallback remains completed generation with invalid CSV evidence, never a passing artifact. Failure/cancellation preserves the actual prefix, suppresses provider exception details and fences late checkpoint writes. Repeated dispatch reads the original run. Explicit finalization requires all eight successful stage events and packages the already-saved file bytes without providers; it cannot overwrite an existing failed/uncertain terminal receipt. A recovered ZIP is first packaged from original file bytes when the terminal bundle was not saved; it does not claim recovery of an unseen prior ZIP byte sequence.

**Verification:** All 97 execution/recovery/planning/preparation/artifact cases pass, with real workflow nodes and disposable MongoDB plus stub providers. Coverage includes dropped terminal writes, cancellation, newer holds, changed runtime/actor/plan, invalid files, stage-log tampering, changed file bytes/authority, missing recovery results and original readback after deletion. The initial 52-case run had one test-only expectation of a completion receipt after a throwing provider; correcting it to the actual saved start prefix yields the passing regression. Ruff passes. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/{workflow-execution.xml,workflow-execution-recovery.xml}`. No delivery, credit, release verification, existing learner change or staff burden is claimed.


### Checkpoint 115 Exact-file inspection and private-release choice on October 7 2026

**Status:** Complete for internal saved learner inspection and approve/hold choices. No handoff or passing assessment is implied.

The authenticated learner reviews every exact file digest and the actual bundle, records usable/repair/unresolved judgments and answers the artifact/release questions. Approval requires acknowledged opening of each file/bundle and passing server format checks; this never proves source correctness or supplies a grade. The destination, learner-only audience and approved-file scope are fixed to the authored case. Invalid CSV can be held but cannot be approved. An immutable record embeds the complete original generation and links the latest release choice; replay cannot replace a newer hold. Interrupted linking finishes the original record, and historical inspection survives run/source deletion. Claimed handoffs fence new release choices.

**Verification:** All 23 disposable-MongoDB inspection cases pass, including changed file/result/case/bundle identity, unopened or unusable files, broader audience/destination, missing/duplicated members, foreign actor, request reuse, linked holds, saved-link recovery and rehashed nested corruption. No additional provider call, handoff or XP is produced. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/file-inspection-release.xml`. Ruff passes. Output and Delivery mechanisms remain unimplemented pending handoff/recovery, automatic assessment and learner UI.


### Checkpoint 116 Contained private handoff, targeted retry and atomic copy receipt on October 7 2026

**Status:** Complete for internal learner-only delivery rehearsal. No external delivery or course readiness is claimed.

The first exact approved request saves the authored controlled failure before any destination copy. Explicit retry requires that actual failed receipt, unchanged generated files and the currently linked approval. Its destination bytes and confirming receipt commit together in one private immutable record. Claim identities prevent starting the same action under another request; a lost insert/reply can finish or read only the original request. No generation stage or provider repeats. A failure permits the learner to hold/reapprove the same files before retry; historical replay cannot unlock a pending or completed retry. Completed delivery freezes that release choice. Original copy and failure evidence survive source/run/review deletion.

**Verification:** All 47 private-handoff and inspection cases pass against disposable MongoDB. Tests cover exact copied PDF/CSV/ZIP bytes, intended first rejection, explicit retry, stale holds, reapproval, wrong files/actors/receipts, duplicate actions, before/after-insert ambiguity, lost completion linking, read-only recovery and rehashed copy/destination/authority corruption. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/private-handoff.xml`. Ruff passes. The copy is a contained training destination, never email, sponsor submission or staff work. Automatic assessment and learner UI remain open; readiness stays 23/33 implemented and 0 release-verified.


### Checkpoint 117 Preserved output interpretation and automatic evidence review on October 7 2026

**Status:** Complete for internal outcome submission, evidence collection and automatic grading. HTTP/UI delivery and live calibration remain open.

A saved interpretation binds the exact file inspection and corresponding actual handoff receipt, preserving its original authorization and private-copy identity. Linked answer revisions remain possible after underlying records disappear. The assessment packet contains original source text, complete extracted file content in bounded chunks, actual bundle membership, exact destination, authenticated inspection/release choices, real failure/retry receipts and the learner’s interpretation. Raw binary payloads and private authored answer keys are excluded. No content is silently truncated. The automatic reviewer must cite the rubric’s required evidence kinds; technical failure stays unavailable and can be retried with the original packet, without generation or handoff repetition. The saved-assessment listing now includes budget reviews as well as output reviews.

**Verification:** All 29 output/affected-budget review cases pass against disposable MongoDB with stub generation and judges. Coverage includes original/revised history, foreign or altered submissions, missing receipts, rehashed copy references, exact evidence assembly for failure-only or completed-private-copy cases, explicit technical retry, read-only assessment delivery and no duplicate model execution. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/automatic-review.xml`. Ruff passes. A scripted supported verdict verifies orchestration, not whether a live judge correctly interprets source facts or accepts a proposed alternative after failure. No passing-quality, credit, staff-review, release or >=8/10 claim follows from these checks.


### Checkpoint 118 Authenticated output HTTP actions and exact original downloads on October 7 2026

**Status:** Complete for HTTP delivery and saved-file/history downloads. Learner interface and browser verification are in progress.

Explicit endpoints expose capture, plan, scope, generation, saved-result finalization, exact-file inspection, contained handoff/retry, outcome interpretation and automatic assessment. Downloads verify ownership/course identity and return the actual source, generated PDF/CSV/ZIP or confirmed private copy. Saved reviews retain the original downloadable bytes after live runs disappear. JSON views exclude binary payloads, execution internals and private authored answer keys. Disabled versioned writes leave original history and downloads readable. Output case discovery replaces the old assessment only in packages containing the new authored case; no existing release was changed.

**Verification:** Six initial output/affected-budget HTTP journeys pass. The final 35-case HTTP/automatic-review regression also verifies module discovery, saved budget/output assessment listing, explicit enrollment, rejected client authority, foreign reads, exact file hashes and safe download headers, deleted-live-work history, technical grading retry and no extra provider/handoff work. Evidence: `artifacts/visual-review/certification-output-case-2026-10-07/{output-http.xml,output-http-review-final.xml}`. Ruff passes. All generation/judge calls use stubs; no real learner, external destination, publication or credit was changed.


### Checkpoint 119 Output learner journey and final responsive browser QA on October 7 2026

**Status:** Complete for the three local Output and Delivery assessment mechanisms. Readiness is 26/33 implemented, 7 still needing implementation and 0 release-verified. Acceptance stays 11/162.

The learner interface now connects owned workflow/source capture, exact generation scope, four real stages, original PDF/CSV/ZIP downloads, per-file inspection, an explicit hold or private-release choice, the controlled first handoff failure, targeted retry, delivery interpretation, linked revisions and automatic feedback. Saved course history remains read-only. Pending requests are persisted before submission; checking an ambiguous reply reads its original record, and only an explicit action may finish an original unresolved request. A claimed handoff cannot be discarded as unsent. File downloads verify the expected digest before becoming available.

**Verification:** 80 affected frontend tests and 82 readiness/catalog/authoring contracts pass; targeted lint and the final production build pass. Three complete production-browser journeys produced 51 normal, 51 enlarged-text and 96 final-layout states. The enlarged-text screenshots prompted reduced nested padding before the final run. All captures pass axe, page-overflow and visible target-size checks; selected narrow layouts were also visually inspected. Each journey verified nine real downloads, two generations, two exact inspections, one failed/private-copy handoff pair, two interpretations and two automatic assessments. Six simulated lost replies recovered by GET without duplicate work. Original history makes only reads. Actual ZIP members match the generated PDF/CSV bytes, and the private ZIP is byte-identical to the approved ZIP. The downloaded PDF was rendered with Poppler and visually checked. All three disposable API databases were removed on shutdown.

**Evidence:** `artifacts/visual-review/certification-output-ui-2026-10-07/` contains the manifests, screenshots, accessibility results, exact downloads and persistence proofs; `certification-output-case-2026-10-07/{output-ui.xml,readiness-final.xml}` contains the frontend/readiness results. The first two manifests retain the harness’s generic fixture-mode label; their per-capture notes and persistence proofs specify the real certification backend. The final manifest corrects this metadata and records measured root font sizes. The original failed TypeScript build was a test mock union-typing issue; the corrected build passes.

**Limits:** synthetic learner and stub providers/judges; the Formatter repair is an explicit fixture edit, not an agentic-chat editor test. Doubled CSS root text does not establish native 200% zoom or screen-reader usability. No passing model-quality, earned credit, real external delivery, publication, migration or >=8/10 claim follows. No staff queue is introduced.

### Checkpoint 120 Readable NSF source for representative validation on October 7 2026

**Status:** Complete for a separate unpublished source repair; Validation assessment remains open.

Poppler rendered the original NSF source as a mostly blank page with disjoint table borders. The new deterministic builder reuses the original generator’s source strings, embeds Vera fonts and gives its five budget columns fixed widths. The draft is one readable page with all substantive content unchanged, including annual versus full-project budgets and the named Co-PI. Original course files and learner assignments remain unchanged.

**Verification:** normalized substantive text matches the original exactly; all five table columns align, and the entire rendered page was visually inspected. Original SHA-256 is `eed235f9fdcf7ae37a548dd34ca677a98d437ace2c1814da4ee37dafb9f33821`; draft SHA-256 is `1217a6f5247a34aadb250553ea6581309aefc86274553993c4f500f01fbc089f`. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/source-checkpoint.json` and before/after renderings. The draft asset is not automatically substituted into an existing release.


### Checkpoint 121 Representative Validation case and strict package binding on October 7 2026

**Status:** Complete for authored case contracts; both Validation practical mechanisms remain unimplemented.

The new assignment pairs the complete readable NSF and NIH proposals and requires Principal Investigator, full-project budget and explicitly named Co-PI checks. It includes an actual absence case, annual-versus-project ambiguity and different project lengths. Learners must save their own expectations and source explanations before running the original revision, preserve an actual value mismatch, repair the same extraction and retest the complete unchanged suite. Optional-field skipping and technical failure cannot masquerade as successful semantic testing. Private expected answers/guidance are excluded from the public definition. The existing recognition assessment remains separate.

**Verification:** 77 case/outcome/catalog/authoring contracts pass, including wrong or missing source/case bindings, incomplete coverage, invented receipts, removed failures, changed rubric, empty expectations, source-anchor mismatches and count-based credit. Ruff and the draft outcome checker pass. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/case-contracts.xml`. Case SHA-256: `8f74f346ebf319263531888be6d510988d152187441a4fccdc262a1ea5947658`. No original course or registry is changed.

### Checkpoint 122 Owned Validation revision and complete source capture on October 7 2026

**Status:** Complete for internal immutable capture; saved test expectations, execution, retest, assessment and UI remain open.

Authenticated capture preserves the exact three owned extraction fields and both assigned PDF byte sequences, complete page text and original ingestion text. Inputs must belong to the selected enrollment’s lab, match the packaged source hashes and have completed ingestion. Both documents and all fields are checked again after capture to reject racing changes. Attached text overrides cannot replace a difficult source. Saved inputs survive source/artifact deletion, carry no execution authority and cannot be dispatched through the generic extraction executor.

**Verification:** All 26 disposable-MongoDB cases pass, covering foreign ownership, wrong/duplicated/missing sources, original request replay, wrong field semantics, duplicate keys, attached text, ingestion and capture races, rehashed nested corruption and no execution/XP. Each database was removed by its test fixture. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/input-capture.xml`. Readiness remains 26/33 implemented and 0 release-verified.


### Checkpoint 123 Preserved learner expectations before Validation execution on October 7 2026

**Status:** Complete for internal source-traceable suite submission. No run approval or grade.

The authenticated learner records all six source/field expectations, an explicit value or absence, references to original PDF pages, and coverage reasoning. The complete suite embeds the original capture and has a stable digest independent of later repaired field instructions. Quotes must exist on the stated page, but quote presence never marks an interpretation correct. Wrong interpretations remain learner evidence for later checks; replay cannot rewrite them. Complete originals remain readable after source/capture/artifact deletion.

**Verification:** All 25 disposable-MongoDB suite cases pass, including incorrect but traceable expectations, missing/duplicate cases, empty values, undeclared absence, fabricated references, foreign work, changed request bodies and rehashed nested corruption. Ruff passes after correcting a test fixture import alias. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/saved-suites.xml`. No provider, staff, execution or credit is introduced.

### Checkpoint 124 Source-bound Validation and repair checks on October 7 2026

**Status:** Complete for internal comparison rules, not authenticated execution or a release grade.

Every source/field pair is compared against both the learner’s saved expectation and the private source expectation. Agreement with an incorrect answer cannot pass. Explicit absence is checked even for optional fields; missing slots, malformed outputs and technical failures remain unavailable evidence. Exact USD formats and normalized single-person names are supported without approximate or substring matching. A repair must preserve the same owned artifact/field identities and complete suite, change an assessed field setting, preserve a real original semantic mismatch, and produce a complete source-supported retest. Its causal explanation and coverage limitations still require automatic review.

**Verification:** All 72 source-check/case contracts pass, covering wrong annual budgets, fabricated optional names, absent output keys, malformed/multiple records, altered sources/revisions, deleted cases, changed expectations, title-only edits and regression failures. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/source-checks.xml`. These checks consume trusted repository evidence; they do not authenticate posted client results or advance readiness. Next: bounded saved-suite plans, explicit approval and durable real extraction receipts.


### Checkpoint 125 Exact Validation plans and authenticated scope on October 7 2026

**Status:** Complete for internal planning and separate explicit approve/hold choices. No dispatch or credit from plan creation.

Original plans bind the exact capture on which the learner saved all expectations. Retest plans require the original complete run with an actual semantic mismatch, the same checked suite, both full sources and a changed revision of the same owned extraction. Production extraction settings resolve every model explicitly; image input is unsupported in this text executor. Scope choices bind the exact plan, case and capture, and an older approval replay cannot replace a newer hold. Plans remain readable after original workspace inputs disappear.

**Verification:** 61 planning/scope/source-check cases pass, including foreign work, altered inputs/suite/settings, missing original failures, unsupported image mode and nested tampering. Provider dispatch is absent during preparation. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/planning-scope.xml`. Ruff passes.

### Checkpoint 126 Durable Validation execution, complete retest and terminal recovery on October 7 2026

**Status:** Complete for internal approved two-case execution and saved-result finalization. Learner review, HTTP/UI delivery and live calibration remain open.

A claimed suite saves each exact case input before extraction and each actual result before the next case starts. Both original and retest receipts preserve the complete suite and source checks; an optional absence is never skipped. Replaying a claimed request reads its original state. Provider failure preserves a sanitized prefix and prevents successor execution; cancellation fences late results. Explicit finalization needs all four complete checkpoints and no terminal receipt, and reconstructs the original results without another model call. It records when the receipt was finalized without inventing an execution-finish timestamp. Existing failed/uncertain terminals cannot be overwritten by finalization.

**Verification:** The initial 37 execution/planning cases pass. The final 89 execution/recovery/planning/source-check cases also pass, including a real ExtractionEngine path with only model dispatch substituted, actual case text/metadata/configuration consumption, original mismatch and complete repaired-suite results, lost terminal writes, cancellation, stale approvals, nested tampering and readback after live source/run/approval deletion. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/{execution.xml,execution-recovery.xml}`. These tests establish orchestration, not live-model correctness, causal learner understanding, release readiness or earned credit. The two practical mechanisms remain unimplemented until learner delivery is verified.

### Checkpoint 127 Automatic Validation repair review on October 7 2026

**Status:** Complete for authenticated saved interpretation, automatic grading and preserved assessment history. HTTP/UI delivery remains in progress.

The learner's repair explanation embeds the original failed run, corrected revision, unchanged complete expectations and actual retest receipts. Automatic review receives source pages, both artifact revisions, all six learner expectations, scope decisions and actual outputs. Source checks veto a favorable model verdict when expectations or corrected values disagree with the source. Missing or malformed results produce unavailable evidence rather than an invented learner failure. Linked answer revisions retain the original record. Technical grading retry reuses the same evidence and never reruns extraction. Recognition remains a separate assessment; no staff queue or credit is introduced.

**Verification:** All 34 automatic-review/execution regressions pass, including forged references, nested corruption, foreign work, wrong expectations, incorrect repaired results, incomplete outputs, live-record deletion, linked revisions and explicit judge-only retry. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/automatic-review.xml`. Readiness remains 26/33 implemented and 0 release-verified pending the learner interface and connected browser QA.

### Checkpoint 128 Authenticated Validation delivery and complete-source downloads on October 7 2026

**Status:** Complete for HTTP actions and saved history; connected learner UI verification in progress.

Explicit endpoints separate capture, saved expectations, preparation, approve/hold, execution, finalization, learner interpretation and automatic assessment. GET requests only read owned records. Responses omit private authored expectations and embedded binary payloads; authenticated downloads return original PDF bytes from captures, suites, runs or preserved reviews. Discovery retains the separate quality-recognition assessment alongside the practical assignment. Original/retest identity and unchanged suite digests are visible without depending on current workspace files or model settings.

**Verification:** Three complete HTTP/discovery journeys pass, including eight source downloads per execution journey, explicit judge retry, replay after live-input/run/approval deletion, disabled-write read-only history, foreign-user denial and unchanged XP. The expanded delivery/review regression passes all 37 cases, including the affected Output review mechanism. Ruff passes. Evidence: `artifacts/visual-review/certification-validation-case-2026-10-07/{http-delivery.xml,delivery-review-regression.xml}`. Readiness remains 26/33 pending connected UI acceptance.


### Checkpoint 129 Complete Validation learner flow and connected browser QA on October 7 2026

**Status:** Complete for the two staged practical mechanisms; 28/33 implemented, 0 release-verified.

The learner interface keeps the recognition assessment and adds capture, six source-grounded expectations, explicit full-suite approval, actual comparisons, same-artifact repair, unchanged-suite retest, saved interpretation and automatic feedback. Requests are preserved before sending; ambiguous replies recover through GET, and an explicit finish retains the original identity. Malformed storage blocks new writes. Source downloads verify SHA-256 before delivery. Original reviews and linked revisions remain read-only in course history, including complete sources and both runs.

**Verification:** 83 affected frontend cases, 37 backend delivery/review regressions, 77 readiness/catalog/authoring contracts, targeted ESLint/Ruff, the outcome checker and the production build pass. The final connected browser journey captures 78 states at 320/390/1440px and 16px/32px root text, with zero axe violations, page overflow, undersized visible controls, page errors or unmatched fixture requests. All actual certification API responses succeed. Six deliberately lost replies recover without resubmission; the journey ends with two captures, one suite, two approved runs, two linked interpretations and two automatic reviews, only four model-dispatch calls and no XP/credential/selection change. Six downloads match original PDF hashes. Both isolated browser databases were removed and confirmed absent.

Manual inspection of selected screenshots caught excessive nested mobile padding despite passing overflow checks; fixed spacing was reviewed at doubled text/320px, normal text/390px, retest/1440px and interpretation/390px. The earlier 78-state journey is retained and not accepted as final because recognition history used the wrong synthetic catalog and mobile form text was too cramped. The final journey fixes both. Evidence: `artifacts/visual-review/certification-validation-ui-2026-10-07/{connected,final-layout,checkpoint.json}` and `artifacts/visual-review/certification-validation-case-2026-10-07/validation-ui.xml`.

**Limits:** Production ExtractionEngine orchestration and HTTP/Mongo persistence are real; model dispatch, automatic judge and the extraction repair endpoint are explicit synthetic fixtures. This is not live grading calibration or agentic editor QA. Doubled root text is not native browser zoom; screen-reader/learner observation remains open. No course is published, no earned credit or existing learner is changed, and no 8/10 score is asserted.


### Checkpoint 130 Readable original-content Batch proposal drafts on October 7 2026

**Status:** Complete for three unpublished source repairs; Batch assessment remains unimplemented.

Poppler rendered the original Batch source as an essentially blank page despite extractable text. All three draft copies now use embedded fonts and readable field/abstract layouts. The builder preserves every original substantive string and existing proposal number; it neutralizes the legacy generator's randomized Python hash so repeated builds do not silently renumber proposals. Original source PDFs and course registry remain unchanged.

**Verification:** Every final single-page PDF was rendered with Poppler and manually inspected. Whitespace-normalized text exactly matches each original after excluding the new training footer. File hashes and all rendered pages are saved under `artifacts/visual-review/certification-batch-case-2026-10-07/`. These readable documents provide sources, not execution or assessment evidence.

### Checkpoint 131 Authored bounded Batch pilot, inventory and recovery case on October 7 2026

**Status:** Complete for case/package contracts; all three Batch mechanisms remain unimplemented.

The new case requires five source-grounded fields across three distinct assigned proposals. A two-source pilot precedes a separate learner scaling decision on the exact same revision and models. Its shared-template limitations and unknown price/usage remain explicit. The first full batch deliberately rejects the second item before provider dispatch, creating a disclosed contained recovery exercise rather than pretending a real outage occurred. Recovery must bind the confirmed failed item and original batch while preserving successful receipts. Deterministic assigned-ID coverage remains distinct from usable source-correct output and automatic explanation review. Private expected answers are absent from public discovery, and the exercise removes legacy document-count stars.

**Verification:** All 78 case/outcome/catalog/authoring contracts pass after correcting the synthetic catalog fixture's rubric identity. Tests reject duplicate or reordered inputs, missing expectations, weakened deterministic coverage, invented receipts/costs, wrong approval phases, retry-all rules and changed source/exercise bindings. Ruff and the draft outcome checker pass. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/case-contracts.xml`. Case SHA-256: `8583fc07f4f74bf1fb04a548ccd1a48937daf01e3c946bdd83af7b85ff835931`. Next: owned capture, exact approved pilot/batch plans, durable per-item execution and targeted retry evidence.

### Checkpoint 132 Owned Batch extraction and complete three-source capture on October 7 2026

**Status:** Complete for immutable authenticated inputs; execution and learner delivery remain open.

Capture now preserves exactly five owned extraction fields and all three distinct assigned source IDs, complete original PDF bytes/pages and separate ingestion text. It rejects incomplete ingestion, substituted source bytes, attached text overrides and source/artifact races. Request replay reads the original capture after workspace deletion. Captures carry no execution permission and cannot enter the generic extraction executor.

**Verification:** All 26 disposable-MongoDB cases pass, including foreign ownership, missing/duplicate sources, field/key substitutions, forged nested content, concurrent source changes and request reuse. The databases were removed by their fixtures. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/input-capture.xml`. Next: deterministic source checks and exact pilot/full-batch/retry plans with separate learner approval. Readiness stays 28/33 implemented and all 33 unverified for release.

### Checkpoint 133 Deterministic Batch inventory and targeted-recovery checks on October 7 2026

**Status:** Complete for internal comparison rules, not authenticated execution or approval.

The checker binds each terminal item to its exact assigned source/document, captured extraction revision, batch, run and stable item identity. All five actual values are checked against the original sources. A mixed terminal inventory retains its failed item; it cannot claim successful coverage or source quality. A targeted retry may replace only a confirmed failed original item in a reconciled view, preserving hashes of every original success and retaining the original failure. Unknown usage/cost stay unknown; invented costs, missing timestamps and external-effect claims are rejected. The actual retry claim and concurrency fence remain executor work, not authority granted by this checker.

**Verification:** All 74 source/inventory/case checks pass, covering repeated/missing/reordered inputs, foreign identity, invented success, wrong amounts/sponsors, malformed outputs, invalid training-rejection placement, retry of successful items, duplicate retries and unresolved recovery. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/source-inventory-checks.xml`. Exact pilot/batch/retry plan resolution is in progress; readiness remains 28/33 implemented, 0 release-verified.

### Checkpoint 134 Exact Batch phase plans and saved scope decisions on October 7 2026

**Status:** Complete for planning and separate learner approve/hold choices. Durable execution verification is in progress.

Pilot plans bind the two assigned pilot sources. Scaling requires a complete source-correct pilot on the same capture and resolved model settings. Recovery plans bind a confirmed failed original item, retain its full original batch and any previous failed retry, and reject successful or uncertain work. Saved phase-specific choices survive workspace deletion; replaying an older approval cannot replace a newer hold. Preparation itself cannot dispatch extraction or award credit.

**Verification:** 62 plan/source-check cases and 38 saved-plan/scope cases pass. Pure plan tests use explicitly synthetic parent receipts; saved-pilot tests exercise real disposable-MongoDB persistence. They cover changed revisions/models, incorrect pilots, unsupported retry targets, exact ancestry, foreign ownership, altered scope and nested tampering. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/{plan-resolution.xml,pilot-planning-scope.xml}`. These tests do not establish actual batch execution, learner delivery or release readiness; readiness remains 28/33 implemented and 0 release-verified.

### Checkpoint 135 Durable Batch execution, exclusive retries and saved-result recovery on October 7 2026

**Status:** Complete for internal pilot/full-batch/item-retry execution. Automatic interpretation review and learner delivery remain in progress.

Every item saves its exact input before extraction and its result before the next item starts. A terminal failed item remains in the complete inventory. The disclosed second-item training gate performs no model dispatch. Targeted recovery atomically reserves one retry identity on the original failed item; competing plans cannot start duplicate extraction, and a lost response resumes only that same identity. Further retries require the exact previous confirmed failed terminal. Original successes, failures and plan/result hashes remain unchanged.

Explicit finalization reconstructs a complete durable inventory after a lost terminal write, including mixed-success inventories, without another model call. It records receipt-finalization time without inventing an execution finish. Cancellation fences late results and successor dispatch. Replaying a claimed request only reads saved state.

**Verification:** The first 18 execution tests and the expanded 115 execution/recovery/planning/source-check tests pass. Coverage includes simultaneous retry reservations, reservation-response loss, exact failed retry chains, stale scopes, malformed claims, wrong pilot values, nested tampering and history after live-record deletion. A real ExtractionEngine journey with only model dispatch substituted makes exactly five calls: two pilot, two full-batch and one targeted retry. Source/result checks and all failed receipts remain real persisted evidence. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/{execution.xml,execution-recovery.xml}`. No live-model correctness, learner understanding, earned credit or release readiness is inferred; readiness remains 28/33 implemented, 0 release-verified.

### Checkpoint 136 Automatic Batch interpretation review on October 7 2026

**Status:** Complete for saved learner interpretation, deterministic inventory checks and automatic explanation review. Learner UI remains in progress.

A saved review preserves the exact original batch and selected targeted retry receipts, including earlier failed retry ancestry. Its evidence includes complete source pages, the unchanged extraction/model settings, actual pilot values and timing, pre-execution learner choices, original successful and failed items, and the final reconciliation. Deterministic assigned-ID coverage remains distinct from successful recovery. Source checks veto a favorable judge verdict for incorrect or still-failed recovery; missing/uncomparable outputs remain unavailable evidence. Revisions retain earlier answers. Technical grading retries reuse the same packet and never repeat extraction or create a staff queue.

**Verification:** All 21 disposable-MongoDB review cases pass, including foreign/forged references, nested tampering, history after live-work deletion, wrong/failed retry vetoes, unavailable values and judge-only retry. The initial test exposed evidence categories outside the declared structured-review rubric; supporting sources and revision details now remain within the permitted batch-result/execution evidence, with no truncated content or widened grader contract. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/automatic-review.xml`. No earned credit, live-model quality or release readiness is asserted.

### Checkpoint 137 Authenticated Batch delivery and preserved source downloads on October 7 2026

**Status:** Complete for HTTP learner actions and read-only history; connected UI verification remains open.

Separate endpoints expose owned capture, exact phase planning, approve/hold, execution, saved-result finalization, interpretation and automatic assessment. Original pilot/batch/retry ancestry remains visible and source PDFs download from preserved captures, runs or reviews. GET requests perform no execution or grading. Responses omit embedded binary data and private authored answers. Course discovery and history retain the versioned Batch assignment.

**Verification:** Three HTTP/discovery journeys pass, including normal assessment and explicit judge-only retry, nine source downloads per full journey with exact SHA-256 checks, repeated-request readback, foreign-user denial and history/downloads after workspace/run/approval deletion. Disabled writes leave original history readable without live settings. Each full journey makes exactly five extraction calls, one or two judge calls, and no XP change. Ruff passes. Evidence: `artifacts/visual-review/certification-batch-case-2026-10-07/http-delivery.xml`. Readiness remains 28/33 implemented and 0 release-verified until learner delivery is accepted.


### Checkpoint 138 Complete Batch learner flow and connected visual QA on October 7 2026

**Status:** Complete for all three staged Batch mechanisms; 31/33 implemented, 0 release-verified.

The learner interface now exposes owned capture, separately approved pilot and scaling, actual mixed item inventory, an exact confirmed-failure retry, reconciliation and saved automatic feedback. It distinguishes terminal coverage, successful items and source-correct values, shows measured time while leaving usage/price unknown, and preserves the disclosed training rejection. Further retry requires a failed terminal; additional failed items can be reconciled from their own saved receipts. Saved original reviews and linked answer revisions retain the complete source, pilot and recovery evidence in read-only course history. Pending requests survive response loss and remount; checking is GET-only, finishing is explicit and malformed storage blocks new writes.

**Verification:** 96 affected frontend tests, 115 execution/recovery/planning checks, 41 Batch/Validation delivery-review regressions, 78 readiness/catalog/authoring contracts, targeted ESLint/Ruff, the outcome checker and production build pass. The connected production-browser journey captures 78 states across 320/390/1440px and 16px/32px root text, with zero axe violations, page overflow, undersized visible controls, page errors or unmatched fixtures. Every actual certification API call succeeds; six deliberately lost replies recover without resubmission. Exactly one capture, three approved runs, two linked interpretations and two automatic reviews persist, with five actual engine model-dispatch calls, two judge calls and no XP/credential/selection change. Nine downloaded PDFs match their original hashes. The isolated API shut down normally and its database was confirmed absent.

Manual screenshot review covers pilot approval at doubled text/320px, the mixed inventory at normal text/390px, actual field details at desktop/1440px and interpretation at doubled text/390px. Evidence: `artifacts/visual-review/certification-batch-ui-2026-10-07/{connected,checkpoint.json}` and `artifacts/visual-review/certification-batch-case-2026-10-07/`. The shared sticky course header still occupies substantial vertical space at doubled text; full-course native zoom and learner accessibility acceptance remain separate work.

**Limits:** Engine orchestration, HTTP, MongoDB and downloaded PDF bytes are real; actor, model dispatch and judge are explicit fixtures. This does not establish live-model grading validity, actual agentic extraction-editor use or broad production batch reliability. Doubled root text is not native browser zoom. No earned credit, migration, publication or deployment occurred, and no 8/10 reassessment is asserted. Accepted checklist count stays 11/162.

### Checkpoint 139 New fictional Governance capstone sources on October 7 2026

**Status:** Complete for two unpublished source PDFs; capstone execution remains in progress.

The capstone introduces a distinct award notice and issued amendment with an explicit simulated task date of January 5, 2027. The sources distinguish a $600,000 planned ceiling, $180,000 initial obligation, $70,000 increment and $250,000 revised cumulative obligation, plus a revised project end date. Both clearly state that they are fictional training records and limit use to the learner-owned rehearsal. Original legacy sources remain unchanged.

**Verification:** Both final single-page PDFs were rendered with Poppler and manually inspected for readable embedded typography, tables, margins and complete text. Text extraction, original page anchors and hashes are recorded in `artifacts/visual-review/certification-governance-case-2026-10-07/source-checkpoint.json`. These authored sources are not learner decisions, observed model failures or delivery receipts.

### Checkpoint 140 Authored Governance supervision and accountable-handoff contract on October 7 2026

**Status:** Complete for assignment/package contracts; both practical mechanisms remain unimplemented.

The new case requires an authenticated correction of an overbroad agent proposal, an actual unsupported original funding value, source-grounded learner finding, same-extraction changed-revision repair and complete retest. The accountable private handoff must identify the learner owner, intended use, supported inputs, limits, exact validation evidence and change/review route. It requires separate release approval, a disclosed no-write training rejection and explicit same-bytes recovery. Broad sharing, sponsor sends, recurring automation and agent claims of learner approval grant no authority or credit. Existing Governance recognition remains separate.

**Verification:** All 75 case/outcome/catalog/authoring checks pass, including original source anchors, private authored-answer exclusion, fixed decision phases, source/rubric/exercise substitutions and unsupported scope/retry shortcuts. Ruff and the outcome checker pass. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/case-contracts.xml`. Case SHA-256: `6f286b6110f55880bb7d44a2ba586f5adbd81d8b7f3529b5862cf7c89d493749`. Next: owned captures, saved scope correction, exact original/repair execution and private accountable-handoff evidence. Readiness remains 31/33 implemented, 0 release-verified; no 8/10 score is inferred.

### Checkpoint 141 Owned Governance capture and source-grounded repair checks on October 7 2026

**Status:** Complete for authenticated immutable inputs and internal comparison rules. Scope/execution/handoff delivery remains in progress.

Capture requires the exact six fields of one owned extraction and both distinct complete assigned records. Original PDF bytes/pages and separate ingestion evidence are preserved, including source/artifact race checks. The checker distinguishes revised cumulative obligations, planned ceiling and the issued amended end date. Missing, malformed or invalid-date outputs remain unavailable evidence rather than invented semantic failures. Repair comparison requires the same owned field identities, unchanged original sources, a changed field revision, an actual comparable original source mismatch and a complete source-correct rerun. A title-only edit cannot establish repair.

**Verification:** All 26 disposable-MongoDB capture tests and 24 source/repair comparison cases pass. The latter use explicitly synthetic result objects to verify comparison boundaries; they do not claim actual model execution. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/{input-capture.xml,source-checks.xml}`. Readiness stays 31/33 implemented, 0 release-verified.


### Checkpoint 142 Authenticated Governance scope correction on October 7 2026

**Status:** Complete for the saved learner correction; execution and handoff remain in progress.

The learner must explicitly reject the overbroad proposal, bind both assigned source IDs, limit the destination and audience to their private training inbox, and keep ongoing automation disabled. The saved explanation preserves the complete original capture and authored question. It grants no execution, external-effect or credit authority. Readback and identical request replay survive deletion of live workspace records.

**Verification:** All 18 disposable-MongoDB cases pass, including altered sources, foreign actors, agent-claimed approval, external destinations, enabling automation, blank reasons, changed request reuse and rehashed nested tampering. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/scope-correction.xml`. Readiness remains 31/33 implemented, 0 release-verified.


### Checkpoint 143 Exact Governance diagnostic plans and separate execution approval on October 7 2026

**Status:** Complete for saved original planning and learner approve/hold decisions; durable execution is being verified.

An original plan embeds the authenticated scope correction, full six-field capture, both complete source records combined into one interpretation, and resolved model settings. Separate approval binds this exact plan. A newer hold takes precedence over replay of an older approval. Preparation performs no extraction and saved readback survives deletion of workspace/capture/correction records.

**Verification:** All 17 disposable-MongoDB planning and scope tests pass, including wrong ownership, changed hashes, mismatched corrections, altered approval scope and invented execution. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/planning-scope.xml`. This does not establish actual extraction, repair or release readiness.


### Checkpoint 144 Durable joint Governance execution and saved-result recovery on October 7 2026

**Status:** Complete for the original internal extraction and durable recovery protocol; repair/handoff delivery remains in progress.

The executor saves both complete source records as one exact input before one extraction call, then saves the actual result before its terminal receipt. The current learner approval binds revision, model settings and implementation. Claimed requests only read their saved state. Cancellation prevents a late provider result from changing the saved prefix. Explicit finalization uses the original completed output without repeating extraction or inventing execution timing. Missing or malformed values remain unavailable evidence, never an assumed semantic failure.

**Verification:** All 48 execution, recovery and saved-planning cases pass. One test uses real ExtractionEngine orchestration with only model dispatch substituted and verifies the exact combined source text, all six field keys, metadata and resolved settings. Other tests cover provider failures without persisted exception secrets, late results, stale approval, altered runtime, source/result tampering, lost terminal writes and unchanged XP. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/execution-recovery.xml`. This is not live-model calibration or completed capstone delivery.

### Checkpoint 145 Original source finding and same-extraction Governance repair on October 7 2026

**Status:** Complete for the saved finding, exact repair plan and complete repaired extraction; memo/release verification is in progress.

A learner finding binds the actual comparable unsupported funding value and exact page quotes from both original records. The repair must capture a changed funding field in the same owned extraction after the saved finding, retain every source and field identity, and preserve model settings. A separate approval precedes the complete joint rerun. Actual repaired values determine source support; a still-wrong result cannot claim successful recovery. Saved repair history embeds the original execution, authenticated scope correction and source finding, surviving deletion of live records.

**Verification:** All 32 finding/repair integration cases pass, including invented values or quotes, already-correct originals, earlier captures, title-only/other-field changes, changed models, forged lineage and still-unsupported repaired output. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/source-finding-repair.xml`. Capture ordering is verified; these tests do not observe when a learner actually edited the workspace or establish the quality of their explanation. Readiness remains 31/33 implemented, 0 release-verified.


### Checkpoint 146 Accountable Governance memo, separate release and contained handoff on October 7 2026

**Status:** Complete for the persisted memo/release/handoff chain; automatic final interpretation and learner delivery remain in progress.

The structured JSON memo includes the actual six source-checked repaired values, complete revision/source/check references and learner-authored intended use, supported inputs, limitations and review route. Its accountable training owner is the authenticated learner. Exact byte hashes and downloads are distinct from a learner opening acknowledgement. Separate approve/hold choices govern only this memo and private inbox. The first authorized attempt records the disclosed rejection before writing. Explicit recovery atomically saves the same approved bytes and confirming private-copy receipt; it never repeats extraction or calls an external destination. A later hold blocks retry; replaying an older approval cannot override it or unlock a delivered copy.

**Verification:** All 33 disposable-MongoDB memo and handoff cases pass, including source-incorrect repair rejection, ownership, incomplete inspection, altered bytes, foreign destinations, old approval replay, holds after failure, duplicate action attempts, nested tampering and lost response after copy commit. Exact canonical JSON bytes are decoded and hashed. History/replay remain readable after upstream live-record deletion and XP remains zero. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/memo-private-handoff.xml`. Opening acknowledgements and explanations require later assessment; this is a private rehearsal, not observed real sponsor or staff delivery. Readiness remains 31/33 implemented, 0 release-verified.


### Checkpoint 147 Automatic Governance supervision and accountable-memo review on October 7 2026

**Status:** Complete for saved final interpretation and automatic explanation assessment; connected learner delivery remains in progress.

The complete review packet preserves both original source pages, original/repaired field revisions and actual values, source checks, authenticated correction/approvals/finding, learner-authored memo accountability and the exact no-write/confirmed-copy receipts. Missing confirmations cannot enter the final supervision review. Source and copy checks do not substitute for reviewing the learner's reasoning. Answer revisions retain the original work, and a technical judge retry uses the same saved packet without repeating extraction or handoff. Governance recognition remains separate.

**Verification:** All 16 integration cases pass, including history and revised answers after upstream record deletion, automatic feedback delivery, foreign/forged submissions, unconfirmed handoff rejection, nested tampering and judge-only retry. The complete evidence packet contains all eight declared evidence categories, no embedded PDF/base64 payloads and no private authored-case object. All review states remain automatic-only, with no earned credit or staff queue. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/automatic-review.xml`. The synthetic judge tests protocol integrity, not live grading validity. Readiness remains 31/33 implemented, 0 release-verified.


### Checkpoint 148 Complete authenticated Governance HTTP journey and preserved downloads on October 7 2026

**Status:** Complete for learner API actions and history. The full interface is implemented locally and is undergoing verification; both Governance mechanisms remain unaccepted.

Distinct endpoints expose captures, scope corrections, original/repair plans, approve/hold decisions, execution/finalization, source findings, memos, release choices, contained handoffs, final interpretations and automatic assessment. Public responses omit embedded PDF/base64 payloads and private authored expectations. Source downloads resolve from every preserved evidence-bearing record, including standalone corrections and findings. Memo downloads from a failed handoff expose its approved source memo without claiming a destination copy. Recognition remains separately discoverable alongside the capstone and course history.

**Verification:** All three initial and all three expanded HTTP/discovery cases pass. Each expanded full journey verifies 16 original-PDF downloads and five exact JSON memo downloads, plus a preserved memo download after upstream records are deleted. GET readback and automatic-assessment request replay survive deleted workspace records and unavailable live settings. Disabled writes retain history, foreign-user access is denied, each journey makes only two extraction calls and one or two judge calls, and XP is unchanged. Ruff passes. Evidence: `artifacts/visual-review/certification-governance-case-2026-10-07/{http-delivery.xml,http-delivery-expanded.xml}`. A clearly synthetic HTTP fixture is retained for frontend identity/ancestry regressions. Readiness stays 31/33 implemented, 0 release-verified until connected learner delivery is verified.


### Checkpoint 149 Complete Governance learner journey and readable panel scrolling on October 7 2026

**Status:** Complete for implementation and connected isolated delivery. Both Governance mechanisms advance to implemented: all 33 draft mechanisms are implemented, none release-verified. Accepted checklist count remains 11/162.

The learner can capture the six-field extraction and both sources, correct scope, separately approve original and repaired runs, record the actual funding mismatch, inspect complete rerun values, write an accountable memo, inspect its exact JSON bytes, approve or hold release, recover the disclosed first no-write handoff, and save/revise a supervision interpretation for automatic assessment. Original course history preserves the entire evidence chain and original downloads without executing or grading. Pending requests retain identity and recover by reading saved state. Staff involvement is not required.

**Repairs found during verification:** Duplicate keys on the evidence and action siblings retained previous evidence after successive saves; distinct keys fix the resulting duplicate memo/download controls, with a regression covering memo-to-release-to-handoff transitions. A generic assessment revision button now requires a separately saved Governance interpretation. The production build also exposed an inappropriate Node filesystem test import; the clearly synthetic HTTP fixture now lives with frontend tests. Enlarged mobile captures showed fixed panel controls, course title and breadcrumbs consuming most of the screen. Those controls and metadata now scroll with course content; only the compact title/close bar stays fixed. This fixes the observed layout issue without claiming complete accessibility acceptance.

**Verification:** All 200 Governance backend regressions, 105 affected frontend tests, 50 case/outcome/release-authoring contracts, targeted lint and production build pass. The corrected production browser journey passes 107 captures across 320/390/1440px at normal/doubled root text: zero axe A/AA violations, horizontal clipping, undersized visible controls, unexpected routes or page errors. It verifies ten exact PDF/JSON downloads and eleven lost-response recoveries, preserving exactly two engine executions, two interpretations and two automatic reviews. The corrected run produces all six supported values; handoff retry copies the same approved memo without repeating extraction. History performs GET-only reads and leaves persistence unchanged. XP, credentials and enrollment selection are unchanged.

Five representative enlarged/mobile/desktop result, memo, handoff and history captures were manually inspected. The first browser attempt selected module 11 instead of the observed module 10; the second exposed the duplicate-evidence defect. Both failed attempts are retained. Both disposable fixture databases were removed after normal shutdown. Evidence: `artifacts/visual-review/certification-governance-ui-2026-10-07/{checkpoint.json,connected-attempt3/}` and associated logs; readiness output is in the Governance case evidence folder.

**Limits:** Real isolated HTTP, MongoDB and ExtractionEngine orchestration use synthetic actors, model dispatch and judges. Editing the funding instruction uses an explicit fixture endpoint, so actual agentic editor use remains unverified. Doubled root text is not native zoom or screen-reader evidence. Live grading, learner observation, actual cohort reconciliation, release activation and earned-credit integration remain open; no publication, deployment, migration or >=8/10 reassessment occurred.


### Checkpoint 150 Disclosed actual stopped-run rehearsal on October 7 2026

**Status:** Complete for controlled execution and durable boundaries; learner delivery is undergoing verification. C8-M05-02 remains open. The unpublished Multi-Step case advances from revision 2 to 3, retaining the same assigned subaward and three assessment outcomes. Revision-2 case/exercise files are archived; the legacy release is unchanged.

A distinct preparation consent and disclosed approval prompt produce a recovery rehearsal. The real workflow engine executes the extraction and preserves its actual output, then records a deliberate rejection before the Reasoning provider is dispatched. Formatter cannot start, the rejection is labeled as training rather than a provider outage, and no final output or completion is claimed. Saved checkpoint validation rejects invented provider output, a dispatched-provider claim, altered stage boundaries and a success claim. A later normal run requires another plan and approval; it retains the stopped run and never resumes it in place.

**Verification:** 169 case/planning/runtime/checkpoint contracts and five disposable-MongoDB persistence cases pass. Exactly one extraction and zero reasoning/formatting calls occur during the rehearsal. Request replay after source/configuration deletion makes no additional provider call; finalization cannot turn the successful prefix into completion. A separate approved normal run succeeds while retaining the original rejection. Ruff and legacy release integrity pass. The first contract run caught a temporarily stale exercise hash after the system Python lacked the project's dependencies; regenerating it using the backend environment and rerunning passed all contracts. Revision-3 case SHA-256: `5c723136fef524753d106c9e9dc9a395cf6ce743168ca6ebd6ac8bb458aab16e`.

Evidence: `artifacts/visual-review/certification-multi-step-recovery-2026-10-07/controlled-stop-persistence.xml`, archived revision-2 definitions and local contract logs. Actual provider outputs remain explicit test fixtures. No credit, external write, staff work, publication or migration occurred.

### Checkpoint 151 Actual stopped-run recovery choices and authenticated history on October 7 2026

**Status:** Complete for saved choices, deterministic feedback and authenticated API delivery; frontend/browser verification remains in progress.

The learner identifies the first failed stage, selects the work to preserve, chooses the supported route and explains the inspected evidence. The three finite choices are checked directly against the actual owned stopped run. Explanations are retained without claiming to assess their quality. Feedback does not award an assessed outcome or authorize execution. Wrong choices can be revised with the original answer and complete stopped-run evidence preserved. Saved history and repeated requests survive deleted upstream records and disabled new writes. There is no model judge or staff queue for this finite-choice practice.

**Verification:** Twelve real database cases and one full HTTP journey pass, covering wrong and revised choices, exact receipts, deleted workspace/execution records, foreign users, rehashed corruption, disabled writes and unchanged XP. The HTTP journey separately prepares and approves a normal run after the rehearsal, preserving the failed history. It ends with two extraction calls, one reasoning call, one formatting call and zero judge calls. The initial HTTP fixture used an internal-plan helper on a public response; its corrected public-response helper passes. Evidence: `artifacts/visual-review/certification-multi-step-recovery-2026-10-07/{recovery-decisions.xml,http-final.xml}`. A synthetic real-HTTP fixture is saved with frontend tests. Counts stay 33 mechanisms implemented, zero release-verified and 11/162 checklist items accepted.


### Checkpoint 152 Usable own-run recovery and native zoom evidence on October 7 2026

**Accepted:** C8-M05-02. **Status:** Complete for the failed-step recovery exercise. Counts are 12/162 accepted and 150 open; 33 assessment mechanisms implemented, zero release-verified. No overall regrade is implied.

The connected learner screen now delivers the disclosed rehearsal, actual preserved extraction, confirmed reasoning rejection, recovery choices and revision history. Supported choices expose preparation of a separate internal run, which still requires a fresh approval before execution. The original failed run cannot be finalized or substituted for a completed comparison. Feedback checks the three finite choices without claiming to grade prose or award credit. Historical choices and embedded execution evidence remain read-only.

Visual review found and repaired excess mobile indentation, raw technical rejection presentation and clipped long dropdown answers at doubled text. Recovery now uses wrapping native radio groups with visible focus. Plain rejection text appears first, with full technical evidence still inspectable. Keyboard checks use arrow/space selection, move to the explanation and reach the enabled save action without submitting any extra work.

**Verification:** The real isolated HTTP/MongoDB/WorkflowEngine journey passed 65 captures, including five lost replies recovered with GET-only reads, wrong choices followed by a preserved revision, separately approved completion, and original read-only history. The final presentation has another 36 normal/doubled-text captures at 320/390/1440px and 18 native 200% zoom captures at physical 640/780/1440px (CSS 320/390/720px, 500px high). Zero axe violations, measured horizontal overflow, undersized visible controls, unexpected routes or browser errors. Both final readbacks are entirely GET-only and leave persistence unchanged: one capture, two runs, four decisions, provider calls [2,1,1], no judge calls, XP, credential or enrollment change. All 112 connected backend regressions, 76 related UI tests and 29 tests after the final radio changes pass; targeted lint and production build pass.

The native zoom harness uses Chrome's own default page-zoom setting in a newly created disposable profile. Root text remains 16px, pinch scale is 1, CSS viewport width halves, and devicePixelRatio becomes 2 from a configured base of 1. A full-page screenshot initially cropped the physical viewport; the harness now takes viewport images and checks PNG dimensions against the full physical viewport. Those initial cropped captures are retained but not accepted. Two readback attempts were stopped because they started before the latest production build finished; the final runs use the completed build. A test-only unsupported selector option initially failed TypeScript; removing it produced the passing build.

**Evidence:** `artifacts/visual-review/certification-multi-step-recovery-2026-10-07/{connected,radio-readback-final,radio-native-final,connected-regression.xml,checkpoint.json}`. Representative doubled-text radio choices and native-zoom rejection/save states were manually inspected. Provider outputs are synthetic; this verifies actual engine orchestration and the finite-choice exercise, not live-model quality. The fixture API was shut down after verification; the shared MongoDB and preview remain available. Actual screen-reader use, all-course enlargement, live grading and release gates remain open. No production publication, migration, deployment or staff task occurred.


### Checkpoint 153 Course-specific graduation and reachable certificate action on October 7 2026

**Status:** Complete for the observed graduation defects; C8-VIS-09, C8-A11Y-03/04/06/10 and C8-VERSION-09/12 retain their broader acceptance gates. Counts remain 12/162 accepted, 150 open.

The graduation dialog, certified banner and chat completion message now use the completed course's title and module count. Older results without a count describe completed requirements without inventing eleven modules. The dialog no longer adds an unsupported universal mastery claim. Its stars have an accessible numeric label. The View Certificate action now opens the course credential section and focuses the download control rather than leaving the learner in the completed module.

Short-screen review found the focused action could remain below the visible dialog after reflow. A fixed action footer keeps it reachable; a separately named, keyboard-focusable content region allows reading the entire message. The first footer revision exposed an axe keyboard-scroll-region failure; the final region and keyboard traversal resolve it. The panel respects reduced-motion preferences for lesson scrolling, progress-ring updates and XP counters; scoped CSS suppresses panel and celebration animations/transitions, including inherited styles.

**Verification:** Seventeen affected UI tests, targeted lint and the production build pass. The final production-browser checks cover 320/390/768/1024/1440px at 500px high and native 200% zoom at physical 640/780/1440px, with CSS height 500px. Ten captures have zero axe violations, page overflow, unexpected routes or browser errors. Real keyboard Tab cycles between scrollable details and the persistent action; Enter reaches the certificate download control with focus restored; Escape closes the panel. The synthetic three-module course proves the message reads the saved count. Exactly one synthetic completion occurs in each independent fixture. No download, real earned credit or credential is claimed. Native-zoom dialog and certificate-focus screenshots were manually inspected.

Evidence: `artifacts/visual-review/certification-completion-accessibility-2026-10-07/{short-final,native-final,final-tests.log,final-lint.log,recovered-build.log,checkpoint.json}`. Earlier failing captures are retained. The restart removed temporary services/logs; the preview was restarted on loopback 5294 after a successful rebuild, and final logs now live with the artifact evidence. No deployment or enrollment change occurred. Course-wide native zoom continues: all nine AI Literacy lessons already pass 45 captures, and the remaining ten modules are running against the final build.


### Checkpoint 154 Explicit correction and material-change policy on October 7 2026

**Accepted:** C8-VERSION-10. **Status:** Complete for the change-classification decision. Counts are 13/162 accepted and 149 open. Amendment delivery, actual cohort review and transition activation remain open implementation gates.

The transition policy now distinguishes application presentation patches, editorial changes inside frozen lessons, optional enrichment, changed assessed requirements and urgent incorrect guidance. It explicitly reconciles editorial patches with immutable packages: presentation fixes may preserve the enrollment, while any changed frozen asset receives a new release identity. A new enrollment default never switches an existing learner. Changed outcomes, passing evidence or grading behavior require a new version and verified equivalence before any credit transfer. Urgent amendments must identify the affected activity and supported replacement, preserve original records and reconcile in-flight work before another attempt. No unsupported activity is declared safe merely because a notice exists.

The change-record requirements include affected releases/assets, classification/reason, assessment impact, attempt boundary, verification and learner explanation. The already selected optional policy retains existing credentials and imposes no deadline without actual cohort evidence and a published support policy. No routine grading burden is assigned to staff.

**Evidence:** [Applying corrections while learners are enrolled](certification-v5-transition-policy.md#applying-corrections-while-learners-are-enrolled). This is the policy acceptance requested by C8-VERSION-10, not a claim that amendment or migration mechanisms have shipped. Existing catalog and publication guards described in checkpoints 3/5 remain unchanged; no course asset, rubric, registry, enrollment or credential was mutated by this documentation change.


### Checkpoint 155 All draft teaching at actual 200% browser zoom on October 7 2026

**Status:** Complete for the native-zoom teaching matrix. Broader C8-A11Y-09 and C8-QA-07/08/09 remain open for other surfaces, assessed controls, mobile keyboard and supported engines/assistive technology. Counts remain 13/162 accepted and 149 open.

All 74 authored lesson replacements across eleven modules were rendered in the production frontend at native Chrome 200% page zoom: physical 640×1000 and 1440×1000 viewports reflow to CSS 320×500 and 720×500. Root text remains 16px and pinch scale 1. PNG dimensions cover the complete physical viewport. Each lesson has reading and practice captures at both widths and wrong-answer/corrected-feedback exercise at the narrower width: 370 captures and 74 corrections, with no assessment or credit writes.

The coverage ledger compares every observed lesson identity/revision against its authored draft rather than a hand-picked lesson list. All captures pass axe A/AA, page-width, breadcrumb and lesson-navigation bounds checks; there are no unexpected routes or browser errors. Representative narrow reading, ordered instructions, question groups and feedback were manually inspected. The ordinary transient last-lesson toast is retained in some captures; it expires and is not evidence of a permanent obstruction. AI Literacy was captured before the graduation-only presentation changes; subsequent modules use the final rebuilt application. Each module manifest retains its exact source fingerprint.

**Evidence:** `artifacts/visual-review/certification-native-teaching-2026-10-07/checkpoint.json`, eleven module capture directories and their run logs. Synthetic course/position responses verify draft presentation and interaction only. This is not publication, live tutoring, screen-reader use, a completed practical lab or an >=8 regrade.


### Checkpoint 156 Module completion is independent of XP on October 7 2026

**Status:** Complete for the active panel's incorrect completion percentage; broader C8-DEF-05 and C8-VERSION-09 remain open. Counts stay 13/162 accepted and 149 open.

The active learning panel previously divided XP by a fixed legacy total or the course's maximum possible XP. That allowed bonus points to inflate apparent completion and confused optional rewards with required work. The course ring now counts completed modules within the selected course, with an accessible progress name and value. XP is separately labeled earned; the next-level bar remains an XP display. Unrelated saved modules do not affect the denominator or completed count.

**Verification:** Twelve affected panel tests pass, including high earned XP plus an unrelated completed record while only one of eleven enrolled modules is complete: the indicator remains 9%. The production build passes after adding required fields to that regression's typed fixture. Seven browser captures confirm two of three selected modules display 67% and preserve the keyboard graduation/certificate journey at five short-screen widths, with no axe, route, overflow or browser errors. Evidence: `artifacts/visual-review/certification-completion-accessibility-2026-10-07/{module-progress,module-progress-tests.log,module-progress-build-final.log,module-progress-lint.log}`. The unused standalone page is not routed; bookmarks and pop-outs use the shared panel. This does not change any grading, XP or credential record.


### Checkpoint 157 Strict certification tool responses and uncertain-write recovery on October 7 2026

**Accepted:** C8-CHAT-02. **Status:** Complete for schemas and malformed-response handling on the seven named course tools. Counts are 14/162 accepted and 148 open. This does not establish live tutoring or grading validity.

Progress, module, lesson, provisioning, check, completion and reflection tools now have explicit strict response models. They preserve the original successful payload and callable signature rather than coercing Boolean strings or introducing success defaults. Invalid arrays, missing required fields, contradictory progress counts, invalid lesson positions, empty/unusable practice answers and invalid rewards produce a structured uncertain-response error. Stored completion strings are no longer converted into truthy module completion. Validation failures log only the tool name, without learner/source payloads. A response failure after a completion call never repeats that call or asserts that its write failed.

The frontend validates the corresponding structures before rendering a rich card or success summary, including historical malformed payloads that bypass the new backend. A rejected payload is labeled Result needs review. Its recovery button reads current course progress and handles read failure explicitly; it never resubmits the action or asks the agent to repeat it. The generic tool summary now agrees with the rich grading card when required checks pass but an optional check does not: it no longer says all checks passed.

**Verification:** 130 backend tests and 67 frontend tests pass. A real backend export covers all 74 original teaching responses, eleven module responses and progress; all 86 pass the frontend contract. Existing valid and explicit-error responses remain supported. Regressions cover malformed nested data, strings in Boolean fields, unrelated next-module references, incomplete enrolled identity, invalid awards, one completion invocation despite an unusable reply, unchanged tool argument signatures, and no source-data leakage into validation logs. One old unit fixture contained a question with no answer options; it now has representative options, with a separate regression proving the empty form is rejected. An additional test exposed an upstream list where module records should be a mapping; that case now produces the same uncertain response.

Ruff, targeted ESLint and the production build pass. Fifty-two browser captures exercise eight malformed/uncertain cases and five valid card types at 320/390/1440px and native 200% zoom. Every explicit recovery issues GET-only certification requests; there are no model calls or certification writes. Axe, horizontal page bounds, unexpected-route and browser-error checks pass. The narrow grading summary and native-zoom recovery action were manually inspected.

**Evidence:** `artifacts/visual-review/certification-chat-contracts-2026-10-07/{normal,native,backend-complete.xml,frontend-recovery-tests.log,ruff.log,eslint.log,build-final.log,checkpoint.json}`. The cross-boundary fixture is `frontend/src/components/certification/__fixtures__/chat-tool-contract.json`, generated by `test_certification_tool_results.py` with the explicit `CERTIFICATION_CHAT_FIXTURE` output path. Schemas validate presentation contracts; they do not award competence, replace saved execution evidence or authorize a repeated write. No course publication, migration or deployment occurred.


### Checkpoint 158 Panel bounds, keyboard handoff and workspace preservation on October 7 2026

**Accepted:** C8-VIS-10. **Status:** Complete for the specified paired-view and work-preservation checks, plus reproduced bounds/focus defects. C8-VIS-09 and C8-A11Y-03/04/06 remain open for broader controls, actual mobile keyboard and full assistive-technology checks. Counts are 15/162 accepted and 147 open.

A dragged 540px panel could extend 340px beyond the right edge and most of its height below the viewport. Its old coordinates also survived a viewport contraction, leaving the entire panel offscreen. Bottom docking kept a 360px height on a 250px viewport, hiding the header and close action. Dragging now clamps the actual panel dimensions, resizes re-clamp saved coordinates, and floating/bottom modes use bounded dynamic viewport heights. Pointer cancellation ends dragging.

Closing after a responsive change could restore focus to a hidden Activity trigger. The panel now restores a visible course/Activity entry when its original target is hidden. A separate browser assertion exposed the Activity drawer focusing Tools and assistant after opening the course. The drawer now distinguishes a course handoff from a workspace handoff, and establishes initial focus synchronously. Fullscreen contains keyboard focus; nonmodal panes allow keyboard return to the workspace. Escape restores a visible entry and the unsent chat draft remains intact.

**Verification:** Production build and targeted lint pass. The 33 affected panel, workspace and Activity regression tests pass. Forty-two final captures cover all five modes at normal and native 200% zoom, a 390×250 CSS viewport contraction, and teaching beside workflow/extraction editors at 1024/1440px. Unsubmitted text input, an unsubmitted extraction-field draft and document selection survive every mode. Opening/closing the lesson preserves the same rendered PDF canvas and editor draft. No certification/editor writes or execution requests occur. Axe, page bounds, unexpected-route and browser-error checks pass. The browser cancels the redundant initial PDF download probe; the actual PDF canvas renders and remains mounted.

**Evidence:** `artifacts/visual-review/certification-panel-navigation-2026-10-07/{baseline,focus-entry,normal-handoff,native-handoff,workspace-lessons,handoff-tests.log,handoff-lint.log,build-handoff.log,checkpoint.json}`. Earlier failed checks and diagnostic captures are retained. This is synthetic transport with an actual local source PDF; viewport contraction is not an actual OS keyboard. Docked panels still overlay part of the workspace, so this evidence proves work preservation and paired viewing, not unrestricted simultaneous access to every underlying control. No migration, publication or deployment occurred.


### Checkpoint 159 Direct chat certificate access and versioned graduation on October 7 2026

**Accepted:** C8-JOURNEY-10. **Status:** Complete for graduation presentation and certificate access in chat/panel, combined with checkpoints 153 and 156. Counts are 16/162 accepted and 146 open. This does not establish the validity of the draft 5.0 grading or issue a real credential.

Certified completion and progress cards now offer a direct PDF action without sending a message to the agent. An enrolled historical card reads credential history and downloads exactly its original enrollment's immutable issuance, even while a different course is selected. A missing or ambiguous match fails visibly rather than substituting today's certificate. Older unversioned cards shown after a course change offer explicit earned-certificate history; the existing unversioned endpoint remains available when still using that course. Download failure is retryable with GET requests only. No course switch, regrade, completion retry or staff queue is involved.

Course progress no longer substitutes a generic credential title for a supplied course. Chat and panel graduation identify the actual course version, show the supplied module count and earned XP, and explain keeping the earned certificate with training records. Chat star counts now have text alternatives. Earlier panel changes keep the completion action reachable, focus the certificate action after dismissal, and calculate completion from selected-course modules rather than a hardcoded XP total.

**Verification:** 50 affected frontend tests, targeted lint and the final production build pass. Forty-two new browser captures cover chat completion/progress, historical and ambiguous identity, unavailable issuance, failed-download recovery, legacy compatibility, and the three-module panel graduation journey. Normal widths include 320/390/768/1024/1440px; native 200% zoom includes CSS 320/390/720px. Twenty keyboard-triggered downloads match the existing real-renderer synthetic PDF byte-for-byte. No download invokes the agent; no certification endpoint is written by the chat fixture. The panel journey uses one explicitly synthetic completion response per run. Axe, page bounds, exact version/count assertions, focus containment/return, unexpected-route and browser-error checks pass. Narrow download recovery and history were manually inspected.

**Evidence:** `artifacts/visual-review/certification-chat-certificate-2026-10-07/{normal,native,panel-final,panel-native-final,tests.log,panel-tests.log,lint.log,panel-lint.log,build-final.log,checkpoint.json}`. PDF bytes originate from the existing October 5 certificate-renderer QA fixture. No real learner credit, credential, publication, migration or deployment changed. The broader actual-model, assistive-technology and release gates remain open.


### Checkpoint 160 Mobile reading width and reachable navigation on October 7 2026

**Accepted:** C8-VIS-02, together with the earlier panel indentation and narrow lesson-layout repairs. **Status:** Complete for reading-width adaptation and preservation of file/tool context. Counts are 17/162 accepted and 145 open. Actual on-screen keyboard and broader focus/engine gates remain open.

The fixed 88px workspace rail consumed over a quarter of a 320px chat viewport. Below 768px it now uses a 56px icon rail, restoring 32px to the lesson column. A keyboard/touch toggle expands the same rail to show all navigation labels. Accessible button names, current-section state and all existing destinations remain available; desktop labels and width are unchanged. The rail scrolls vertically on short screens so lower destinations remain reachable. This changes presentation only, without selecting another project, clearing chat or discarding files.

**Verification:** Eight existing workspace/navigation tests, targeted lint and the production build pass. Fifty-one final captures cover reading heading/body, expanded labels, returning from Files and keyboard focus at 320/390/768/1440px, actual native 200% zoom at CSS 320/390/720px, and doubled root text. Browser assertions measure the exact 32px reading-width difference, confirm the original lesson DOM and unsent draft survive toggling/source navigation, and confirm the selected document remains selected. Actual Tab presses reach the lower navigation action at a 250px CSS viewport height with visible focus. Axe, page-width, route and browser-error checks pass; narrow native body text and short-screen focus were manually inspected.

**Evidence:** `artifacts/visual-review/certification-mobile-width-2026-10-07/{normal-final,native-final,large-text-final,tests.log,lint.log,build.log,checkpoint.json}`. Earlier diagnostic captures remain separate. This is a real exported teaching payload with synthetic transport. The long composer draft remains present intentionally; viewport contraction does not claim an actual OS keyboard. No course requirements, credit, enrollment or publication changed.


### Checkpoint 161 Saved assessment result consistency on October 7 2026

**Status:** Complete for read-time semantic validation of saved draft reviews and recognition feedback. Counts remain 17/162 accepted and 145 open; no broad grading or release gate is closed.

A valid storage digest identifies saved bytes but does not prove that their assessment is internally consistent. Saved automatic-review reads now require the original policy, exact required outcome coverage, Boolean verdicts, original evidence/contract/judge identities, valid evidence citations, and agreement between final summaries and the original model plus deterministic checks. Missing-evidence and unavailable-provider results remain supported. A saved source/arithmetic veto cannot be removed by restoring a model success. Draft results cannot assert credit, module completion or staff grading. Canonical comparisons distinguish Boolean values from numeric lookalikes.

Recognition history checks owner/course/bank identity, learner submission origin, complete unique question/outcome coverage, valid selected choices, Boolean verdicts and summaries matching the saved checks. It preserves historical verdicts and explanations without calling the scenario grader. Malformed results fail with controlled reconciliation messages; reading cannot silently repair, rerun or award anything.

**Verification:** 179 unit checks and 156 persistence checks pass: 20 integrity/delivery cases, 49 process/design/connected review cases, 83 advanced/output/validation/batch/governance cases, and four scenario-history cases. Corrupted results with recomputed valid hashes are rejected by both list and detail reads, with unchanged records, no second judge call and no XP. Actual result producers for all ten practical modules remain readable across supported, missing-evidence, technical-failure and supporting-veto states. Ruff passes. Existing dependency deprecation warnings remain.

**Evidence:** `artifacts/visual-review/certification-review-integrity-2026-10-07/{final-unit.xml,persistence.xml,remaining-reviews.xml,module-reviews.xml,scenario-persistence.xml,ruff-final.log}`. Persistence runs use disposable test databases on a dedicated loopback MongoDB 8.0.25 process, downloaded from the official distribution and checked against its published SHA-256 (`9f929b78ebbd4fc257a2d1ee2a34659bf3e311055ed68c50410c14730929ed37`). Test fixtures remove their own databases. This is compatibility and corruption handling, not live-model calibration, new final-credit integration or an >=8 regrade. The course registry, learner enrollments and original credentials remain unchanged.


### Checkpoint 162 Direct authored lesson navigation in chat on October 7 2026

**Accepted:** C8-JOURNEY-03. **Status:** Complete for dependable authored navigation. Counts are 18/162 accepted and 144 open. Live tutoring and full accessibility acceptance remain open.

Chat lesson cards now offer previous/next, a named lesson list, return to the saved lesson, and explicit Save my place. Navigation follows authored stable IDs within the selected course, including repeated lesson titles and reordered arrays. Starting lessons from a module card opens the same direct reader. Neither action asks the LLM to infer a title or numeric offset. Browsing and local practice do not write progress or award credit. Saving updates the versioned server cursor explicitly; legacy courses retain their existing user-scoped browser position format.

Course/enrollment/manifest, lesson identity, revision and original content must match before navigation is enabled. Unidentifiable or historical cards stay readable and point to the current learning panel. Changing the selected course removes navigation rather than substituting another version's teaching. New lesson focus moves to its heading; practice choices cannot leak into another lesson. Failed saves retain reading and the original saved place, with a read-only refresh action and no automatic write retry.

**Verification:** 53 targeted frontend tests pass, including existing chat contracts and cursor concurrency checks. Seventy final captures cover normal widths 320/390/768/1440 and native 200% zoom at CSS 320/390/720. Browser assertions exercise next/previous, the lesson list, return, first/last boundaries, practice feedback/reset, explicit save, conflict/refresh, module-card entry, reload, historical revision rejection and panel agreement. Navigation adds no agent request. The unsent chat question survives browsing. Axe, page bounds, route and browser-error checks pass. Native selector focus and narrow module teaching were manually inspected. The production build and targeted ESLint pass; initial type-narrowing failures and a fixture locator failure are retained separately.

**Evidence:** `artifacts/visual-review/certification-chat-navigation-2026-10-07/{normal-complete,native-complete,final-tests.log,handoff-lint.log,build-handoff.log,checkpoint.json}`. These captures use authored draft teaching with synthetic transport; the module entry fixture retains legacy overview/instructions to exercise the existing module-card contract. They do not accept that legacy copy as future 5.0 curriculum. The shared final build also includes the reopening fix verified in checkpoint 163. No curriculum publication, migration, model calibration or credit changed.


### Checkpoint 163 Cross-browser resume and preserved panel work on October 7 2026

**Accepted:** C8-JOURNEY-01. **Status:** Complete for the server cursor, direct chat/panel resume and explicit reading restart. Counts are 19/162 accepted and 143 open. Other engines, actual mobile keyboard and assistive technology remain separate open gates.

A previously opened panel could retain an earlier module after the learner saved a new place in chat. The panel now follows a cursor changed while it was closed when it reopens. A progress refresh while it is open does not replace the current module/draft, and closing/reopening without a new cursor preserves an unsaved module selection. Legacy explicit saves update the existing browser module location as well. Opening the panel is disabled during a chat position save to avoid an incomplete handoff.

**Verification:** Forty affected frontend tests pass, including actual module selection followed by close/reopen with no new cursor, and an external cursor change that must not replace an open module. Three real-MongoDB cursor tests preserve credit/answers/lab references and reject stale or revoked writes. The production build and lint pass.

Nine connected browser captures use two separate Chrome processes/profiles, desktop 1440px and narrow 390px, with actual certification HTTP routes and an isolated MongoDB database. Browser storage isolation is explicitly checked. Browser A opens Foundations, closes it, saves an AI Literacy lesson from chat, and reopens directly to the saved AI Literacy lesson. Browser B's stale revision receives HTTP 409; the original cursor remains intact and refresh causes no retry. A subsequent save resumes in A after reload, then a panel save resumes in B's module reader. Selecting lesson one and explicitly saving restarts reading without erasing earned work. The four successful writes advance revisions 0→4; the rejected stale write does not advance them. XP, certification state, completed-module record, reflection answer, document references, active enrollment, assessment-attempt count and credential count remain unchanged; no write lease remains held.

**Evidence:** `artifacts/visual-review/certification-resume-connected-2026-10-07/{browser-final,cursor-persistence.xml,frontend-verified-tests.log,ruff.log,lint.log,api-final.log,checkpoint.json}`. The persistence receipt records exact requests/statuses and before/after records. Authentication and initial chat transport are test substitutes; payloads come from the real backend tools. This verifies shared reading persistence, not live tutoring, real-device hardware, new grading or a 5.0 release. The copied test registry and synthetic learner are disposable; the application registry and real learners are untouched.


### Checkpoint 164 Readable module states, stars and required answer groups on October 7 2026

**Accepted:** C8-A11Y-08, combined with the previously verified eight diagram text equivalents and named validation/graduation stars. **Status:** Complete for these alternatives; broader course structure, focus, assessment-control and actual screen-reader gates remain open. Counts are 20/162 accepted and 142 open.

Locked module cards no longer hide their titles/subtitles behind a lock overlay. They state the actual unmet prerequisites from the selected course; a nonlinear course cannot incorrectly name the numerically preceding module. Completed cards explicitly say Completed. Module cards, detail headers, progress widgets and criteria expose named star counts. Filled and unfilled stars have stronger contrast, consistent with already named validation and graduation results. Chat progress identifies completed/next/incomplete rows and names its progress value. Tier progress names the stage and completed count; empty stages are omitted rather than presenting a zero-range indicator.

Reflection choices now form named required groups with shared instructions and unique per-form radio names. Keyboard focus is visible around the selected answer. Inputs remain disabled while the exact selected answers are being saved. This does not change answer meaning, prerequisites or grading. A purple-theme browser check found completed chat module names at 4.43:1 contrast; they now use the readable muted-text color. The earlier failed captures and missing credential-history fixture route are retained separately.

**Verification:** 46 affected frontend tests, targeted ESLint, whitespace checks and the final production build pass. The first build identified two unsupported Testing Library selector options introduced in checkpoint 163's test-only edits; they were corrected and the full current source then built successfully. Fifty-four final course captures cover four normal widths, native 200% zoom at CSS 320/390/720, and gold/purple themes. Actual Space/ArrowDown keyboard input selects each reflection answer. The pending submission retains all selected answers with disabled controls; the saved state does not change XP or mark the module complete. All named status/progress assertions, axe scans, page bounds, routes and browser-error checks pass. Seven additional graduation captures retain focus containment/return, correct version/module count and readable stars at five short-screen widths. Narrow locked cards, native answer focus, purple chat progress and graduation were manually inspected.

**Evidence:** `artifacts/visual-review/certification-course-semantics-2026-10-07/{normal-final,native-final,graduation,tests.log,lint.log,final-lint.log,star-lint.log,build-stars.log,checkpoint.json}`. This uses synthetic course/assessment responses and actual UI/keyboard interaction. Existing diagram prose supplies its previously verified text alternative; lucide's decorative-icon default was checked in the installed implementation. This is not an actual screen-reader session, real grading or a release regrade. No learner data, registry, publication or migration changed. The separate checkpoint 163 API was shut down and its database removal verified in `certification-resume-connected-2026-10-07/cleanup.json`.


### Checkpoint 165 Additional browser-engine verification on October 7 2026

**Status:** Complete for the bounded WebKit checks below; Firefox, actual Safari/iOS devices and assistive technology remain unverified. Counts remain 20/162 accepted and 142 open. No broad browser or accessibility gate is closed.

The visual harness now records and selects Chromium, Firefox or WebKit explicitly. Engine-incompatible Chrome executable/zoom settings are rejected. Repository-pinned Playwright browsers were installed into disposable temporary storage without using real browser profiles or changing user privacy settings.

**Verification:** Five clean serial WebKit 26.6 runs produced 103 captures: 40 direct lesson navigation/recovery/panel-handoff captures, 18 certificate states with 12 byte-verified downloads, 36 module/answer/progress semantics captures, two actual notification-poll/reload captures and seven graduation/focus-return captures. Normal widths include 320, 390, 768 and 1440px; graduation also covers 1024px at a short 500px height. Axe, page bounds, expected routes and browser-error assertions pass. Narrow graduation and purple reflection focus were manually inspected. These are actual frontend components with synthetic transport, not actual Safari/iPhone hardware or live grading.

Earlier concurrent WebKit runs reported action timeouts and one notification access-control error; they remain separate failed diagnostics. Serial runs with a bounded 90-second action timeout passed, and the real 30-second notification polling/reload check did not reproduce the error. The shared notification fixture was corrected to the actual response shape; no notification application behavior changed. Graduation initially failed because default macOS WebKit Tab skips buttons. An isolated plain HTML reproduction confirmed Option+Tab reaches buttons. The final test uses that actual platform shortcut, records it in the manifest and verifies modal containment and focus return; it does not change user settings.

Firefox failed before app navigation with “Could not find profile folder.” Its launch symptom matches the reported macOS profile-access issue ([Playwright #42768](https://github.com/microsoft/playwright/issues/42768), [Mozilla #2062988](https://bugzilla.mozilla.org/show_bug.cgi?id=2062988)); the exact local cause was not established. No privacy grants, real-profile modifications or binary changes were attempted. Firefox acceptance remains open.

**Evidence:** `artifacts/visual-review/certification-browser-engines-2026-10-07/{webkit-navigation-serial,webkit-certificates-serial,webkit-semantics-serial,webkit-polling,webkit-graduation-keyboard,checkpoint.json}` plus retained diagnostic logs. These runs use checkpoint 164's production bundle; the milestone source change started during this batch was not yet built. Native 200% zoom evidence remains the separately recorded Chrome evidence. No real learner data, curriculum registry, model calibration, publication or migration changed.


### Checkpoint 166 Readable XP milestones on October 7 2026

**Status:** Complete for the XP milestone display. Counts remain 20/162 accepted and 142 open; broader typography, clipping and grading criteria remain open.

The old nine-milestone strip used 9px labels and clipped its final entries on narrow screens. It also assumed every course used a legacy level name. The replacement is a keyboard-operable disclosure with a named list, readable 14px names and 12px XP/status text, wrapping custom names and explicit Reached/Not reached status derived from earned XP. Its explanation distinguishes XP milestones from required module checks. Unknown level names render safely instead of dereferencing absent legacy configuration. This is presentation only.

**Verification:** Seventeen existing panel/journey tests and targeted lint pass. The full TypeScript/production build passed. A doubled-text check then exposed excessive nested padding around a long custom name; reduced padding and a later two-column breakpoint fixed the narrow word fragments. The final styling was rebuilt with Vite. Sixty-six final captures cover normal 320/390/768/1440 widths, native Chrome 200% zoom at CSS 320/390/720, and doubled root text. Standard and long custom milestone names plus a 123,456,789 XP threshold pass element-overflow, minimum-font, last-item reachability, keyboard Enter/Space, axe, page bounds, route and browser-error assertions. All certification requests are GET-only and progress stays identical. Normal, native and doubled-text narrow custom milestones were manually inspected. Earlier successful pre-padding and failed doubled-text captures remain separate diagnostics.

**Evidence:** `artifacts/visual-review/certification-xp-milestones-2026-10-07/{normal-padding,native-padding,large-text-padding,tests.log,lint.log,build.log,build-padding.log,checkpoint.json}`. Doubled text is distinct from browser zoom. Synthetic custom milestones do not change actual course thresholds, earned XP, requirements or credentials. No course publication, migration or live grading occurred.


### Checkpoint 167 Explicit combined draft outcome results on October 7 2026

**Status:** Complete for read-only aggregation and its HTTP boundary. Final-credit integration and learner-facing selection remain open. Counts remain 20/162 accepted and 142 open; no grading acceptance gate is closed.

The new module-readiness reader evaluates the selected module's complete outcome list using explicitly selected original scenario and automatic-review receipts. It never scans for the latest or best attempt. A selected failed scenario remains failed after a newer passing submission. A mixed module requires both kinds of evidence; a practical pass does not cover its scenario outcome, and a scenario pass does not cover its practical outcomes. Existing saved-result integrity checks preserve original source/execution vetoes, missing evidence and technical failure. Prepared/in-flight reviews remain pending. Every outcome keeps its state and selected receipt identity, so one result cannot conceal another missing or failed requirement.

The response binds enrollment, course manifest, outcome-contract/rubric identity and original receipt/result digests. It is explicitly a draft preview, with credit and completion eligibility false and no staff queue. It does not constitute a saved completion authorization. The authenticated GET endpoint requires an explicit enrollment, accepts exact optional receipt IDs, and remains read-only when active delivery is disabled. It does not initialize enrollment, call a judge, retry an assessment, write progress or issue a credential. Legacy participation courses have no competency result through this endpoint.

**Verification:** Ten real-MongoDB selection/integrity cases pass, including original failure versus later pass, no implicit selection, pending/provider-failure/model-revision states, digest-valid inconsistent results, cross-owner/module rejection, mixed scenario/practical evidence and a real saved execution veto despite a synthetic model's supported verdict. An additional actual FastAPI HTTP test verifies 401 authentication, 409 ownership/inapplicable selection, 404 missing receipts, 422 missing enrollment, 405 write rejection and 503 corrupted receipt handling. Reads preserve original progress and receipts, never rerun the synthetic judge, and never award credit. Ruff passes. The first run's credential-count assertion referenced the wrong repository property; it was corrected to query the credential collection, and the expanded final run passes. The failed diagnostic remains separate.

**Evidence:** `artifacts/visual-review/certification-module-readiness-2026-10-07/{final-persistence.xml,http.xml,ruff.log,checkpoint.json}`. Tests use disposable databases and copied synthetic course packages; source extraction/model responses are test substitutes. No real course registry, learner enrollment, credential, live-model calibration, publication or migration changed. All 33 mechanisms remain draft implementations with zero release-verified mechanisms.


### Checkpoint 168 Foundations assignment matches the staged assessment on October 7 2026

**Status:** Complete for the separately authored draft assignment and its chat/panel presentation. Full-course packaging, assessed credit and live grading remain open. Counts remain 20/162 accepted and 142 open.

Foundations had new lessons and a staged scope/execution/source-review mechanism, but no separate 5.0 exercise asset. Reusing the old exercise would tell learners to earn credit through field counts and extra-field stars, expose the old answer key, and suggest asking the agent to complete the module. The new `foundations-exercise.json` instead explains the bounded assigned source, deliberate incorrect-source proposal, explicit learner correction and approval, separate saved execution, all five source checks, repair and exact-work automatic assessment. Chat adds a clear statement that the learner records their own decisions in the panel. Extra fields, XP and quality scores do not replace those requirements. The legacy exercise and frozen course assets are unchanged.

The authored exercise binds the original proposal digest and required field list, contains no answer key or legacy star rubric, and requires readable instructions on both routes. Catalog validation rejects a scoped exercise with no original proposal and rejects semantic mismatches even after package hashes are recomputed. Old packages without the new assessment method retain their original behavior. The full new assignment appears before preparation in the practical-review panel as an initially open, keyboard-operable disclosure; collapsing it keeps the preparation action reachable. History does not substitute these new instructions for saved original work.

**Verification:** 35 unit/catalog/lifecycle cases, nine real-MongoDB saved-scope cases and 52 existing frontend cases pass. The authoring contract check, Ruff, ESLint, whitespace and full TypeScript/production build pass. Fifty-four captures cover panel introduction/scope/source checks/preparation plus chat first/final steps at normal 320/390/1440 widths, native 200% zoom at CSS 320/390/720 and doubled text. All seven panel steps and eight chat steps are present; ordered steps retain authored text, wrap within their cards and omit old field-count stars. Viewing/collapsing makes only certification GET requests and leaves XP/certification unchanged. Axe, page bounds, expected routes and browser-error checks pass. Narrow panel scope, native chat final instructions and doubled-text preparation were manually inspected.

**Evidence:** `artifacts/visual-review/certification-foundations-assignment-2026-10-07/{normal,native,large-text,catalog-unit.xml,scope-persistence.xml,frontend-tests.log,final-ruff.log,frontend-lint.log,build.log,checkpoint.json}`. Browser transport, course identity, prepared-document marker and prompt digests are synthetic; these reading checks do not execute the lab or establish grading validity. The schema/catalog tests and separate saved-scope persistence checks provide their own evidence. This draft has not been packaged into the application registry or assigned to existing learners. No publication, migration, model call, staff task or credential change occurred.


### Checkpoint 169 Assemble and inspect the complete draft course on October 7 2026

**Status:** Complete for isolated assembly and entry inspection. Counts remain 20/162 accepted and 142 open. All 33 mechanisms are draft implementations; zero are release-verified.

The reproducible assembler combines all eleven module definitions, 74 revised stable lessons, eleven assignments, original case/scenario assets, assigned documents and the outcome contract into a separate draft-only catalog. AI Literacy now has its own scenario assignment rather than the old reflection exercise. Public discovery excludes private answers and review guidance. The assembler rejects stale lessons, incomplete or mismatched assets, existing output directories and any output inside the application catalog. It stages and validates before publishing its local output directory. No live registry/default/enrollment was added. A deliberate rubric placeholder prevents preview credit. Preview prerequisites and XP/star policy are explicitly unfinished inspection settings, not a proposed release policy.

**Verification:** 35 assembly/catalog/outcome tests and Ruff pass. Deterministic reassembly yields the same package; lifecycle checks reject enrollment, support/default selection and publication of this draft. Sixty-nine production-UI captures cover course entry and the teaching/assessment entry for all eleven modules at 320/1440px plus native Chrome 200% zoom at CSS 390px. Each expected assessment panel opens, including both recognition and practical sections in mixed modules. No legacy completion/reflection-submit controls or alerts appear. Axe, page bounds, routes and browser errors pass. Narrow AI/Governance and native Governance views were manually inspected. All certification requests are GET-only. The browser uses synthetic enrollment, a prepared-document marker and empty histories; these captures verify entry, not lab execution or grading.

Initial diagnostic runs exposed missing public prerequisite metadata and an incomplete synthetic budget field list. The export now includes course structure with a regression assertion, and the budget fixture derives only the actual public field descriptors from its saved case. Earlier failures remain separate. The assembled preview also exposed the next UI work: direct assessment access from chat and legacy star/status wording in outcome modules.

**Evidence:** `artifacts/visual-review/certification-full-course-preview-2026-10-07/{package-complete,normal-all,native-all,final-assembly-tests.xml,ruff-final.log,checkpoint.json}`. Manifest SHA-256: `325d8dfffffc33f7de524e615d3fadb6ea2d8ec5449a341a77608ad133c2d13a`. Captures use checkpoint 168's built UI. No final-credit integration, live calibration, real learner change, migration or publication is claimed.


### Checkpoint 170 Direct chat entry to the assigned assessment on October 7 2026

**Status:** Complete for module-card assessment handoff. Counts remain 20/162 accepted and 142 open; broader route-equivalence, stale-card and assessment-validity gates remain open.

Current outcome-based module cards now open the exact module's Challenge panel directly. Enrollment, course version, manifest, module and prerequisites must match the selected course. The provider and panel recheck the destination, which takes priority over an unrelated saved reading position. Repeated requests can refocus the same assessment, while normal curriculum navigation clears the request. Opening focuses Challenge, preserves the unsent chat and does not save a cursor, prepare a lab, call the agent or grade work. New assessment directions can be read before lab preparation; legacy exercise lab gates remain intact.

Historical or unavailable module cards retain their instructions but remove preparation and generic grading actions. A separate enabled recovery action opens the current course; missing course/provider data never falls back to an unbound grading prompt. The first browser pass caught that recovery action inside the historical card's disabled fieldset. Moving it to the card footer fixed actual browser activation, and the regression now explicitly checks it is enabled.

**Verification:** 60 focused frontend cases, targeted ESLint and full TypeScript/production build pass. The test batch also corrected two stale test expectations from the earlier course-aware completion/certificate work and supplied the missing authentication fixture for the new detail-view test; earlier diagnostics remain. Sixty-nine corrected browser captures exercise all eleven module chat entries and matching assessment panels at 320/1440px and native 200% zoom at CSS 390px, with zero provisioned documents. Each respects keyboard entry/focus, preserves an unrelated saved cursor and unsent question, and omits legacy completion controls. Historical recovery works at every width. Certification traffic is GET-only and no assessment-entry action calls chat. Axe, bounds, routes and browser errors pass. Narrow Foundations entry and native Governance chat actions were manually inspected.

**Evidence:** `artifacts/visual-review/certification-assessment-entry-2026-10-07/{normal-corrected,native,tests-corrected.log,lint.log,build-corrected.log,checkpoint.json}`. These use the isolated checkpoint 169 package and synthetic transport; no lab execution, grade, release verification, learner transition or publication is implied. The subsequent combined-outcome source work is not part of these captures.


### Checkpoint 171 Explicit learner selection of combined module outcomes on October 7 2026

**Status:** Complete for the read-only learner-facing selection and combined results. Final credit and release validity remain open. Counts remain 20/162 accepted and 142 open.

Each outcome-based Challenge now offers a collapsed combined-outcome preview. Opening it loads required outcomes and recent original assessment references; it never chooses the newest or best attempt. The learner explicitly selects automatic and/or scenario evidence and checks that selection. Mixed modules retain every missing or failed requirement. Pending and unavailable assessments remain distinct from needed learner revisions. Changing the choice removes the prior summary; closing or changing courses discards late responses. Full references allow older records to be selected when recent discovery fails. No model, assessment retry, staff queue, completion or credit action is triggered.

Responses must match the enrollment/version/manifest, contract, rubric, selected receipt identities, complete required-outcome list and consistent state summary. Incomplete/mismatched/contradictory responses cannot display success. Original saved feedback remains the detailed revision route. Native dropdowns truncated long selected descriptions on narrow screens, so the full descriptions now also wrap beneath each control, including older references.

**Verification:** 32 initial focused component/API cases passed; the final 34-case batch includes readable-selection and overlapping status regressions. TypeScript/production build and targeted ESLint pass after supplying one missing test receipt field. Thirty-six corrected flow captures and 18 additional selected-description captures cover scenario-only, practical-only and mixed modules at 320/1440px and native Chrome 200% zoom at CSS 390px. They exercise no implicit selection, explicit original failure, missing mixed evidence, pending/unavailable results, passing selections, malformed responses and older-reference recovery. Expected synthetic 503 discovery failures are retained in logs; axe, bounds, unexpected routes and page errors pass. Narrow selectors and native wrapped descriptions/results were manually inspected.

Six additional captures at 390/1440px connect the actual frontend to real authenticated HTTP routes and a disposable MongoDB containing original Validation suite, repair, automatic-review and scenario receipts. The selected earlier failed scenario remains failed despite a newer pass; a practical-only choice stays incomplete; explicitly choosing both passing receipts supports all three outcomes. A digest of every collection and all row counts remains identical before/after; the synthetic judge stays at one original call. The API was shut down and database removal verified. Providers and the original judge remain synthetic, so this is persistence/integration evidence, not live calibration.

**Evidence:** `artifacts/visual-review/certification-outcome-selection-2026-10-07/{selection-readable,selection-readable-native,labels,labels-native,connected,tests-readable-selection.log,build-readable-selection.log,lint-readable-selection.log,ruff.log,cleanup.json,checkpoint.json}`. Connected captures preceded the descriptive-label-only fix; final synthetic captures verify that wrapping change. The later build also contains checkpoint 172 status presentation. No registry, real learner, credential, publication or migration changed.


### Checkpoint 172 Truthful status for outcome-based modules on October 7 2026

**Status:** Complete for the affected curriculum cards and module header. Counts remain 20/162 accepted and 142 open; overall progression/XP policy, status coverage and regrading remain open.

The assembled draft used new required-outcome assessments but still showed three empty stars on every curriculum card and in the detail header. The header also called an incomplete challenge “Not started” even when saved assessment work existed. Outcome modules now show “Required outcomes” on their cards and “Module: Not complete” until actual completion is recorded. Their detail headers omit the inapplicable legacy star display. Legacy modules keep their original stars and completion presentation; earned progress is untouched. Card footers wrap rather than forcing outcome labels and metadata into one row. No new credit rule is established by this display change.

**Verification:** 36 focused module/journey/selection/panel tests, targeted lint and the full production build pass. Seventy-eight final captures inspect all eleven outcome module status/assessment entries and the first/final curriculum cards at 320/1440px and native 200% zoom at CSS 390px. Separate synthetic legacy cards/details retain 2-of-3-star accessible labels and completed status. Every outcome module omits the three-star count and inaccurate Not started label; axe, bounds, routes and page errors pass, with GET-only certification traffic. The changed narrow/native status was manually inspected. Earlier entry captures did not bring the changed footer into view; the final batch targets those labels explicitly. An initial capture selector used a shortened Governance title and timed out; it was corrected to the actual authored title without changing the application.

**Evidence:** `artifacts/visual-review/certification-outcome-status-2026-10-07/{visible-final,visible-final-native,tests.log,build.log,lint.log,checkpoint.json}`. Final captures use the subsequent readable-selection build recorded in checkpoint 171. Draft transport and the legacy completion are synthetic. No earned XP, star history, requirements, course publication, migration or grading changed.


### Checkpoint 173 Preserve explicit evidence selections across completion retries on October 7 2026

**Status:** Complete for the internal journal and recovery boundary. HTTP completion selection, the new rubric runner and earned credit remain separate unfinished work. Counts remain 20/162 accepted and 142 open.

A completion journal can now retain the exact explicitly requested automatic-review/scenario references as canonical JSON with its own digest. These are requested inputs, not claims that the evidence is valid or passing; the future rubric must still authenticate and assess them. The full insertion intent includes this selection before journal insertion, so interrupted-write recovery can preserve it. A repeated request cannot replace its selected evidence in evaluating, graded, applied, rejected or failed states. Retrying the original request without resending references retains the original selection. Empty, malformed, inferred/latest/best inputs and verdict fields are rejected. The preserved legacy rubric rejects competency-selection inputs; historical journals without the new fields still replay.

Recovery validates the original selection digest before materializing a seed or reconciling a saved journal. Corruption does not turn into a completed result. This adds no new assessment call, model dispatch, public endpoint, publication or credit path.

**Verification:** 83 real-MongoDB selection/completion/recovery cases and 28 catalog/history unit cases pass. Coverage includes actual saved scenario references, caller-object mutation after insertion, original recovery seeds, all five journal states, wrong owner/module, malformed selections, corrupted selection bytes, legacy records without new fields and explicit interrupted-attempt recovery. Existing duplicate-credit, delayed-worker and recovery cases remain green. Ruff passes. All databases are disposable and removed by their fixtures.

**Evidence:** `artifacts/visual-review/certification-completion-selection-2026-10-07/{final-persistence.xml,unit.xml,ruff-final.log,checkpoint.json}`. Later outcome-runner source work is not verified by these results. No real course registry, learner record, issued credential or deployed behavior changed.


### Checkpoint 174 Gated validation of selected competency outcomes on October 7 2026

**Status:** Complete for the new rubric runner's validation boundary. Completion API/journal integration and competency credential evidence remain unfinished. Counts remain 20/162 accepted and 142 open; all 33 mechanisms still have zero release-verified status.

The outcome runner validates the explicitly selected original receipts against every required module outcome. It never chooses a latest/best receipt, reruns an assessment or writes credit. Partial selections and saved failed outcomes cannot pass; saved execution/source vetoes survive a synthetic model's supported verdict. Missing/foreign receipts return a controlled selection error. Pending or unavailable grading is a technical condition, not a failed learner judgment. Successful validation carries the exact original outcome snapshot, selected record/result digests and a snapshot digest for the completion journal. Any prerequisite must already be complete in the same enrollment.

Loading this runner requires a release-candidate contract, exact installed rubric bytes pinned by the course, one completion threshold and zero legacy star enrichment. Normal grading additionally requires a supported published course. The assembled preview still contains its deliberately unavailable placeholder rubric and remains non-enrollable; its design contract and all draft assets remain unverified. Existing synthetic scenario packages containing old rubric bytes still cannot run competency credit. The preserved legacy runner is unchanged and rejects competency receipt selections.

**Verification:** 63 unit/catalog/lifecycle cases, three actual saved-receipt MongoDB cases and three original unsupported-package regressions pass; Ruff passes. Unit cases cover incomplete/changed outcome sets, wrong selected references, altered enrollment/contract/manifest, contradictory summaries, missing original receipts/results, prerequisite credit, technical states, unverified contracts, changed runner bytes and incompatible star policy. Integration fixtures install the exact runner in their copied synthetic package before enrollment/evidence creation, then save original suite runs, repairs, automatic feedback and failed/passing scenario receipts. Validation preserves original failures and deterministic execution vetoes, changes no progress or saved receipt and leaves the synthetic judge at one original call. The fixture's verified/published metadata is synthetic test setup, not calibration evidence or a release claim.

**Evidence:** `artifacts/visual-review/certification-outcome-rubric-2026-10-07/{unit-final.xml,persistence.xml,unsupported-package.xml,ruff-final.log,checkpoint.json}`. Two existing fixture assertions were updated from the generic unsupported-runner message to the stricter pinned-rubric mismatch. The actual application registry hash remains `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`. No actual course publication, new learner credit, credential, live model or migration occurred.


### Checkpoint 175 Selected-outcome completion and frozen competency credentials on October 7 2026

**Status:** Complete for authenticated completion and credential persistence. Learner completion controls and release verification remain unfinished. Counts remain 20/162 accepted and 142 open; zero mechanisms are release-verified.

The existing completion endpoint accepts explicitly consented automatic-review/scenario references only with an explicit request identity. The journal saves those inputs before grading and retries use the original selection. Passing every required outcome earns the module base XP once; partial or failed evidence earns none. Credit freezes the original validation, selection and digests. Credential preparation requires complete supported outcome evidence for every required module and retains the original outcome snapshots and selected receipt digests. Legacy issuance remains unchanged. Course levels for the new runner now come from its pinned course structure; the first connected completion test exposed an obsolete dependency on legacy rubric constants.

**Verification:** 51 unit/catalog/credential cases, seven authenticated real-MongoDB completion/graduation cases, 18 selection-journal cases and 57 legacy completion/credential/recovery regressions pass; targeted Ruff passes. Coverage includes incomplete and deterministically invalid evidence, explicit consent/authentication, duplicate and changed-selection requests, exact bodyless replay, all 33 outcomes in a synthetic full-course credential, and actual one-module graduation from saved suite/repair/review/scenario receipts. Interrupted credential persistence recovers the original frozen payload without regrading; repeated graduation creates neither extra XP nor a second credential. Full-course credential inputs and published course metadata are synthetic test fixtures; the saved-receipt graduation course intentionally contains one module and three outcomes. These checks do not establish live grading validity or full-course learner completion.

**Evidence:** `artifacts/visual-review/certification-outcome-completion-2026-10-07/{unit.xml,http-selection.xml,graduation.xml,legacy-regression.xml,checkpoint.json}`. The HTTP-selection batch contains the earlier five completion cases plus 18 journal cases; the seven-case graduation batch supersedes those five. Actual application registry remains unchanged at `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`. No real learner, publication, production credential, staff queue or migration changed.


### Checkpoint 176 Gated learner completion and original-request recovery on October 7 2026

**Status:** Complete for explicit learner completion and retry against a supported synthetic course. Counts remain 20/162 accepted and 142 open; release validity and course-transition gates remain unfinished.

Course delivery advertises selected-outcome completion only for supported published/retired requirements with the exact verified runner. Draft previews remain read-only. After explicitly checking a complete passing evidence selection, the learner can separately complete the module. Missing or failed outcomes cannot enable that control. Completion stores both the request identity and original selected references before dispatch, including when a request never arrives at the server. Reloads and retries retain those references; newer work cannot silently replace an uncertain selection. In-flight dispatch is deduplicated. Definite assessment failure ends that request; uncertain or mismatched responses preserve it. A confirmed write followed by a failed progress read asks for refresh and blocks another completion. Outcome-based celebration omits the legacy three-star display and retains the pinned level name.

**Verification:** 64 focused frontend tests, 40 backend runner/credential/capability cases, seven authenticated MongoDB completion cases, targeted lint/Ruff and the full production build pass. Seventeen connected browser captures cover 320px, desktop certificate state and native Chrome 200% zoom at CSS 390px. A synthetic one-module course uses actual saved suite, repair, review and scenario receipts. The original failed scenario disables completion. A dropped request survives reload with no earned credit; a dropped response after real persistence survives another reload and replays the same request/body. Each fresh database has one completion journal, one credential and one base-XP award; the original synthetic judge remains at one call. Narrow and native completion controls and graduation were manually inspected; axe, bounds, routes and page errors pass. Both disposable databases were removed and removal verified.

The first browser diagnostic used a harness that cleared session storage on every navigation. It was stopped and corrected to preserve normal reload state; final captures use the corrected harness. Initial TypeScript errors were confined to new test assertions and were fixed. The final refresh-failure guard has unit/build evidence and was added after the connected captures. Notification delivery is outside this evidence: the initial isolated browser fixtures had no Notification collection or synthetic learner User record; future completion fixtures explicitly stub the notification hook. Existing course-aware notification and per-credential delivery work remains open. No live model, real learner, release, migration or external communication was involved.

**Evidence:** `artifacts/visual-review/certification-selected-completion-ui-2026-10-07/{connected-corrected,connected-native,frontend-refresh-guard.log,capability-unit.xml,capability-http.xml,build-refresh-guard.log,lint-refresh-guard.log,cleanup.json,checkpoint.json}`. Application registry is unchanged. These connected captures establish a three-outcome module's delivery and persistence, not full-course calibration or graduation from all 33 outcomes.


### Checkpoint 177 Per-record preservation proposals for optional upgrades on October 7 2026

**Status:** Complete for the read-only preservation plan. Activation, accepted decisions and rollback remain unfinished. Counts remain 20/162 accepted and 142 open.

The consistent transition inventory now assigns every saved completion, lab input, scenario, lab run, automatic assessment, workflow approval, process design and learner decision an explicit proposed disposition under its original enrollment. Prepared executions and unassessed packets remain distinguishable from original results. Evaluating completions/reviews, graded-but-unconfirmed completions and executing/uncertain runs require reconciliation. Unknown operation states fail closed. The plan does not establish receipt validity, transfer credit, approve execution or authorize a switch; activation remains unavailable.

Learners can expand the plan to read preservation instructions and original references. A saved uncertain run remains visible as unresolved even when the write boundary has already ended and the older work-in-flight flag is false. Module names come from the source course. Content, answers, provider settings and outputs are excluded. The UI rejects a foreign or contradictory plan, preserves the current course and restores keyboard focus when closing.

**Verification:** 15 policy tests, 27 real-MongoDB transition/comparison/race cases, 13 frontend cases, full production build and targeted lint/Ruff pass. Metadata fixtures explicitly test preservation planning, not graded-receipt authenticity. Concurrent changes to operation state or saved-result/event digests invalidate the original preview. Twelve final synthetic browser captures pass at 320/1440px and native 200% zoom at CSS 390px, with keyboard disclosure, readable reference wrapping, zero certification writes and no axe/bounds/route/page errors. Narrow unresolved-work and native reference states were manually inspected. Initial browser passes failed because the test used a fully scoped locator inside a relative filter; using the observed disclosure parent corrected the harness without an application change.

**Evidence:** `artifacts/visual-review/certification-transition-preservation-2026-10-07/{unit.xml,persistence.xml,frontend.log,build.log,ruff.log,lint.log,normal-corrected,native-corrected,checkpoint.json}`. No real learner, publication, credential, staff queue, migration or external communication changed. The proposed plan still needs durable explicit acceptance, complete external-job reconciliation, activation and rollback verification before a learner may switch.


### Checkpoint 178 Durable exact preservation-choice receipts on October 7 2026

**Status:** Complete for the internal consent record. No acceptance/activation endpoint or rollback is exposed. Counts remain 20/162 accepted and 142 open.

A new insert-only owned record preserves an explicit request identity, exact preview and preservation plan, original source snapshot, offered target requirements, consent and original acceptance time. Recording the choice does not create/select an enrollment, transfer credit or lock future learner work. Replays return the original choice rather than renewing consent against newer work. Every receipt explicitly requires a fresh activation check. A future switch must revalidate that snapshot under the enrollment write boundary.

Fresh consent rejects changed work, withdrawn offers, unsupported grading targets, other learners' selections, uncertain/executing work, unfinished completions and unpreserved credentials. A new reviewed choice has a new request; it cannot overwrite an earlier receipt. The model is registered for initialization and included in owned account deletion. The internal API has no staff queue or provider calls.

**Verification:** Fifteen real-MongoDB decision cases plus eight related preservation/completion cases pass, along with twelve existing database-registration/account-deletion-summary cases and targeted Ruff. Six concurrent identical requests preserve one original receipt. Lost insertion responses recover the same acceptance time and content even after later progress; the receipt still requires fresh activation validation. Cross-user access, request rebinding, malformed consent, extra credit claims, corrupted records, changed/withdrawn targets, incomplete preservation and active writes fail without new consent. Later reviewed choices preserve earlier history and original saved work. The complete source enrollment, selection and progress are unchanged by acceptance. Source receipt fixtures and published/verified target flags remain synthetic; this is persistence evidence, not external-job reconciliation or release verification. Completion regression fixtures now explicitly stub notification hooks.

**Evidence:** `artifacts/visual-review/certification-upgrade-decision-2026-10-07/{final-persistence.xml,registration.xml,ruff.log,checkpoint.json}`. The earlier twelve-case persistence report is superseded by the expanded fifteen-case decision batch. No real learner, production decision, course publication, migration, external message or credential changed.


### Checkpoint 179 Revalidate accepted work while holding the source write boundary on October 7 2026

**Status:** Complete for the internal held-choice boundary. Target staging, external-job reconciliation, activation and rollback remain unfinished. Counts remain 20/162 accepted and 142 open.

An owned saved choice can now be revalidated while the source enrollment's existing database write lock excludes competing certification writes. The original source work, selection revision, target manifest and credential must still match a separate stable decision fingerprint. The ordinary preview still compares complete write fences to detect races; only a verified matching lease can normalize its own guard for the internal comparison. Guard acquisition/release alone does not expire consent. Changed XP, reading state, saved inputs/runs, selection revision, target requirements or credentials do. Revalidation preserves the original consent record and performs no selection or credit change.

The offered target must still support the exact outcome runner, and its offer is checked again after inventory assembly. Revoked ownership, foreign choice references, unknown guards and withdrawn offers cannot enter the caller's protected section. This boundary is one prerequisite for a future recoverable switch; it is not authorization to skip unresolved external effects or activation journaling.

**Verification:** 26 real-MongoDB boundary/decision/preservation cases and 26 existing read-only preview/concurrent-update regressions pass; targeted Ruff and whitespace checks pass. Cases include repeated clean locks, blocked competing writes, later saved work, changed navigation/selection/XP, revoked progress fences, normalization without ownership, withdrawal before or during revalidation and unchanged original consent. No browser surface changed.

**Evidence:** `artifacts/visual-review/certification-upgrade-boundary-2026-10-07/{persistence.xml,preview-regression.xml,ruff.log,checkpoint.json}`. The stable fingerprint is internal and does not expose source content. All course flags and learners are synthetic; no production decision, enrollment activation, publication, external message or migration occurred.


### Checkpoint 180 Restartable target preparation without selecting it on October 7 2026

**Status:** Complete for internal target staging. Source-work reconciliation, selection commit, rollback and public transition delivery remain unfinished. Counts remain 20/162 accepted and 142 open.

Target enrollment/progress identities derive from the accepted choice. Preparation revalidates and holds the original source boundary, inserts missing records only, and retains the source selection. The target starts with zero XP, no completed modules, no reading/assessment/lab state and its pinned zero-XP level. Old XP and stars remain with the original course. Invalid, duplicate, unordered or unreachable target level thresholds block preparation. This does not finalize the overall progression policy.

Interruptions before or after enrollment/progress insertion resume the same target. Existing target credit, navigation, override or lab state is never reset. Foreign progress collisions, mismatched target identity and revoked source ownership fail closed. An unselected target cannot accept certification writes. Preparation remains internal; it cannot activate a course or authorize a later switch without fresh checks.

**Verification:** Ten target-staging persistence cases, ten held-choice regressions and ten progression unit cases pass; targeted Ruff passes. The source fixture includes original earned XP, stars and a completion date, all preserved byte-for-byte apart from its ownership fence. Three interrupted insertion phases resume without extra enrollments/progress. Existing target work and foreign progress survive rejected retries. All MongoDB data and course release flags are synthetic.

**Evidence:** `artifacts/visual-review/certification-upgrade-target-2026-10-07/{final.xml,ruff.log,checkpoint.json}`. Earlier ten-case staging diagnostics are superseded by the strengthened earned-source fixture and combined thirty-case batch. No actual learner, enrollment selection, course publication, credit transfer, external message or migration changed.


### Checkpoint 181 Preserve terminal completion and recovery history on October 7 2026

**Status:** Complete for preservation inventory and consent invalidation. Exact receipt integrity and activation remain unfinished. Counts remain 20/162 accepted and 142 open.

The preservation plan now includes applied, rejected and failed completion results plus completed recovery records. A started recovery requires reconciliation even when no write is currently running. Terminal receipt and recovery digests participate in both preview consistency checks and the stable accepted-choice fingerprint. New or changed history therefore requires a new reviewed choice; rotating the write guard alone still does not. Original choices and history remain unchanged. Public summaries exclude raw answers, judgments, recovery reasons and operator identity.

**Verification:** 51 targeted real-MongoDB and policy cases pass; Ruff passes. Eight new cases cover all terminal completion states, completed/started recovery, new history after consent, result changes during preview without a progress write, foreign ownership and byte-preserved source data. These metadata fixtures verify preservation and concurrency, not semantic receipt authenticity. Existing target staging and held-choice regressions remain green. No frontend source changed; the existing generic preservation list supports both added kinds.

**Evidence:** `artifacts/visual-review/certification-transition-history-2026-10-07/{tests.xml,ruff.log,checkpoint.json}`. No real enrollment, publication, migration, credit or external communication changed.


### Checkpoint 182 Verify original saved records before target preparation on October 7 2026

**Status:** Complete for source-record integrity under a held enrollment boundary. External workspace-job reconciliation, selection commit and rollback remain unfinished. Counts remain 20/162 accepted and 142 open.

A new read-only verifier checks all nine certification record collections against their original learner, enrollment and pinned package. It dispatches module-specific input, plan and learner-decision validators; checks saved automatic/scenario feedback semantics; verifies terminal completion/recovery envelopes; and requires each run's original input record and digest. Prepared work stays unexecuted. Running/uncertain runs, evaluating reviews and unfinished completion/recovery records block preparation. Original failed results remain failed. Unknown or inconsistent records do not receive a verified preservation snapshot.

The verifier compares complete stored bytes across two reads, then rechecks both selection ownership and the progress fence. Its response contains counts and digests, excluding answers, outputs and operator details. Target staging now requires this check; a metadata-only accepted choice cannot bypass damaged original receipts. This does not reconcile generic workspace workers or authorize activation. No grading, provider dispatch, retry, cancellation, credit transfer or history mutation occurs.

**Verification:** 35 persistence cases pass across the final 32-case reconciliation/staging batch and three additional focused cases. Coverage uses actual saved records for Foundations, Extraction, process/workflow design, Multi-Step, Advanced Nodes, Output, Validation, Batch and Governance, plus original failed/passing scenarios, completion and completed recovery. Private handoff checks retain both failed and delivered learner-only copies. Tampered bytes, rehashed contradictory feedback, orphaned inputs, changed inventory, foreign records and revoked selection/progress guards fail closed. Original records and earned progress remain unchanged; synthetic provider/judge call counts do not increase. Ruff passes.

The initial Advanced Nodes diagnostic exposed a dispatch omission in the new verifier: source calculations share the input collection with workflow captures. Each now uses its own validator. A separate test fixture unpacking error was corrected. These failures and corrected results are retained as evidence.

**Evidence:** `artifacts/visual-review/certification-transition-records-2026-10-07/{final.xml,remaining-fixed.xml,ruff-final.log,checkpoint.json}`. No actual learner, publication, enrollment selection, migration, credit or external communication changed.


### Checkpoint 183 Credential-specific completion notices and mobile notification repair on October 7 2026

**Status:** Complete for versioned completion-message persistence, mocked email boundaries and browser rendering/navigation. Cohort messaging, actual email delivery/client compatibility and release verification remain open. Counts remain 20/162 accepted and 142 open.

Versioned completion now freezes its message from the immutable issued credential: original learner name, course title/version, module count and issue date. It does not claim a fixed 11 modules, 1,600 XP or endorsement of every published workflow. A deterministic insert-only notification reference prevents duplicate notices on concurrent or interrupted retries, including after reading or deleting a confirmed notice. Completion retries recover a missing notice without regrading or adding credit. Preserving historical unknown-version credentials does not announce a new graduation. Unversioned legacy hooks remain unchanged.

Each issuance has a separate durable email state, so a legacy once-per-user flag cannot suppress a later earned credential. Sending respects the deployment email switch and announcement opt-out. An issuance gets at most one automatic provider attempt; a negative/missing acknowledgement or interrupted claim remains uncertain/sending and is not blindly retried. This favors avoiding duplicate messages over guaranteed email delivery. The in-app notice and credential remain available without a routine staff queue. No external message was sent during implementation or QA; every new transport test uses a mock. The new collection participates in database initialization and account deletion.

Visual QA reproduced a notification dropdown extending 109px off the left edge at 320px. The dropdown now anchors within the viewport and responds to resizing/scrolling. Certification messages wrap and retain their complete version/date; read notifications retain accessible contrast instead of reduced parent opacity. The trigger exposes its expanded state; Escape restores focus. Email rendering escapes original names/course text, wraps long versions, keeps a reachable certificate-history link and includes preference access.

**Verification:** 19 completion/notice persistence cases pass, with two focused final replay checks; 11 database/deletion/legacy-hook cases and seven frontend notification/certificate-history tests pass. Ruff, targeted lint and the production build pass. Eighteen final browser captures cover single/full/long email copy and unread/read notifications plus original certificate history at 320/1440px and native Chrome 200% zoom at CSS 390px. Bounds, axe, keyboard dismissal, routes and browser errors pass. Narrow email/dropdown and native read-state screenshots were manually inspected. A completed one-module synthetic course recovers a failed notification write on the same completion request, with unchanged XP and one original synthetic judge call.

**Evidence:** `artifacts/visual-review/certification-completion-notices-2026-10-07/{final.xml,replay-final.xml,unit.xml,frontend.log,build-final.log,ruff-final.log,lint-final.log,browser,browser-native,inapp-final,inapp-native-final,checkpoint.json}`. The initial offscreen capture is retained. Browser fixtures do not establish email-client support, actual email delivery or live grading. The real course registry remains unchanged at `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`; no real learner, migration, publication or external communication changed.


### Checkpoint 184 Restartable internal optional selection commit on October 7 2026

**Status:** Complete for the internal zero-credit selection journal and synthetic preservation rehearsal. Public activation, rollback/resume, actual cohort reconciliation and release remain unfinished. Counts remain 20/162 accepted and 142 open. The public comparison continues to advertise activation unavailable.

Activation requires a separate explicit request after an accepted preservation choice. It freshly revalidates that choice under the source guard, verifies all saved certification records, stages the same blank target, and persists an immutable activation intent. Immediately before selection it rechecks the offered executable course and both staged target fingerprints. The source write fence is revoked before the new selection becomes visible. The selection CAS retains its exact receipt and a pending-confirmation marker; new certification writes and subsequent switches stay blocked until the original journal receipt is confirmed. A lost response resumes the original request without regrading, resetting target work or selecting twice.

The operation changes selection only. Original enrollments, credit, reflections, reading position, credentials, lab-folder/document references and saved practical results stay in place. Independent workspace jobs retain their existing identities; this path does not dispatch, retry, cancel, move or rewrite them. Code review found no certification/enrollment coupling in the inspected generic workflow/document execution paths. Synthetic in-flight workspace records remain unchanged across selection and can finish against the same references. This is an identity-preservation policy and scoped rehearsal, not proof that arbitrary external deliveries have completed or broad live-worker integration evidence.

**Verification:** 37 activation/staging/held-choice cases, 43 existing enrollment/fence/recovery regressions and 12 registration/account-deletion cases pass; Ruff passes. Seventeen activation cases cover original earned credit and historical credentials, actual one-module competency graduation with saved practical receipts, interruptions after intent insertion/before selection/after selection/after journal persistence/before marker cleanup, concurrent requests, target mutation, offer withdrawal, revoked source fence, changed revision, foreign/rebound requests and a rehashed contradictory selection receipt. Existing target work survives replay; pending/corrupt receipts cannot unlock writes. The one-module synthetic judge stays at its original single call and no second credential is issued by selection. An initial withdrawn-offer test omitted its existing controlled exception type; that assertion was corrected without changing the rejection behavior.

**Evidence:** `artifacts/visual-review/certification-upgrade-activation-2026-10-07/{final.xml,boundary-regression.xml,registration.xml,ruff.log,checkpoint.json}`. All learners, offers, release flags and workspace workers are synthetic/disposable. No real enrollment selection, publication, migration or external communication occurred. No frontend activation endpoint/control was added.


### Checkpoint 185 Return to and resume preserved courses on October 7 2026

**Status:** Complete for internal reviewed course selection and synthetic rollback/resume preservation. Public delivery and actual cohort reconciliation remain open. Counts remain 20/162 accepted and 142 open.

A learner can review the two enrollments from their original applied upgrade, then explicitly return to the original course or resume the same saved upgrade. Both full record inventories, earned credit, credentials, reading places and destination support are checked twice and again under the source write boundary immediately before selection. Changed work or support requires a fresh review. Selection uses a durable original intent and receipt, with the same pending-confirmation protection as initial activation. Historical request replay returns its original result without selecting again. Nothing is copied, reset, reassessed or reissued.

**Verification:** 60 saved-selection, activation and record-integrity persistence cases pass, plus two focused final legacy/ownership cases and 12 registration/account-deletion cases; Ruff passes. Eighteen return/resume cases cover original and newly earned credentials, all five interrupted-write phases, concurrent choices, both courses changing, unsupported destinations, pending assessment/credential work, foreign or rebound requests, actual saved one-module practical graduation and unknown legacy origin/date. The full-new-credential cohort uses seeded synthetic credit solely to prove preservation; it does not establish actual full-course grading. The actual one-module graduation keeps its original saved receipt bytes and one synthetic judge call. Both enrollment histories remain unchanged apart from ownership fences.

The selection journal implementation is shared with initial activation and rechecked by its original activation suite. Pure saved-record verification is shared by guarded initial preparation and both-course return/resume review. No HTTP activation or return/resume control is exposed yet.

**Evidence:** `artifacts/visual-review/certification-saved-course-selection-2026-10-07/{final.xml,legacy-final.xml,registration.xml,ruff-final.log,checkpoint.json}`. No real learner, publication, migration, earned credit or external communication changed.


### Checkpoint 186 Learner recovery of a committed course choice on October 7 2026

**Status:** Complete for learner-owned status and confirmation delivery, including the actual agentic-chat certification panel. Starting an upgrade or return/resume remains internal; pre-commit interrupted preparation and the full public choice flow remain open. Counts remain 20/162 accepted and 142 open.

Authenticated status reads discover the learner's exact pending selection from its original journal, including from another device without browser storage. Reading does not initialize an enrollment or repair a record. The separate explicit confirmation request can finalize only an already committed selection, never create or choose a target. It stays available when new versioned delivery is disabled. Original receipt IDs and hashes are checked; foreign, malformed, changed or uncommitted receipts cannot unlock work. Replaying an old confirmation cannot reselect a course or clear a later switch/worker. Responses omit saved answers and private grading payloads.

The panel and certification page show the saved upgrade/return/resume and preserve a clear confirmation action. Uncertain responses require a fresh read before another explicit confirmation; no automatic POST retry occurs. A reload discovers the original saved choice. After confirmation, a separate course refresh loads the current selection without assuming an old receipt is still active. Controls wrap at narrow widths and retain keyboard focus after replies. No routine staff task is introduced. Corrupt or unrelated operations remain protected instead of being silently cleared.

**Verification:** 49 selection-delivery/activation/return persistence checks pass, followed by 22 strengthened delivery checks spanning both pre- and post-journal interruption states. Thirty-one frontend checks, production build, targeted lint and Ruff pass. Twenty connected Chrome captures cover actual HTTP/MongoDB recovery at 320/1440px and native 200% zoom (CSS 390px), including an undelivered request, lost successful response, component reload, read-only reconciliation, return and resume. Axe, bounds, browser errors, request allowlists and exact original request identity pass. Original history hashes, XP and credential counts remain unchanged. Narrow, desktop and native screenshots were manually inspected.

An initial stricter pending-marker comparison exposed MongoDB's order-sensitive embedded-document equality after canonical JSON replay. The final implementation compares receipt values, then conditionally clears the exact document read from MongoDB, while preserving worker and selection guards. Both interrupted-journal cases pass. An initial browser capture raced the course's initial load; the harness now waits for the loaded course before inspecting recovery. Earlier failures are retained.

**Evidence:** `artifacts/visual-review/certification-selection-recovery-2026-10-07/{final.xml,delivery-final.xml,frontend.log,build-final.log,lint-final.log,ruff-final.log,browser-final,browser-native,checkpoint.json}`. Browser servers and synthetic databases were removed. No actual learner, new release, migration, provider call or external message changed.


### Checkpoint 187 Stop uncommitted selection preparation without staff recovery on October 7 2026

**Status:** Complete for the internal recovery journal and actual paused-worker concurrency rehearsal. Learner delivery is in progress. Counts remain 20/162 accepted and 142 open.

Initial activation and saved-course return/resume now persist their exact typed selection request in the original source write marker before preparation begins. A separately reviewed recovery can claim only these two operations. It validates the owned original choice, enrollment, progress identity and allowed fence states; generic assessment/review/workspace operations are excluded. It claims the selection marker before fencing the source, so a late original worker cannot commit, reacquire its old fence or clear a newer worker. Recovery commits its immutable result before releasing the marker. Both the recovery and original selection request are restartable without resetting work, credit or target staging.

**Verification:** 88 combined preparation-recovery, activation, return/resume, held-choice and committed-confirmation cases pass, including 21 new recovery cases; 12 registration/account-deletion cases and Ruff pass. Actual running tasks pause before progress acquisition, after intent persistence and after source-fence closure immediately before selection CAS. Tests resume the old task while a new ordinary write holds the course: it fails without changing or unlocking that worker. Five recovery interruptions resume the same journal; a winning original selection stays selected. Competing recovery requests, foreign/rebound/stale requests, rehashed substitution of another owned progress record, changed fences and old receipt replay cannot release unrelated work. Both original and newly earned credentials remain intact.

**Evidence:** `artifacts/visual-review/certification-preparation-recovery-2026-10-07/{final.xml,registration.xml,ruff-final.log,checkpoint.json}`. The earlier 18-case diagnostic is superseded by the strengthened 88-case batch. All accounts, release flags and workers are disposable. No actual enrollment, publication, credit or external communication changed.


### Checkpoint 188 Learner delivery for interrupted preparation on October 7 2026

**Status:** Complete for the owner-only preparation status/stop path and its agentic-chat panel controls. Public initial upgrade and return/resume choices remain unfinished. Counts at this checkpoint remain 20/162 accepted and 142 open.

Status reads distinguish an uncommitted preparation from an already claimed recovery. The same reviewed snapshot supplies a stable recovery request across devices. After a partial claim, the original journal supplies that request and preview hash; reloading never manufactures a replacement consent or worker identity. Stopping requires separate explicit consent. This endpoint remains available when new versioned delivery is disabled and never initiates an upgrade, assessment or external job.

The learner can wait and refresh, stop preparation to retain the current course, or finish confirming an interrupted stop. Lost replies require GET status reconciliation before another explicit POST. The notice explains retained work, credit and certificates and keeps the current course distinct from a saved-but-committed choice. No routine staff request is required for these supported interruptions.

**Verification:** 28 preparation/committed-selection HTTP and persistence cases, 40 frontend cases, the production build, lint and Ruff pass. Fifteen connected browser captures cover 320/1440px and native 200% zoom at CSS 390px. A genuinely paused synthetic worker is held just before selection CAS. Browser actions lose the first request, interrupt recovery after it claims ownership, reload to discover the original recovery, lose the successful reply and reconcile with a read. Resuming the old worker is rejected; the source selection/revision, full history hash, earned XP and credential remain unchanged. One recovery record survives all retries. Axe, bounds, routes, keyboard action and browser errors pass; narrow and native recovery screenshots were manually inspected.

**Evidence:** `artifacts/visual-review/certification-preparation-delivery-2026-10-07/{http.xml,frontend-final.log,build.log,lint.log,ruff.log,browser,browser-native,checkpoint.json}`. Disposable servers/databases were removed. The actual course registry remains unchanged at `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`. No real learner, publication, migration or external communication changed.


### Checkpoint 189 Migration and rollback rehearsal acceptance on October 7 2026

**Accepted:** C8-MIGRATE-11. **Status:** Complete for the checklist's copied/synthetic-cohort rehearsal requirement. Counts are now 21/162 accepted and 141 open. This accepts rehearsal evidence, not actual cohort inventory, public upgrade delivery, publication, live grading or an 8/10 reassessment.

The acceptance review maps each required cohort and interruption to current persistence evidence:

| Required case | Evidence and result |
| --- | --- |
| Partial modules | Three final cohort tests include original unfinished answers, attempts, reading revision, lab folder/document references and completed module XP. New partial work is added to the upgrade; forward selection, return and resume preserve both histories exactly. |
| Mid-assessment work | The actual attempt journal pins a partial learner's original answers, progress and course artifacts. Both a running write and its unresolved saved assessment block switching without losing the original snapshot or progress. |
| Completed and newly earned credentials | Checkpoints 184–185 and the 187 regression batch preserve original credentials, actual saved one-module graduation and a synthetic full-new-credential cohort through return/resume. The full-cohort seed is preservation evidence, not proof of live full-course grading. |
| Duplicates | Two conflicting legacy progress records retain their exact original bytes and XP on repeated initialization attempts; neither is guessed, merged, reset or selected. |
| Unknown provenance/date | The final legacy case at checkpoint 185 retains legacy-version-unknown enrollment and an unverifiable original credential with no invented version or issue date through upgrade, return and resume. |
| Restart and rollback | Checkpoints 184–188 cover all selection/journal insertion and cleanup phases, concurrent requests, live paused workers, interrupted recovery, lost requests/responses and fresh-device discovery. Stale receipts cannot undo later choices; old workers cannot release new writes. |

**Verification:** The three final cohort cases and Ruff pass. They complete the acceptance matrix alongside the 60-case rollback/integrity batch, final legacy cases, 88-case live-worker regression batch and connected browser evidence in checkpoints 185–188. Counts overlap and are not presented as one summed test total. No production cohort size, policy deadline or earned-outcome equivalence is inferred from these fixtures.

**Evidence:** `artifacts/visual-review/certification-migration-rehearsal-2026-10-07/{cohorts.xml,ruff.log,checkpoint.json}`, together with the specifically scoped checkpoint 185–188 artifacts. The next work is the complete learner choice flow and staged-course lifecycle presentation.


### Checkpoint 190 Distinguish prepared courses from active and retained work on October 7 2026

**Status:** Complete for the prepared-target lifecycle, promotion boundary, history labels and inventory classification. Broader completed/transferred/abandoned lifecycle policy and public upgrade controls remain open. Counts remain 21/162 accepted and 141 open.

Target staging now creates a prepared enrollment. It cannot accept course writes or masquerade as a started course. Activation promotes only the original staged target after both selection and its journal commit, retaining the pending-confirmation guard until promotion succeeds. Interrupted promotion resumes the same target and changes only its lifecycle field; historical replay leaves later selections/enrollment state alone. Changed target identity or incompatible state stays protected. Already-committed internal activation records from the earlier rehearsal retain their supported receipt path; uncommitted targets are not silently reset or adopted.

Owned history independently labels prepared, awaiting confirmation, current and retained courses, without changing selection. History checks selection stability across the read. Prepared-course copy explains that preparation has not started a course or awarded credit. The cohort inventory recognizes valid prepared records and pending confirmation while still flagging prepared work/credentials, invalid provenance or an unguarded read-only selection. Existing achievement remains in its original credential.

**Verification:** The 99-case lifecycle/selection/recovery/cohort batch produced 96 passes and three error-message expectation failures; the prepared-course rejection now explicitly explains that the original switch needs confirmation. A final ten-case history/interruption batch passes, including all three affected cases. Forty-one cohort inventory cases, 36 frontend cases, production build, lint and Ruff pass. Nine connected Chrome captures at 320/1440px and native 200% zoom show prepared history, committed-but-unconfirmed selection, promoted current course and original retained course. Actual MongoDB evidence verifies one target lifecycle change with otherwise unchanged enrollment identity, progress, credential and counts. Axe, bounds and read/write allowlists pass; narrow and native screenshots were inspected. The initial browser run used a label locator that included option text; the final run uses the rendered named combobox role.

**Evidence:** `artifacts/visual-review/certification-prepared-lifecycle-2026-10-07/{initial.xml,history-fixed.xml,inventory.xml,frontend.log,build.log,lint.log,ruff-final.log,browser-final,browser-native,checkpoint.json}`. Initial diagnostics remain retained. Browser fixtures were removed. No actual learner, publication, migration or external communication changed.


### Checkpoint 191 Complete learner-owned optional upgrade, return and resume on October 7 2026

**Accepted:** C8-MIGRATE-05. **Status:** Complete for explicit choice delivery and preservation/recovery of the original request. Counts are now 22/162 accepted and 140 open. This does not publish the draft 5.0 course, establish credit equivalence, verify live grading or authorize actual cohort rollout.

The agentic-chat panel presents the retained source work and newly required outcomes before recording preservation consent. Saving that choice does not switch courses. A separate explicit action selects the prepared target through the verified activation journal. Another device can discover the original saved consent and activation request even after harmless write-guard rotation; immutable consent is never rewritten. Earlier internal choices without the new lookup metadata remain readable without a migration during GET. Source/target identities, manifests, request IDs and receipt proofs must match before the UI offers continuation.

Learners can review and explicitly return to their original course or resume the same upgraded enrollment. Both histories, reading places, original answers, XP and credentials remain separate; an existing started course prevents creating a second enrollment for that version. Reads do not initialize, select or accept anything. Owned decisions, receipts and saved choices remain readable when new versioned delivery is disabled. New writes remain gated. Missing, changed, foreign, unavailable or inconsistent references fail without guessing a target.

Uncertain writes require GET reconciliation before another explicit retry; no automatic POST retry occurs. Historical receipts refresh the currently selected course instead of reselecting their old target. Preparation and confirmation recovery remain available through the existing notice. Explicit course refresh now also reloads selection status when an interrupted preparation left the enrollment unchanged. Toggling consent cannot erase an uncertain saved-course request. Version labels distinguish releases that share a title, and closing a comparison no longer implies that a completed switch was undone.

**Verification:** 57 backend persistence/HTTP/decision/boundary/confirmation cases and 64 frontend cases pass, followed by 28 focused final-copy regressions. Production build, targeted lint and Ruff pass. Nineteen final connected Chrome captures cover 320/1440px and native 200% zoom at CSS 390px. They exercise separate consent/switch actions, lost preservation replies, fresh-page original-choice discovery, an undelivered switch, a lost successful switch reply, return and resume. Original source history hashes remain unchanged; both full histories stay unchanged through return/resume. Each cohort ends with two enrollments, one decision, one activation and two saved-course selections, with no new XP. Axe, bounds, read/write allowlists and page-error checks pass. Final narrow/native screenshots were inspected.

Earlier diagnostics are retained: one frontend assertion needed to await the uncertain response; the browser script initially called an unavailable cleanup helper after all application assertions passed; one later preview reload overlapped a production rebuild. The final runs use the completed build and the established flush/close cleanup. No real learner, provider grading, staff queue, publication, migration or external communication changed.

**Evidence:** `artifacts/visual-review/certification-upgrade-delivery-2026-10-07/{api-verified.xml,frontend-recovery.log,frontend-identity.log,build-identity.log,lint-recovery.log,ruff-final.log,browser-identity-final,browser-identity-native-final,checkpoint.json}`. The actual registry remains unchanged at `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`.


### Checkpoint 192 Enrollment lifecycle policy and completion protection on October 7 2026

**Accepted:** C8-VERSION-03. **Status:** Complete for explicit enrollment identity, lifecycle/selection rules and closed-state protection. Counts are now 23/162 accepted and 139 open. No abandon/restore action, credit-transfer equivalence, support deadline or automatic inactivity change is introduced.

The transition policy now distinguishes prepared, active, completed and closed historical enrollments from which course is currently selected. Optional upgrades preserve the source as active/completed and retained; they do not mark it transferred or abandoned. Prepared targets cannot learn before original activation confirmation. Transferred/abandoned records remain readable but reject ordinary writes and selection as a learning destination. Completion retains the immutable original credential while supported review/improvement follows the original rubric. Publication, inactivity, opening history and closing a panel never change enrollment state.

Credential completion previously set state by user/enrollment alone. It now checks the exact progress, course, manifest and allowed lifecycle before issuance and conditionally marks the same enrollment completed afterward. An intervening closure or identity change cannot be overwritten. If issuance already succeeded, the original credential and pending completion remain preserved for explicit reconciliation rather than losing the record or reopening the course. History separately explains completed and closed courses without implying that retained means incomplete. Empty assessment history no longer implies that a certificate was earned.

**Verification:** Twelve disposable persistence cases pass, including six incompatible-state interruptions before/after issuance, two identity substitutions, original issuance recovery and existing closed-state read/write behavior. Two actual saved-outcome graduation/issuance-recovery cases also pass; these use the established one-module assessment fixture and are not a claim of full live-course graduation. Nineteen frontend cases, production build, lint and Ruff pass. Nine selected presentation captures cover 320/1440px and native 200% zoom; lifecycle labels and current/retained selection remain distinct. History actions issue only GETs; axe, bounds, page errors and unexpected routes pass. Native completed/closed explanations were manually inspected. Earlier native captures precede the final empty-history wording correction and remain as diagnostics.

**Evidence:** `artifacts/visual-review/certification-enrollment-lifecycle-2026-10-07/{lifecycle.xml,graduation.xml,frontend-final.log,build-final.log,lint.log,ruff.log,browser,browser-native-final,checkpoint.json}`. The policy is in `docs/certification-v5-transition-policy.md`; enrollment identity, history and upgrade/rollback evidence additionally remains in checkpoints 184–191. No actual enrollment, release or external communication changed.


### Checkpoint 193 Pin the draft progression and reward policy on October 7 2026

**Status:** Complete for explicit draft policy authoring, integrity checks and learner presentation. C8-DEF-03 remains awaiting complete route/accommodation and release evidence. Counts stay 23/162 accepted and 139 open. This resolves hidden preview defaults as an inspectable design; it does not publish or approve the policy for rollout.

The draft `required-outcomes-flexible-order.1` records a suggested course order with no prerequisite locks, all required outcomes in all eleven modules, 1,850 base XP awarded once, one completion threshold without bonus stars, learner revision with preserved assessment history, automatic-only grading, separate technical recovery and no learner timer/speed criterion. Required errors cannot be compensated by optional work. Equivalent accessible presentation preserves required evidence criteria; unsupported assessment alternatives are not invented. Old immutable packages have no inferred new policy or changed grading requirement. The obsolete commented prerequisite bypass in the unversioned service was replaced with an explanation of preserved legacy behavior; execution behavior is unchanged.

The assembler now pins a separate draft journey definition and policy. Course XP, order, absence of prerequisite locks, star rules, reachable milestone levels and exactly-once journey-group coverage must agree. Changed requirements or unsupported policy values fail verification. An unreviewed design-draft policy cannot pass publication even if outcome readiness flags are changed. Published policy must itself be a release candidate. The inherited intermediate “certified builder” and premature graduation messages are removed from the new draft journey; completion of one group points to the remaining full-course requirements.

The same verified public policy is emitted by course delivery and the isolated assembler, and displayed in an expandable learning/credit explanation in the agentic-chat panel and certification page. The preview clearly states it cannot award credit. Learner text explains studying order, requirements, rewards, revision and technical failures without exposing journal mechanics or internal staffing terminology.

**Verification:** Twenty-six policy/assembly/publication-gate cases pass, followed by 72 combined policy/rubric regressions and 17 actual saved-outcome completion/upgrade-delivery persistence cases. The installed credit runner also checks a present pinned policy. Three earlier rubric tests conflicted with the newly pinned flexible-order/star policy; the generic-runner tests now explicitly use a separate policy-free fixture, while policy-bound contradictions retain their rejection tests. Production build, targeted lint and Ruff pass. Eight final browser captures use the actual assembled draft payload at 320/390/1440px and native 200% zoom. Keyboard expansion/collapse, exact module/outcome/XP totals, draft status, GET-only requests, axe, horizontal bounds, page errors and unexpected routes pass. Narrow policy entry and native recovery guidance were inspected. Earlier captures retain the more technical wording corrected during QA.

**Evidence:** `artifacts/visual-review/certification-progression-policy-2026-10-07/{policy-copy.xml,combined-final.xml,credit-delivery.xml,build.log,lint-final.log,ruff-final.log,package-final,browser-final,browser-native-final,checkpoint.json}`. The new isolated preview is `v5.0-preview-2026-10-07.3`; the report records its manifest and source hashes. It still has 74 lessons, eleven modules, 33 required outcomes, zero release-verified outcomes, a non-executable grading placeholder and no enrollment/default/offers. The application registry is unchanged. No actual learner or external communication changed.


### Checkpoint 194 Administrator progression coherence on October 7 2026

**Status:** Complete for the pinned flexible-order policy in administrator reads, controls and CSV. C8-DEF-03 and reasoned administrative override acceptance remain open. Counts stay 23/162 accepted and 139 open.

Administrator list/detail responses expose the same verified study-order policy as learner course delivery. Flexible-order courses show “Any study order” and explain that every required outcome still applies. They offer no ineffective unlock button. The server rejects both unlock and lock requests before claiming a write or changing progress, selection or fences. Policy-free older packages retain their existing access behavior. The CSV identifies study order and policy and marks unlock as inapplicable. Course-control wording replaces the old debug label and explains that access controls do not complete assessments or award XP.

**Verification:** Four authenticated API/persistence regressions and seven frontend tests pass. Production build, targeted lint and Ruff pass. Six final production-browser captures at 320/1440px and native 200% zoom verify readable course controls, reachable table columns and matching downloaded CSV values. Axe, bounds, page errors and unexpected routes pass, with no browser writes. The final native course-controls screenshot was manually inspected. An initial test fixture failed because one direct repository constructor was not bound to the isolated catalog; that fixture binding is corrected. An initial browser route omitted the auth-config fixture; final runs include it. Earlier diagnostics are retained.

**Evidence:** `artifacts/visual-review/certification-admin-progression-2026-10-07/{http-final.xml,frontend-final.log,build-final.log,lint.log,ruff.log,browser-copy-final,browser-copy-native,checkpoint.json}`. No actual learner, registry, publication, migration or communication changed.

### Checkpoint 195 Cohort communication drafts on October 7 2026

**Accepted:** C8-MIGRATE-12, for prepared cohort copy and credential-specific completion-notification identity. Counts are now 24/162 accepted and 138 open. This is not announcement-sender implementation, actual email delivery verification or rollout authorization.

The transition policy contains separate new, active and graduated learner messages. They explain optional choice, all required new outcomes, original course/XP/credential preservation, separate consent and switching, and returning to saved courses. The drafts require exact approved course/version/outcome/link bindings and reconciled cohorts before use. Unknown history is not invented, no bridge or deadline is announced, and future equivalence changes require revised copy. Announcement delivery remains unimplemented and separate from earned-completion notices.

**Verification:** Copy was checked against the pinned draft policy, the verified optional-choice flow (checkpoint 191), lifecycle rules (192) and completion-notice implementation/evidence (183). Completion notices already use immutable credential identity; a later earned credential is not suppressed by a previous once-per-user flag. Original-notice replay avoids regrading/XP and retains uncertain email delivery without blind repeat sends. No provider/client delivery claim is added. The approved-release, reconciled-recipient and separately authorized-send gates are explicit. No message or recipient list was sent or approved, and no staff grading queue was added.

**Evidence:** `docs/certification-v5-transition-policy.md` under “Cohort communication drafts”; checkpoint 183 and `backend/app/services/certification_versions/completion_notices.py`. All 33 draft mechanisms still await release verification.


### Checkpoint 196 Complete eleven-module credit and credential rehearsal on October 7 2026

**Accepted:** C8-VERSION-07, immutable credential issuance. Counts are now 25/162 accepted and 137 open. The full-course credit integration is verified with saved owned evidence and stubbed providers; this does not satisfy live practical/model calibration, real learner graduation or release acceptance.

A single unchanged assembled course and enrollment now has an end-to-end persistence/API rehearsal covering all eleven modules and all 33 required outcomes. The learner completes modules in reverse suggested order, creating source captures, scope decisions, original/repaired executions, source checks, designs, automatic-review receipts and recognition submissions in that same enrollment. No assessment receipt is transplanted or relabeled, and no credit is seeded. Test workspace helpers now accept an already pinned enrollment so each module can reuse its actual action flow without authoring another course. Foundations uses all five source-bound fields from the actual assembled PDF.

The rehearsal rejects capstone completion without its separate recognition requirement. Each successful module earns only its base XP, earlier completions do not graduate, and the final module issues one immutable credential containing eleven original assessment snapshots and all 33 outcomes. Both normal issuance and interrupted final issuance pass. A fresh repository resumes the original pending credential exactly, with no new assessment/model calls or XP. Replaying every original completion preserves the certificate and all module credit at 1,850 XP. Enrollment lifecycle ends completed.

**Verification:** Two complete-course persistence/API cases pass; 139 fixture/action/notification regressions and 23 outcome-credential, legacy issuance and lifecycle cases pass. Ruff passes. The credential regressions preserve original name/date across pre/post-insert interruption and retain unknown historical provenance without inventing competency outcomes. The earlier successful single full-course case is retained separately; counts are not summed with the final two-case run. No learner UI change required another browser build.

**Evidence:** `artifacts/visual-review/certification-full-course-credit-2026-10-07/{recovery.xml,fixtures.xml,credentials.xml,ruff.log,checkpoint.json}` and `backend/tests/integration/test_certification_full_course_completion.py`; prior issuance/history evidence remains in checkpoints 175, 183 and 192. All databases were disposable and removed by teardown. External completion hooks were disabled in the full-course rehearsal; notification tests use their existing no-external-email fixture. No actual release, enrollment, deployment or message changed.


### Checkpoint 197 Exact-package publication impact preparation on October 7 2026

**Status:** Complete for read-only impact preparation. C8-OPS-02 remains open for publication-gate integration and actual cohort/runtime/release evidence. Counts stay 25/162 accepted and 137 open.

The new inspection command compares verified source/target packages and records exact manifest and registry digests. It lists changed modules, lessons/revisions, outcome definitions and lab assets. Changed lessons retaining an old revision are explicit blockers. Shared exercise, rubric or policy changes conservatively flag every affected target outcome for compatibility review even if outcome wording is unchanged. It never infers credit transfer from matching labels, XP or IDs. Current enrollment, selection, credential, default and notification effects are explicitly zero for the inspection.

Optional aggregate cohort input is validated for complete/nonnegative counts, reconciled totals, metadata digest, double-read provenance and ordered timestamps. Inconsistent/unowned records remain visible; extra payload fields are omitted. Counts are observations, not proof of current membership, credential integrity or migration authorization. Missing input remains unknown. Package readiness flags do not prove live model/tool compatibility or satisfy learner/accessibility/rollout gates. Those remain blocking findings. This report does not yet authorize or wrap publication.

**Verification:** 48 impact/authoring/policy/assembly unit cases pass, followed by 15 impact cases after correcting the pytest fixture import for Ruff. Targeted Ruff passes. The CLI inspected the unchanged actual draft baseline and assembled preview, reported 74 revised lessons and 33 new outcomes with zero transferred credit, and exited 2 with actionable open gates. All changed lessons have advanced revisions. Tests cover malformed inventories, changed lab requirements behind unchanged outcome text, stale lesson revisions, concurrent registry changes and no file mutation. No model, database or external communication was contacted by the inspection.

**Evidence:** `artifacts/visual-review/certification-release-impact-2026-10-07/{final.xml,import-final.xml,ruff-clean.log,draft-impact-final.json,checkpoint.json}`; implementation in `backend/app/services/certification_versions/release_impact.py` and `scripts/inspect_certification_release_impact.py`. Initial diagnostics remain retained. The production registry is unchanged. Follow-up on October 8 adds explicit before/after rubric, star and bonus rules and conservative compatibility review for shared source changes. Seventeen cases and Ruff pass (`source-review-verified.xml`, `ruff-source-verified.log`, `draft-impact-sources.json`). Earlier source-change fixtures were correctly rejected by the catalog because their original case/exercise bindings were stale; the final cases separately verify that rejection and valid new-source review.


### Checkpoint 198 Full-course issued certificate retrieval and rendering on October 8 2026

**Accepted:** C8-VERSION-08, certificate generation from preserved issuance records. Counts are now 26/162 accepted and 136 open. C8-QA-11 remains open for its broader practical-output and release verification scope.

Both complete eleven-module rehearsals now create a long synthetic learner name before actual assessment/credit completion and download the resulting certificate through the authenticated credential endpoint. The PDF contains the recorded name, course/version, original date, eleven-module completion and credential identity. Renaming the profile and making course-catalog loading unavailable leaves the retrieved text unchanged. Foreign access returns 404; unauthenticated access returns 401. The test exports only synthetic certificate evidence when an explicit output directory is supplied.

**Verification:** Two complete-course persistence/API/issuance/download cases pass, covering normal and interrupted issuance. All 33 original assessed outcomes remain in the saved credential. One-page PDFs were rendered with Poppler; normal and recovered renderings are pixel-identical and were visually inspected. The long name wraps cleanly, course/version and footer remain legible, all text bounds stay on the page and no content is clipped or overlapped. Targeted Ruff passes. Historical unknown-date/name preservation additionally remains covered by the 23 credential/lifecycle cases in checkpoint 196 and earlier PDF tests. No certificate renderer change was necessary.

**Evidence:** `artifacts/visual-review/certification-full-course-certificate-2026-10-08/{certificate.xml,certificate-normal.pdf,certificate-recovered.pdf,certificate-normal.png,certificate-recovered.png,certificate-normal.json,certificate-recovered.json,ruff.log,checkpoint.json}`. Certificate names explicitly identify the synthetic QA learner and isolated preview. Models remain stubbed, release flags are isolated fixture metadata, and no real learner or publication changed.


### Checkpoint 199 Comprehensive CI persistence coverage on October 8 2026

**Accepted:** C8-QA-03, durable-state verification with an isolated backend. Counts are now 27/162 accepted and 135 open. This does not satisfy live agent/model calibration, actual cohort rollout, real device/learner observation or final 8/10 grading.

The dedicated CI persistence job previously ran only the original enrollment test file. A deterministic four-shard runner now discovers every certification integration file, rejects incomplete collection, records exact test identities and partitions parameterized cases without duplication or omission. CI gives each group its own MongoDB service, sets a process file limit, allows 45 minutes and preserves JSON/XML reports even on failure. The workflow change is local; no GitHub run, merge or deployment was performed.

**Verification:** All 1,488 cases across 72 files pass with zero failures, errors or skips. Four exact inventories are disjoint and exhaustive and match their JUnit counts (380, 355, 363 and 390). This covers enrollment, saved inputs/answers/positions, every assessment family, concurrency, completion, source preservation, upgrade/return/resume, interruption recovery and immutable credential issuance/retrieval. All 1,168 certification unit/PDF cases, 29 chat-tool contract cases and 461 frontend cases across 41 files also pass. Six shard-partition cases pass; workflow YAML and the independent service matrix were checked. Overlapping earlier checkpoint test counts are not added to these totals.

The first concurrent attempt exhausted the long-lived shared QA MongoDB process's open-file limit (WiredTiger error 24) and was explicitly interrupted. Its diagnostic logs/XML remain separate. The successful replacement used four fresh loopback-only disposable servers with higher process-local limits, one per group. Local verification used MongoDB 8.0.25; the configured CI service remains MongoDB 7.0 and has not run remotely. Every completed test database was dropped. Ports 27030–27032 were verified empty of QA databases and their servers stopped; 27029 remains available for subsequent targeted work. The old 27028 process is stopped. Actual application MongoDB on 27018 is untouched.

**Evidence:** `artifacts/visual-review/certification-persistence-ci-2026-10-08/{isolated-shard-0.xml,isolated-shard-1.xml,isolated-shard-2.xml,isolated-shard-3.xml,units.xml,chat-contracts.xml,frontend.log,unit.log,cleanup.json,checkpoint.json}` and each matching shard JSON/log. The prompt implementation remained unchanged throughout this complete persistence run; the staged coaching correction was applied only afterward and is checked separately at checkpoint 200.


### Checkpoint 200 Version-aware certification help and agent coaching on October 8 2026

**Status:** Complete for version-aware coaching metadata, help and assessment-entry presentation; C8-OPS-08 remains open. Counts remain 27/162 accepted and 135 open. The certification help article incorrectly promised the whole program in chat, fixed XP, no recognition questions and three permanently reflective modules. The article now explains pinned requirements, learner-owned decisions, saved assessments, uncertainty recovery, optional switching and preserved credentials. The user guide removes the unmeasured ten-minute claim and the whole-course-in-chat promise. Presentation pitch copy limits the certificate to its completed course rather than implying institutional compliance or future accuracy. Thirteen existing help tests, targeted Ruff, production frontend build and targeted presentation-content lint pass. The 220-word delivered article is retained in `artifacts/visual-review/certification-help-policy-2026-10-08/delivered-copy.txt`.

The generic agent prompt also contains old module-name routing. A reviewed patch is prepared under `/private/tmp/certification-chat-policy-2026-10-08/` (`llm-service.patch`, `chat-tools.patch`, `tool-results.patch`) and passes `git apply -p0 --check`. It adds explicit module assessment modes and public required-outcome metadata, suppresses legacy reflection keys for competency courses, rejects contradictory response metadata and updates coaching to use the learner-owned panel path. Two staged test files cover all-module pinned read-only routing and malformed/old card compatibility. The patches and staged tests were applied after the complete persistence run finished, preserving its fingerprinted implementation throughout that run. 168 focused prompt/tool/assessment checks pass on disposable MongoDB port 27029, including both full-course completion paths and all eleven module coaching routes for legacy and competency courses. Targeted Ruff passes. The CI inventory now discovers 1,490 cases across 73 files; the two new routing cases passed in this focused batch after the complete 1,488-case run. Live-model behavior still needs the deferred calibration gate.

**Browser verification:** 69 captures across 320/1440px and native 200% zoom cover all eleven assessment-entry cards, keyboard activation and historical-card protection. The fixture now includes the new assessment metadata from the assembled outcome contract. Axe, page bounds, page errors and unexpected requests pass; unsent drafts and saved lesson position remain unchanged, and entry issues no agent call or certification write. Native AI-literacy entry and narrow Governance assessment were manually inspected. Evidence is in `artifacts/visual-review/certification-help-policy-2026-10-08/{routing.xml,routing-ruff.log,browser,browser-native,checkpoint.json}`. A follow-up inspection found remaining legacy-only descriptions on the submission/check/completion tools; these are addressed separately rather than claimed aligned here.


### Checkpoint 201 Connect impact findings to publication on October 8 2026

**Status:** Complete for the local publication refusal boundary. C8-OPS-02 remains open for actual cohort/runtime evidence and the eventual verified release authorization path. Counts remain 27/162 accepted and 135 open.

Authored/outcome courses now require the exact reviewed impact report inside the authoring lock. Publication regenerates the comparison against the current source/target packages, exact registry bytes and supplied aggregate inventory. Stale, malformed, edited and rehashed reports cannot clear findings. The existing frozen continuation-baseline path is preserved. CLI refusal reports actionable reasons and exits 2 without selecting a default or modifying learner data.

The inspector still has no verifier for the deferred live compatibility and rollout evidence. Consequently even synthetically verified course flags remain insufficient to publish a new competency course. There is no force switch or manual flag to clear these checks. This is a refusal safeguard, not a claim that a complete release authorization workflow exists.

**Verification:** 62 impact-gate, report, authoring, progression-policy and preview cases pass; targeted Ruff passes. Tests include both direct authoring and an actual CLI subprocess, changed source/target registry bytes, changed target manifests and cohort metadata, altered findings with recomputed hashes, missing reports and the unchanged legacy baseline lifecycle. Every rejected publication retains exact registry bytes, draft state and no enrollment default. Evidence: `artifacts/visual-review/certification-publication-impact-gate-2026-10-08/{tests.xml,tests.log,ruff.log,checkpoint.json}`. No actual registry, release, enrollment, default or external communication changed.


### Checkpoint 202 Reject obsolete reflection writes for competency courses on October 8 2026

**Status:** Complete for the shared legacy-assessment boundary and tool instructions. Counts remain 27/162 accepted and 135 open; broader messaging alignment remains under C8-OPS-08.

The older reflection tool, HTTP endpoint and service could save self-assessment answers on a selected-outcome course, even though those answers could not earn competency credit. The shared storage service now refuses that obsolete route before changing progress and points the learner to Open module assessment. Normal legacy reflection saving and completion retain their pinned behavior. Tool descriptions for progress, setup, validation, completion and reflection now distinguish legacy assessment from explicit selected saved outcomes, learner-owned decisions and uncertain-result recovery. Module names no longer instruct the agent to choose the reflection route.

**Verification:** 55 targeted checks pass, including all-module read-only metadata, all three reflection modules through service/tool/authenticated HTTP for both course types, and the original complete legacy chat path. A rejected competency submission leaves the complete saved progress unchanged and awards no XP or completion. Existing legacy storage/date and tool contracts pass; targeted Ruff passes. Evidence: `artifacts/visual-review/certification-legacy-assessment-boundary-2026-10-08/{tests.xml,tests.log,ruff.log,checkpoint.json}`. No browser component changed. Live-model behavior remains deferred; no learner, publication or external message changed.


### Checkpoint 203 Correct legacy certification email claims on October 8 2026

**Status:** Complete for the remaining inspected legacy email copy and local certificate-message rendering. C8-OPS-08 remains open for final surface reconciliation; actual provider/client delivery remains a separate verification gate. Counts remain 27/162 accepted and 135 open.

The legacy completion email no longer claims a fixed 1,600 XP, a badge on every published workflow or competence in an unspecified trust stack. It describes the completed course, limits the credential's meaning and explains that an optional course upgrade preserves the original record. The learner name is escaped, long text wraps, and local document language/title, focusable link and footer contrast are accessible. The launch email removes the unmeasured ten-minute certification promise; onboarding points to the selected course's actual requirements rather than promising every module is a short hands-on step.

**Verification:** 43 existing template/engagement/promotional-switch cases pass. The first run exposed an environment-dependent announcement test: its success path inherited promotional email disabled from the QA environment. The two announcement tests now explicitly provide local settings while retaining mocked senders, so they exercise success and opt-out without changing the environment or contacting a provider. Six completion-message captures pass at 320/1440px and native 200% zoom with zero axe violations, overflow, page errors or unexpected requests. The long synthetic name with literal angle brackets/ampersand was visually inspected and remains text. Targeted Ruff passes. Evidence: `artifacts/visual-review/certification-legacy-email-2026-10-08/{tests-final.xml,ruff.log,browser,browser-native,legacy.html,legacy-long.html,launch.html,onboarding.html,checkpoint.json}`. No email was sent.


### Checkpoint 204 Simultaneous completion and original-credit preservation on October 8 2026

**Accepted:** C8-GRADE-06. Counts advance to 28/162 accepted and 134 open. This accepts concurrency/reward integrity, not live grading validity.

Eight new disposable persistence scenarios run two authenticated HTTP clients against the actual completion endpoint with a deterministic overlap inside validation. Same-request and separate-request cases cover new competency completion, first legacy completion, legacy star upgrades and upgrades with an unknown original date. The competing request receives 409 while the first holds the write boundary. After completion, fresh repository/catalog objects replay the original request or return zero extra XP for a separate repeat. A late first response remains the original receipt. Saved totals, maximum stars and original dates remain correct; separate request journals preserve the earlier one-star state and subsequent upgrade result. The competency fixture uses saved real records with a stubbed judge; these tests do not involve a live model or claim actual browser-tab observation.

**Verification:** Eight simultaneous HTTP cases and 29 related interruption/recovery/selection/date checks pass, plus targeted Ruff. Existing frontend evidence in checkpoint 199 includes duplicate dispatch prevention, uncertain-request preservation across remount, obsolete progress-read rejection and a separate refresh failure after confirmed completion. These frontend cases complement the two-client server overlap rather than claiming UI mocks prove atomic storage. Full-course replay/issuance remains covered at checkpoints 196–200. The first new test run used the public payload's `xp` field name instead of the manifest's `base_xp`; its fixture was corrected without a product change. Evidence: `artifacts/visual-review/certification-completion-concurrency-2026-10-08/{tests-contract.xml,recovery.xml,ruff.log,checkpoint.json}`. No actual learner or registry changed.

### Checkpoint 205 Reconcile help and completion messaging on October 8 2026

**Accepted:** C8-OPS-08. Counts advance to 29/162 accepted and 133 open. This is messaging alignment; live tutoring, publication approval and actual provider/email-client delivery remain separate open gates.

The final surface review ties each current message to the selected or completed course. Help and the user guide distinguish chat coaching from learner-owned panel assessment. Tool metadata and descriptions use the pinned assessment mode instead of hard-coded module names. Promotion removes the unmeasured completion time and certificate-as-quality-guarantee claim. The legacy in-app completion notice now points to the earned certificate/history without claiming a badge validates every published workflow. Certificate download denial refers to selected course requirements rather than a fixed module count. Credential-specific notices retain the original course/version/date, and transition/support guidance preserves optional choice, original history and separate uncertainty recovery. The launch email's absolute claim that every tool result exposes its accuracy now explains that quality signals require source checking.

| Surface | Current source and evidence |
| --- | --- |
| Help and user guide | `help_content.py`, `docs/AGENTIC_CHAT_USER_GUIDE.md`; checkpoint 200 delivered copy and help tests |
| Agent instructions and tool descriptions | `llm_service.py`, `chat_tools.py`; checkpoints 200/202 pinned all-module metadata and service/tool/HTTP boundaries |
| Course promotion | `frontend/src/pages/present/content.ts`, certification paragraphs in `email_service.py`; production build/lint and checkpoints 200/203 |
| Legacy completion email/notification | `email_service.py`, `certification_service.py`; six rendered-email captures and final hook/template tests |
| Versioned completion notices | `completion_notices.py`; checkpoint 183 preserved issuance identity, no blind uncertain resend and original credential retrieval at 198 |
| Download denial and certificate history | `routers/certification.py`, original credential delivery; preserved certificate identity remains independent of today's course |
| Transition/support explanation | `docs/certification-v5-transition-policy.md`, course help, retained-course/history notices; checkpoints 184–195 optional choice and recovery evidence |

**Verification:** 35 final help/template/hook/certificate tests pass after the final notice and download wording corrections. The 43 email/engagement checks and six local renders remain in checkpoint 203; the final template extraction is updated. Relevant source searches found no remaining fixed 1,600-XP, ten-minute or every-published-workflow promise in active service messaging. Frozen historical teaching remains preserved rather than relabeled as verified 5.0 material. Evidence: `artifacts/visual-review/certification-legacy-email-2026-10-08/{messaging-final.xml,launch.html,checkpoint.json}` plus checkpoints 183/195/200/202/203. No announcement, email, publication or migration occurred.


### Checkpoint 206 Preserve the credential promise from introduction through issuance on October 8 2026

**Accepted:** C8-DEF-01, definition and consistent delivery of the credential promise. Counts are now 30/162 accepted and 132 open. This accepts the scoped program definition and its delivery; the draft is still unpublished, and no live competence or 8/10 claim follows.

The learner can open Course goal and certificate scope to read the pinned contract's bounded research-administration task, permitted agent assistance and exclusions. A draft is explicitly labeled unable to award a credential. The same promise appears in the issued PDF and, together with assistance/limits, the recorded certificate description. Technical contract identifiers remain in the data rather than the reading flow.

New competency issuance uses schema 2 and freezes the original scope, contract identity and exact artifact digest. Old schema-1 records keep their original shape and notice hashes; no newer promise is inferred for old or unknown historical credentials, including older competency records without a recorded scope. Interrupted issuance validates and restores either original schema. Credential reads use only the recorded snapshot, so a changed profile or unavailable catalog cannot rewrite the original description. The legacy unversioned PDF's unsupported mastery phrase now describes completion of its course requirements.

**Verification:** 48 backend/PDF/authoring/persistence cases pass, including both complete eleven-module/33-outcome issuance paths, lifecycle interruption and all existing completion notices. One additional real-persistence case verifies schema-1 and schema-2 notice hashes coexist and replay unchanged without sending email. Twenty-eight frontend cases, production build, ESLint and Ruff pass. Sixteen browser captures at 320/390/1440px and native 200% zoom verify readable scope/limits, keyboard details controls and GET-only presentation. The issued long-name PDF and native/narrow UI were manually inspected; normal and interrupted issuance PDFs render pixel-identically. The exact original promise remains in the one-page PDF and API description after profile/catalog changes, with foreign access 404 and unauthenticated access 401.

**Evidence:** `artifacts/visual-review/certification-credential-scope-2026-10-08/{backend.xml,notice-compatibility.xml,frontend.log,build.log,lint.log,ruff-final.log,browser,browser-native,certificate-normal.pdf,certificate-recovered.pdf,checkpoint.json}`. The separately assembled presentation package is `v5.0-preview-2026-10-08.1`; its 74 lessons and 33 implemented outcomes remain at zero release-verified. Both complete-course tests use isolated synthetic release flags and stubbed providers. No actual release or learner changed. Visual inspection additionally exposed unmeasured duration claims in the surrounding panel/journey chrome; those are the next correction under C8-CONTENT-08, not a claim that the scope verification closes all copy work.


### Checkpoint 207 Remove unmeasured course-duration promises on October 8 2026

**Status:** Complete for duration labels in the panel, journey map, module cards and module headers. C8-CONTENT-08 remains open for its complete terminology/content reconciliation. Counts remain 30/162 accepted and 132 open.

The surrounding UI still advertised a five-minute walkthrough, per-module minutes and a summed total with a 10–25-minute-per-module promise. Those labels now describe self-paced work and resume behavior. Historical course files remain unchanged; their unverified duration metadata is not promoted as a learner-facing completion estimate. The module header explains saved reading position even when no duration metadata exists.

**Verification:** 22 existing panel/journey/module cases, production build and ESLint pass. Thirty-three captures at 320/1440px and native 200% zoom cover the course introduction, all visible course cards, AI Literacy/Foundations/Governance headers and assessments, and preserved legacy stars. GET-only routing, axe, bounds and page errors pass. Native introduction and narrow legacy detail were visually inspected. The fixture now explicitly excludes the new scope/policy from its synthetic legacy course and reports only the modules it actually inspected. Evidence: `artifacts/visual-review/certification-duration-copy-2026-10-08/{frontend.log,build.log,lint.log,browser,browser-native,checkpoint.json}`.

### Checkpoint 208 Detect changed promises and shared outcome rules in impact review on October 8 2026

**Status:** Complete for shared-scope impact detection. C8-OPS-02 remains open for actual cohort/runtime evidence and release authorization. Counts remain 30/162 accepted and 132 open.

Publication comparison now records before/after shared outcome rules, including the credential promise, permitted assistance, exclusions, evidence policy and contract/rubric identity. Changes to these shared requirements conservatively require compatibility review for every target outcome, even if each outcome row is textually unchanged. An isolated outcome wording change retains its specific review scope. The exact reviewed report consumed by the authoring gate must match this current comparison; editing findings or readiness flags cannot clear runtime/rollout gates.

**Verification:** 41 scope/impact/authoring-gate cases and Ruff pass. The current inspection of the actual unchanged baseline and isolated October 8 draft identifies 74 changed lessons, 33 target outcomes for review and the shared scope change. It exits 2 with all unresolved source-support, outcomes, policy, rubric, cohorts, live compatibility and rollout findings. Evidence: `artifacts/visual-review/certification-scope-impact-2026-10-08/{tests.xml,ruff.log,draft-impact.json,checkpoint.json}`. Registry bytes remain unchanged and no publication or learner change occurred.


### Checkpoint 209 Maintain the complete outcome-to-evidence matrix on October 8 2026

**Accepted:** C8-DEF-02, traceable outcome mapping. Counts are now 31/162 accepted and 131 open. This accepts mapping/coverage, not live assessment validity or publication.

The existing full design checker now emits an explicit contract-derived matrix. All 33 required outcomes name their module, authored lesson IDs/titles/revisions/source file, practice, assessment, selected saved assessment home, evidence types, passing conditions, critical failures, rubric and implementation status. Recognition rows include the actual 17 assigned scenario identities. The contract digest binds the matrix to its source. Shared lessons or evidence support distinct per-outcome criteria; another passed outcome, practice answer or extra XP cannot offset a missing required result.

The checker already validates every module's cases, prompts, scenarios, exercise bindings and relevant source documents before producing the report. CI's existing backend release-check job now runs it and retains the JSON matrix. Every row remains implemented rather than release-verified. The complete saved-receipt/credit mapping also has the all-eleven-module evidence at checkpoints 196–206; its providers remain stubbed and are not calibration evidence.

**Verification:** The actual checker completed; its 33 unique rows cover all eleven modules with nonempty teaching and passing/failure criteria, and all scenario rows resolve assigned cases. One hundred existing outcome/scenario/rubric cases and Ruff pass. Workflow YAML parses and the checker/artifact steps were inspected; remote CI has not run. Evidence: `artifacts/visual-review/certification-outcome-traceability-2026-10-08/{outcome-matrix.json,tests.xml,ruff.log,checkpoint.json}`. No package, learner, release or external message changed.

### Checkpoint 210 Repair the narrow lab-entry card on October 8 2026

**Status:** Complete for the observed narrow layout, hover contrast and touch-target defects. Counts remain 31/162 accepted and 131 open.

The setup card now stacks its description and full-width action on narrow screens, preserves the status icon, wraps long document names and keeps the button label on one line. Ready-state hover text is darker after axe exposed insufficient contrast. A measured browser check also found that shared workspace styling overrode the intended button height; the component now explicitly preserves a 44px minimum. Setup behavior and stored lab state are unchanged.

**Verification:** 18 initial module/panel cases and 23 final related frontend cases pass, with production build and lint. Twenty-seven final captures cover 320/1440px and native 200% zoom, both ready/unprovisioned lab entries, the current draft and original legacy stars. Axe, bounds, page errors, unmatched requests and measured touch-height checks pass; narrow and zoomed entries were visually inspected. Initial failing runs remain diagnostic evidence. Final evidence: `artifacts/visual-review/certification-lab-entry-layout-2026-10-08/{browser-final,browser-native-final,frontend.log,build.log,lint.log,checkpoint.json}`. Browser data is synthetic and GET-only.

### Checkpoint 211 Preflight certificate rendering before publication on October 8 2026

**Status:** Complete for course-metadata render preflight and documented credential-reader deployment requirements. C8-OPS-02 and C8-VERSION-11 retain their broader live rollout gates. Counts remain 31/162 accepted and 131 open.

The read-only impact comparison now invokes the actual PDF renderer in memory with the target course title, release identity and credential promise. Valid package text that overflows the certificate, or unavailable renderer assets, adds an actionable publication blocker. A successful render uses a synthetic learner identity and does not replace visual inspection or arbitrary-name verification. No volatile PDF metadata is included in the impact digest.

Authoring guidance now describes the mandatory impact-report arguments and current refusal gates. It also records the schema-2 deployment boundary: all credential/history/recovery/notification readers must support both schemas before new competency issuance, and rollback must preserve compatible readers and original immutable records. Multiworker deployment evidence remains open.

**Verification:** 49 impact/publication/PDF cases and Ruff pass, including oversized title/promise rejection and unchanged legacy rendering without invented scope. The actual October 8 draft passes course-field rendering and still reports all seven unresolved publication findings. Evidence: `artifacts/visual-review/certification-certificate-preflight-2026-10-08/{tests.xml,ruff.log,draft-impact.json,checkpoint.json}`. Registry bytes remain unchanged; nothing was issued, published or sent.


### Checkpoint 212 Separate participation from assessed credit on October 8 2026

**Accepted:** C8-DEF-05. Counts advance to 32/162 accepted and 130 open. This accepts the credit distinction and enforcement, not live model validity.

The introduction's pinned policy states that reading, practice and reflections do not earn assessed credit. Lesson checks label their feedback as practice; legacy answers are labeled saved reflections. Progress uses the selected manifest's completed modules rather than XP, and XP milestones do not issue credentials. All 33 outcomes require selected saved passing evidence under their original rubric; other passing history is not automatically substituted. Original legacy requirements and earned records retain their separate scope.

Two additional authenticated persistence cases seed a synthetic learner with the final reading position, saved reflections, an Architect label and 9,999 XP. Missing or failed selected recognition evidence still prevents module credit and certificate download, even though a different passing receipt exists. Participation and XP remain unchanged, and no credential is created. The existing selected-completion checks also retain deterministic execution vetoes and original issuance/replay behavior. Obsolete reflection writes remain blocked for outcome-based enrollments through the service, HTTP and chat boundaries at checkpoint 202.

**Verification:** 36 backend/persistence cases and 23 frontend cases pass. Frontend checks cover practice feedback, saved reflections, course policy, module entry and high-XP completion percentages. The first command used an incorrect test path and ran no tests; the corrected run is the accepted evidence. Evidence: `artifacts/visual-review/certification-participation-boundary-2026-10-08/{tests.xml,tests-final.log,frontend.log,checkpoint.json}`. All learners and judges are disposable/stubbed, and nothing was published or sent.


### Checkpoint 213 Use the pinned reward policy in chat cards on October 8 2026

**Status:** Complete for chat grading-scale presentation. C8-CONTENT-08 and C8-VERSION-12 retain their broader reconciliation work. Counts remain 32/162 accepted and 130 open.

Chat cards still announced a fixed three-star denominator even for the new single-threshold outcome course. Versioned service responses now include their exact maximum stars and whether credit uses required outcomes or the legacy rubric. Progress, module, check and completion cards omit decorative star grading for required outcomes. Legacy cards use their recorded scale; historical versioned replies without a scale retain the count without inventing a denominator. The original saved receipts and grades are unchanged.

Backend and frontend contracts reject incomplete reward metadata, contradictory outcome scales and stars above the pinned maximum. Real-persistence routing checks verify the metadata across all eleven modules and progress in both legacy and competency enrollments. Old payloads remain readable; these additions describe a result rather than selecting evidence or enabling agent-driven competency completion.

**Verification:** 65 backend/HTTP/persistence cases, 19 final schema cases and 72 frontend cases pass; build, Ruff and ESLint pass. Twenty-four browser captures at 320/1440px and native 200% zoom cover four outcome card types, original/historical star displays and two invalid-policy responses. Axe, page bounds, routes and browser errors pass; narrow progress/legacy and zoomed completion were inspected. Evidence: `artifacts/visual-review/certification-chat-reward-policy-2026-10-08/{backend.xml,contracts-final.log,frontend.log,browser,browser-native,build.log,lint.log,ruff.log,checkpoint.json}`. Visual responses are synthetic and do not establish grading validity. No real learner, package or issuance changed.


### Checkpoint 214 Bind chat actions to the complete selected course on October 8 2026

**Accepted:** C8-CHAT-08. Counts advance to 33/162 accepted and 129 open.

The shared card boundary now matches enrollment, course version, manifest and applicable module against both selected course and progress. Missing course data, mismatched progress, obsolete manifests and removed modules keep course actions disabled. Disabled controls also look inactive and reject synthetic event dispatch. Original instructions and source links remain readable. Module-completion cards now show their recorded course title/version; an old result opens the current course directly instead of prompting from obsolete context. Preserved certificate retrieval remains outside the disabled action group and uses original issuance identity.

**Verification:** Initial 55 frontend cases were followed by 113 related cases and 57 final payload cases in checkpoint 215, including original certificate access and readable historical source links. Three actual disposable persistence cases verify HTTP/chat identity consistency, stale-course write refusal, changed-answer rejection of uncommitted grades and nested-operation boundaries. Thirty final captures at 320/1440px and native 200% zoom cover matching and mismatched enrollment/version/manifest, removed modules and recorded completion identity. Axe, bounds, routes and browser errors pass; narrow disabled controls and zoomed original completion were inspected. Initial test failures exposed synthetic click dispatch through disabled fieldsets; the final event guard addresses controls while preserving read-only links.

**Evidence:** `artifacts/visual-review/certification-chat-identity-2026-10-08/{browser-final,browser-native-final,server-boundary.xml,frontend-final.log,checkpoint.json}`; final shared component build/tests are in checkpoint 215. Browser transport is synthetic; backend tests use only disposable MongoDB. No actual selection, credit or certificate changed.

### Checkpoint 215 Reduce module-card overload without hiding required outcomes on October 8 2026

**Accepted:** C8-VIS-08. Counts advance to 34/162 accepted and 128 open.

Module actions appear after the introduction and before long exercise detail. Numbered instructions and expected fields use a named, counted disclosure with a 44px summary control. Passing requirements stay outside that disclosure. The first all-module run exposed that outcome-based cards had no legacy star criteria and were not rendering their authored outcomes; every required outcome is now explicitly listed, with the assessment action identifying where to inspect passing evidence. Legacy passing criteria remain visible. The header wraps without breaking Completed or the XP label into fragments.

Frontend response validation now checks required-outcome identity, unique coverage, method, statement and contradiction with legacy reflection metadata before rendering. Both old response formats and the exported 86-response baseline remain supported. Historical cards can expand original instructions and follow source links while their course actions remain disabled.

**Verification:** 113 related frontend cases and 57 final payload cases pass, with production build, ESLint and diff checks. The final 102 browser captures cover all eleven modules at 320/1440px and native 200% zoom: collapsed entry, keyboard-expanded instructions, exact step counts/bounds, direct panel assessment and return with the unsent chat draft and saved lesson unchanged. Required outcomes remain visible, old cards route to the selected course without an extra agent request, and no certification write occurs. Axe, page errors and unexpected routes pass. Native Foundations entry, narrow Advanced Nodes steps and the complete desktop AI Literacy card were visually inspected. The initial missing-outcome failure remains diagnostic evidence.

**Evidence:** `artifacts/visual-review/certification-chat-module-layout-2026-10-08/{browser-final,browser-native-final,frontend-final.log,contracts-final.log,build-final.log,lint.log,checkpoint.json}`. This verifies layout and controlled navigation, not live assessment validity or actual mobile OS keyboard behavior. Visual reading also identified agent-directed wording in the new-course chat instructions; separating that coaching from learner steps is the next copy correction.

### Checkpoint 216 Verify teaching export and publication synchronization on October 8 2026

**Accepted:** C8-CONTENT-10. Counts advance to 35/162 accepted and 127 open.

The existing frontend CI/export gate compares exact authored lessons, practice, diagrams, reflection definitions, panel modules and course structure. Five isolated fault cases now run with that gate: stale diagram, panel title, XP structure, changed authored reflection question and stale practice feedback. Every mismatch fails read-only without silently updating the rejected export. Versioned panel reflections are supplied from the same packaged lessons definition read by chat; they do not use an independently edited current-course fallback.

The authoring regression now covers mismatched lesson identity, revision, title, content, objective, variant, diagram and practice. All fail before registration or a partial package remains. Catalog validation checks manifest coverage/order, exact lesson presentation parity and pinned exercise/source hashes. Existing immutable-publication protection remains separate from draft editing; no stale artifact can be accepted simply by leaving a generated export behind.

**Verification:** Five Node fault cases and 46 catalog/authoring/preview cases pass, plus Ruff. The actual working export passes for all 74 lessons across eleven modules, and the real catalog/history check against HEAD passes. The frontend certification check is already included by npm CI and Makefile CI; it now also runs the fault cases. Remote CI has not run. Evidence: `artifacts/visual-review/certification-teaching-sync-2026-10-08/{export.log,tests.xml,release-check.log,ruff.log,checkpoint.json}`. All changed examples were in disposable copies; actual course registry bytes remain unchanged.


### Checkpoint 217 Separate learner exercise steps from assistant guidance on October 8 2026

**Status:** Complete for new-course chat instruction delivery. C8-CONTENT-08 remains open for the broader terminology/control audit. Counts remain 35/162 accepted and 127 open.

Some authored chat instructions address the assistant directly. Outcome-based module replies now put the actual learner exercise procedure in instructions and retain assistant-specific coaching separately as agent_guidance. The tool description explains that distinction. Cards render the learner procedure only; the assistant still receives the original boundaries on approvals, evidence and assessment. Original legacy chat-native instructions remain unchanged, and no authored/frozen package is rewritten.

**Verification:** 56 backend/schema/HTTP/persistence cases and 82 frontend cases pass, with build, Ruff and ESLint. The actual all-module routing test checks both fields against the pinned exercises for all eleven legacy and competency modules. The final 102 captures repeat narrow/desktop/native-zoom entry, keyboard disclosure and assessment handoff; every displayed step exactly matches its authored learner instruction, and distinct assistant directives are absent from the card. Axe, bounds, route/error checks and draft/position preservation pass. Narrow Advanced Nodes instructions were visually inspected after removing assistant-directed wording.

**Evidence:** `artifacts/visual-review/certification-learner-instructions-2026-10-08/{backend.xml,frontend.log,browser,browser-native,build.log,lint.log,ruff.log,checkpoint.json}`. Transport and judges are synthetic; no live grading, publication, migration or staff queue was enabled.


### Checkpoint 218 Read-only saved learner status on October 8 2026

**Status:** Complete for original reading position and completion-journal support. C8-OPS-05 remains open for outstanding automatic reviews and lab operations. Counts remain 35/162 accepted and 127 open.

Staff can open the exact learner/enrollment row to see its original course, earned state, last saved lesson, pending credential/completion requests and ten recent completion records. The server verifies the saved lesson ID, integer revision and content hash. Failed outcomes use the original authored statements; selected review/scenario references stay in an expandable section. The view distinguishes technical failure from unmet requirements, ambiguous unfinished requests from a safe single retry, and changed answers from an applicable saved grade. Preserved courses do not inherit another selected course’s worker state.

The detail endpoint now returns only permitted earned-state module fields, removing arbitrary reflection/source blobs. History queries are bounded, indexed and scoped to owner plus enrollment. Corrupt history is unavailable rather than inferred; corrupt pending course bindings return a conflict. Opening, refreshing and closing the view never enrolls, recovers, grades, issues, sends or writes. The UI rejects changed row identity, clears stale data during refresh and returns focus on close.

**Verification:** 19 authenticated persistence cases and 20 related frontend cases pass, with production build, Ruff and ESLint. Twenty-seven browser captures cover 320/1440px and native 200% zoom: saved, pending, rejected, legacy, corrupt, failed-read/retry and mismatched-course states. Axe, bounds, exact GET routes, keyboard disclosure, restored focus and page errors pass; the intentional 503 logs are expected failure fixtures. Narrow status, desktop history and zoomed references were manually inspected.

**Evidence:** `artifacts/visual-review/certification-support-summary-2026-10-08/{backend-final.xml,frontend-final.log,build.log,ruff.log,lint.log,browser,browser-native,checkpoint.json}`. The first frontend command used an incorrect file destination; the final run includes the new component and all twenty cases. These are synthetic/browser and disposable-database checks, not actual support or learner observations. No published package, actual learner or communication changed.


### Checkpoint 219 Automatic review and lab-operation support on October 8 2026

**Status:** Complete for saved automatic assessments and execution receipts. C8-OPS-05 remains open for private-handoff status and final coverage review. Counts remain 35/162 accepted and 127 open.

The read-only learner view now includes outstanding automatic reviews, recent review results and lab runs. It retains older pending work even when newer records fill the recent-history window. Each kind shows up to five outstanding plus five recent records, removes duplicates and explicitly reports further history. Original owner/enrollment/course bindings and receipt integrity are verified before display. Workflow-specific decoders validate connected, advanced, output, validation, batch and governance runs.

Technical grading failures never become learner failures; uncertain execution never becomes permission to rerun successful stages. Required revisions show authored outcome statements without source quotations, learner answers or provider diagnostics. Original request/run/input and technical-retry references remain expandable. A selected course’s pending worker or course change is visible, while preserved enrollments do not inherit its activity. A recorded successful execution or review does not claim module completion or select evidence for the learner.

**Verification:** 36 distinct backend/persistence cases pass across the initial, extended-family and final connected/history runs; 22 frontend cases, production build, Ruff and ESLint pass. Cases use actual saved evidence and stubbed providers, reject rehashed semantic corruption, retain pending history beyond the recent cap, exclude other owners and prove repeated reads make no database writes or further model calls. Thirty-nine browser captures at 320/1440px and native 200% zoom pass axe, bounds, GET-only route, keyboard disclosure, refresh and focus checks. Narrow automatic status, desktop runs and zoomed references were inspected. Disclosure markers are now visible.

**Evidence:** `artifacts/visual-review/certification-support-operations-2026-10-08/{backend.xml,operations-final.xml,connected-history.xml,frontend.log,build.log,ruff.log,lint.log,browser,browser-native,checkpoint.json}`. Browser responses are synthetic; persistence uses disposable MongoDB. Live calibration, actual learner observation and release validation remain deferred/open.


### Checkpoint 220 Complete private support status on October 8 2026

**Accepted:** C8-OPS-05. Counts advance to 36/162 accepted and 126 open.

Support can inspect original enrollment/version, saved reading position, completion attempts, outstanding automatic assessment/execution work, pending selection/worker/credential state, failed requirements and exact relevant references. The final addition distinguishes successful execution from the deliberately failed first private training handoff and its later approved copy. Output and governance handoffs use their original integrity readers; generated files, private memo contents, learner decisions and raw provider errors are never returned. A training copy is explicitly not external delivery. Opening the view creates no staff grading task and performs no writes or provider calls.

History limits and additional pending/older records are explicit. Automatic-review and run queries fetch identifiers first, then decode one receipt at a time, avoiding simultaneous retention of multiple large private payloads. Handoffs use the same bounded approach. Completion history now verifies the saved terminal result, validation, original request/course identity and state consistency. Damaged pending grades receive reconciliation guidance rather than an implied safe recovery. Actual saved selected-evidence completions and rejections verify this path; rehashed contradictory results are refused.

**Verification:** 45 distinct backend/persistence cases pass across the combined forty-case run and final twenty-four-case completion run (overlapping checks counted once). Twenty-three frontend cases, production build, Ruff, ESLint and diff checks pass. Forty-five browser captures cover narrow/desktop and native 200% zoom, including private success/failure, original retry references, technical-review failure, required revisions, uncertain runs, unreadable records and refresh/focus behavior. Axe, bounds and GET-only routes pass. Narrow handoff context and zoomed delivery/reference states were inspected; prior summary/operation inspections are in checkpoints 218–219.

**Evidence:** `artifacts/visual-review/certification-support-handoffs-2026-10-08/{backend.xml,completion-final.xml,actual-completion.xml,frontend.log,build.log,ruff.log,lint.log,browser,browser-native,checkpoint.json}`. These checks use disposable MongoDB, stubbed providers and synthetic browser responses. No actual course publication, cohort migration, external message or audit-score change occurred. The course registry remains byte-identical. Actual learner/support observation remains a separate release evidence gate.


### Checkpoint 221 Preserve earned work during legacy access changes on October 8 2026

**Status:** Complete for the legacy prerequisite update defect. C8-OPS-04 remains open for the full administration audit/reason trail. Counts remain 36/162 accepted and 126 open.

The old unversioned access path loaded progress and saved the whole document after changing its unlock flag. Four reproductions showed it overwriting concurrently earned modules/XP, reflections, reading position and completion/issuance receipts, creating progress for a missing learner, and replacing changed access or row binding. The corrected path atomically updates only prerequisite access and its timestamp. It compares the reviewed access/binding, returns fresh progress, refuses records carrying a versioned write fence, and requires an existing learner progress row. Older documents without the access flag retain their false default and arbitrary historical fields.

Versioned changes retain the existing enrollment write boundary. Flexible-order outcome courses still refuse any prerequisite override, and no access change can waive their assessed requirements. This bounded fix does not claim to complete audit reasons, unversioned grading concurrency, or a cross-collection migration protocol.

**Verification:** All four original cases failed before the fix. Eight final disposable-persistence cases pass, including old missing-field compatibility, fenced-record refusal, original selected-enrollment/role behavior and the flexible-order policy. Ruff and diff checks pass. Evidence: `artifacts/visual-review/certification-legacy-access-preservation-2026-10-08/{before.xml,final.xml,ruff.log,checkpoint.json}`. No UI behavior, real learner, publication or external communication changed.


### Checkpoint 222 Stable lesson identities and revisions on October 8 2026

**Accepted:** C8-VERSION-04. Counts advance to 37/162 accepted and 125 open.

All 74 lessons have authored stable IDs and positive integer revisions shared by chat, panel and manifest. Authoring guidance now explicitly preserves IDs across renaming/reordering, requires a new identity for a replacement concept and advances retained-lesson revisions when teaching or practice changes. IDs are never regenerated from display positions or edited titles.

Thirteen additional impact cases check title, body, objective, presentation variant, diagram and practice-feedback edits both with and without a revision increase, plus pure reordering. Coherent changes in both renderers still fail revision policy when the revision is reused. Pure reorder preserves all 74 lesson revisions while reporting its module-definition change. The original loaded package bytes remain unchanged. Existing publication gates consume the exact comparison and continue to block unresolved release evidence.

The persistence reorder case now also saves an actual original-enrollment cursor before publishing a synthetic revised/reordered test package: the original learner retains the same revision, content, position and enrollment; a new learner receives the separate definition without inheriting that cursor. Additional persistence cases verify saved answers/lab references/credit survive navigation, HTTP and chat share identity-based resume, stale devices fail, and revoked writes cannot move the cursor. Frontend checks cover reordered lesson identity, isolated enrollment storage, server restoration, failed-save recovery and stale responses.

**Verification:** 118 catalog/authoring/impact/teaching cases, four persistence cases and 32 frontend cases pass. Five export fault checks and the actual 74-lesson export comparison pass; Ruff and diff checks pass. Evidence: `artifacts/visual-review/certification-stable-lessons-2026-10-08/{contracts.xml,persistence.xml,frontend.log,export.log,ruff.log,checkpoint.json}`. No rendered UI changed, so no redundant browser capture was required. All publication in these tests is confined to temporary synthetic catalogs; the actual registry and learner data are untouched.

### Checkpoint 223 Preserve course-specific completion totals on October 8 2026

**Accepted:** C8-VERSION-09. Counts advance to 38/162 accepted and 124 open.

An isolated persistence rehearsal publishes synthetic three-module and eleven-module definitions in a temporary catalog. Existing completed and active enrollments retain their original selection and byte-for-byte progress when the default changes. Authenticated HTTP, chat and admin reads agree on original module IDs, totals, maximum XP, prerequisites and next-module identity: the old completed course remains 3/3, its active peer remains 1/3, and the expanded course is 1/11. Unrelated completed-module entries and 9,999 XP do not inflate course completion.

Frontend verification covers the selected-course progress ring, home continuation, chat progress semantics, admin totals and original certified banner. Eighteen production-browser captures cover the three course states at 320/1440 widths and native 200% zoom. The expanded course displays 9% and 1/11; the preserved certified course retains its original title, version and three-module completion banner. Manual inspection covered the narrow expanded panel and native-zoom original certified panel. Automated bounds, accessibility, console and unexpected-request checks pass; certification requests are GET-only.

**Verification:** One persistence case, 52 frontend cases, 18 final browser captures, Ruff, targeted ESLint and diff checks pass. Evidence: `artifacts/visual-review/certification-course-denominators-2026-10-08/{persistence.xml,frontend.log,browser-final/manifest.json,browser-native/manifest.json,checkpoint.json}`. The initial browser assertion incorrectly expected a progress ring on the certified state; its failure is retained, and the corrected harness checks the actual certified banner. No production component change was needed.

**Limits:** This checkpoint seeds synthetic cohort states and does not independently prove grading or credential issuance. Actual saved-evidence completion/issuance and the high-XP participation boundary were separately verified at checkpoints 196/198/206/212 with stubbed providers. Actual cohort migration, live grading calibration, real-device/screen-reader observation and release authorization remain open. The actual course registry and learner data are unchanged.

### Checkpoint 224 Preserve assessed evidence behind the complete credential on October 8 2026

**Accepted:** C8-GRADE-02. Counts advance to 39/162 accepted and 123 open.

The full-course persistence rehearsal now follows every earned module’s selected receipt hashes back to the exact saved assessment. Ten automatic reviews preserve their source/artifact evidence, authenticated decisions, reviewer configuration, original contract and result. Three scenario receipts preserve submitted answers and their pinned bank digest and reproduce their original result. Together these explain all 33 outcomes across eleven modules.

After both normal and interrupted issuance, the test edits live source text, field instructions and workflow titles, then removes 129 fixture records: documents, extraction definitions, workflows/steps/tasks, lab inputs/runs and intermediate learner/process/design decisions. All thirteen assessment records remain byte-for-byte unchanged and owned; public automatic-review feedback still renders. The credential and PDF text retain their original identity, scope and learner name. Repository evidence retrieval and credential retrieval also work with catalog loading deliberately unavailable; the ordinary public review reader still requires its pinned course to validate the original contract. No assertion implies deletion of the assessment journals themselves is recoverable.

**Verification:** Two strengthened full-course cases and 78 targeted persistence cases pass. The latter cover immutable inputs/answers, original replay, linked revisions, technical retries, deleted live sources and rejection of changed or inconsistent nested evidence/results. Ruff and diff checks pass. Evidence: `artifacts/visual-review/certification-assessed-evidence-2026-10-08/{graduation.xml,retention.xml,certificate-normal.json,certificate-recovered.json,checkpoint.json}`. No product rendering changed in this checkpoint, so browser recapture was unnecessary.

**Limits:** All removal occurs in per-test disposable QA databases. Automatic judges and execution providers are stubbed; this proves persistence, integrity and ownership behavior, not live grading accuracy. Historical legacy completion retains explicitly unknown/unverified evidence provenance rather than inventing missing proof. Actual retention operations, account deletion policy and release verification remain separate gates.

### Checkpoint 225 Distinguish mandatory checks from advice on October 8 2026

**Accepted:** C8-GRADE-03. Counts advance to 40/162 accepted and 122 open.

The legacy Extraction Engine rubric intentionally passes on the extraction-field count while suggesting missing expected fields. A response adapter now assigns explicit required/advisory roles on both unversioned and pinned legacy validation paths. It preserves the original verdict, star thresholds and frozen rubric bytes. New competency checks already declare required roles and compute passing from all required outcomes and prerequisites.

Chat and panel results label required checks as met/not met and advisory findings as suggestions. A passed result with unmet advice says “Module requirements met”; “All checks passed” remains reserved for a nonempty set of actually passing checks. Existing historical responses without roles retain their prior compatible presentation. Backend and frontend chat contracts reject unknown/mixed roles, advice-only records and summaries that contradict explicit required checks. No original saved attempt is rewritten.

Visual QA also found that shared workspace control CSS overrode utility-class sizing for the result-dismiss button. Its minimum width/height is now explicitly 44 pixels, confirmed by browser measurement and functional dismissal. This is a local control fix, not acceptance of the entire accessibility checklist.

**Verification:** 107 backend cases, 97 frontend cases and seven persistence cases pass. Eighteen final production captures cover three result states in chat and panel at 320/1440 widths and native 200% zoom; bounds, axe, page errors and unexpected-request checks pass. Manual inspection includes the narrow passing panel/chat and native-zoom required-failure panel. Ruff, ESLint and diff checks pass. Full TypeScript/build verification passed for the role and payload changes; the final button-only style correction was bundled with Vite into an isolated output and served separately on port 5297. A redundant subsequent full type check was interrupted under machine load and is not counted as a pass.

Evidence: `artifacts/visual-review/certification-check-roles-2026-10-08/{contracts-final.xml,frontend-final.log,persistence.xml,vite-final.log,browser-isolated/manifest.json,browser-native-final/manifest.json,checkpoint.json}`. Earlier fixture/locator failures, the observed 36-pixel sizing failure and a slow initial native browser action are retained. Final browser verification uses intercepted synthetic responses and performs no real completion, model call or learner mutation. Course registry bytes remain unchanged.

### Checkpoint 226 Revalidate original evidence when awarding credit on October 8 2026

**Accepted:** C8-GRADE-05. Counts advance to 41/162 accepted and 121 open.

Three new authenticated HTTP cases first obtain a genuinely passing saved-outcome preview, then remove the selected automatic review, replace its result with a digest-valid but incomplete assessment, or corrupt the selected scenario receipt. Completion re-reads the original selected records and refuses them with controlled 409/503 responses. The earlier passing preview never becomes authority to award XP, mark completion or issue a certificate. The judge remains called once; completion does not silently rerun it or invent a staff grading task.

The same verification bundle covers explicit consent and request identity, authenticated enrollment selection, missing/failed outcomes, deterministic execution failure despite a supportive stub judge, high-XP participation without competency proof, preserved explicit failure despite a later passing attempt, cross-owner/module selections, technical/pending states and idempotent completion/credential recovery. The actual pinned rubric requires all selected original outcomes and same-enrollment prerequisites, and freezes validated receipt hashes into earned credit.

**Verification:** All 25 persistence cases across outcome completion, pinned outcome rubric and module readiness pass; Ruff and diff checks pass. Evidence: `artifacts/visual-review/certification-completion-revalidation-2026-10-08/{persistence.xml,persistence.log,ruff.log,checkpoint.json}`. No product code changed in this checkpoint, so browser recapture was unnecessary. This verifies server enforcement against saved evidence with stubbed providers, not live grading accuracy. Source/workspace edits do not rewrite an immutable selected assessment; missing or inconsistent original assessment records cannot be substituted with the old preview.

### Checkpoint 227 Bind competency attempts to original work on October 8 2026

**Accepted:** C8-GRADE-01. Counts advance to 42/162 accepted and 120 open.

New competency review producers collect explicitly referenced lab inputs, runs and authenticated learner decisions. They check enrollment/module/package identity, pinned exercise or case digests, assigned source bytes, artifact configuration revisions and the relevant execution chain before saving an automatic-review request. Process and workflow design use their saved submissions and approvals; execution modules use exact captured/rerun records; scenario-only literacy uses the pinned bank and explicit answer receipt. The automatic judge receives the saved packet and contract rather than a fresh workspace search. The preserved legacy rubric remains historically distinct and does not establish these V5 outcomes.

The full eleven-module rehearsal at checkpoint 224 traces all 33 credited outcomes through thirteen exact selected receipt hashes, including ten automatic reviews and three scenario receipts. Its original records survive live edits/deletion. Checkpoint 226 confirms those exact selected records are revalidated at completion. Earlier complete persistence coverage at checkpoint 199 includes the Foundations, extraction-repair and connected-workflow collector boundaries; checkpoint 224 reruns their original/rehashed evidence protections.

**Verification:** An additional 78 targeted persistence cases pass across scope selection, saved process/workflow design and advanced/output/validation/batch/governance review bindings. They reject fabricated, changed, foreign, mismatched and incomplete references before they can claim the original work. Evidence: `artifacts/visual-review/certification-assessment-binding-2026-10-08/{persistence.xml,persistence.log,checkpoint.json}`. A redundant supplemental collector run was interrupted under severe local contention and is not counted; its diagnostic log is retained. No product source changed for this acceptance, so no new browser capture was needed.

**Limits:** This accepts evidence identity and collection boundaries, not the full access-control checklist. Project/team visibility, revocation and permitted shared-lab behavior remain C8-GRADE-07 and are being reviewed separately. All fixtures are isolated and providers stubbed; live grading calibration and release verification remain open.


### Checkpoint 228 Enforce current project access for sources on October 8 2026

**Fixed and verified; C8-GRADE-07 remains open.** Counts remain 42/162 accepted and 120 open.

A reproduced defect allowed an owned assigned document inside an inaccessible project to be captured because certification checked document ownership alone. The application's ordinary document read correctly denied that same synthetic learner. New source capture and live assigned-source delivery now use a shared ownership plus canonical project-access check. All seven source-reading capture families check again after storage reads. Legacy and versioned provisioning also require contribution access to the lab folder and current access to reused documents. The original course/rubric bytes and actual release registry remain unchanged.

Read-only capture of individually owned assigned work remains permitted for project owners, viewers, editors and current team members under normal application permissions. Provisioning requires contribution access; viewers cannot use it to create or reuse a lab through a write operation. Transferred, deleted and wrong-lab sources are rejected. Revocation during a storage read prevents a new evidence record. Old authorized snapshots and their identical-request replays remain personal history, and live source delivery hides revoked text without deleting saved calculation evidence. Shared artifacts owned by other people do not establish new V5 personal competency. The explicit policy is in `backend/certification-data/courses/README.md`.

**Verification:** 22 focused real-Mongo access cases and 133 source-capture/full-course regression cases pass against isolated QA MongoDB on port 27029. The latter includes both normal and interrupted eleven-module completion rehearsals. Ruff and diff checks pass. Evidence: `artifacts/visual-review/certification-project-access-2026-10-08/{before.xml,access-verified.xml,regression.xml,ruff-final.log,checkpoint.json}`. `before.xml` retains the original failing regression. An intermediate provisioning test incorrectly modeled an unversioned learner with an already-versioned progress record; correcting that fixture produced the final 22-case pass without changing the protected write boundary. Earlier and failed diagnostic runs are not additional passing cases. No visual behavior changed, so no browser recapture was needed.

**Remaining:** The preserved legacy field collectors can follow a linked extraction ID or select a creator-only artifact without checking current access. This needs a separate compatibility-aware investigation before accepting the overall ownership item. Existing earned credit must stay preserved. All tests use synthetic learners; real cohorts, live-model calibration and release verification remain open.


### Checkpoint 229 Preserve legacy criteria while enforcing read access on October 8 2026

**Accepted:** C8-GRADE-07. Counts advance to 43/162 accepted and 119 open.

Four isolated regressions reproduced unauthorized legacy field credit through linked extraction IDs and creator-only references in both the current and frozen runners. A per-invocation adapter now applies the ordinary extraction/library read ACL to those field queries. It binds the existing collector functions to a private read scope; no shared rubric globals are mutated and the frozen rubric bytes are unchanged. Field merging, thresholds and star policy still execute from their original code. Inaccessible linked fields are omitted while valid inline fields remain. Legacy global, team and library access remains permitted under its historical rules; new V5 captures continue to require individually owned artifacts and assigned sources.

**Verification:** 34 final persistence cases pass, including 32 focused legacy permission cases plus existing pinned-course and parallel-chat compatibility cases. They cover both runners, linked and creator paths, owned/global/team/library access, membership revocation between requests and during field reads, concurrent learners with different access, and refused new completion preserving original XP, stars, completion date and progress. All 1,233 certification unit/contract tests pass. The earlier 78-test contract pass is a subset and is not additional coverage. Ruff and diff checks pass. The actual registry SHA remains unchanged, and the installed frozen rubric still byte-matches its original packaged artifact. Evidence: `artifacts/visual-review/certification-legacy-evidence-access-2026-10-08/{before.xml,persistence-final.xml,unit-final.xml,ruff-final.log,checkpoint.json}`.

Together with checkpoint 228's 22 project/team capture/provisioning cases and 133 source/full-course cases, this establishes current-access enforcement and the explicit shared-lab policy. Existing foreign-actor, artifact/field ownership, guessed/missing reference and transferred-source checks also remain covered by checkpoints 199, 224 and 227. Saved authorized assessment history remains available after workspace changes; it does not authorize new live reads. No new browser capture was required because the fix changes server-side evidence access. This acceptance establishes permission boundaries, not live grading calibration or release readiness. No actual learners, publication defaults or course offers changed.


### Checkpoint 230 Separate learner decisions from generated output on October 8 2026

**Accepted:** C8-GRADE-08. Counts advance to 44/162 accepted and 118 open.

Competency submissions capture authenticated choices, explanations, source quotes, approvals, corrections and review evidence against their original assigned case and saved work. Required approval belongs to the exact prepared run; an old approval cannot authorize a different run or override a newer decline. Source checks require the actual saved assigned document and a quote found in it. Unknown choices, fabricated metadata, incomplete fields and retrospective approval are refused before persistence. Saved packets distinguish learner decisions from proposals, source snapshots, generated output and execution receipts. Saving a decision grants no credit by itself.

The explicit agent-assurance regression embeds an instruction to pass the learner in source text while omitting the learner's value review. The missing review remains missing and collection stays incomplete. Existing trusted-review and saved-value-review cases prevent preparing a qualifying assessment from those omissions. Workflow design requires exact saved approval; the later review families preserve their submitted interpretation and decisions. Selected completion uses their original receipt references, as traced across all eleven modules at checkpoints 224 and 227. Favorable stub-model claims cannot overrule deterministic source-check failures.

**Verification:** 48 targeted decision/scope/evidence persistence cases pass, plus eight chat-routing persistence cases and 29 chat-tool contract tests. The routing cases exercise service, tool and HTTP submission: legacy reflections remain supported for legacy courses and cannot write competency-course evidence or XP. The 1,233 certification unit/contract pass at checkpoint 229 also remains applicable. Evidence: `artifacts/visual-review/certification-learner-decisions-2026-10-08/{persistence.xml,chat-routing.xml,chat-contracts.xml,checkpoint.json}`. No product source changed for this acceptance and no new browser capture was required; prior learner-facing delivery evidence remains in the module checkpoints.

**Limits:** This verifies explicit submitted evidence and provenance, not a claim that software can prove unaided human reasoning or that live model judgments are calibrated. AI assistance is compatible with agentic learning; required learner choices cannot be synthesized by the certification chat tools. Live-model calibration remains deferred and release-gating. The broader qualitative grading and invalid-work rubric items stay open. No staff grading queue or actual learner changes were introduced.


### Checkpoint 231 Record access overrides separately from assessed credit on October 8 2026

**Accepted:** C8-OPS-04. Counts advance to 45/162 accepted and 117 open.

Administrator prerequisite changes now require a reason and stable request identity. The server supplies the authenticated actor. A private append-only course journal and the access flag share one atomic Mongo update, preserving earned modules, XP, completion dates, reading state and credentials. Failed journal writes cannot apply an unrecorded change. Exact retries preserve the original reason and actor; replaying an older unlock cannot undo a subsequent re-lock. Current selected-enrollment and write-fence protections remain enforced, and flexible-order competency courses refuse the override entirely.

The administrator form explains the access-only effect, requires a reason and preserves the same request after an uncertain response. Support sees the latest ten access changes, actor, reason and recorded time separately from assessment history; older events remain retained. Missing historical attribution and corrupt history are explicit rather than invented. The bounded history query projects only its required metadata, and ordinary learner serialization excludes the private journal. Existing completion recovery already preserves original grade/credit and a reasoned actor trail; no manual grading or credential override was added.

**Verification:** All 72 final persistence cases pass against isolated QA MongoDB. They cover both legacy/versioned atomic updates, lost responses, changed-request rejection, authorization, missing/spoofed request fields, original credit, ordinary-save retention, history bounds, and existing support/recovery privacy. Twenty-six unique frontend cases pass: the initial final run had one machine-load timeout that passed separately; the final focus changes also pass all fourteen affected form/history cases. Twelve normal-width and six native-200%-zoom captures pass layout bounds, axe, reason/retry, no-double-event and focus-return assertions. The narrow form and saved history plus enlarged uncertain state were manually inspected. Ruff, ESLint, diff checks, the isolated production build and application TypeScript check pass.

Evidence: `artifacts/visual-review/certification-admin-access-trail-2026-10-08/` contains `persistence-verified.xml`, `frontend-verified.log`, `frontend-timeout-recheck.log`, `focus-tests.log`, `browser-isolated/`, `browser-native/`, `typescript-verified.log`, `vite-isolated.log`, `dist-isolated/` and `checkpoint.json`. Source manifests identify the frozen visual build and typecheck source. The typecheck used the already-corrected shared optimizer helper, whose unrelated undeclared offset read had changed during other work; certification source stayed identical. Two focus failures, the crowded initial header, obsolete request fixtures, interrupted checks and transient shared-file build failures remain as diagnostics and are not passing evidence. A minimal missing JSX delimiter in a shared theme edit was repaired while unblocking the build; its subsequent concurrent correction is preserved.

**Limits:** This verifies exceptional access support, not permission to award competence or publish a course. Generic historical admin logs may contain additional context, but the course flag itself does not establish a reason or actor. No actual learner record, course registry, deployment, publication or external communication changed. Live calibration and the remaining rollout gates stay open.


### Checkpoint 232 Exercise real persisted chat-result contracts on October 8 2026

**Accepted:** C8-QA-02. Counts advance to 46/162 accepted and 116 open.

The live-write detector previously accepted an abbreviated completion containing only a module ID and XP total. It now uses the same structural contract as the course cards before emitting a successful-write refresh. Invalid cursor revisions, incomplete provisioning or assessment responses, negative XP and malformed stars cannot imply completed writes. An unclear reply still offers saved-state inspection; it does not invite repeating a potentially saved operation.

The stream tests now consume JSON exported directly from a real persisted chat flow in disposable QA MongoDB. The five original tool responses include saved assessment, checking, completion, idempotent completion replay and a stale-enrollment rejection. Completion awards 125 XP once and replay awards zero additional XP. No receipt fields were invented for the fixture. This complements the earlier real backend export of all 74 lessons, eleven modules and progress.

**Verification:** 54 backend serializer/tool tests, one persisted end-to-end chat flow and 100 frontend cases pass. Frontend cases cover both actual exports, incremental and buffered results, duplicate/history replay, obsolete card identity and malformed/error responses. Targeted Ruff, ESLint and an isolated application TypeScript check pass. Prior contract/error-recovery and stale-card browser captures at checkpoints 157, 214 and 225 remain applicable; this change has no new UI markup. Evidence: `artifacts/visual-review/certification-contract-acceptance-2026-10-08/{backend.xml,persisted-chat.xml,frontend-verified.log,typescript-verified.log,typecheck-source.json,checkpoint.json}`. The isolated source manifest records the four updated files relative to checkpoint 231.

**Limits:** This verifies serialization, rendering and refresh signaling at real service/tool boundaries with synthetic QA learners. It does not verify live-model assessment quality or actual rollout. No course publication, learner migration, staff queue or external communication occurred.


### Checkpoint 233 Match panel access to preserved and pinned progression on October 8 2026

**Accepted:** C8-CHAT-10. Counts advance to 47/162 accepted and 115 open.

Two regressions reproduced inconsistent panel access: unversioned legacy modules were locked by their display number despite having no assessed prerequisites, while a pinned enrollment without its definition could use the fallback unlock flag. The panel now preserves legacy any-order study and requires the actual definition for pinned access. Explicit prerequisites use the selected enrollment's completed modules, independently of display order and the historical unlock flag. Missing pinned requirements explain refreshing the course instead of inventing a preceding-module requirement.

The active service already preserves the original legacy rubric intentionally; the historical temporary-bypass comment remains only in the immutable archived rubric, whose bytes are not rewritten. Pinned competency grading enforces actual prerequisites and every required outcome at the service boundary. Flexible-order V5 definitions have no prerequisite lock and refuse administrative waivers. Exceptional legacy access changes remain scoped and atomically recorded at checkpoint 231, without granting assessed credit.

**Verification:** 51 backend cases pass, including actual legacy and pinned service/chat/HTTP checks: a later module is accessible with no earlier credit, fails without its original answers, and completes only after those answers are saved. Generic pinned prerequisite tests now exercise both values of the historical unlock flag. Twenty-seven frontend cases, the four final hook cases, 14 release-authoring cases, export synchronization, release integrity, targeted Ruff/ESLint, isolated production build and application TypeScript pass. Four normal and two native-200%-zoom browser captures verify keyboard entry into the last legacy module with zero earlier credit, no course writes, readable bounds and no axe/browser errors. Narrow journey and enlarged lesson captures were manually inspected.

Visual reading exposed an adjacent current-copy error: Governance claimed that completing this module alone earns the credential. Current authored panel/chat exports now say every course module is required. The archived pinned teaching package remains unchanged and its historic wording is still a separate content-correction concern under C8-CONTENT-08; actual issuance already requires the full course.

Evidence: `artifacts/visual-review/certification-progression-consistency-2026-10-08/{before.log,backend-verified.xml,frontend-verified.log,hook-final.log,authoring.xml,typescript-copy-final.log,build-copy-final.log,release-integrity.log,isolated-source.json,dist,browser-copy-final,browser-copy-native,checkpoint.json}`. Initial synthetic-fixture signature/type errors and a duplicate-text browser locator failure remain as diagnostics. The frozen build source is separately identified from concurrent shared-tree edits.

**Limits:** Synthetic published packages verify server boundaries, not live calibration or release approval. No actual registry, assessed requirements, learner record, deployment or migration changed. Full accommodation and policy acceptance remain open under C8-DEF-03.


### Checkpoint 234 Retain formative practice separately from reading and credit on October 8 2026

**Accepted:** C8-JOURNEY-02. Counts advance to 48/162 accepted and 114 open.

Knowledge checks now retain the latest twenty explicitly checked answers in browser-local history. The key binds the signed-in learner, enrollment (or legacy course), module, stable lesson ID and revision; the record also requires the exact question/options/feedback definition. Revised questions, different courses, other learners and malformed stored records cannot inherit a practice result. Merely selecting an answer records no attempt. Duplicate Check activation is disabled, and restored history does not preselect or submit an answer.

Chat and panel reuse the same history, including changes in another view or tab. The disclosure labels correct/incorrect practice answers and says the history is browser-local, not synced across devices and not assessed credit. Clearing history affects only that lesson's practice and returns focus to its first choice. Storage failure preserves usable immediate feedback and explains that history was not saved. Historical/unbound cards remain visit-only practice. No practice operation calls the course or grading APIs.

Reading remains a separately labeled cursor and local viewed-state; lesson visits and knowledge checks do not complete modules. Reflections and original assessed evidence keep their existing records and semantics. The server participation boundary from checkpoint 212 continues to reject missing/failed evidence even for high XP, saved reflections and a final reading position.

**Verification:** All 28 targeted frontend cases pass, covering persistence, independent identity/revision/question scope, duplicate checks, corrupt history, clear/focus, two views, another tab, bounded history, storage failure and existing panel/chat navigation. Two real MongoDB cursor cases pass, preserving earned credit and answers while rejecting stale devices. Six normal and three native-200%-zoom captures pass keyboard, reload, chat-to-panel history agreement, clear/focus and storage-failure checks with no course writes, no axe/browser errors and matching page bounds. Narrow chat/panel and native storage-failure images were inspected. Targeted ESLint, isolated production build, application TypeScript and diff checks pass.

Evidence: `artifacts/visual-review/certification-practice-history-2026-10-08/{frontend.log,position.xml,eslint.log,build.log,typescript.log,isolated-source.json,dist,browser,browser-native,checkpoint.json}`. Browser source manifests identify the frozen bundle separately from the shared tree.

**Limits:** Formative history is deliberately local convenience, not cross-device assessment evidence or a staff reporting feed. Browser storage can be cleared by the learner or browser; the UI states that scope. No actual learner/server credit, registry, publication or migration changed.


### Checkpoint 235 Preserve unfinished reflection choices through errors and expiry on October 8 2026

**Accepted:** C8-JOURNEY-07. Counts advance to 49/162 accepted and 113 open.

Legacy reflection choices previously lived only in component state. They now save a browser-tab draft scoped to the authenticated learner, enrollment (or legacy course), module and exact question definition. The UI distinguishes a tab-local draft from answers saved to the course. Reopening or reloading the same question set restores only actual supported choices; a changed user/course/question set or malformed stored value cannot silently transfer answers. Restoring never submits anything. A confirmed complete server answer set takes precedence over a stale draft and removes it. Blocked storage preserves the current form and explicitly asks the learner to keep the page open until submission.

The module passes its actual enrollment identity. Draft writes neither call the agent nor award credit, and the explicit submit callback preserves the learner's selected answer strings. Existing V5 scenario/practical forms retain their scoped drafts and saved original decision/assessment references from the preceding implementation checkpoints; checkpoint 230 verifies that certification tools cannot synthesize required competency decisions from a reflection. No staff queue was introduced.

**Verification:** 28 frontend cases pass, covering required question semantics, original choices while saving, remount/reload, failed submission, scope/definition changes, malformed values, storage denial and confirmed server precedence. Ten actual MongoDB service/tool/HTTP cases pass for original reflection storage, changed-answer grade protection and refusal of obsolete reflection writes into competency courses. Ten normal and five native-200%-zoom captures verify a partial draft, restored complete choices after a simulated 503, simulated 401 plus failed token refresh, explicit identical retry, saved-server presentation and blocked storage. All requests are intercepted in browser QA; the final manifests have no unexpected routes, page errors or axe violations and have matching page bounds. Narrow and native expiry-recovery views were manually inspected. Targeted ESLint, unchanged authored export, isolated build, application TypeScript and diff checks pass.

Evidence: `artifacts/visual-review/certification-reflection-drafts-2026-10-08/{frontend.log,persistence.xml,eslint.log,build.log,typescript.log,isolated-source.json,dist,browser-final,browser-native,checkpoint.json}`. Expected simulated 503/401 console messages are retained; they are exercised recovery cases.

**Limits:** Unsubmitted drafts live in the browser tab, not across devices or after tab storage is discarded; that scope is explicit in the form. The expiry test exercises authenticated HTTP failure and unsuccessful refresh transport with synthetic authentication, not a live identity-provider outage. No actual learner record, course publication, model invocation or external communication changed.


### Checkpoint 236 Reject stale unversioned progress writes on October 8 2026

**Status:** Complete for legacy progress concurrency protection; C8-CHAT-07 remains in progress for request replay and provisioning deduplication. Counts remain 49/162 accepted and 113 open.

A two-client MongoDB regression reproduced a real lost-credit race: while one module completion was waiting to save, another module earned credit; the delayed request then returned success and replaced the newer progress with its older total/modules. Unversioned writes now read one operation-bound progress snapshot and compare the original fields plus a private revision in the same atomic Mongo update. A stale save returns a conflict without replacing newer work; a fresh retry reads that work and awards only the missing credit. Validation and completion use the same original snapshot, so changed reflection answers cannot receive an older grade.

The fallback has an explicit learner/read-or-write context, refuses changed enrollment/fence/admin state, and rejects new work through an inherited context after its request has ended. Multiple saves within one legitimate request update their baseline. Private support history and unknown historical fields are retained. Concurrent first reads use a stable new-record identity so only one unversioned progress document is inserted; existing identifiers are unchanged. Ambiguous historical records fail closed instead of selecting one arbitrarily. This introduces no expiring lock, automatic enrollment, staff grading queue or forced course upgrade.

**Verification:** The original lost-credit regression fails before the fix. All 1,263 certification unit/tool contracts pass. The initial 44-case persistence run had one old fixture that directly saved a detached legacy model; after using the required write boundary, both legacy/versioned cases pass. All 70 final focused boundary cases pass, including nine legacy concurrency/lifecycle cases, earlier progression/access checks and completion/tool compatibility. Fifty-four separate persisted source/project/field-access regressions pass. Targeted Ruff and diff checks pass. This changes server concurrency, not UI markup; existing conflict/error presentation remains applicable.

Evidence: `artifacts/visual-review/certification-legacy-concurrency-2026-10-08/{before.xml,first-fix.xml,contracts.xml,persistence.xml,access-recheck.xml,access-regression.xml,final-boundary.xml,ruff-verified.log,checkpoint.json}`. The initial one-fixture failure is retained explicitly rather than counted as a wholly passing run.

**Limits and next work:** This prevents stale progress replacement; it does not yet make every unversioned request replay an immutable receipt or deduplicate external document provisioning. Those remain open under C8-CHAT-07. Deployment must replace/drain workers still running the previous unguarded fallback; local verification does not establish a mixed-worker rollout. No actual learner record, registry, deployment, publication, migration or communication changed. The actual registry SHA-256 remains `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`.


### Checkpoint 237 Replay identified legacy completion requests from original receipts on October 8 2026

**Status:** Complete for identified legacy completion replay; C8-CHAT-07 remains in progress for provisioning and the remaining submission matrix. Counts stay 49/162 accepted and 113 open.

A regression reproduced the old behavior: after a successful legacy completion and a later answer edit, retrying the same request regraded the changed answers and returned a different result. Identified legacy requests now save the exact successful or failed result with the progress update, then copy that receipt to an insert-only collection scoped to learner, progress record and request. A lost copy or response recovers the original result without evaluating mutable answers/artifacts again. Later completions preserve older receipts. Changed module bindings, invalid references and corrupt saved results fail closed; one learner cannot reuse another learner's result.

The panel now keeps its completion reference for legacy progress across uncertainty and remounts, as it already did for pinned enrollments. Live chat derives a stable reference from the authenticated learner, conversation, turn, tool-call identity, module and supplied enrollment when no explicit reference is given. Explicit retries retain their original reference. Low-level legacy callers without a request reference remain compatible; they do not receive an immutable request-replay guarantee.

Concurrent identical identified calls can save only one winning attempt and award; the losing stale worker receives a conflict and can retrieve the winner on retry. A failed assessment retains its original failure; corrected work needs a new explicit request. Pinned continuation copies any pending legacy receipt before replacing the progress receipt. Account deletion includes the new private receipt collection. This adds no staff queue, enrollment migration or new grading rule.

**Verification:** 92 distinct backend cases pass across the four final suites: 31 persisted concurrency/replay/continuation/routing cases and 61 contract/compatibility cases. Fifty-one frontend hook/API/stream cases pass, including legacy reference retention through remounts. Targeted Ruff, ESLint, isolated application TypeScript and diff checks pass. The change introduces no new UI markup; existing uncertain-completion presentation remains applicable.

Evidence: `artifacts/visual-review/certification-legacy-replay-2026-10-08/{before.xml,persistence.xml,compatibility.xml,same-request.xml,live-chat.xml,frontend.log,typescript.log,typecheck-source.json,ruff-verified.log,eslint.log,checkpoint.json}`. The original failing replay case is retained. The isolated typecheck manifest identifies the two updated hook files relative to checkpoint 235.

**Limits:** Legacy receipts freeze the returned original judgment; they do not retroactively create missing immutable lab evidence or assert V5 competency. Browser references are tab-local. Live-model behavior, external provisioning deduplication and mixed-worker deployment remain separate gates. No actual learner, registry, deployment, publication or communication changed.


### Checkpoint 238 Keep legacy sample reuse inside the selected lab on October 8 2026

**Status:** Complete for lab-folder scoping; C8-CHAT-07 and C8-JOURNEY-06 remain in progress. Counts remain 49/162 accepted and 113 open.

Legacy provisioning could reuse an owned same-named document from anywhere in the workspace, even when the actual sample already existed in the Certification Lab. Two disposable MongoDB regressions reproduced this incorrect assignment. Both legacy and pinned courses now restrict the existing-document query and canonical access check to the selected lab folder. Missing samples are uploaded to that folder, and unrelated personal files remain unchanged.

**Verification:** The before run has two reproduced legacy failures and two passing pinned-course cases. All 26 final persisted scope/project-access cases pass, including existing/missing lab copies, denied contribution rights, authorized project sources and revocation. Upload dispatch is mocked in the new scope cases; these establish selection and routing, not real ingestion. Targeted Ruff passes. No UI markup changed in this checkpoint.

Evidence: `artifacts/visual-review/certification-provisioning-scope-2026-10-08/{before.xml,persistence.xml,ruff.log,checkpoint.json}`.

**Limits:** Folder scoping does not deduplicate concurrent external creation or establish document processing readiness. Those remain explicit next work. No actual learner file, registry, publication, migration, deployment or communication changed.


### Checkpoint 239 Show actual assigned sample status and safe recovery on October 8 2026

**Accepted:** C8-JOURNEY-06. Counts advance to 50/162 accepted and 112 open.

The panel previously called a lab ready whenever progress contained a document ID. An authenticated read-only status route now inspects only the selected course's assigned references in its lab, through canonical folder/document access. It distinguishes not set up, processing, text ready, failed and unavailable; missing, moved, deleted, transferred, revoked, malformed or unknown-status sources cannot become ready by filename substitution. It exposes authored filenames and accessible folder identity, not raw text or private worker diagnostics. Readiness means extracted text is available, not that the learner passed, that source quality is perfect, or that every downstream capability is ready.

The panel shows explicit preparation, per-file state, the resulting folder and the next safe action. Status refresh never uploads or awards credit. Processing explains that closing the panel does not cancel work; failure directs the learner to inspect/retry the file's processing instead of implying setup repairs it. Unavailable status supports checking access and explicitly restoring missing samples. Transport errors clear stale readiness and retain a read retry. Reopening reads current saved state without restarting setup. Late responses from another module/course are rejected. The module view is also keyed to learner/progress identity.

Browser QA caught lost keyboard focus caused by disabling the refresh button. Repeated checks are now guarded without dropping focus; setup hands focus to the status control. Visual inspection caught contradictory green assignment styling beneath a processing failure; the challenge-instructions link now uses neutral styling and a 44px target. Inline assignment text no longer claims processing readiness.

**Verification:** Five real MongoDB integration cases pass, including legacy/pinned source-state and permission transitions, authenticated course isolation, and connected HTTP setup followed by processing/failed/ready reads. Real folder creation and assignment persistence are exercised; external upload/Celery is stubbed and worker fields are advanced explicitly. Sequential setup reuse uploads once. All 29 targeted frontend cases pass. Fourteen final narrow/desktop captures and seven native-200%-zoom captures pass axe, page/region bounds, reload, explicit setup, status-only retries, errors and keyboard-focus assertions; final manifests contain no unexpected requests or browser errors. Narrow failure and native ready images were inspected. Targeted Ruff, ESLint, isolated production build, application TypeScript and diff checks pass.

Evidence: `artifacts/visual-review/certification-lab-status-2026-10-08/{persistence-final.xml,frontend-verified.log,build-reviewed-final.log,typescript-reviewed.log,eslint-reviewed.log,ruff-final.log,isolated-source.json,dist,browser-reviewed,browser-native-reviewed,checkpoint.json}`. Earlier focus failure and interim visual iterations remain as evidence; expected simulated 503 console messages are retained.

**Limits:** This closes the setup control and truthful status delivery item, not real external ingestion execution or concurrent creation deduplication. Those remain separate acceptance work. No live learner record, file, registry, publication, deployment, migration, staff queue or model invocation changed.


### Checkpoint 240 Reject invalid fallback setup before external creation on October 8 2026

**Status:** Complete for early course binding; C8-CHAT-07 remains in progress. Counts stay 50/162 accepted and 112 open.

A disposable regression showed that legacy setup created a folder and dispatched an upload before finally discovering that progress was already pinned and required its enrollment write boundary. Setup now reads and binds its original progress before creating folders or uploading samples. Existing folder contribution checks still run, and the final assignment saves through the same bound snapshot. Pinned, fenced and ambiguous saved records fail before external creation, whether or not a lab folder already exists.

**Verification:** The original regression fails on an unexpected folder-creation call before the fix. All 32 persisted setup, source-access and status regressions pass. An expanded ten-case scope/boundary suite passes, including six invalid-record/existing-folder combinations; the four folder-scope cases overlap the broader run. Targeted Ruff and diff checks pass. This is a server-boundary change with no new markup.

Evidence: `artifacts/visual-review/certification-provisioning-boundary-2026-10-08/{before.xml,persistence.xml,boundaries.xml,ruff.log,checkpoint.json}`.

**Limits:** Reading progress early prevents invalid fallback creation and binds the final conditional save; it does not make external uploads transactional or deduplicate concurrent creation. No actual learner, file, course publication, migration, deployment or communication changed.


### Checkpoint 241 Recheck current lab rights before assigning uploaded samples on October 8 2026

**Status:** Complete for post-upload assignment checks; C8-CHAT-07 remains in progress. Counts stay 50/162 accepted and 112 open.

A persisted regression reproduced setup saving a new assignment after an editor was downgraded to a project viewer during upload. Before the final progress save, setup now rechecks contribution access to the lab and canonical ownership, folder and expected filename for every proposed source. It checks reused sources again after later uploads and rejects duplicate returned document identities. Newly moved, deleted, renamed, transferred or revoked sources cannot silently become the saved assignment.

A failed check preserves the earlier module assignment and earned work. It does not delete uploaded files or roll back external processing; those may already exist and must not be mistaken for newly accepted course evidence. Restoration of normal access and an explicit later setup can reuse legitimate owned lab copies.

**Verification:** The original viewer-downgrade case fails before the fix. All 47 persisted setup/access/status cases pass, including ten mid-upload source/access changes and the prior scope, early-binding and HTTP readiness cases. Four additional legacy/pinned cases pass for renamed results and revocation of the first reused batch sample while two later samples upload. Targeted Ruff and diff checks pass. External ingestion is simulated; folders, documents, assignments and project permissions use disposable MongoDB. No UI markup changes in this checkpoint.

Evidence: `artifacts/visual-review/certification-provisioning-revocation-2026-10-08/{before.xml,persistence.xml,reused-source.xml,ruff-final.log,checkpoint.json}`. One test-launch permission review timed out; its permitted retry succeeded. No permission denial remains.

**Limits:** These are current authorization checks at the assignment boundary, not a transaction across every project/document collection and external system. They do not deduplicate concurrent creation or undo completed side effects. No actual learner, file, registry, publication, migration, deployment or communication changed.


### Checkpoint 242 Preserve mounted workspace drafts when leaving lab setup on October 8 2026

**Status:** Complete for the lab-to-Files handoff; related C8-JOURNEY-08 remains in progress for exact artifact/editor routing. C8-VIS-10 preservation is rechecked. Counts stay 50/162 accepted and 112 open.

The old Open Workspace anchor performed a full page load. Browser QA against the archived checkpoint-239 bundle reproduced that reload while a synthetic workflow draft was open. The application now supplies a client-side Files navigation callback to the global course panel. It preserves current editor, document/knowledge/project/share-token search state, waits for navigation, then closes the panel through its existing focus-return behavior. The workspace and original draft inputs stay mounted. The control says Open Files in workspace. Pending navigation is guarded against repeated activation; navigation failure keeps the course open with a retry instead of losing the learner's place.

**Verification:** All 31 targeted frontend cases pass, including a single pending handoff and retained lab/error retry. The first parallel run timed out in two existing focus tests under load; the single-worker rerun passes all cases. Application TypeScript caught missing required search fields; the final callback preserves them explicitly and passes. Final ESLint, isolated production build and diff checks pass. Fourteen normal browser captures cover 320px, 1024px and 1440px; seven native-200%-zoom captures cover compact chat and desktop editors. They verify the original workflow/extraction/chat input nodes remain connected, unsent values and selected files survive, route identities are retained, Files opens, and returning to Chat reveals the original draft. A page sentinel confirms no reload. All API writes are intercepted and none occur; final manifests have no browser errors, unexpected requests, axe failures or page overflow. Narrow handoff and enlarged resumed-chat images were inspected.

Evidence: `artifacts/visual-review/certification-lab-handoff-2026-10-08/{browser-before,frontend-final.log,typescript-final.log,eslint-final.log,build-final.log,isolated-source.json,dist,browser-reviewed,browser-native-reviewed,checkpoint.json}`. Earlier narrow harness runs incorrectly queried a hidden compact Chat pane by accessible role; the final harness checks its retained original input and explicitly reopens Chat. Those diagnostic runs remain separate from final evidence.

**Limits:** This opens Files within the current workspace; it does not yet select an exact course artifact or assert successful external processing. No actual learner record, file, publication, migration, deployment, model request or external communication changed. The actual registry SHA-256 remains `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`.


### Checkpoint 243 Open the selected preparation artifact without leaving the course on October 8 2026

**Status:** Complete for practical-preparation extraction and workflow-design links; C8-JOURNEY-08 remains in progress for remaining modules and the full handoff journey. Counts stay 50/162 accepted and 112 open.

Learners choosing a practical extraction or workflow design could see its name but had no exact editor handoff. The selected owned choice now exposes an encoded relative link to that specific extraction/workflow. It explicitly opens a new tab, leaving the original course form, lesson and workspace draft mounted. Guidance explains why to use the editor, to return to the original course tab after saving, refresh choices before capturing a new revision, and that current workspace edits do not replace saved assessment evidence. Pending/blocked capture controls offer no active navigation link. Older unverified references are not turned into assumed-owned links.

**Verification:** All 26 focused frontend cases pass, including exact destination identity, query escaping, new-tab isolation, disabled unresolved work, and selection without preparation/capture/approval side effects. ESLint, isolated build, application TypeScript and diff checks pass. Final browser runs cover extraction and workflow at 320px and 1440px, plus native 200% zoom at a 780px viewport. Twelve normal captures comprise eight course views and four editor views; six native captures comprise four course views and two editor views. Original course forms, selected IDs and unsent chat nodes remain intact; editor URLs identify the selected artifacts, opener access is absent, and no API writes or model requests occur. All course/editor axe and page-bound checks pass. Final manifests have no unexpected routes or page errors; popup captures and checks are recorded in their observations. Narrow link and enlarged workflow-editor images were inspected.

Evidence: `artifacts/visual-review/certification-editor-links-2026-10-08/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,dist,browser-final,browser-native-final,checkpoint.json}`.

The first browser runs exposed test-harness storage setup running in opaque popup/axe frames and three missing workflow read fixtures. Harness setup now tolerates unavailable storage only around its own optional fixture writes; application page errors remain tracked. The missing read routes are explicitly intercepted. Those failed fixture runs remain in the earlier directories and are not final evidence.

**Limits:** These links inspect/edit current workspace artifacts; they do not execute, capture, grade or update an existing attempt. Return is to the retained original course tab. Remaining module selectors and exact source navigation still need coverage. No actual learner, artifact, registry, publication, migration, deployment or external communication changed.


### Checkpoint 244 Extend exact editor links across the remaining assessment selectors on October 8 2026

**Status:** Complete for six additional initial selectors; C8-JOURNEY-08 remains in progress. Counts stay 50/162 accepted and 112 open.

Connected, budget and output workflow choices, plus validation, batch and capstone extraction choices, now offer the same explicit new-tab editor handoff. Links resolve only selected entries in the current owned listing. Existing pending/blocked and history-only boundaries remain in place. The original course form and unsent chat remain mounted, with guidance to return after saving and refresh before capturing another revision. The validation repair state is separate follow-up work because its selector intentionally fixes the original artifact.

**Verification:** All 98 targeted frontend cases pass. Isolated application TypeScript, production build, targeted ESLint and diff checks pass. Final browser evidence contains 36 normal captures across 320px and 1440px and 18 captures at native 200% zoom, covering all six course forms, exact popup editors and retained original tabs. Destination IDs, opener isolation, original chat nodes and selected IDs are asserted; no API writes or model calls occur. Axe, page bounds, errors and unexpected-route checks pass. Narrow budget and enlarged capstone layouts were inspected. Earlier full browser passes used a short synthetic extraction ID; final runs use realistically formatted IDs so the extraction capture controls also reflect a valid choice. No production correction was needed for that fixture adjustment.

Evidence: `artifacts/visual-review/certification-assessment-editor-links-2026-10-08/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,dist,qa-script.mjs,browser-final,browser-native-final,checkpoint.json}`. Popup captures are recorded within manifest observations.

**Limits:** This verifies initial selection and editor navigation, not saving a repaired artifact, capturing it or grading the revised evidence. Complete return-to-course action and source navigation remain acceptance work. No actual learner, artifact, registry, publication, migration, deployment or external communication changed.


### Checkpoint 245 Open the same extraction from preserved repair evidence on October 8 2026

**Status:** Complete for validation and capstone repair editor handoffs; C8-JOURNEY-08 remains in progress. Counts stay 50/162 accepted and 112 open.

Regression checks reproduced two gaps: validation's intentionally fixed original-artifact selector also disabled its editor link, and a saved capstone source finding had repair instructions but no direct editor handoff. Validation now permits inspecting/editing that same owned extraction while keeping the selector fixed. The capstone finding links to its exact captured extraction only when that identity is still present in the current owned listing. Existing pending/history controls remain. Opening an editor does not recapture, rerun, grade or replace the original failed evidence.

**Verification:** Both regressions fail before the production fixes and all 41 targeted frontend cases pass afterward. A new reusable validation fixture records real authenticated local HTTP capture, expectations, approved execution and original semantic failure using a synthetic provider and disposable MongoDB on port 27029; its database is dropped afterward. The capstone reuses the existing disposable HTTP fixture. Final browser evidence contains twelve normal and six native-200%-zoom course/editor captures, with exact artifact IDs, retained original failure/finding selection and original chat nodes, opener isolation, zero API writes/model requests, clean axe/page bounds and no unexpected routes or page errors. Desktop optional-field and enlarged capstone repair images were inspected.

The desktop editor check found a measured contrast failure in the optional-field badge. Its foreground is now darker in both field-list and validation views. Final isolated build, application TypeScript and diff checks pass. Targeted ESLint has no errors; the existing editor file retains two unrelated hook-dependency warnings. An initial validation test import typo was corrected before the recorded behavioral regression. Earlier failed contrast evidence is retained separately.

Evidence: `artifacts/visual-review/certification-repair-editor-links-2026-10-08/{before.log,before-validation-corrected.log,frontend.log,fixture.log,export-fixture.py,validation-http.json,build-final.log,typescript-final.log,eslint.log,eslint-editor-final.log,isolated-source.json,dist,qa-script.mjs,browser-final,browser-native-final,checkpoint.json}`.

**Limits:** This proves repair navigation with preserved original evidence; it does not establish a new saved repair or live-model accuracy. Dedicated return-to-course action and exact current sample-file navigation remain acceptance work. No actual learner, source, registry, publication, migration, deployment or external communication changed.


### Checkpoint 246 Inspect the exact assigned sample and return to the course on October 8 2026

**Status:** Complete for current assigned-sample navigation and modal return; C8-JOURNEY-08 remains in progress for the editor return affordance. Counts stay 50/162 accepted and 112 open.

Each accessible lab sample now has an explicit view action. The full-screen source preview rechecks the selected course, original document ID, authored filename and lab assignment before mounting the existing PDF viewer. Missing, moved or inaccessible assignment responses cannot silently open a different source; the download endpoint independently enforces current source access. The preview clearly distinguishes the current assigned file from an assessment's original captured copy and awards no credit. Pending status/provisioning offers no view action.

The preview keeps the course and chat mounted. Return to course and Escape close only the source preview and restore focus to its original source button; modal Tab/Shift+Tab remain inside the preview. Unavailable course binding supports a read-only retry, and a file removed or revoked after the status check receives the viewer's source-unavailable state with course-specific guidance. Existing workspace viewer copy remains the default outside this course context.

**Verification:** All 17 targeted frontend cases pass, including wrong course/source/name/folder, late response rejection, explicit access retry and the earlier setup/handoff controls. All 17 existing download-authentication, inline/range and project-access contract cases pass. Ten normal browser captures use 320px/1440px widths and a 650px viewport height; five native-200%-zoom captures use 780 physical pixels and 650 CSS pixels of height. They render the actual authored NSF PDF bytes and verify access recheck, a later file denial, modal keyboard containment, return focus, retained course/chat and zero API writes. Axe, page bounds and unexpected-route/page-error checks pass. Narrow PDF and enlarged unavailable-source screenshots were inspected. Expected simulated 404 and aborted PDF cleanup requests are retained in logs.

Final isolated build, application TypeScript and diff checks pass. Targeted ESLint reports no errors and one existing unrelated DocumentViewer hook-dependency warning. Evidence: `artifacts/visual-review/certification-sample-preview-2026-10-08/{frontend.log,file-access.xml,build.log,typescript.log,eslint.log,isolated-source.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`.

**Limits:** This is current lab-source inspection, not proof of real ingestion or a replacement for captured assessment-source evidence. Assistive-technology observation and the editor-tab return action remain separate work. No actual learner, sample, grade, registry, publication, migration, deployment or external communication changed.


### Checkpoint 247 Return explicitly from the editor to the retained course tab on October 8 2026

**Status:** Complete for explicit editor-tab return; C8-JOURNEY-08 remains in progress for a correctly saved instruction repair and recapture. Counts stay 50/162 accepted and 112 open.

Course editor links now carry a dedicated handoff marker. Those editor tabs show save-first guidance and an explicit Close editor tab and return to course action. It closes only on learner activation and does not save, run, capture or grade work. If the browser refuses to close, it keeps the editor open and offers to open the learning panel there. Ordinary workspace tabs do not show this close action. Unsaved changes in the editor must be saved before using the explicitly labeled close action; the original course and its chat draft remain intact.

Browser QA caught the router parsing the marker as numeric 1 instead of string 1; validation accepts both representations. WebKit returned to the original tab but pointer activation focused the containing course panel instead of its link. DOM focus tracing identified that behavior. The link now explicitly focuses itself on ordinary or middle-button activation, without installing a global focus restorer or stealing later input focus.

**Verification:** All 38 targeted frontend/workspace cases pass, including the blocked-close fallback, ordinary workspace exclusion and activation focus. Final Chrome evidence includes 32 normal and 16 native-200%-zoom captures for practical extraction, workflow design and both saved repair states. Sixteen additional WebKit captures pass. All verify actual popup closure through the new action, active original tab and link focus, retained form selections, original failed-run/finding references, original chat input nodes and zero API writes/model calls. Axe, page bounds, unexpected routes and page errors pass. Narrow workflow-return and enlarged validation-return layouts were inspected. Isolated build, application TypeScript, targeted ESLint and diff checks pass. An initial WebKit launch used an empty default cache; the verified run uses the existing isolated installation under `/private/tmp/vandalizer-certification-browsers`.

Evidence: `artifacts/visual-review/certification-editor-return-2026-10-08/{frontend-verified.log,build-verified.log,typescript-verified.log,eslint.log,eslint-verified.log,isolated-source.json,dist-verified,qa-editor-verified.mjs,qa-repair-verified.mjs,browser-verified,browser-native-verified,repair-browser-verified,repair-browser-native-verified,browser-webkit-verified,checkpoint.json}`. Earlier marker/focus failures and traces remain diagnostic evidence; the earlier `dist` is an interim bundle.

**Remaining handoff gap:** Inspecting the actual editor revealed that its existing field-rename handler sends both searchphrase and title. The course requires changing a field's extraction instructions while preserving its required name and identity. That needs an explicit independent instruction control and connected save/recapture verification before accepting the complete journey item. No actual learner, artifact, grade, registry, publication, migration, deployment or external communication changed.


### Checkpoint 248 Save an instruction repair and retain its original attempt on October 8 2026

**Status:** Complete; C8-JOURNEY-08 accepted. Counts are 51/162 accepted and 111 open. This accepts editor handoff continuity, not a new 8/10 grade or a released course.

The extraction editor now separates required field names from extraction instructions. Expanding a field offers an explicitly labeled instruction form and Save instructions action; saving sends only searchphrase. Names, field IDs, optional settings and allowed values remain unchanged. Names render independently, with wrapping controls at narrow widths. Renaming a field preserves an already customized instruction. Instruction edits never save merely on blur, disable duplicate pending submissions, retain drafts after unconfirmed saves and detect refreshed instructions that conflict with a local draft. An explicit reset adopts the current saved instructions.

**Verification:** All 37 targeted frontend cases pass, along with a new real authenticated PATCH/read/recapture persistence case. A connected browser fixture uses the actual extraction item and certification APIs backed by disposable MongoDB on 27029. Starting from a seeded original failure, each browser edits the exact field, receives a simulated save denial, retains and retries the draft, saves the instruction, closes the editor through the product return action, recaptures the changed artifact and prepares a retest linked to the unchanged original run and complete expectations. Original chat nodes and selected artifact identity remain intact. Original captured evidence is byte/hash stable; XP stays zero and no additional model execution or grading occurs.

Final evidence contains twelve normal Chrome captures, six native-200%-zoom Chrome captures and twelve WebKit captures. Axe, page bounds, unexpected routes and page errors pass. Desktop original instructions, narrow saved controls and enlarged retry states were inspected. Isolated build, application TypeScript and diff checks pass. Targeted ESLint has no errors and two existing unrelated editor hook warnings.

WebKit exposed an existing incidental write: moving focus away from an unchanged Allowed values input submitted enum_values. The editor now compares normalized values before saving. The final browser check explicitly focuses and leaves that input and requires zero writes before the instruction save. Earlier WebKit traces and the initial history-order selector failure are retained as diagnostics. The persistence fixture initially lacked the complete authenticated User shape; it was corrected without bypassing authorization.

Evidence: `artifacts/visual-review/certification-field-instructions-2026-10-08/{frontend-related.log,frontend-editor.log,persistence.xml,build-final.log,typescript-final.log,eslint-final.log,isolated-source.json,dist-final,qa-script-final.mjs,qa-server.py,browser-final,browser-native-final,browser-webkit-final,server.log,checkpoint.json}`.

**Limits:** The original failure uses a synthetic provider; this verifies persistence, handoff and linked preparation, not live-model repair accuracy. The preparation remains unapproved and unexecuted. Surrounding workspace/course presentation uses fixtures; extraction field reads/writes, captures and retest preparation use real local APIs. The disposable server is stopped and its database removed. No actual learner, artifact, grade, registry, publication, migration, deployment or external communication changed.


### Checkpoint 249 Reuse one course lab folder after races and interrupted creation on October 8 2026

**Status:** Complete for lab-folder creation identity; C8-CHAT-07 remains in progress for document storage/queue side effects and the remaining submission matrix. Counts stay 51/162 accepted and 111 open.

Two disposable MongoDB regressions reproduced duplicate labs: two legacy setup requests both observed no folder, and a pinned-course request created a folder but failed before saving its progress reference. Retrying the latter created another folder. New lab creation now uses a deterministic identity bound to the learner, original progress record and enrollment (or unversioned context). A MongoDB set-on-insert uses built-in _id uniqueness to converge competing workers and recover an unknown creation response. It needs no expiring lease, in-process mutex or new staff queue.

Existing assigned labs still use their current reference and access checks. Replaying creation preserves user renames and moves, checks the stored creation identity and ownership, and rechecks current contribution access before uploading into the recovered folder. Conflicting identity, transferred ownership/team, or a newly inaccessible project fails without replacing the folder or assigning it to progress. No existing folder is migrated or renamed by this change.

**Verification:** Both regressions fail before the fix. The provisioning/source/project-access suite passes 48 cases. The expanded folder recovery suite passes nine cases (two overlap), for 55 distinct passing persistence cases. These include a response lost after committed creation, preserved user changes, four conflicting-identity cases, a recovered folder moved into a private project and a different learner supplying someone else's progress. All run against disposable MongoDB on port 27029. Ruff and diff checks pass.

Evidence: `artifacts/visual-review/certification-lab-folder-identity-2026-10-08/{before.xml,persistence.xml,recovery-final.xml,ruff-final.log,source-hashes.json,checkpoint.json}`.

**Limits:** Uploads are deliberately stopped or mocked in the new folder tests. This establishes one canonical folder, not exactly-once document creation, storage writes or queue execution. Those still require durable side-effect identity and safe recovery; a timeout lock would not establish that guarantee. No actual learner folder, course registry, publication, migration, deployment, model execution or external communication changed.


### Checkpoint 250 Arbitrate concurrent sample creation before background dispatch on October 8 2026

**Status:** Complete for concurrent course sample creation; C8-CHAT-07 and interruption recovery remain in progress. Counts stay 51/162 accepted and 111 open.

A real upload-service regression reproduced two sample records after parallel setup requests both passed the filename lookup. Course uploads now carry an internal creation key bound to the learner, original progress/enrollment, lab, filename and source bytes. A partial unique MongoDB index arbitrates active course sample insertion. Both requests may stage separate storage objects, but only the inserted candidate dispatches processing. The losing request reuses the canonical sample and removes its own unused storage object. Temporary local task files for remote storage are created only after winning insertion.

The new index excludes ordinary uploads and inactive/deleted samples. An explicit rename or move releases the course creation binding, so the learner can keep or move earlier work and set up a replacement without an index collision blocking later edits. The binding is creation metadata, not immutable assessment evidence. Existing captured work remains separate. A repeated setup after an unknown dispatch response reads the same sample and does not automatically dispatch again, claim readiness or award credit.

The lab's pending message now says Sample text is not ready yet and Text processing has not finished. Stored in-progress flags do not prove that a worker is currently running; queued or interrupted work must not be described as confirmed active execution.

**Verification:** The duplicate-creation regression fails before the fix. Sixty provisioning/folder/source-access persistence cases pass, and the final eight-case source lifecycle/dispatch suite adds three distinct cases, for 63 distinct passing persistence cases. These cover successful and unknown dispatch responses, one canonical sample/dispatch, cleanup of the losing staged object, replay without redispatch, retained processing status, replacement after deletion/rename/move, ordinary preexisting duplicate names, and real rename/move operations. Storage is in memory and queue dispatch is stubbed; MongoDB uses disposable databases on port 27029. All 16 existing upload-size/dispatch contract cases and 17 frontend lab/preview cases pass.

Fourteen normal and seven native-200%-zoom browser captures pass axe, bounds, pending-state reload, keyboard focus, error recovery and zero additional setup writes during status refresh. The enlarged pending layout was inspected. Browser status responses are fixtures; they do not establish worker execution. Isolated frontend build, Ruff and diff checks pass.

Evidence: `artifacts/visual-review/certification-sample-creation-2026-10-08/{before.xml,persistence-final.xml,dispatch-boundary.xml,uploads.xml,frontend.log,build.log,ruff-final.log,source-hashes.json,isolated-source.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`.

**Remaining limits:** An interrupted insertion/dispatch or stalled worker still needs safe reconciliation and re-execution; this change does not make the entire storage/broker/worker sequence transactional. Failed cleanup may leave an unused staged object and is logged. Deployment must ensure the new index and drain/replace older upload code before relying on the concurrency guarantee. No index was installed in the application database, no actual learner/sample changed, and no live storage, queue, model, course publication, migration, deployment or external communication occurred. The course registry hash is unchanged.


### Checkpoint 251 Claim extraction retries before dispatch on October 8 2026

**Status:** Complete for concurrent retry arbitration; C8-CHAT-07/09 remain in progress. Counts stay 51/162 accepted and 111 open.

Two regressions reproduced duplicate retry dispatch and a stale retry erasing newly completed text. Retry extraction now atomically compares the source identity, access context, extraction state and original evidence before clearing text or dispatching work. Only one matching snapshot can claim a restart. A changed document or competing request returns an actionable HTTP 409; an unknown dispatch response remains pending and does not immediately dispatch a second copy. Knowledge-base retry restores its preceding source status if its document claim loses.

The restart revision is stored as private database metadata, loaded into the model without inclusion in normal model saves. This prevents an older worker save from resetting the counter. Initial persistence checks exposed Beanie's automatic field projection dropping the private counter; full document projection now preserves it. This protects restart arbitration, but does not fence late worker results or prove safe recovery of an actually stalled worker.

**Verification:** Both initial regressions fail before the fix. All 40 retry, sample-creation and project-access persistence cases pass against disposable MongoDB on 27029. Ten directly cover retry arbitration, stale completed text, old worker saves, unknown dispatch, actual concurrent authenticated HTTP requests and changed ownership/folder/deletion/path/OCR decisions. All 135 related document, task, route, knowledge-base and file-access contract tests pass. Ruff and diff checks pass. An initially misplaced route test was corrected; diagnostic failures remain in the evidence directory.

Evidence: `artifacts/visual-review/certification-extraction-retry-2026-10-08/{before.xml,persistence-verified.xml,boundaries.xml,contracts-final.xml,document-contracts.xml,source-hashes.json,checkpoint.json}`.

**Limits:** Dispatch is stubbed and no actual queue or model runs. Existing stale-extraction timing policy is unchanged. This is not an exactly-once worker guarantee and does not establish automatic reconciliation after interrupted processing. No actual learner, application database, registry, course publication, migration, deployment or external communication changed.


### Checkpoint 252 Keep in-flight assessment rules through course publication on October 8 2026

**Status:** Complete; C8-VERSION-05 accepted. Counts are 52/162 accepted and 110 open.

Four new persistence cases pause actual completion before/after grading, a practical extraction inside the provider thread, and automatic review inside the model boundary. While paused, a disposable successor course publishes changed lesson revisions and exercise bytes and retires the original only for new enrollment. New learners receive the successor. Existing learners retain the same enrollment, original attempt content/exercise/rubric hashes, captured input plan, scope approval and reviewer evidence. Finishing retains those identities and replay neither grades nor dispatches again. Practical execution/review alone awards no credit or credential and creates no staff review.

**Verification:** Seventeen boundary cases pass, including the four new cases plus initial-enrollment publication recovery, original completion receipt recovery, parallel chat isolation, scenario replay and changed runtime/implementation refusal before dispatch. Ruff and diff checks pass. Existing all-module evidence binding and preserved grading/issuance coverage remain documented at checkpoints 224–230. No production change was needed for this acceptance item.

Evidence: `artifacts/visual-review/certification-publication-boundary-2026-10-08/{persistence.xml,boundaries.xml,source-hashes.json,checkpoint.json}`.

**Limits:** Publication affects only copied test catalogs and disposable MongoDB on 27029. Providers are synthetic, so this proves identity and persistence rather than assessment accuracy. Changed incompatible runtime code must refuse prepared work instead of silently changing its meaning; maintaining supported old runners and coherent production rollout remain C8-VERSION-06/11. No actual catalog, learner, live provider, course publication, migration, deployment or external communication changed.


### Checkpoint 253 Preserve authored practical drafts through navigation on October 8 2026

**Status:** Complete for validation expectations and Governance memo/supervision drafts; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

These forms previously kept unsubmitted answers only in mounted React state. They now retain tab-local drafts under the authenticated learner, enrollment, manifest, exact saved source/run/result and exercise revision. Returning restores the original authored input without submitting, approving execution, grading or awarding credit. Changed users, courses, inputs or revisions receive separate drafts. A revised supervision explanation also binds its original submission. Validation restores only the expected source/field structure. Storage failure preserves the current in-memory edit and explains that the form must remain open until an explicit course save.

**Verification:** All 49 new and related frontend cases pass, including immediate unmount/reload, six identity changes, unconfirmed submission, malformed saved expectations, blocked storage and original/revised explanation separation. TypeScript, ESLint, isolated production build and diff checks pass. Eighteen normal Chrome, nine native-200%-zoom Chrome and eighteen WebKit captures verify restored authored values, storage warnings, no API writes and no model execution. Axe, bounds, unexpected routes and browser errors pass. Enlarged restored expectations and the narrow memo storage warning were visually inspected.

The initial WebKit run navigated away before unrelated fixture reads finished, producing cancelled-read access-control errors. The final script waits for each page's background reads before navigation; it does not suppress those errors. The failed run remains diagnostic evidence.

Evidence: `artifacts/visual-review/certification-practical-drafts-2026-10-08/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,dist,qa-script-initial.mjs,qa-script-final.mjs,browser,browser-native,browser-webkit-final,source-hashes.json,checkpoint.json}`.

**Limits:** Browser APIs use synthetic saved-history fixtures. Draft storage is local to this tab, not a server save or cross-device synchronization. Other practical controls and full optional-switch draft coverage remain open. No actual learner, submission, grade, release, migration or external communication changed.


### Checkpoint 254 Retain scope-choice drafts without granting execution on October 8 2026

**Status:** Complete for validation, batch, output, budget and Governance execution-scope drafts; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

The five forms now preserve the learner's unsubmitted choice and explanation in tab storage. Their binding includes user, enrollment, manifest, run, plan, case and current saved approval. Changing either the prepared plan or saved approval opens a fresh held draft. Returning to the original context restores its original draft. Restoring approve never saves an approval or enables execution; the server's saved run controls execution availability, and an explicit Save action is still required.

**Verification:** All 101 focused frontend cases pass, including twelve new scope restoration, changed approval and changed plan cases. Existing budget/output/batch/Governance/validation request and pending-response coverage passes. TypeScript, ESLint, isolated build and diff checks pass. Twelve normal Chrome and six native-200%-zoom captures inspect validation and Governance scope controls across narrow/desktop widths, reload and blocked storage. All pass axe, bounds, route and browser-error checks with zero API writes. The enlarged restored Governance choice was visually inspected.

Evidence: `artifacts/visual-review/certification-scope-drafts-2026-10-08/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,dist,source-hashes.json,qa-script.mjs,browser,browser-native,checkpoint.json}`.

**Limits:** Browser histories and prepared states are fixtures. The broader preservation of every practical input and course-switch journey remains open; no actual approval, execution, learner, grade, migration or publication changed.


### Checkpoint 255 Preserve capstone correction, finding and release drafts on October 8 2026

**Status:** Complete for the remaining substantial Governance authored forms; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

The original scope correction, observed unsupported value, both source quotes/pages, proposed repair and exact-memo release choice now survive remounts in the same browser tab. Each binds the learner, enrollment, manifest and original captured input or result. Memo release additionally binds the memo record and exact file hash. A changed input, result or file starts a fresh draft, including an unchecked inspection acknowledgement and held release for different bytes. Restoring a checked acknowledgement or approval never saves a release or creates a private handoff.

**Verification:** All 51 focused draft, scope and Governance tests pass. TypeScript, ESLint, isolated production build and diff checks pass. Eighteen normal Chrome, nine native-200%-zoom Chrome and eighteen WebKit captures verify three form drafts, restored values/choices, blocked-storage guidance and zero API writes. All pass axe, bounds, route and browser-error checks. The enlarged restored exact-file release draft was visually inspected. An initial patch-writing script had a quoting error and made no source change; the applied patch and final checks succeeded.

Evidence: `artifacts/visual-review/certification-capstone-drafts-2026-10-08/{frontend.log,typescript-final.log,eslint.log,build.log,isolated-source.json,dist,source-hashes.json,qa-script.mjs,browser,browser-native,browser-webkit,checkpoint.json}`.

**Limits:** These are browser-tab drafts with synthetic saved-history browser APIs. They are not server saves, cross-device drafts, approvals, source verification, delivery or earned credit. Other practical controls and the full optional-switch draft journey remain open. No actual learner, artifact, grade, migration, deployment or course publication changed.


### Checkpoint 256 Preserve connected approval and validation repair explanations on October 8 2026

**Status:** Complete for these two forms; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

Connected scope keeps its initially unselected choice and preserves an authored draft only for the exact run, plan and saved approval. Validation repair interpretation now has an independent form with tab drafts bound to the original retest result and previous-submission lineage. Opening a different result or revising a different saved explanation cannot inherit another draft. Neither restoration submits or awards anything.

**Verification:** All 48 focused frontend cases pass. TypeScript, ESLint, isolated build and diff checks pass. Twelve normal Chrome and six native-200%-zoom captures verify restored choices/answers, storage failure warnings and zero API writes; axe, bounds, route and browser errors pass. The enlarged interpretation was visually inspected. A new test initially assumed a run button; it was corrected to use the existing saved-work selector.

Evidence: `artifacts/visual-review/certification-connected-validation-drafts-2026-10-08/{frontend-final.log,typescript.log,eslint.log,build.log,isolated-source.json,dist,source-hashes.json,qa-script.mjs,browser,browser-native,checkpoint.json}`.

**Limits:** Browser records are synthetic; the retest fixture demonstrates form persistence, not repair correctness. Full switch/navigation preservation remains open. No actual learner, approval, execution, grade, migration or publication changed.

### Checkpoint 257 Preserve batch interpretation and re-read selected recovery evidence on October 8 2026

**Status:** Complete for batch interpretation draft and receipt restoration; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

The batch interpretation now retains its authored explanation, partially entered reference and selected retry IDs/result hashes under the learner, enrollment, manifest, original batch result, case and previous interpretation. Restoring a draft rereads each selected owned receipt and validates it against the original batch and saved result hash. Local stored JSON cannot supply recovery evidence. Changed, unavailable, incomplete or duplicate-source receipts block submission while retaining the explanation. Explicit reread retries only GETs; an explicit clear-selection action retains the explanation and requires new verified receipt selections.

**Verification:** Thirty-seven focused frontend cases pass, including original receipt rereads, two saved selections, hash/parent/state/access failure, retained explanation, explicit clearing and a delayed read after unmount. Related batch workflow and scope contracts pass. TypeScript, corrected ESLint and diff checks pass. The first lint invocation used the wrong extension for the new hook and was corrected. Six normal Chrome and three native-200%-zoom captures verify restoration and blocked-storage guidance. Axe, bounds, routes and browser errors pass, with zero browser API writes. The enlarged restored interpretation was visually inspected. The fixture was generated through actual local authenticated HTTP against disposable MongoDB 27029 with synthetic providers; original failures and a successful bounded retry remain distinct, XP stays zero, and its database was removed.

Evidence: `artifacts/visual-review/certification-batch-review-drafts-2026-10-08/{frontend-initial.log,frontend-final.log,typescript.log,eslint-final.log,source-hashes.json,fixture.log,http-fixture.json,build.log,isolated-source.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. The frozen preview now includes checkpoint 257. Browser navigation replays the exported HTTP fixture; it does not rerun extraction or grade work. Full course-switch draft preservation remains open.


### Checkpoint 258 Isolate budget explanations by completed result on October 8 2026

**Status:** Complete for budget review result/revision drafts; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

A reproduced parent-flow regression showed a second completed budget run inheriting the first run’s authored explanation. The review now owns a tab draft bound to learner, enrollment, manifest, run, result, case and previous submission. A new run begins blank; reopening the first restores only its own explanation. Revising a saved review retains its initial saved answer under a distinct lineage.

**Verification:** All 13 budget workflow cases pass after the fix. `before-binding.log` preserves the actual failing cross-run assertion (an earlier fixture setup error was corrected separately). TypeScript, ESLint and isolated build pass. Six normal Chrome and three native-200%-zoom captures verify reload restoration and blocked-storage guidance with zero API writes; axe, bounds, routes and browser errors pass. The enlarged restored form was visually inspected. A fixture exported through authenticated local HTTP uses disposable MongoDB 27029 and a synthetic provider; intentionally incorrect calculations receive no grade or XP, and the database was removed.

Evidence: `artifacts/visual-review/certification-budget-review-drafts-2026-10-08/{before-binding.log,frontend.log,typescript.log,eslint.log,fixture.log,http-fixture.json,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Full optional-switch draft coverage remains open. No live learner, publication, migration, model execution or grade changed.


### Checkpoint 259 Preserve exact-file inspection and delivery revision drafts on October 8 2026

**Status:** Complete for output draft isolation and storage feedback; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

Four reproduced regressions showed inspection answers and opened-bundle acknowledgements surviving a changed learner, manifest, ZIP hash or individual file hash. Inspection drafts now bind all of those identities plus the exact result and current saved release. Changed context begins with unchecked acknowledgements, blank observations and a held release. The outgoing request rebuilds its identities and fixed destination from the owned server record. Delivery interpretation drafts bind the exact inspection, handoff and revision lineage; revising one explanation cannot overwrite its original draft. Storage failure is visible and preserves current edits.

**Verification:** All 42 focused output, authored-form and scope cases pass; TypeScript and ESLint pass. Twelve final normal Chrome and six final native-200%-zoom captures pass reload restoration, blocked-storage, axe, bounds, route and browser-error checks with zero browser API writes. Visual inspection caught a clipped long release option; the shorter final option fits while the full exact-file/private-audience explanation remains visible. The final enlarged inspection was visually inspected. Both builds and their evidence are retained.

Evidence: `artifacts/visual-review/certification-output-drafts-2026-10-08/{before.log,frontend.log,typescript.log,eslint.log,generate_fixture.py,fixture.log,http-fixture.json,build-final.log,isolated-source.json,source-hashes.json,dist-final,qa-script.mjs,browser-final,browser-native-final,checkpoint.json}`. The fixture generator uses authenticated local HTTP, actual generated files, synthetic providers and disposable MongoDB 27029. Its controlled failed handoff writes no destination copy, awards no XP and its database is removed. Old unscoped tab draft keys are retained but are not imported into a different, authenticated draft identity. No actual learner, release, migration, publication or external delivery changed.


### Checkpoint 260 Preserve unfinished budget calculations and method decisions on October 8 2026

**Status:** Complete for calculation-entry and workflow-method drafts; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

Calculation inputs, partial amounts, source pages/quotes, unresolved choices, results, arithmetic method and limits explanation now survive closing the form or reloading. Drafts bind learner, enrollment, manifest, assignment/source, selected document and original calculation revision. A different selected source or saved calculation opens its own draft. A method explanation binds the selected saved calculation and workflow version; learners select those records before authoring that explanation. Saved original calculation records remain immutable.

**Verification:** All 16 budget workflow cases pass, including incomplete `123.` restoration, separate source/revision drafts, workflow-version method isolation and existing lost-response recovery. TypeScript, ESLint and isolated build pass. Twelve normal Chrome and six native-200%-zoom captures verify calculation and method restoration, visible storage failures, zero API writes, axe, bounds, route and browser-error checks. The enlarged calculation form was visually inspected. The browser reuses checkpoint 258’s exported local HTTP fixture, with intentionally incorrect saved calculations and no earned credit.

Evidence: `artifacts/visual-review/certification-budget-calculation-drafts-2026-10-08/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Browser-tab drafts remain separate from course saves; whole-course optional switching and late-worker reconciliation remain open. No actual learner, grading, publication, migration or external communication changed.


### Checkpoint 261 Preserve connected comparisons and stopped-run recovery drafts on October 8 2026

**Status:** Complete for these authored forms; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

Connected result comparisons now bind the learner, enrollment, manifest, case, both actual run/result pairs and previous interpretation. A changed original, correction, result or revision opens its own draft. Both distinct runs must be selected before authoring a comparison. Stopped-run choices and explanation bind the original run, result, stage receipt digest and previous decision. Returning restores the exact choices without preparing, executing, assessing or saving recovery. Existing explicit revision flows retain their original answers.

**Verification:** All 37 connected-workflow and stopped-run cases pass, including six comparison identity changes, remount recovery choices and changed receipt/revision isolation. TypeScript, ESLint and isolated build pass. Twelve normal Chrome and six native-200%-zoom captures verify comparison/recovery restoration, blocked-storage guidance, zero API writes, axe, bounds, route and browser-error checks. The enlarged recovery form was visually inspected. The recovery fixture was previously exported from real isolated HTTP with synthetic providers; the comparison pair is synthetic rendering data and proves no successful repair.

Evidence: `artifacts/visual-review/certification-connected-comparison-drafts-2026-10-08/{frontend-final.log,typescript-final.log,eslint-final.log,build-final.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Full optional-switch preservation remains open. No actual learner, execution, credit, migration or publication changed.


### Checkpoint 262 Optional course switching preserves eighteen practical form drafts on October 8 2026

**Status:** Complete for this browser matrix and the durable transfer regression batch; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

Each of eighteen authored practical forms is filled, left via the actual saved-course preview/consent/switch controls, and restored after an explicit return to the original course. The alternate course has a different enrollment, manifest and visible title. Original draft storage remains byte-identical while away; no original form remains mounted there. Reopening the original saved record restores its text, approval choices, checked file acknowledgements or recovery selections without submitting them. Validation, Governance, connected scope/comparison/recovery, batch interpretation, budget calculations/method/review and output inspection/interpretation are included.

**Verification:** 108 normal Chrome and 54 native-200%-zoom captures pass form restoration, storage-failure guidance, axe, bounds, routes and browser-error checks. The only 108 browser POSTs are explicit synthetic saved-course selections; no assessment, execution, release or grading request occurs. These fixture responses prove frontend preservation, not durable migration. Separately, all 59 current MongoDB persistence cases pass for partial-course migration, mid-assessment blocking, activation, return/resume, interruptions and fenced late selection workers. Each fixture uses disposable MongoDB 27029 and removes its database. Earlier connected actual-HTTP selection evidence remains in checkpoints 184–191.

Evidence: `artifacts/visual-review/certification-course-switch-drafts-2026-10-08/{qa-script.mjs,run_matrix.py,source-hashes.json,matrix.json,matrix-native.json,persistence.log,persistence.xml,checkpoint.json}` and all eighteen named normal/native browser directories. The browser uses the unchanged checkpoint 261 frozen bundle. The audit also reproduced an earlier Workflow Design form carrying answers into a new captured revision; that fix and remaining early-module coverage are the next checkpoint. No actual learner, migration, credit, publication or external communication changed.


### Checkpoint 263 Bind workflow approval drafts to captured configuration on October 8 2026

**Status:** Complete for workflow approval draft identity; C8-MIGRATE-07 remains in progress. Counts stay 52/162 accepted and 110 open.

A reproduced regression carried a previous capture’s approval explanations into a new captured workflow revision. Authored decisions now bind learner, enrollment, manifest, case, captured input ID/hash and prior approval. A fresh capture opens blank answers. Reopening the original capture or an existing approval’s linked revision restores only its own authored draft. Pending requests retain their frozen exact bodies and existing GET-based recovery. Confirmed approval preserves its server history and clears the submitted local form.

**Verification:** All 14 workflow-design tests pass, including the formerly failing cross-capture case, a draft revision reopened from its original approval, and existing pending/lost-response recovery. TypeScript, ESLint, isolated build and diff checks pass. Six normal Chrome and three native-200%-zoom captures pass explicit switch-away/return, reload, storage-failure guidance, axe, bounds, routes and browser-error checks. The enlarged restored form was visually inspected. Six synthetic selection POSTs are the only browser writes.

Evidence: `artifacts/visual-review/certification-workflow-design-drafts-2026-10-08/{before.log,frontend-final.log,typescript.log,eslint.log,generate_fixture.py,fixture.log,http-fixture.json,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. The original capture fixture was exported through authenticated local HTTP with no execution, assessment or XP; its disposable MongoDB 27029 database was removed. Old unscoped draft keys remain untouched and are not silently reassigned. No actual learner, approval, migration or publication changed.


### Checkpoint 264 Accept authored-work preservation during optional course selection on October 8 2026

**Accepted:** C8-MIGRATE-07. Counts are now 53/162 accepted and 109 open. This accepts the current optional zero-credit selection policy and authored-work preservation; it does not publish an upgrade, transfer equivalent credit, calibrate grading or reconcile actual cohorts.

The final early-module check preserves separate Process Design and practical decision drafts across enrollment changes and returns. Existing recognition/reflection coverage confirms pinned bank/user/course isolation, pending-request identity, unavailable-storage handling and confirmed-answer precedence. Process Design now reports failed tab storage immediately while preserving current text in memory.

**Verification:** All 58 focused Process Design, practical review, scenario and reflection draft cases pass. TypeScript, ESLint and isolated build pass. Six normal Chrome and three native-200%-zoom Process Design captures pass explicit switch-away/return, restoration and storage warnings, with axe, bounds, route and browser-error checks. The enlarged blocked-storage form was visually inspected. Its assignment fixture was exported through authenticated local HTTP without authored submission, model execution or grading; the disposable MongoDB 27029 database was removed.

Acceptance evidence combines these checks with checkpoints 253–263:

| Transfer requirement | Evidence |
| --- | --- |
| Preserve substantial authored input | Twenty practical forms pass actual frontend saved-course preview/consent/switch-away/return controls at narrow/desktop/native zoom: 120 normal and 60 native captures across 262–264. Earlier reflection, scenario and practical-decision isolation/recovery is verified in the 58-case component batch and prior connected delivery checks. All six scope forms have restoration and changed-plan/approval coverage. |
| Keep answers with their evidence | Source, exact run/result/file and revision bindings are verified through the reproduced and repaired regressions in 253–263. Batch retry selections are reread from owned receipts. Restored choices never submit or execute. |
| Preserve in-flight attempts | The 59-case durable regression batch at 262 blocks a switch during a live write and after an unresolved assessment, without losing its original snapshot. Existing real paused-worker checks and interrupted preparation recovery at 187–191 reject revoked workers. |
| Recover interrupted activation | The durable selection journal and explicit reconciliation preserve both source/target inventories, places, original and newly earned credentials through all tested interrupted phases, return and resume. Current selection transfers zero credit and never regrades or awards it. |

Evidence: `artifacts/visual-review/certification-early-draft-preservation-2026-10-08/{frontend.log,typescript.log,eslint.log,generate_fixture.py,fixture.log,http-fixture.json,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`, plus specifically scoped 262–263 and 187–191 evidence. Browser selections are synthetic fixture mutations, distinct from the durable MongoDB tests. Drafts are tab-local; unavailable storage is explicitly reported and does not claim cross-device retention. Independent workspace workers keep their original references; stalled ingestion reconciliation and late extraction-result fencing remain separate CHAT-07/09 work. The actual course registry remains unchanged. No actual learner, migration, earned credit, publication or external communication changed.


### Checkpoint 265 Accept preservation of existing graduate credentials on October 8 2026

**Accepted:** C8-MIGRATE-04. Counts are now 54/162 accepted and 108 open. No production change was needed for this acceptance; current checks substantiate the existing preservation implementation.

Legacy completion is preserved with its original stored learner identity and issue date, with no invented V4/V5 attribution. An unavailable historical date remains unavailable. Six concurrent preservation requests yield one immutable issuance; later profile names do not replace it. The owned history and PDF remain readable after selected progress and the catalog are removed from the disposable test. Foreign or corrupted records fail rather than regenerating a current-course credential. Upgrade, return and resume retain the original issuance and any separately earned new credential without regrading, revoking or relabeling the earlier award.

**Verification:** Three current persistence cases pass, including actual PDF text checks for the original name/date and unknown historical version. Twenty-two current certificate history, chat certificate access and versioned chat-card cases pass. The current 59-case selection/rollback batch at 262 independently covers both original/new credentials, unknown dates and actual saved one-module graduation through return/resume; these overlapping cases are not summed. Earlier certificate layout, focus and byte-verified download checks and checkpoint 211 rendering preflight remain the visual evidence for the unchanged presentation.

Evidence: `artifacts/visual-review/certification-legacy-credential-preservation-2026-10-08/{persistence.log,persistence.xml,frontend.log,source-hashes.json,checkpoint.json}`, plus 262’s preservation batch. Tests use disposable synthetic records on MongoDB 27029 and remove their databases. This accepts preservation behavior, not actual cohort inventory/backfill or recovery of a known historical course version from records not yet examined. Those remain MIGRATE-01/02/03. No actual learner, credential, migration, course publication or external communication changed.


### Checkpoint 266 Reject late classification results without restoring stale sample state on October 8 2026

**Status:** Complete for classification writes; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Eight reproduced regressions showed classification saving an old whole-document model over a retry, new text, manual label, deletion, owner or processing change. A deleted row could even be recreated. Classification now updates only its four fields, with no upsert. Automatic/default results compare the original text, file identity, restart generation and classification metadata before writing. They preserve human decisions and reject changed/deleted/moved documents. An explicit manual classification writes only its fields and returns a conflict if the authorized document identity no longer matches; no successful audit is recorded for that conflict.

**Verification:** All 23 current MongoDB classification/retry cases and 40 service, task and route cases pass. Actual asynchronous classification workers are paused while a restart or other document change occurs. The same-text/new-generation case also rejects the old result; unrelated processing changes survive while the classification may succeed. Tests use synthetic model output and disposable MongoDB 27029 databases that are removed afterward. The first combined run identified two route mocks still expecting whole-model saves; they were updated to exercise the narrow write.

Evidence: `artifacts/visual-review/certification-late-classification-2026-10-08/{before.log,after.log,unit-final.log,persistence-final.log,persistence-final.xml,source-hashes.json,checkpoint.json}`. This does not yet fence extraction, validation callbacks, external vector writes or knowledge-base mirroring. No visual presentation changed. No actual learner, model request, migration, publication or external communication changed.


### Checkpoint 267 Fence extraction generations across queued and delayed callbacks on October 8 2026

**Status:** Complete for document-row generation fencing; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Five paused-reader regressions reproduced old success, empty reading and error results overwriting a newer explicit retry. The restart CAS now passes its generation to extraction, completion, cleanup, semantic ingestion, classification and independent validation, including the validation chord callback. Legacy messages without a generation belong to zero, not whichever retry is current. Worker reads/status/bookkeeping writes reject superseded or deleted documents; extraction also preserves source-file/owner identity. A stalled-worker reaper atomically advances the generation when marking a dead read failed. Orphan completion dispatch preserves its actual generation. A current retry still extracts, completes, validates and indexes normally.

**Verification:** All 155 relevant document/upload/validation/classification/route/KB unit cases pass. Forty-three distinct current persistence cases are covered across the initial 34-case batch, 17-case extended extraction batch and three new classifier/chord contracts (overlaps are not summed). These include paused success/error readers, old queued follow-up tasks, same-text/new-generation classification, reaper revocation and repeat sweep, a complete current retry, validation paused during its model response, and ingestion paused during both successful and failed index responses. The delayed provider calls are synthetic. Disposable MongoDB 27029 databases are removed after each test. Targeted diff checks pass.

Evidence: `artifacts/visual-review/certification-extraction-generations-2026-10-08/{before.log,unit.log,unit-final.log,persistence.log,persistence.xml,persistence-final.log,persistence-final.xml,dispatch-contracts.log,source-hashes.json,checkpoint.json}`. Existing test fakes were extended for MongoDB `$exists`/`$inc` and the new guarded filters after the first unit run. No visual presentation changed.

**Remaining limits:** These predicates protect MongoDB document state and reject already-obsolete tasks before external calls. They do not cancel an already-running Chroma write, fence every knowledge-base/folder-automation side effect, provide exactly-once queue delivery or establish compatibility with old deployed worker code. Those remain separate gates. The upload caller's post-dispatch whole-model save was also found to risk erasing a fast worker's result and is next. No actual learner, model request, queue dispatch, migration, publication or external communication changed.


### Checkpoint 268 Preserve fast-worker results when upload dispatch returns on October 9 2026

**Status:** Complete for post-dispatch document writes; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Six certification sample regressions reproduced the upload caller saving its pre-dispatch document over a worker that had already completed, failed, retried, deleted the document or advanced processing. The shared upload and workflow/extraction/automation file-upload routes now record only `task_id`, conditioned on the original generation still processing with no task ID. No whole-model save follows queue dispatch. Completed/failed/retried/deleted records remain unchanged; an in-progress current worker keeps its new fields and receives the queue ID. A disappeared source produces the existing course provisioning conflict rather than being resurrected.

**Verification:** All fourteen sample-creation persistence cases pass across the initial batch’s twelve passing cases and the final six fast-worker cases (overlap excluded). Two first-run cases were updated to expect the now-correct existing provisioning conflict for a deleted source. All 185 upload/file/automation/extraction/workflow route cases pass. Existing route mocks now isolate the shared persistence helper; the actual helper is exercised against MongoDB in the six fast-worker cases. Targeted diff checks pass. Tests use in-memory file storage, synthetic queue responses and disposable QA MongoDB 27029, with databases removed afterward. One automatic approval check timed out; the permitted retry succeeded.

Evidence: `artifacts/visual-review/certification-dispatch-preservation-2026-10-08/{before.log,persistence.log,persistence.xml,fast-worker-final.log,fast-worker-final.xml,routes.log,routes-final.log,source-hashes.json,checkpoint.json}`. The folder name retains the start date; verification crossed into October 9. This does not make queue publication transactional or fence external index writes. No visual presentation, actual learner, storage service, queue, migration, publication or external communication changed.


### Checkpoint 269 Recover stalled validation and preserve honest sample readiness on October 9 2026

**Status:** Complete for course sample validation recovery; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Five reproduced cases showed an abandoned validation leaving a sample indefinitely processing, and active retries/processing stages showing an old failure or unavailable state. Uploads and retries now mark validation outstanding before queue dispatch. Active validation chunks and summaries renew a private heartbeat. Once extraction has settled, a check with no activity beyond the shared stale-work window becomes failed/retryable while retaining its source text. The reaper advances the generation, so old queued chunks skip model work and late summaries cannot overwrite the recovered state. Dead extraction recovery clears its superseded validation lock as well. No automatic resubmission or successful check is inferred.

Course status now prioritizes actual in-progress work over previous validation/reading failure flags, while an explicit extraction error remains failed. It recognizes OCR, security and retrieval-preparation stages as processing. A fast extracted sample remains pending until its independent validation settles; the owned course status then becomes ready without changing credit.

**Verification:** All 56 current persistence cases pass for extraction/reaper/validation callbacks, actual assigned course status, competing sample creation and restart boundaries. An additional current queue-order contract verifies processing→ready with unchanged progress. Two heartbeat tests preserve a recent check and a heartbeat that wins between the reaper read and CAS; legacy missing-heartbeat recovery is repeat-safe. All 296 relevant unit/route cases, ten Microsoft attachment-intake cases and eleven unchanged lab-status component cases pass. The first unit run’s three old fixed-write-order assertions were updated to identify the validation result independently of the new heartbeat. Targeted diff checks pass.

Evidence: `artifacts/visual-review/certification-stalled-validation-2026-10-09/{before.log,persistence.log,persistence-final.log,persistence-final.xml,queued-validation.log,unit.log,unit-final.log,m365.log,frontend.log,source-hashes.json,checkpoint.json}`. Local tests use synthetic providers and disposable MongoDB 27029 only. Existing processing/failed/ready UI presentation is unchanged; earlier sample-status visual evidence remains applicable. The deployed reaper schedule and mixed-version worker rollout are not asserted. Course readiness uses extracted text and validation state, not the legacy document search index; already-running external vector/KB side effects remain a separate shared-worker concern. No actual learner, model request, queue, migration, publication or external communication changed.


### Checkpoint 270 Coalesce pending reflection, setup and legacy-check requests on October 9 2026

**Status:** Complete for shared-hook request coalescing and reflection activation; CHAT-07 remains in progress. Counts stay 54/162 accepted and 108 open.

Four reproduced regressions dispatched duplicate reflection/setup/check requests or allowed different reflection answers over a pending save. The shared hook now synchronously registers a promise keyed to learner, progress/enrollment/manifest, action and module before dispatch. Identical actions share that promise through the post-write progress read. A changed reflection body waits for the original save; its actual request receives a copied answer object. Failed requests release the guard for an explicit retry. Different modules remain independent and unbound actions cannot dispatch before progress loads.

The browser matrix caught two error toasts after one coalesced reflection request: both click handlers were awaiting that result. A synchronous reflection-form guard now permits only one activation/notice before the parent renders its saving state. The initial failing browser evidence is retained.

**Verification:** All 66 focused hook/panel/reflection/lab-status cases, application TypeScript, targeted ESLint and frozen production build pass. Twelve final normal Chrome and six native-200%-zoom captures pass the pending double-click, failed-save reload, expired-session recovery, explicit identical retry, saved-server presentation and unavailable-storage cases. All writes are intercepted; manifests report no unexpected routes, page errors, axe violations or horizontal overflow. The enlarged pending state was visually inspected. An initial TypeScript run caught a test fixture using `success` instead of `stored`; the corrected final run passes.

Evidence: `artifacts/visual-review/certification-pending-actions-2026-10-09/{before.log,frontend-verified.log,typescript-final.log,eslint-final.log,build-final.log,isolated-source-final.json,source-hashes.json,dist-initial,dist-final,qa-script.mjs,browser,browser-native,browser-final,browser-native-final,checkpoint.json}`. Cross-tab durability remains the server’s responsibility; the remaining legacy check/completion parent callback matrix is next. No actual learner, model request, queue, grading, migration or publication changed.


### Checkpoint 271 Guard panel callbacks through completion and star upgrades on October 9 2026

**Status:** Complete for the parent callback guards; CHAT-07 remains in progress. Counts stay 54/162 accepted and 108 open.

Five reproduced cases allowed duplicate parent callbacks for check, completion, setup and reflection, including a second check while the first was saving a star upgrade. The chat panel and standalone course handlers now synchronously guard each pending action through its full success/error/refresh path. The guard clears after failure for an explicit retry. A progress check stays guarded until its star-upgrade save settles, preventing a duplicate upgrade call or misleading second notice.

**Verification:** All 51 focused panel/hook cases, application TypeScript, targeted ESLint and isolated production build pass. The tests invoke rapid activations through actual panel handlers with synthetic detail controls, assert one dispatch/notice, retry after a failure and retain the check guard during the upgrade save. A test initially used Playwright’s `exact` option in a Testing Library query; the corrected typecheck passes. No markup changed; checkpoint 270 retains the current pending-state visual proof.

Evidence: `artifacts/visual-review/certification-panel-action-guards-2026-10-09/{before.log,frontend.log,typescript-final.log,eslint.log,build.log,isolated-source.json,source-hashes.json,dist,checkpoint.json}`. The next server check concerns a different request ID completing the same saved competency evidence: it currently preserves XP but replaces the module’s original credit reference and increments its attempt count. No actual learner, request, grading, migration or publication changed.


### Checkpoint 272 Preserve original credit when the same saved outcomes are completed again on October 9 2026

**Status:** Complete for repeated identical V5 outcome credit; CHAT-07 remains in progress. Counts stay 54/162 accepted and 108 open.

A reproduced case showed a new completion request for the same saved review/scenario replacing the original earned-credit reference and increasing the assessment count, although XP was already protected. Completion now verifies the original and current frozen outcome evidence and preserves the entire original module credit when the selected immutable receipts match. A different saved assessment remains a new attempt. Rehashed changes to the same receipt identity, or corrupt original credit, fail without replacing earned work.

Each distinct request still receives its own auditable completion receipt. A lost response after the progress save can finish that receipt on explicit retry without changing the original credit or adding XP. No automatic grading or staff task is introduced.

**Verification:** Thirty-eight distinct checks pass: the 35-case outcome/completion-concurrency/credential batch, one additional interrupted-receipt case and two added same-identity receipt-hash checks. The final fourteen-case credential run overlaps twelve cases in the original batch; those are not counted twice. Targeted Ruff and diff checks pass. Actual two-client completion races and receipt recovery use synthetic providers and disposable MongoDB 27029 databases that are removed afterward.

Evidence: `artifacts/visual-review/certification-repeated-outcome-credit-2026-10-09/{before.log,results.log,results.xml,lost-receipt.log,credentials-final.log,ruff.log,source-hashes.json,checkpoint.json}`. This preserves credit for identical saved V5 evidence, not a global prohibition on deliberately submitting a new assessment with a new identity. No visual presentation, actual learner, model request, migration or publication changed.


### Checkpoint 273 Make uncertain scenario recovery a read-only check on October 9 2026

**Status:** Complete for scenario receipt reconciliation; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Ten reproduced frontend cases showed “Check saved scenario result” sending the original POST again. The owned receipt endpoint now returns a read-only view of whether the original result is selected, awaits its progress link, has been superseded or cannot be linked to verified progress. It reads the original enrollment/progress bindings without loading a current catalog, grading, repairing links or changing credit. Missing or mismatched bindings do not become a claimed successful selection.

The form now uses GET for the check and compares the receipt identity, course/bank and exact choices before accepting it. Only a missing receipt or unfinished progress link exposes a separate explicit action using the original request and choices. Failed/expired checks retain the locked draft and offer only another read. Superseded results cannot silently replace newer work. A synchronous guard covers rapid check activation and the subsequent progress refresh; checking and saving have distinct labels.

**Verification:** Thirty focused scenario/history frontend cases and twenty distinct persistence cases pass. The initial sixteen-case persistence run and final nine-case run overlap five cases, excluded from the total. Application TypeScript, targeted ESLint/Ruff, frozen production build and diff checks pass. Twelve normal-width and six native-200%-zoom captures cover confirmed, missing, unlinked, superseded, unavailable and failed-check states. They verify zero POSTs from checking, exact-body explicit retries, focus on recovered feedback, no overflow, axe findings, unexpected routes or page errors. The narrow missing-receipt and enlarged unfinished-link states were visually inspected.

Evidence: `artifacts/visual-review/certification-scenario-reconciliation-2026-10-09/{before.log,frontend-verified.log,persistence.log,persistence.xml,persistence-final.log,persistence-final.xml,typescript.log,eslint.log,ruff.log,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Existing synthetic/connected scenario harness expectations now require read-only recovery. Browser receipts are intercepted fixtures; actual HTTP/persistence tests use disposable MongoDB 27029 databases and remove them afterward. No actual learner, model request, queue, migration or publication changed.


### Checkpoint 274 Keep practical decision checks read-only on October 9 2026

**Status:** Complete for practical decision reconciliation; CHAT-07/09 remain in progress. Counts stay 54/162 accepted and 108 open.

Two reproduced failures showed a missing decision receipt causing “Check saved decision” to POST automatically, and a rejected GET unlocking uncertain answers as though their original submission had been rejected. Checks now read only. A confirmed missing receipt offers a separate explicit retry with the exact original body. Unsuccessful reads retain the locked request, and only an actual rejected submission permits answer correction. Checking and saving have distinct labels. The existing explicitly labeled “Check and finish saved preparation” still describes its bounded write behavior.

**Verification:** All 82 practical review/preparation/automatic-assessment cases, application TypeScript, targeted ESLint and isolated build pass. Six normal-width and three native-200%-zoom captures verify found, missing and failed-read states, zero resubmission from checking, original-body explicit retry, result focus and locked answers. Axe, overflow, page errors and unexpected routes pass. The enlarged missing-receipt state was visually inspected. Underlying immutable decision receipt and execution APIs are unchanged; their prior persistence evidence remains applicable.

Evidence: `artifacts/visual-review/certification-decision-reconciliation-2026-10-09/{before.log,frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. No actual learner, model request, grading, migration or publication changed.


### Checkpoint 275 Explain completion resumption as an explicit write on October 9 2026

**Status:** Complete for accurate completion recovery wording; CHAT-09/12 remain in progress. Counts stay 54/162 accepted and 108 open.

The pending-completion action called the original completion POST while labeled “Check saved result.” It now says “Resume original completion” and explains that it may finish validation and save credit, preserving already earned rewards. The separate status refresh remains read-only. Panel/page uncertainty notices use the same distinction. In-flight and unreconciled evaluation still cannot be resumed through this action. Server behavior is unchanged.

**Verification:** All 56 completion notice/panel/hook cases, targeted ESLint and frozen build pass. Six final normal-width and three native-200%-zoom captures pass with short 480-CSS-pixel-height viewports, eleven pending modules, keyboard access to the final notice controls and read-only refreshes. Axe, overflow, page errors and unexpected routes pass; the enlarged notice was visually inspected. Six baseline captures had already passed reachability, so no scrolling-layout repair is claimed or retained. No actual completion, support message, model request, migration or publication occurred.

Evidence: `artifacts/visual-review/certification-completion-resume-copy-2026-10-09/{frontend-final.log,eslint.log,build-final.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser-before,browser,browser-native,checkpoint.json}`. Original request/credit persistence is independently verified at 204, 237 and 272.


### Checkpoint 276 Index retained baseline, browser coverage and source provenance on October 9 2026

**Status:** Complete for the evidence inventory and searchable report; QA-01 remains open for complete reproducibility/coverage acceptance. Counts stay 54/162 accepted and 108 open.

The new ledger derives checklist state and checkpoint references directly from their existing files. It indexes 374 retained browser manifests and 5,465 recorded states, explicitly including repetitions and diagnostics rather than labeling them passes. All 151 original selected audit captures, their images/accessibility snapshots/axe reports and the contract probe remain present; baseline assets, the unchanged audit and source manifests receive SHA256 references. No referenced capture asset or evidence directory is missing, and no browser manifest fails decoding.

Each later run retains exact state/device records, reported commit and source/fixture fingerprints, browser version and native zoom/text settings, recorded errors, execution limitations and any explicit frozen-build/archive reference. Retained package manifests identify course/rubric versions separately from publication. The ledger does not reconstruct unavailable old dirty sources, infer an exact served build from a shared-tree fingerprint, convert fixtures into live execution evidence or change audit grades. Such provenance limitations remain visible.

**Verification:** Six inventory integrity/escaping cases and Ruff pass. The generated local report passes every local-link check, full/search/empty-result behavior, four desktop/narrow captures, axe, page bounds and page-error checks. The baseline audit itself is unchanged. The report and JSON are under `docs/reviews/certification-v5-evidence-ledger.*`; the generator is `scripts/build_certification_qa_ledger.py`.

Evidence: `artifacts/visual-review/certification-evidence-ledger-2026-10-09/{build.log,tests-final.log,ruff.log,browser.log,browser/report-ui.json,source-hashes.json,checkpoint.json}`. Generated totals will change as later checkpoints are added; retained checkpoint evidence describes this verification. No database, model, publication, deployment or external communication occurred.


### Checkpoint 277 Accept basic AI Literacy supervision decisions on October 9 2026

**Accepted:** C8-M00-03. Counts are now 55/162 accepted and 107 open. This accepts the deterministic recognition assessment and its learner delivery, not the full AI Literacy module, operational competence or a released 5.0 credential. No production change was needed for this acceptance.

Nine pinned scenarios cover unsupported rules, fabricated missing values, limits of a previous quality score, instructions embedded in sources, a wrong workspace/document, broader release scope, institutional judgment, credential limits and the timing of a human checkpoint. Every one of the eighteen incorrect choices has specific remediation and fails its required outcome even when all other choices are correct. Missing choices do not pass. Reflection/comfort responses cannot replace this assessment.

Authenticated receipts preserve exact learner choices, course/bank identity, original feedback and separate revised submissions. The read-only history and recovery paths retain earlier answers after a new result, reject mismatched/corrupted receipts and never award XP merely for saving recognition responses. Module credit remains a separate explicit selected-outcome action. This mechanism has no live-model dependency; practical execution and learner comprehension still require their own evidence.

**Verification:** All 88 current scenario-kernel/result-integrity cases pass. Thirteen current browser captures pass actual radio keyboard selection, all-wrong submission, a lost response, reload through the mobile activity drawer, read-only receipt recovery, displayed remediation and corrected submission under a distinct request. No unexpected routes, page errors, axe findings or page overflow were observed; narrow feedback was visually inspected. The served bundle is byte-matched to checkpoint 275’s archive. Current 30-case frontend, twenty-case HTTP/persistence and six native-200%-zoom recovery evidence at 273 is reused without counting it as new runs.

Evidence: `artifacts/visual-review/certification-literacy-decisions-2026-10-09/{kernel.log,kernel.xml,browser.log,browser,source-hashes.json,bundle-verification.json,checkpoint.json}`, plus 273’s exact receipt checks. Original choice-specific feedback was reviewed against all nine prompts. No baseline grade, release-readiness flag, actual learner, published requirement, grading queue, migration or communication changed.


### Checkpoint 278 Return from scenario feedback to the exact answer on October 9 2026

**Status:** Complete for scenario remediation navigation; JOURNEY-09 remains in progress. Counts stay 55/162 accepted and 107 open.

Failed scenario feedback now repeats the original question beside its specific explanation and offers “Review scenario” to focus the learner’s existing selected radio answer. It neither chooses a different answer nor submits, clears or resets any result. Other successful choices and the original saved feedback remain intact. Unconfirmed submissions keep correction controls disabled until their receipt is reconciled.

**Verification:** The initial missing-action test fails, then all 31 scenario/history tests, application TypeScript, targeted ESLint and frozen build pass. An exact-text test was corrected to distinguish the numbered fieldset legend from the repeated prompt. Sixteen normal and eight native-200%-zoom captures verify read-only recovery and actual keyboard return to visible, selected answers for both current and superseded feedback. Focus stays in the visible course and no POST is sent by remediation. Axe, page bounds, unexpected routes and page errors pass; enlarged focused-answer rendering was inspected.

Two simultaneous Chrome launches timed out before loading the app. The single-browser normal retry passed. A native pointer-stability wait then timed out on the visible Challenge tab; native keyboard entry and all subsequent remediation checks passed in a fresh profile. These diagnostics remain retained rather than being reported as successful pointer coverage.

Evidence: `artifacts/visual-review/certification-scenario-remediation-2026-10-09/{before.log,frontend-final.log,typescript.log,eslint.log,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser-retry,browser-native-retry,browser-native-final,checkpoint.json}`. Browser APIs are synthetic; the underlying assessment and persistence behavior is unchanged. No actual learner, grade, migration, publication or communication changed.


### Checkpoint 279 Confirm an earlier decision after its run becomes read-only on October 9 2026

**Status:** Complete for receipt checks after preparation closes; CHAT-09 remains in progress pending the combined acceptance review. Counts stay 55/162 accepted and 107 open.

Three reproduced cases showed a pending decision’s receipt check being disabled when its run left preparation, and a direct form submission bypassing the disabled presentation. The form now permits the owned read-only receipt check while keeping answer fields and write actions blocked. A missing receipt on a closed run explains that decision changes are no longer accepted and directs the learner to saved history; it does not offer another POST. The handler enforces the current write permission independently of its buttons.

**Verification:** All 85 review/preparation/assessment cases, application TypeScript, targeted ESLint and frozen build pass. Six normal and three native-200%-zoom captures start with an uncertain save, refresh into a read-only run, then check found, missing or failed receipt reads. They verify locked answers, an enabled read-only check, no new POST, no retry permission, and preserved saved-result focus. Axe, page bounds, unexpected routes and page errors pass; enlarged unavailable-receipt guidance was inspected.

Evidence: `artifacts/visual-review/certification-readonly-decision-recovery-2026-10-09/{before.log,frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,source-hashes.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Underlying owner-only receipt and immutable decision APIs are unchanged. No actual learner, model, grading, migration, publication or communication changed.


### Checkpoint 280 Accept course interruption recovery on October 9 2026

**Accepted:** C8-CHAT-09. Counts are now 56/162 accepted and 106 open. This accepts the controlled implementation’s reconciliation and next-action behavior; it does not assert live-provider reliability or deployment readiness. No new production change was needed for this acceptance.

| Interrupted boundary | Preserved state and safe next action | Evidence checkpoints |
| --- | --- | --- |
| Partial/malformed chat result | No inferred write success; read current progress without resubmitting the tool | 157, 232 |
| Sample preparation/processing | Recover the canonical lab/sample, inspect actual processing/validation state, explicitly retry failed work, reject superseded callbacks | 239, 249–251, 267–269 |
| Reflection/scenario/practical decision | Keep exact answers and request identity; check original receipts; offer a separate retry only when permitted | 235, 270, 273–274, 279 |
| Practical execution/assessment | Preserve original plans, stage results and evidence; inspect before explicit bounded finish/retry; never infer a grade from partial output | 135, 138, 144, 149, 151–152, 161, 264 |
| Completion/credential | Retain the original request and evidence before sending; replay original saved result after a lost response; preserve earned credit and issuance | 173, 175–176, 204, 237, 272, 275 |
| Completed write/failed refresh | Preserve the successful operation and refresh its display without repeating completion | 3, 176, 270 |
| Course switch/reopen/history | Keep both course identities, retained work and original credentials; old callbacks cannot overwrite the selected course | 186, 189, 191, 252, 264–265 |

**Verification:** All 367 current frontend cases across twenty relevant hook, form, execution, assessment, completion and chat-card files pass. The acceptance matrix links the retained connected-browser, authenticated HTTP, disposable-MongoDB and task-callback evidence for each boundary; these historical test/capture totals are not summed into a new run. Recent fixes have normal and native-zoom proof at 273–279. Providers, file storage and brokers are synthetic where explicitly documented; database and request/receipt behavior is real.

Evidence: `artifacts/visual-review/certification-interruption-acceptance-2026-10-09/{frontend.log,acceptance-matrix.json,source-hashes.json,checkpoint.json}`. This does not promise exactly-once external vector/KB writes, cancel already-running providers, establish mixed-worker rollout or close the separate two-tab duplicate-submission matrix. Technical ambiguity remains visible instead of manufacturing success or a routine staff grading task. No actual learner, model request, migration, publication or communication changed.


### Checkpoint 281 Deduplicate automatic assessment across separate tabs on October 9 2026

**Status:** Complete for identical trusted automatic-review evidence; CHAT-07 remains in progress for the full submission matrix. Counts stay 56/162 accepted and 106 open.

Six reproduced failures showed separately identified requests creating additional review records, including eight concurrent requests for the same evidence. Trusted reviews now carry an atomic unique evidence-request key scoped to owner, enrollment, module, immutable course, exact evidence/provenance, parent retry and frozen rubric/reviewer settings. Identical work returns an owned original-reference conflict before another grade. Same-ID replay remains unchanged; revised work and explicit technical retry retain their separate records. Older receipts without the new key are verified and compared without rewriting history.

All nine assessment routes preserve that conflict reference. The second tab records it and offers an explicit read-only check, including after reopening. The normal receipt identity checks still reject another run, enrollment or retry lineage. Conflict recovery itself neither dispatches a model nor finishes a prepared review; unavailable browser storage is explained honestly.

**Verification:** 59 distinct backend cases pass (48 review/persistence regressions, three additional HTTP/retry/integrity checks and eight route-family checks), along with 74 frontend/API-client cases, targeted ESLint/Ruff and the isolated production build. Application TypeScript initially caught an unknown-exception assertion in the new API-client test; the assertion was narrowed and the completed rerun at checkpoint 282 passes. The authenticated HTTP test sends three later IDs and recovers the original result with exactly one synthetic grader call. Six normal and three native-200%-zoom captures exercise two real browser tabs, different request IDs, reopening, keyboard recovery and original feedback at narrow/desktop widths. Axe, page bounds, route and page-error assertions pass; narrow conflict guidance and enlarged recovered feedback were inspected.

Evidence: `artifacts/visual-review/certification-cross-tab-assessment-2026-10-09/{before.log,backend.log,backend-regression.log,backend-http.log,route-conflicts-final.log,frontend.log,typescript.log,eslint.log,ruff.log,build.log,build-final.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. The first build failed because the old temporary snapshot had lost unchanged entry files; a fresh complete source snapshot built successfully and is explicitly fingerprinted. Browser APIs and graders are synthetic; request persistence uses disposable MongoDB. This does not establish mixed-worker/index rollout, live grading validity or deduplication of other submission types. No registry, actual learner, earned credit, publication, migration or communication changed.


### Checkpoint 282 Distinguish pending action from saved status on October 9 2026

**Status:** Complete for practical preparation/execution/grading status and the six later-module request hooks; CHAT-12 remains in progress. Counts stay 56/162 accepted and 106 open.

Three reproduced cases used the same waiting/checking copy for different operations. Preparation now distinguishes listing extractions, checking the original preparation and saving its inputs/plan. Practical execution distinguishes a GET from sending execution; automatic grading distinguishes read, new assessment, technical retry and explicit resumption. Connected, budget, output, validation, batch and governance requests now expose their actual read/send phase through a shared status component with action-specific labels. No percentage or inferred server stage is invented.

Pending write guidance explains that closing the panel does not establish completion or cancellation and directs the learner back to the saved request. The two-minute result promise was removed: the backend timeout can leave a provider still working. Enlarged visual inspection also caught a prior prepared receipt appearing current during execution; it is now labeled **Last confirmed**, and start instructions/control remain hidden while the sent request is unresolved. Saved evidence itself is retained.

**Verification:** 188 distinct affected component cases pass: the initial nine-file 187-case run, then final governance coverage (26, including one additional lost-response/read-phase test) and execution coverage (15, including the saved-status correction). Application TypeScript completes with exit 0 after narrowing the prior checkpoint's unknown API-test exception; the API-client tests and targeted ESLint pass. The new governance test initially recreated its assignment on each render, causing repeated effect setup; its fixture now holds stable identity and the corrected run passes. This was a test-fixture error, not a learner retry.

Fourteen normal and seven native-200%-zoom captures pause actual frontend requests at listing, save, execution, assessment and read boundaries. Six additional execution captures verify the final **Last confirmed** wording and absence of a second start control. All checks preserve exact request identity, confirm that reads add no writes, and pass axe, page bounds, unmatched routes and page errors. The enlarged pending execution view was inspected. The final bundle is byte archived and linked to the final execution captures; earlier preparation/assessment captures preceded that execution-only wording change.

Evidence: `artifacts/visual-review/certification-action-status-2026-10-09/{before.log,frontend.log,governance-final.log,governance-stable-fixture.log,execution-final.log,typescript-final.log,typescript-verified.log,eslint.log,build.log,build-final.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-preparation.mjs,qa-execution.mjs,qa-assessment.mjs,browser-preparation,browser-execution,browser-assessment,browser-native-preparation,browser-native-execution,browser-native-assessment,browser-execution-final,browser-execution-final-native,checkpoint.json}`. These are deliberately delayed synthetic HTTP states, not live-provider timing evidence. No actual learner, model, earned credit, deployment or registry changed.


### Checkpoint 283 Return directly from feedback to saved work on October 9 2026

**Status:** Complete for the practical feedback return action; JOURNEY-09 remains in progress. Counts stay 56/162 accepted and 106 open.

Saved automatic feedback now offers **Open saved work to review**. Every practical module binds that action to the verified run, process design, workflow approval or saved interpretation referenced by the assessment. Pending work disables navigation where the owning form requires it. Opening uses the existing owned read/identity checks and never changes the original feedback or automatically submits a revision. Practical feedback additionally rejects malformed run references before offering navigation. Foundations/Extraction return to the saved run’s after-execution review and focus the source/work region; this can show newer saved value checks while the original assessment stays immutable.

**Verification:** Three reproduced missing-action/reference cases fail before the fix. All 201 cases across ten affected component files pass, followed by the 36-case practical-review suite including one additional integrated return/focus/no-write case (202 distinct). Application TypeScript completes successfully; ESLint and the frozen build pass. Four normal and two native-200%-zoom captures verify a keyboard return from failed Foundations feedback to the same source/run and values-review stage at narrow/desktop sizes. The original choices and write count remain unchanged. Axe, page bounds, unexpected routes and page errors pass; enlarged focused source/evidence was inspected.

Evidence: `artifacts/visual-review/certification-feedback-return-2026-10-09/{before.log,frontend.log,practical-return.log,typescript.log,typescript-final.log,eslint.log,build.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Browser navigation is verified for Foundations; other module callbacks use their existing verified owned readers and current component coverage, not a newly claimed all-module browser run. No actual learner, new grade, model, credit, registry or publication changed.


### Checkpoint 284 Keep prior check guidance and reject stale display context on October 9 2026

**Status:** Complete for retained-course check feedback/recheck presentation; JOURNEY-09 remains in progress pending its combined acceptance review. Counts stay 56/162 accepted and 106 open.

Rechecking no longer clears the prior result before a reply. Both panel and certification page label it **Previous check results** while checking or after an unavailable response; passed details and concrete repair guidance remain readable. An explicit **Recheck this module** control stays disabled during the check. Feedback is bound to learner, enrollment, course/manifest and module. A response received after that context changes cannot appear as current feedback or trigger the panel’s subsequent automatic star-upgrade request; old upgrade notifications are also suppressed after navigation.

**Verification:** The prior-feedback test reproduced the loss before the fix. Three initial context fixtures omitted the enrolled lesson position and consequently had no check control; those fixture failures are retained and corrected. All thirty panel/result cases now pass, including four late-response identity/module changes, no stale auto-upgrade, pending/error guidance preservation and explicit retry. TypeScript caught optional fixture fields, which were narrowed; the completed final check exits 0. ESLint and the isolated build pass. Four normal and two native-200%-zoom browser captures pause a recheck, return a synthetic 503, retain the original passing/failing guidance and then explicitly retry. Only the three intended validation requests occur; no completion or XP write is dispatched. Axe, page bounds, unexpected routes and page errors pass; enlarged retained guidance was inspected.

Evidence: `artifacts/visual-review/certification-validation-context-2026-10-09/{before.log,frontend.log,frontend-final.log,frontend-all-contexts.log,typescript-final.log,typescript-verified.log,eslint.log,build.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-native,checkpoint.json}`. Check results in this browser run are synthetic; no actual model, validation, learner, registry, publication or earned credit changed.


### Checkpoint 285 Accept failed-grade explanation and remediation on October 9 2026

**Accepted:** C8-JOURNEY-09. Counts are now 57/162 accepted and 105 open. This accepts feedback, next-action and persisted-history behavior; actual model calibration and observed learner comprehension remain separate requirements.

The acceptance matrix ties each failure boundary to its next action: scenario feedback returns to the actual selected answer; practical feedback shows the original requirement, verdict, citation and repair instruction and can open saved work; combined readiness preserves explicitly selected failures rather than silently substituting a better historical result. Retained-course checks distinguish required criteria from advice, preserve previous passing/failing guidance through unavailable rechecks, and reject responses from a changed learner/course/module. Revisions remain separate saved work; technical failures retain their original evidence and explicit retry lineage without a routine staff grading queue. No repeated grading is used merely to refresh a display.

**Verification:** All 104 current backend readiness/HTTP/result-integrity cases and 111 frontend scenario, formative-check, practical-feedback, automatic-request, combined-outcome and retained-check cases pass. The disposable database checks prove failed selection survives a later pass, original technical/result states remain distinguishable, corrupt/foreign evidence is rejected, and read-only previews change neither progress nor receipts. The acceptance matrix reuses the specifically bounded browser/persistence evidence at 273, 277–278 and 281–284; those captures are not counted as a new run. Automatic judgment remains synthetic in this local evidence.

Evidence: `artifacts/visual-review/certification-remediation-acceptance-2026-10-09/{backend.log,frontend.log,acceptance-matrix.json,source-hashes.json,checkpoint.json}`. This does not accept the live rubric’s reliability, complete learner usability pilot, release of draft teaching, or all-module live practical execution. No actual learner, grading, migration, registry, publication or communication changed.


### Checkpoint 286 Truthful design save, capture and approval status on October 9 2026

**Status:** Complete for early design forms; CHAT-12 stays in progress because the status inventory also found course-choice writes labeled as checking. Counts remain 57/162 accepted and 105 open.

Process saving, workflow configuration capture and workflow approval now distinguish sending a write from reading its saved state. The shared notice explains that closing the panel does not establish completion or cancellation; saved work remains available and the pending reference should be checked before retrying. Controls retain their existing pending-request protection and exact saved-work verification.

**Verification:** Thirty-one design component cases pass, including held writes, lost replies, read-only recovery and one write per explicit action. TypeScript, targeted ESLint and the isolated production build pass. Twelve normal-width and six native-200%-zoom browser captures verify all three sending/checking pairs at 320, 1440 and effective 390 CSS pixels. Recovery adds no POST, execution, grade or credit. Axe, page bounds, unexpected routes and page errors pass; narrow approval and enlarged capture-check notices were inspected. Initial component selectors matched both draft and request statuses; they were narrowed. The initial browser fixture paired a supplied-map selection with an owned-map receipt and correctly failed verification; final runs select the matching saved map. Diagnostic runs remain retained.

Evidence: `artifacts/visual-review/certification-design-status-2026-10-09/{frontend.log,frontend-final.log,typescript.log,eslint.log,build.log,status-audit.txt,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-final,browser-native,checkpoint.json}`. Final browser runs are tied to the archived bundle. No actual learner, workflow execution, model, registry, migration or publication changed.


### Checkpoint 287 Separate preservation-choice and course-switch status on October 9 2026

**Status:** Complete for optional-upgrade and saved-course switch pending notices; CHAT-12 awaits the combined acceptance matrix. Counts stay 57/162 accepted and 105 open.

The optional upgrade step now names loading a preservation review, saving a choice and checking the saved choice separately. It states that this step neither switches the course nor transfers credit. The shared activation/return/resume control distinguishes sending the switch from checking its saved receipt. Closing does not cancel or confirm a switch; the learner can reopen the course to inspect its selection and pending confirmation, with both histories retained.

**Verification:** All sixteen course-choice component cases pass, including delayed choice save, separate delayed switch, lost reply and GET-only recovery. TypeScript, targeted ESLint and the isolated build pass. Eight normal and four native-200%-zoom final browser captures cover saving/checking the choice and sending/checking the switch. Only the two explicit synthetic writes occur; checks do not repeat them. Axe, page bounds, unexpected routes and page errors pass. Visual inspection identified an inconsistent initial synthetic preview (pending work alongside an available switch); the final preview has no pending operation and the enlarged switch notice was reinspected. Production eligibility checks were not relaxed.

Evidence: `artifacts/visual-review/certification-choice-status-2026-10-09/{frontend.log,typescript.log,eslint.log,build.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-native,browser-final,browser-native-final,checkpoint.json}`. The final browser runs have exact archived bundle fingerprints. No real learner, credit, migration, registry or publication changed.


### Checkpoint 288 Reuse exact scenario choices across browser tabs on October 9 2026

**Status:** Complete for deterministic scenario deduplication; CHAT-07 remains open for the remaining legacy completion boundary. Counts remain 57/162 accepted and 105 open.

Different request IDs with the same learner, enrollment, module, course/manifest, bank and exact choices now reuse one original scenario receipt. A partial unique answer-identity index arbitrates concurrent inserts. Historical receipts are checked without regrading or backfill; old duplicate history stays readable. An interrupted receipt can finish its original progress link, while a superseded result cannot replace newer choices. The learner sees the original reference and a clear reuse explanation; reopening an older result retains the newer-selection warning. Changed choices have separate results, and different learners never share private receipts.

**Verification:** Three tests reproduced duplicate records, replacement of newer choices and unnecessary regrading before the fix. Thirty-four distinct persistence/HTTP cases, twenty-nine result-integrity cases and thirty-three frontend cases pass. Eight concurrent repository calls converge on one receipt; eight HTTP clients plus explicit retries converge on the same owned result with no XP. Historical, corrupt, interrupted and foreign-owner boundaries pass. An initial implementation shadowed the answer digest with the serialized-record digest; final runs correct this. Two history fixtures now represent pre-index duplicate rows and the earlier integrity rejection. TypeScript, targeted ESLint/Ruff and the frozen build pass. Eight normal and four native-200%-zoom final captures exercise two real tabs, distinct request IDs, original-reference recovery and an unchanged newer selection; reload performs no POST. Page bounds, axe, errors and unexpected routes pass. The enlarged original-result explanation was inspected and clarified before the final captures.

Evidence: `artifacts/visual-review/certification-scenario-deduplication-2026-10-09/{before.log,backend.log,backend-final.log,backend-expanded.log,backend-history-final.log,backend-owner.log,result-integrity.log,frontend-copy-final.log,typescript-final.log,eslint-final.log,ruff-final.log,build-final.log,isolated-source.json,source-hashes.json,bundle-verification.json,dist,qa-script.mjs,browser,browser-native,browser-final,browser-native-final,checkpoint.json}`. This does not verify mixed-worker/index rollout, live grading or real learners. The registry fingerprint is unchanged. No publication, actual learner, credit or migration changed.


### Checkpoint 289 Accept understandable long-running course actions on October 9 2026

**Accepted:** C8-CHAT-12. Counts are now 58/162 accepted and 104 open.

The combined acceptance matrix covers actual provisioning/text status, scenario and decision saves, practical preparation/execution, automatic assessment, all design and later-module actions, completion/progress refresh, and optional course choices. Sending, checking and last-confirmed results are distinguishable. Closing is described as closing the view; it does not fabricate cancellation or success. Explicit checks and retries preserve their original request and completed work. Progress displays measure recorded completion rather than an invented timer or estimated provider percentage.

**Verification:** All 323 current component cases across sixteen files pass. The matrix links retained browser and persistence evidence at 189, 191, 239, 264, 267–269, 272–275, 279–282 and 286–288. Final design, choice and scenario changes have normal/narrow/native-zoom captures, error/overflow/axe checks and visual inspection. This checkpoint adds no new browser captures and does not relabel historical runs as current exact-bundle evidence. The final scenario explanation also passes its targeted thirty-three-case suite after copy clarification.

Evidence: `artifacts/visual-review/certification-action-status-acceptance-2026-10-09/{frontend.log,acceptance-matrix.json,source-hashes.json,checkpoint.json}`. Full screen-reader/learner observation, provider cancellation, live grading calibration and deployment remain separate gates. No actual learner, earned credit, registry, migration or publication changed.


### Checkpoint 290 Fence new completion requests against stale tab credit on October 9 2026

**Status:** Complete for new guarded panel completion requests; CHAT-07 remains open for its final route/compatibility matrix. Counts remain 58/162 accepted and 104 open.

New retained-course completion requests carry the module attempt counter shown to the learner. Before creating a new assessment journal or grading, the server rejects a changed counter with an explicit conflict. An already recorded request still replays its original receipt even after credit advances. The hook retains the original counter with its request across uncertainty/remount, prevents mixing counters and references, and blocks dispatch before progress loads. A definite stale-counter conflict clears only that stale pending request and refreshes course state; it never resubmits automatically. A new explicit request after reviewing current progress remains possible.

**Verification:** Two HTTP tests reproduced the duplicate legacy completion, covering unversioned and pinned continuation courses. Twenty-two persistence/replay/concurrency cases, thirty-two backend contract cases and sixty-six frontend hook/API/panel cases pass. The extended boundary verifies stale rejection, exact winner replay and a separately reviewed new request with zero duplicate XP. One assertion initially compared the internal pinned write fence as learner data; the final comparison excludes only that fence. Two hook expectations were updated to include the preserved counter. Further cases reject mixed stored/in-memory request references and retain the original counter when reopened progress has advanced. TypeScript, ESLint, Ruff and the isolated build pass. Two normal and one native-200%-zoom final browser captures use two real tabs: the stale tab sends counter zero, receives a conflict, refreshes to one completed attempt and clears its stale pending notice without another POST. Axe, page bounds, unexpected routes and errors pass; the enlarged refreshed state was inspected.

Evidence: `artifacts/visual-review/certification-completion-precondition-2026-10-09/{before.log,backend.log,backend-final.log,backend-precondition-final.log,backend-contracts.log,frontend.log,frontend-final.log,typescript-final.log,eslint-final.log,ruff.log,build-final.log,isolated-source-final.json,source-hashes.json,bundle-verification.json,dist-initial,dist-final,qa-script.mjs,browser,browser-native,browser-final,browser-native-final,checkpoint.json}`. Older pending requests without a counter retain their original replay contract; older callers without this new precondition do not gain its guarantee. This does not equate mutable legacy artifacts, eliminate deliberate reassessments or verify mixed-client/worker rollout. No actual learner, credit, registry, publication or migration changed.


### Checkpoint 291 Accept independently checked budget teaching on October 9 2026

**Accepted:** C8-M06-01. Counts are now 59/162 accepted and 103 open. Advanced-module live execution/calibration and the remaining M06 items stay open.

The budget worked example now has revision 3 and a concrete, explicitly fictional source: laptop 1,200.00, monitor 600.00, accessories 200.00, and printed total 2,150.00 USD for one period. Independent Decimal calculation verifies the listed sum is 2,000.00 and the discrepancy is 150.00. The lesson records the addition rule and leaves the cause of the source discrepancy unresolved. These teaching figures do not expose the assigned assessment answers. Deep Analysis is accurately described as findings/analysis followed by synthesis; neither model pass supplies an independent arithmetic check. Dependent narrative and release claims wait for the recorded calculation and required review.

**Verification:** All 157 teaching/preview/outcome/advanced-case/calculation contracts and 35 calculation-record/review persistence cases pass. Real assigned-source checks distinguish wrong operands from wrong addition and reject false/missing source quotations, changed units, fabricated receipts and model-only assurance. A synthetic judge pass cannot override failed arithmetic. Seventeen normal-width and seven native-200%-zoom browser captures cover the calculation-method lesson, updated worked example, its middle arithmetic paragraph and wrong-to-correct formative feedback. Axe, page bounds, unexpected writes/routes and page errors pass; the calculation at 320 CSS pixels and native 200% was visually inspected. Browser position saves are synthetic; no assessment or XP write occurs.

Evidence: `artifacts/visual-review/certification-budget-teaching-acceptance-2026-10-09/{independent-arithmetic.json,contracts.log,persistence.log,acceptance-matrix.json,source-hashes.json,bundle-verification.json,fixtures,qa-script.mjs,browser,browser-native,checkpoint.json}`. The renderer bundle is byte-identical to checkpoint 290’s retained build; teaching fixtures are separately archived. The published registry and enrolled learners’ original requirements are unchanged. No live model, learner, credit, migration or publication changed.


### Checkpoint 292 Accept permission and capability teaching on October 9 2026

**Accepted:** C8-M06-02. Counts are now 60/162 accepted and 102 open.

The capability lesson now explains secret handling and the actual ordinary-access assessment route. The build lesson and revision-2 case specify one or two source-review Prompt tasks followed by a Prompt/Formatter memo, with recorded arithmetic and all required preceding results. This corrects the previous suggestion that Deep Analysis could run inside this bounded assessment. Code, API, crawler and Research tasks remain outside its supported scope. Learners need neither external secrets nor admin enablement; an unavailable optional integration does not create a staff task. Existing authorized external connections are discussed only when an actual external operation is required.

A regression exposed that an exercise could retain the right case digest while replacing its instructions with contradictory requirements. The case now verifies exact instruction equality. The copied exercise instructions and digest were updated together; initial stale-binding and instruction-drift failures are preserved.

**Verification:** The final 62 case/preview/outcome contracts and 25 disposable-MongoDB plan/HTTP cases pass, including actual one/two-task engine execution with synthetic provider responses, blocked unsupported node types/models, dependent memo ordering and no Code permission. Targeted Ruff passes. Seventeen normal and seven native-200%-zoom captures pass page bounds, axe, unexpected writes/routes and browser errors. The credential paragraph at 320 CSS pixels and native zoom and the narrow supported-route procedure were visually inspected.

Evidence: `artifacts/visual-review/certification-advanced-capability-2026-10-09/{contracts.log,contracts-final.log,instruction-drift-before.log,contracts-binding-final.log,persistence.log,persistence-binding-final.log,acceptance-matrix.json,source-hashes.json,bundle-verification.json,fixtures,qa-script.mjs,browser,browser-native,checkpoint.json}`. The renderer is byte-identical to checkpoint 290’s archived build; current teaching/case/exercise fixtures are separately retained. The registry fingerprint is unchanged. This does not verify live grading, actual learners, full advanced-module completion or release readiness. No migration, publication or actual learner requirement changed.


### Checkpoint 293 Accept shared progression and accommodation policy on October 9 2026

**Accepted:** C8-DEF-03. Counts are now 61/162 accepted and 101 open.

The pinned policy now names the available presentation choices, no timer/speed penalty, supported assignment alternatives and the boundary when required access is missing. These preserve required evidence and need no routine staff approval or grading. A cross-surface gap was repaired: the chat progress tool now returns the same public policy as the course API, and its card renders the same shared disclosure as the panel. Strict result checks reject malformed rules, contradictory module/XP totals, missing course identity and a new policy attached to legacy credit. Historical policy-free cards remain readable and do not inherit the current course’s rules.

The acceptance matrix combines the original policy integrity/publication guard (193), administrator behavior (194/231), required-outcome versus participation/credit boundaries (204/212/226/272), access consistency (233), and feedback/recovery evidence (280/285). Study order, required outcomes, enrichment, retries, critical errors and star rules remain consistent. This accepts the local policy implementation, not publication or a claim that every accessible route has been observed.

**Verification:** Sixty policy/tool/preview cases, 71 overlapping policy/rubric/automatic-review cases, eleven current persistence cases and 88 frontend cases pass. Actual authenticated API/admin and chat-tool reads return the same policy and leave learner state unchanged; both administrator lock/unlock requests are rejected for the flexible-order course. TypeScript, targeted ESLint/Ruff and the isolated build pass. The first build used the repository root with an absolute temporary Vite root and failed asset-path resolution; the final build runs within the isolated snapshot. Eighteen normal and six native-200%-zoom captures verify identical chat/panel rules, keyboard disclosure, page bounds, axe, errors and GET-only course access. Narrow panel/chat and enlarged chat guidance were visually inspected.

Evidence: `artifacts/visual-review/certification-policy-routes-2026-10-09/{contracts.log,policy-enforcement.log,persistence.log,frontend.log,typescript.log,eslint.log,ruff.log,assembly.log,build.log,build-final.log,isolated-source.json,package,dist,source-hashes.json,bundle-verification.json,qa-script.mjs,browser,browser-native,acceptance-matrix.json,checkpoint.json}`. Full screen-reader and representative learner observation, live calibration and rollout remain open. No actual learner, assessed requirement in an existing enrollment, registry, publication or migration changed.


### Checkpoint 294 Explain stopped budget operations and saved-result recovery on October 9 2026

**Status:** Complete for budget failure/capability guidance; CHAT-11 and M06-04 retain broader capability and live assessment gates. Counts stay 61/162 accepted and 101 open.

Saved budget evidence now distinguishes an unavailable/failed model operation from an empty required result. Unknown failure identifiers receive a generic explanation rather than displaying untrusted details. A stopped run explains revising the workflow and method, preparing a new plan and approving it separately; completed original outputs remain in history and are not automatically reused. An unfinished final receipt instead directs the learner to inspect the original run and use saved-result finalization only when offered, without another model call.

**Verification:** Nineteen frontend cases pass, including no implicit rerun, finalization or assessment action after a stopped task and no display of a synthetic secret in an unknown failure identifier. Twenty-eight distinct disposable engine/persistence/recovery cases pass across the initial run and four-case corrected rerun. Three initial delivery assertions incorrectly expected no result object; failed runs correctly retain a structured failure receipt with no final memo. The corrected assertions preserve that receipt and export genuine QA run-view fixtures. TypeScript, targeted ESLint/Ruff and the isolated build pass. Twelve normal and six native-200%-zoom browser captures use those actual saved run views with synthetic read-only delivery, covering provider failure, empty output, checkpoint failure and interrupted finalization. Axe, bounds, errors, unexpected routes and GET-only access pass. Narrow stopped-task/memo ordering and enlarged finalization guidance were inspected.

Evidence: `artifacts/visual-review/certification-budget-capability-recovery-2026-10-09/{frontend.log,persistence.log,persistence-delivery-final.log,typescript.log,eslint.log,ruff.log,build.log,fixtures,dist,source-hashes.json,bundle-verification.json,qa-script.mjs,browser,browser-native,checkpoint.json}`. The browser does not execute or finalize the fixture. Synthetic provider responses do not establish live grading validity or full M06 acceptance. No actual learner, credit, registry, publication or migration changed.

### Checkpoint 295 Direct course access without a chat model on October 9 2026

**Status:** verified local correction; no additional checklist acceptance. CHAT-03/11 retain live-agent and permission-path gates.

**Change:** both first-session and returning home provide a direct course action independent of the disabled chat action. New/active learners can open the course; graduates can review their completed course. The selected enrollment and saved lesson remain authoritative; no prompt is submitted.

**Verification:** 21 component tests passed; TypeScript, ESLint and isolated production build passed. Final normal and native-zoom browser runs cover both home variants and new/active/completed enrollments, including actual lesson entry and retained lesson 2. All 54 final captures report no browser errors, unexpected requests, course writes, chat submissions or axe violations. Inspected the final native-zoom saved-lesson view. Earlier incomplete synthetic-fixture runs are retained as diagnostics and excluded from final coverage.

**Evidence:** `artifacts/visual-review/certification-home-panel-fallback-2026-10-09/`; final runs `browser-complete` and `browser-native-complete`, archived renderer, fixtures and source hashes. This is synthetic API delivery with zero models; it is not a live-agent test or publication. Count remains 61 accepted / 101 open.

### Checkpoint 296 Creation-preview and quality teaching on October 9 2026

**Accepted:** C8-M00-01. Count is 62 accepted / 100 open. This accepts accurate introductory teaching; live tutoring, beginner observation and assessed practical execution remain open.

**Change:** five draft AI Literacy/Foundations lessons now describe discovery before the creation preview, review of proposed name/source/field summary/project, approval reusing that proposal, abbreviated field summaries and inspection of the full saved template before execution. Creation does not itself execute an extraction. The introduction explicitly explains missing/Unscored quality evidence without equating it to a pass or failure. Lesson revisions advance; published legacy teaching and assessment requirements remain unchanged.

**Verification:** 79 teaching/scenario/outcome/preview contracts and 11 existing creation/extraction/workflow capability tests passed. These check current implementation, including reuse of the approved discovery proposal. All five changed lessons passed 55 focused browser captures at narrow/desktop widths and native 200% zoom with zero browser errors, unmatched requests or unexpected assessment writes. Inspected the revised Unscored explanation and creation procedure. Existing all-nine-lesson introductory coverage and full-course native-zoom coverage remain applicable to unchanged lessons; this batch does not repeat the full course.

**Evidence:** `artifacts/visual-review/certification-creation-preview-teaching-2026-10-09/`, source review and logs, archived fixtures/script and byte-identical renderer from 295. The initial test selector selected no tests and is retained as diagnostic only. No model request, publication or actual learner change occurred.

### Checkpoint 297 Assessment-first bridge and explicit credit eligibility on October 9 2026

**Status:** implemented and locally verified; C8-MIGRATE-06/08/09 remain open. Count remains 62 accepted / 100 open. Read-only transfer eligibility is not credit application, and a functioning study path does not establish a measured bridge duration or live competence.

**Delivered behavior:** an immutable optional bridge asset groups the same eleven modules and 33 outcomes into scope/approval, verification, recovery/delivery and the governance capstone. The actual panel provides keyboard-accessible links directly to each module’s Challenge assessment, keeping related teaching available. It uses the same grading and credential requirements, displays completed status only from the matching enrollment/course, and makes no time-saving or duration promise. Existing packages without this asset receive no new path.

**Credit eligibility:** optional upgrade previews now include a read-only equivalence plan. An authored target-package policy must bind the exact source manifest, target release and unchanged assessment basis. Every eligible outcome needs verified original enrollment-bound completion evidence. Changes to passing conditions, rubric/runtime assets, exercises, sources, judge configuration, progression or unknown assets invalidate the mapping; editorial presentation changes may preserve it. No rule, unknown legacy provenance, XP, completion alone, missing evidence or a rule for another source cannot establish eligibility. Corrupt saved receipts fail closed. Plans retain original completion/digest references without exposing answer payloads. No authored production equivalence rules or credit-application endpoint are added.

**Verification:** 36 initial equivalence/original-credential tests, then 37 final bridge/equivalence/assembled-preview contracts passed (overlapping coverage, not additive unique counts). 34 frontend tests, TypeScript, ESLint, Ruff and the isolated production build passed. Twenty-five distinct optional-upgrade persistence cases passed across the main run and a single setup-timeout retry; one final upgrade regression also passed after the bridge package addition. The transient failure was disposable MongoDB discovery exceeding the three-second fixture timeout, not a failed application assertion. Eighteen focused browser captures cover narrow/desktop/native 200% zoom, all four phases, all eleven links and direct keyboard entry to the actual AI Literacy assessment. No browser errors, unmatched requests, axe violations or writes; narrow/native layouts and assessment focus were visually inspected.

**Evidence:** `artifacts/visual-review/certification-credit-equivalence-2026-10-09/`, including the assembled unpublished package, archived renderer, source digests, script, final browser runs and logs. The application registry retains SHA256 `959317a4f0e9a9bb8d6557920e9cfbc1a245f502221213a9d28ad66e479efeed`. No publication, production enrollment change or actual learner migration occurred.

**Remaining for this journey:** explicit consent and durable application of eligible credit, prevention/accounting of duplicate rewards, issuance provenance, rollback, richer per-outcome remediation and a bridge pilot. Original legacy records without qualifying evidence retain original credit and require new demonstrations. Live calibration remains deferred; these local checks do not claim 8/10 or release readiness.

### Checkpoint 298 Explicit equivalent credit application on October 9 2026

**Status:** Awaiting verification of the new learner screen in the browser. Counts remain 62/162 accepted and 100 open. Work was checkpointed for version control at the user’s request before further features.

A separately consented transfer can apply one whole module only when every required outcome has authored equivalence and verified original completion evidence. It preserves the original enrollment and credential, freezes the original assessment provenance into target credit, and distinguishes XP carried toward the selected course from a new XP reward (zero). Missing legacy evidence or partial eligibility does not waive assessment. A fresh transfer requires the installed target rubric to match. No production equivalence policy was authored.

Transfers use the existing completion journal and write boundary. Replays return the same saved result; interrupted writes resume the original proof without regrading or provider calls. The learner control preserves its request before sending, requires a distinct checkbox, checks saved receipts after uncertainty and does not resubmit on mount or refresh. Credential issuance retains source assessment evidence. The progress label now says “XP toward this course” and transfer results identify carried XP.

**Verification:** 15 final disposable-MongoDB tests pass, including explicit consent/ownership at HTTP delivery, changed-preview rejection, competing requests, lost progress/journal replies, worker revocation, unsupported target grading, all-module credential issuance, and a real optional activation → transfer → return → resume sequence. Both histories and original credentials remain unchanged. All 115 focused frontend tests pass; 99 earlier overlapping outcome/equivalence/tool contract tests, TypeScript, targeted Ruff/ESLint and the release catalog check pass. Initial test-only recovery-result nesting and old XP-label expectations were corrected; diagnostic logs remain retained. These tests use synthetic course packages and no live grader.

Evidence: `artifacts/visual-review/certification-credit-application-2026-10-09/`, including final logs, an exported genuine disposable-persistence browser fixture and checkpoint metadata. Browser/build verification of the newly added transfer screen is the immediate next check. Live calibration, real-cohort reconciliation, a bridge pilot, full accessibility observation and publication remain open.

### Checkpoint 299 Local commit checkpoints on October 9 2026

The user requested commits after the accumulated working tree grew too large. New features were paused for a scope audit. The inventory contained 837 changed/new files, including unrelated work in the same checkout. Certification content, backend and learner UI were split into local commits; the test/QA/CI/tracker commit completes the series. Shared database/chat-tool/chat-panel/result-display and test files were staged by reviewed hunks. RA inbox, knowledge-base counts, unrelated panel refresh and unrelated styling changes remain in the working tree.

- `54a7892f`: preserved legacy course plus authored unpublished V5 course/source assets (82 files).
- `98dc6db1`: enrollment, assessment, recovery, credentials and optional upgrades/transfer backend (216 files).
- `9cc91de6`: learner panels, chat integration, assessment controls and saved choices (138 files).
- The following QA/tracking commit contains regressions, browser harnesses, CI gates, the audit baseline and acceptance ledger. Large retained screenshots and local QA databases remain excluded by existing ignore rules.

**Commit verification:** catalog release integrity and staged whitespace checks pass. Backend checkpoint Python files parse. An isolated frontend tree contains the exact staged implementation plus its scoped tests, without the unrelated in-progress features. The first test run passed 184 cases but included two unrelated knowledge-base cases; those cases were separated with their implementation. A focused rerun passes all 31 tool-display/bridge cases. The full TypeScript project build found an incomplete bridge-only test fixture, now corrected. The corrected full TypeScript project build passes in the isolated commit tree (`commit-typescript-complete.log`). No full release-ready or 8/10 claim follows from committing this work. The latest transfer screen still awaits visual QA, and live calibration remains deferred.

Future completed implementation batches should be checkpointed promptly instead of accumulating another multi-day uncommitted change set. No push, deployment, publication or actual learner migration was performed.

### Checkpoint 300 Visual transfer verification and prompt commit follow-up on October 9 2026

**Status:** Complete for the local whole-module transfer journey. Counts remain 62/162 accepted and 100 open; broad migration/bridge and release acceptance still require their remaining evidence.

The exact committed frontend (`82673dc8`) builds successfully, and all 529 production source files in its isolated renderer match that commit. The archived renderer and fixture digests distinguish this build from unrelated working-tree changes. Twelve final captures cover 320/1440 CSS pixels and actual 200% zoom (390 CSS pixels), separate checkbox consent, an intentionally lost POST response, reopening via direct course access, recovery through the original saved receipt, and carried-XP progress. Each journey submits exactly once; its saved-result read does not submit again. Keyboard activation, axe, page bounds and page-error checks pass. Narrow consent and enlarged recovered feedback were visually inspected.

The initial harness assumed a browser reload would reopen the panel; the next version raced the automatic route-opening action. Both diagnostics remain retained. Final runs use the real Home “Open course without chat” control consistently. No product correction was needed. The network failures in these captures are deliberate lost-response simulations, not unreported application errors.

Evidence: `artifacts/visual-review/certification-credit-application-2026-10-09/{browser-complete,browser-native,dist,bundle-verification.json,visual-checkpoint.json,commit-build.log,commit-typescript-complete.log}` and the committed reproducible browser script. Synthetic delivery uses real disposable-persistence receipts; it does not establish live-model grading, a production transfer policy or actual learner outcomes. The completed QA batch is committed immediately after the four accumulated-work checkpoints. No push, deployment, course publication or actual learner migration occurred.

### Checkpoint 301 Course-health reporting and compatibility review triggers on October 9 2026

**Status:** Complete for the bounded local operations batch. C8-OPS-06/07 remain open for missing journey events, deployment-change evidence and an actual release-specific compatibility review. Counts remain 62/162 accepted and 100 open.

The existing certification admin screen now offers an on-demand, read-only report of enrollment, module-completion, automatic-review and lab-run saved states. Counts are separated by course version and exact manifest, with optional-upgrade provenance and historical-unknown identity preserved. MongoDB aggregates only allowlisted metadata; answers, reflection text, document contents and individual identifiers never leave the query. Prepared courses are not counted as starts, rejected evidence is not labelled a dispute, and failed training runs are not automatically labelled platform defects. Missing event instrumentation is explicitly unavailable. The report has bounded group counts and query time; failed/partial reads return unavailable, never empty success. It creates no support or grading queue.

CI now records committed product changes requiring course compatibility review, retaining the exact base/product commits, registered course manifests and changed paths. Tool/approval, lab/model, course-content, runtime/dependency and learner-control/visual changes are included; deletion/rename and new backend capabilities remain visible. The transition policy assigns release-owner accountability and certification-maintainer responsibility, lists non-code deployment triggers and requires a named review with concrete evidence before advertising current compatibility. The generated scope is not a completed review or a replacement for the existing publication/live-calibration gates.

**Verification:** six disposable-MongoDB/HTTP checks, 15 focused frontend checks (including the existing admin tab), and eleven real-temporary-Git detector checks pass. Full isolated TypeScript project build, production build, targeted Ruff/ESLint and the registered course integrity check pass. Twelve final browser captures cover 320/1440 pixels and native 200% zoom, separate manifests, unknown history, keyboard opening/refresh, explicit read failure and retry to an empty report. All final captures have no page errors, unmatched requests, axe violations or horizontal page overflow. Visual inspection found and corrected a wrapped Count heading; earlier captures retain that diagnostic. Final narrow and enlarged views were inspected. The intentionally delivered HTTP 503 is the error-state test.

**Evidence:** `artifacts/visual-review/certification-course-health-2026-10-09/`, including final `browser-complete` / `browser-native-complete`, exact build-source verification (810 source/test files from `a43a06f0` plus the listed certification changes), build/typecheck logs, test receipt and product-change review sample. The sample compares committed inbox changes against `188c232d`; it demonstrates a real product-change trigger and does not assert compatibility of that feature. The browser uses synthetic API delivery; actual aggregate and authorization behavior is separately verified in disposable persistence. No actual learner, assessment, course registry, publication, deployment or GitHub issue changed. This batch is committed promptly with its tracker update.


### Checkpoint 302 Privacy-safe learner journey observations on October 9 2026

**Status:** Complete for the local instrumentation batch. C8-OPS-06 remains open for grading disputes, abandonment and defensible journey-success rates. Counts remain 62/162 accepted and 100 open.

The course now records best-effort observations for initial/refresh read failures, reading-place save failures, display of an originally saved lesson and requested bridge assessment entry. Events contain only an allowlisted event, request identity and course identity; the server derives the owned enrollment's version/package. Unknown historical provenance remains unknown. UUID deduplication, a request limit, a 90-day retention index and account-deletion cleanup bound storage. Reading or recording these events neither initializes progress nor awards or changes assessment credit.

The existing administrator report separates the last 30 days of client observations from its lifetime saved-state census. It groups by exact course package, excludes future/expired observations and exposes no answer text, documents or learner identifiers. Offline/missing reports remain unavailable evidence; an initial background read is not called a deliberate course start, a browser save failure is not proof the server failed to save, and an assessment entry is not bridge completion. No staff grading queue is created.

**Verification:** 15 backend persistence/HTTP/privacy/deletion cases and 47 focused frontend cases pass, plus 32 overlapping panel/admin cases and three module-entry cases. An isolated ModuleDetail test import initially encountered Vite's symlinked PDF-worker path restriction; its main-checkout rerun passes. Targeted Ruff/ESLint, TypeScript and production build pass. Optional telemetry deliberately bypasses API recovery that could reload the tab. Final browser checks verify that a telemetry CSRF rejection leaves the failed-save recovery and reading state intact, does not navigate/reload, and creates no assessment write. Direct bridge entry does not falsely report another lesson restoration.

The final retained renderer contains exactly the base commit `27ec2aa5` plus the eleven listed certification overrides: all 812 source files are byte-verified and its 99 bundle files are hashed. An interruption removed the initial temporary build workspace; the successful checks were repeated in the retained evidence directory. Nine final narrow/desktop/native-200%-zoom captures pass bounds, axe, page-error and route checks. The grouped report was visually inspected at 320 CSS pixels and native enlargement. Earlier captures and the interrupted source-verification attempt remain diagnostics, not the final build proof.

**Evidence:** `artifacts/visual-review/certification-journey-events-2026-10-09/{backend.log,frontend.log,test-receipt.json,health-fixture.json,retained-source.json,retained-check-results.json,bundle-verification.json,retained-source,browser-retained-complete,browser-retained-native,checkpoint.json}` and the reproducible browser script. The report fixture comes from actual disposable-MongoDB events; browser learner requests are synthetic. No actual learner, publication, production migration or live model was changed.


### Checkpoint 303 Accurate quality evidence teaching on October 9 2026

**Status:** Complete for current working teaching and the two changed V5 lesson bodies. C8-CONTENT-02 remains open until affected frozen historical lessons receive explicit corrections. Counts remain 62/162 at this checkpoint.

The quality lessons distinguish Unscored/missing evidence from zero, failure or approval; explain that scores describe identified tested examples; and explicitly show why additional cases may lower a score by exposing errors. Adding a test case is separate from repairing an extraction. The working course no longer promises a score on every result, assumes verification always raises a tier, or tells learners the assistant cannot see score metadata when its tools return it. Governance copy distinguishes review status from available measured evidence. Ten working lesson revisions advance, with generated chat/panel exports kept in parity; no assessed or formative passing requirement changes. Corresponding draft revisions stay ahead of the working definitions. Frozen course bytes and the application registry remain unchanged.

**Verification:** 45 outcome/preview/catalog cases and five exporter regressions pass; the regenerated export check passes. A structural comparison confirms only lesson title, objective, content and revision changes in the working definitions, preserving every assessment/practice property. Twenty-five final focused browser captures cover both changed V5 lesson bodies at 320/1440 CSS pixels and native 200% zoom, including corrected formative answers and the exact new paragraphs. Bounds, axe, page errors and unexpected writes pass. Narrow score-limitation and enlarged test-case guidance were visually inspected. The renderer is the byte-verified retained build from 302 with explicit runtime lesson delivery; the assembled preview remains unpublished and cannot grade or enroll.

**Evidence:** `artifacts/visual-review/certification-quality-evidence-teaching-2026-10-09/{contracts.log,check-results.json,content-preservation.json,source-hashes.json,package,renderer-provenance-final.json,browser-retained-complete,browser-retained-native,checkpoint.json}`. Earlier interrupted captures are diagnostics. This does not establish calibrated grading, current-answer correctness or a published course. Historical-enrollment correction delivery is the next bounded task. Reporting work is now locally committed as `a3a7d1e8`.

### Checkpoint 304 Complete method-selection teaching on October 9 2026

**Accepted:** C8-M02-01. Counts are 63/162 accepted and 99 open. This accepts the teaching comparison, not live practical assessment or representative learner performance.

The first Process Mapping lesson now compares bounded chat, a project, reusable extraction, a connected workflow and an automation using five concrete RA situations. A project organizes ongoing work and its sources; it does not itself execute or prove knowledge readiness. An automation initiates an existing method when a configured trigger occurs. Learners inspect a manual result first, review future scope, and understand that chat-created automations start disabled and that disabling future triggers does not undo completed work. The examples retain the principle that extra saved processes can add unnecessary setup and maintenance.

**Verification:** the project source/readiness badge, automation tool, service and disabled model default were reviewed against the copy. Isolated preview assembly and all seven assembly/publication-guard cases pass. Fourteen final 320/1440/native-200%-zoom captures verify the new comparison, formative correction and readable layout with no page errors, unexpected routes/writes, bounds or axe violations. The enlarged automation explanation was inspected. The first selector matched a phrase in both teaching and practice; its diagnostic run is retained, and the corrected unique-paragraph runs pass. This is an unpublished lesson revision; the assessment contract and existing enrollments remain unchanged.

**Evidence:** `artifacts/visual-review/certification-method-selection-teaching-2026-10-09/{source-review.json,source-hashes.json,assembly.log,preview-contracts.log,package,renderer-provenance-final.json,browser-final,browser-native-final,checkpoint.json}`. Related process critique, live qualitative grading and learner observation remain open.


### Checkpoint 305 Correct preserved teaching without rewriting learner history on October 9 2026

**Accepted:** C8-CONTENT-02 together with checkpoint 303. Counts are 64/162 accepted and 98 open. This accepts accurate quality guidance across working, V5 and known preserved teaching; live tutoring quality, grading calibration and deployment remain separate gates.

A dated editorial notice now supplements ten affected lessons in the exact retained historical package. It explains missing/Unscored evidence, tested-case scope, lower scores after revealing failures, the distinction between saving a case and repairing an artifact, model-visible score metadata, and the separate meanings of execution, review and correctness. The notice appears above original teaching in both the panel and saved chat cards. The tutor and direct lesson/course APIs receive the same correction separately from original content. One authored JSON source feeds the frontend and its checked backend export.

Older cards may lack a course version, stable lesson ID and the new notice field. Their known text can be matched locally against explicitly authored SHA256 digests. The UI states that the original course version remains unavailable; matching text does not reconstruct enrollment history. A different known manifest cannot inherit a correction through this fallback. Async matches cannot attach to a later lesson. No extra model/API request, progress write, assessment waiver, grading queue or forced upgrade is introduced. Original lesson bytes/revisions, practice/assessment properties, package manifest and course registry remain unchanged. The transition policy now documents this distinction between editorial correction and changed passing conditions.

**Verification:** all 77 targeted backend cases, 22 frontend cases and six exporter cases pass. The initial tests incorrectly loaded the retained draft without preview permission and assumed a historical lesson had a practice check; those test assumptions were corrected without relaxing preservation. The export gate detects a stale correction copy. Real read-only delivery/tool projections agree and preserve original content; authored digests match all ten frozen targets, invalid or assessment-changing notice definitions are rejected, and missing correction assets cannot silently become successful uncorrected delivery. Ruff, ESLint, TypeScript and the isolated production build pass.

The final retained renderer matches all 814 source files from `169d3380` plus the six explicit frontend overrides. Eighteen final narrow/desktop/native-200%-zoom captures cover the panel, an old-format inactive-enrollment chat card and a card with no version/lesson identity. Actual WebCrypto matches its preserved text; browser checks confirm no course writes, unexpected routes, page errors, axe violations or page overflow. Narrow unversioned-card guidance and the enlarged panel correction were visually inspected. Earlier pinned-only captures and setup diagnostics remain retained separately.

**Evidence:** `artifacts/visual-review/certification-historical-corrections-2026-10-09/{backend-final2.log,frontend-final.log,exporter.log,ruff-final.log,eslint-final.log,fixture-final.json,source-hashes-final.json,retained-source-final.json,bundle-verification-final.json,retained-source-final,browser-final,browser-native-final,checkpoint.json}`. This is a retained-package preview and synthetic browser transport, not an actual learner migration or deployed correction. The prior teaching batch is locally committed as `169d3380`; the correction batch follows as a separate local commit.


### Checkpoint 306 Reconcile baseline preservation and current build provenance on October 9 2026

**Status:** Complete evidence audit; C8-QA-01 stays open for the explicitly identified historical scratch-script gap. Counts remain 64/162 accepted and 98 open.

All 151 selected original captures, their accessible snapshots and axe records match the baseline hashes already retained in commit `82673dc8`. The original audit and contract probe retain SHA256 `5480e73133404e65213fd5a74952952ba3832264eab27854c7761481ae34f62f` and `83468597987a64dd5919d4b58ef2332c35c6513138bc9e0b5ad77b6011b4cbc7`; all six dimension grades and eleven module grades remain unchanged. Six ledger regression cases pass. The inventory distinguishes diagnostics and repeats from selected baseline states and has no missing referenced captures or invalid manifests.

The latest retained renderer's 814 source files now match committed `e33b87bf` exactly. Its frozen build, fixture, native zoom/device-state records and the separately retained V5 preview manifest/rubric are explicitly linked. This supports reproduction of current local verification, not publication or a regrade.

The original product commit `fdce9913` remains available, and its fixture bytes match the original manifest. However, that commit plus current copies of the originally untracked certification QA scripts does not reproduce the original source fingerprint. Exact historical scratch-script bytes have not been recovered; the audit must not silently describe all old runs as byte-reproducible. The original assets remain preserved and this gap is recorded without blocking unrelated implementation work.

**Evidence:** `artifacts/visual-review/certification-evidence-reconciliation-2026-10-09/{source-hashes-committed-renderer.json,checkpoint.json}` together with the baseline/current artifacts linked there. The historical-correction batch is locally committed as `e33b87bf`; no push, publication or learner change occurred.


### Checkpoint 307 Checked arithmetic teaching and preserved-course correction on October 9 2026

**Accepted:** C8-CONTENT-03 together with 291/292. Counts are 65/162 accepted and 97 open. This accepts the arithmetic teaching and required calculation mechanism, not calibrated live grading or a published release.

Six working lessons now distinguish interpretation from a checked calculation, allow recorded calculator/human arithmetic when code execution is unavailable, and require actual source amounts, units, formula and result. The worked example uses fictional one-month USD inputs totaling 2,000 against a printed 2,150, preserving the 150 discrepancy and unresolved source meaning. Deep Analysis cannot establish arithmetic by repeating a number. A dependent memo must wait for the calculation. The existing bounded V5 budget exercise separately verifies recorded sums and source evidence; model assurance cannot override an unsupported calculation.

A dated notice supplements the exact six original lesson bodies and is also available to old cards without version metadata through authored text digests. Existing course identity, original teaching bytes, assessed requirements and earned credit remain unchanged. The mutable Code Execution practice question now explicitly conditions use on availability and authorization; its answer choices and correct selection are unchanged. This practice does not award credit. Draft revisions stay ahead of the working definitions; the already-correct V5 lesson bodies are unchanged.

**Verification:** 94 backend cases cover arithmetic/source rejection, correction delivery and isolated preview assembly; 17 reader cases and six exporter cases pass. Targeted Ruff/ESLint, export parity, isolated TypeScript and production builds pass. A structural receipt records all six editorial changes and preserved assessed definitions; independent Decimal arithmetic verifies the teaching example. The first command named a nonexistent preview test file and ran no tests; the corrected final command passes all 94. Visual inspection found a duplicate “Correct” prefix in practice feedback and removed it before the final build.

Thirty-five selected captures cover old panel/chat/unversioned correction delivery and the working calculation lesson/example at 320/1440 CSS pixels and native 200% zoom. Final bounds, axe, page errors and unexpected routes/writes pass. Enlarged feedback and correction, plus the narrow arithmetic example, were inspected. Historical-card runs use the initial byte-verified renderer; final working-teaching runs use the final renderer after the feedback-only fix. Both retain all 814 source-file hashes and bundle hashes, and no running renderer was rebuilt in place. Earlier working captures remain diagnostics.

**Evidence:** `artifacts/visual-review/certification-arithmetic-guidance-2026-10-09/{backend-final.log,frontend.log,exporter.log,content-preservation.json,source-hashes.json,fixture.json,bundle-verification.json,bundle-verification-final.json,check-results-final.json,browser-history,browser-history-native,browser-working-final,browser-working-native-final,checkpoint.json}`. Historical evidence reconciliation at 306 remains explicit about the original scratch-script fingerprint gap. No model call, deployment, publication, actual learner migration or GitHub change occurred. This batch is checkpointed locally before continuing approval teaching.


### Checkpoint 308 Concrete approval decisions and honest preview limits on October 9 2026

**Accepted:** C8-CONTENT-05. Counts are 66/162 accepted and 96 open. This accepts explicit teaching; live tutoring, assessment calibration and learner comprehension remain separate gates.

Two V5 Workflow Design lessons now name a training workflow and paused review step, then walk through approving supported findings with preserved uncertainty, rejecting an unsupported date, and revising an overbroad document selection before a new run. Approval records a decision and requests resumption; the learner still checks execution. Rejection ends the run rather than continuing and does not undo earlier work. Revising a saved definition does not rewrite a prior run. “Cancel action” is a conversational cancellation request, distinct from deciding a paused review or confirming that background work stopped.

The teaching distinguishes workflow/extraction creation, workflow dispatch and review-decision previews from existing-extraction execution that can act directly. It explains that a workflow-run preview gives an input count or mode, not every source name, fixed input or setting. Extraction field discovery precedes its creation confirmation. Learners inspect the concrete saved settings and selected sources before proceeding. Existing practice questions and all assessment requirements remain unchanged; only two draft lesson bodies/revisions change.

**Verification:** seven reviewed tool functions exactly match committed product source; source hashes and implementation observations are retained. Thirty-seven approval/transition/pause/preview-assembly cases pass, and an isolated 74-lesson preview assembles without modifying the application catalog. Thirty-one normal/native-200%-zoom captures pass bounds, axe, route and page-error checks, with no assessment writes. Narrow rejection and enlarged preview limitations were visually inspected. The retained renderer's 814 source files match arithmetic commit `e9ce89ad`; only the two runtime draft lessons changed, so no unrelated frontend rebuild was required.

**Evidence:** `artifacts/visual-review/certification-approval-decisions-2026-10-09/{source-review.json,content-preservation.json,contracts.log,assembly.log,package,renderer-provenance.json,browser,browser-native,checkpoint.json}`. Existing-workflow reviewers are product permissions, not a certification staff-grading queue. No live run was approved or rejected, no learner data changed, and nothing was published or deployed. Continue with source/scope teaching after the local checkpoint commit.


### Checkpoint 309 Distinguish source selection, retrieval and workspace scope on October 9 2026

**Accepted:** C8-CONTENT-04. Counts are 67/162 accepted and 95 open. This accepts source/scope teaching, not actual learner performance or an expanded permission boundary.

The Foundations source lesson now compares selected files, project knowledge, attached knowledge bases and configured public web lookup. It accurately describes the project knowledge-base override without claiming every agent tool is restricted to that project. It distinguishes readable source identity from availability, partial document reads and bounded retrieved passages from whole-collection review, failed search from no match, and current external evidence from general model knowledge. Examples explain wrong document, project and team selection and require correction before execution.

The source router, project context, badge, retrieval and public-search contracts were reviewed. Fifty-eight focused backend cases pass, including source authorization/routing, multiple knowledge bases, partial document reads, unavailable web search and isolated V5 preview guards. Only one draft lesson title/objective/body/revision changes; its practice and assessed requirements remain unchanged. Twenty-three focused 320/1440/native-200%-zoom captures pass bounds, axe, page errors and unexpected route/write checks. Narrow project knowledge and enlarged public-web guidance were inspected. The already verified certification renderer is reused with explicit runtime teaching delivery.

**Evidence:** `artifacts/visual-review/certification-source-scope-teaching-2026-10-09/{source-review.json,content-preservation.json,contracts.log,browser,browser-native,checkpoint.json}`. Source hashes record the current checkout review; unrelated chat changes are excluded from this certification commit. No real external search, live model, enrollment, course publication or learner migration occurred. Approval teaching is locally committed as `8f45609a`; source teaching is checkpointed before recovery work.


### Checkpoint 310 Teach inspection before retry across interruption types on October 9 2026

**Accepted:** C8-CONTENT-06. Counts are 68/162 accepted and 94 open. This accepts recovery teaching, not live provider resilience or learner-observed success.

The Foundations evidence review now includes four controlled examples: a saved template followed by a failed run, a completed tool followed by an interrupted chat reply, unavailable earlier context after reopening/reset/compaction or session expiry, and mixed success in a three-document batch. Learners preserve completed work, read the existing run or artifact state, re-establish exact source/course scope and report uncertainty before deciding whether another operation is justified. The copy explicitly says generic retry resends the previous request; stopping a streamed response is not rollback. It links these introductory decisions to existing connected-stage and per-document batch recovery teaching without inventing an in-place resume feature.

**Verification:** 26 backend preview/compaction and eight isolated frontend interruption/history cases pass. Only one draft lesson title/objective/body/revision changes; its practice and all assessment requirements are preserved. Twenty focused normal/native-200%-zoom captures pass bounds, axe, route/error and unexpected-write checks. Narrow interruption and enlarged unavailable-context examples were inspected. The retained renderer is unchanged; the new lesson arrives through synthetic course delivery. No broad UI or runtime redesign was needed.

**Evidence:** `artifacts/visual-review/certification-recovery-teaching-2026-10-09/{source-review.json,backend.log,frontend.log,browser,browser-native,checkpoint.json}`. No real run was restarted, no model called, no saved learner state altered, and no publication or deployment occurred. Source/scope teaching is locally committed as `f0534703`; continue the shared curriculum corrections after this checkpoint.


### Checkpoint 311 Controlled source instruction and external-send proposal on October 9 2026

**Accepted:** C8-CONTENT-07, with the existing required scope-and-authority recognition case. Counts are 69/162 accepted and 93 open. This accepts teaching and assessed recognition, not a live agent prompt-injection evaluation.

AI Literacy now presents a complete four-line fictional source document containing two ordinary task values and a misleading instruction to send the document externally while declaring itself approved. The source is retained as a text asset in the hashed preview package and shown verbatim in the lesson, requiring no upload or prior workspace artifact. A deliberately incorrect agent proposal illustrates the scope violation; the lesson then demonstrates refusing the send, correcting the proposal and preserving the two-field internal draft. The expected result is explicit and the difference between source data and authorization is explained. If a send is claimed to have occurred, the learner preserves and checks actual delivery status rather than assuming cancellation recalled it.

The recognition bank, learner-choice requirements and existing formative check are unchanged. Ninety-five scenario/integrity/preview cases pass, including refusal of every critical wrong recognition choice. The final isolated package contains the exact text asset under its manifest digest. Twenty final 320/1440/native-200%-zoom captures pass bounds, axe, page errors and unexpected route/write checks. Visual review found Markdown had linked the fictional email address; non-actionable address notation removes that distraction, with a final narrow inspection and snapshot confirming it. Initial captures/package are retained as diagnostics. The existing verified renderer serves the new runtime lesson; no frontend rebuild was needed.

**Evidence:** `artifacts/visual-review/certification-instruction-boundary-teaching-2026-10-09/{source-review.json,contracts.log,assembly-final.log,package-final,browser-final,browser-native-final,checkpoint.json}`. No external action or model call occurred. Recovery teaching is locally committed as `292b0a6a`; this batch is committed before continuing the remaining vocabulary and control audit.


### Checkpoint 312 Complete quality-status vocabulary without conflating decisions on October 9 2026

**Accepted:** C8-M08-01. Counts are 70/162 accepted and 92 open. This accepts teaching with its explanation practice and existing required recognition case; practical repair and live grading remain separate.

The quality lesson now explicitly distinguishes Unscored, measured quality, stale evidence, active alerts, completed execution and examiner/library review. It separates author-assigned catalog ratings from actual measurements, age thresholds from changed settings/plans, and alert acknowledgment from repair. A combined-state example explains why Completed, a strong historical score and a configuration-change alert can coexist while the current answer remains unverified. Library review does not approve every future result or create a staff queue for certification.

**Verification:** 76 backend scenario/preview/asserted-rating cases and 13 isolated badge cases pass. Source review records current score, alert and staleness semantics. The existing required historical-score scenario rejects certifying an unsupported current answer; no assessment or formative passing requirement changes. Twenty normal/native-200%-zoom captures pass bounds, axe, route and error checks, with narrow alert distinctions and enlarged combined-state guidance visually inspected. Only one draft lesson body/revision changes, delivered through the retained renderer.

**Evidence:** `artifacts/visual-review/certification-quality-vocabulary-2026-10-09/{source-review.json,backend.log,frontend.log,browser,browser-native,checkpoint.json}`. No actual validation, grading adjustment, enrollment change, publication or deployment occurred. Instruction-boundary teaching is locally committed as `78a25ccc`; continue with concrete design and authoring guidance after this checkpoint.


### Checkpoint 313 Concrete iterative design and honest extraction authoring controls on October 9 2026

**Accepted:** C8-M03-01 and C8-M04-01. Counts are 72/162 accepted and 90 open. These are teaching acceptances; actual architecture, source execution and repair assessment remain their own open gates.

Workflow Design now demonstrates a full short-document iteration: bounded requirements, an unnecessarily large extraction proposal, correction to a supported Prompt/Formatter design or simpler one-Prompt route, editor inspection of the same saved artifact, and checking actual intermediate/final output. It justifies a saved workflow only when repeat use warrants it and does not invent an extraction prerequisite. Existing proposal-preview limitations and practice remain intact.

Extraction Engine now explicitly distinguishes document-driven field discovery from authoring a complete field schema. The creation tool has no Optional/Allowed values parameters; those settings must be inspected and corrected in the extraction editor. Concrete amount/category examples reinforce precise meaning, missing evidence and source checks over field counts. Asking for a setting in prose cannot establish that it was saved. No practice answers, outcome definitions or assessed requirements change; only two draft lesson bodies/revisions advance.

**Verification:** 41 creation, project-binding, extraction-field and preview-assembly cases pass. Current tool signatures, builder operations and editor labels were reviewed and hashed. Forty normal/native-200%-zoom captures cover each changed teaching section and preserved practice, with no bounds, axe, page errors or unexpected writes/routes. Narrow refinement and enlarged field settings were visually inspected. Runtime lesson delivery reuses the retained renderer; unrelated workspace edits remain outside this batch. Old preview servers were stopped after their completed QA; the final isolated renderer remains available for ongoing checks.

**Evidence:** `artifacts/visual-review/certification-design-authoring-teaching-2026-10-09/{source-review.json,contracts.log,browser-design,browser-design-native,browser-fields,browser-fields-native,checkpoint.json}`. No actual workflow, extraction or learner enrollment was changed, and no model call, publication or deployment occurred. Quality vocabulary is locally committed as `33b9db31`; continue the remaining historical copy reconciliation after this checkpoint.


### Checkpoint 314 Correct remaining credential, time and control claims in current and preserved teaching on October 9 2026

**Status:** Complete for this bounded copy batch; C8-CONTENT-08 remains open. Counts stay 72/162 accepted and 90 open.

Eight working lessons and the introductory module description now remove premature Governance-only credential claims, unmeasured module durations/time savings/rapid-review promises, future Package Builder promises, automatic correct-workflow assumptions, universal previous-step input claims and review-after-consequence advice. Export portability now requires resolving local dependencies and testing the imported revision. Current practice and assessed properties are unchanged; only content/revisions and the introductory metadata change. Corresponding draft revisions stay ahead without changing their already-correct bodies.

A third dated editorial notice supplements the exact original versions of those eight lessons in panel and tutor delivery and on old cards, including text-matched cards with unknown course identity. Original lesson/package/rubric bytes, saved requirements and earned credit remain preserved. The notice is guidance rather than an automatic upgrade or a new grading condition.

**Verification:** 75 backend correction/preview/scenario, 17 reader and six exporter cases pass; export parity, targeted ESLint, isolated TypeScript and production build pass. Structural preservation and unchanged registry digests are retained. The exact 814-source renderer derives from `8148432e` with only the two listed frontend overrides. Twenty-seven final captures pass normal/native zoom, bounds, axe, page-error and unexpected-write checks. Current credential copy, historical notice and expanded checkpoint guidance were visually inspected. The first glossary harness used indices against a shrinking closed-disclosure list and timed out; its corrected first-remaining loop passes, with diagnostics retained. No product behavior was changed to accommodate the harness.

The audit also records unfinished work: old extraction copy still overpromises optionality/constraints/repetition; the historical module description itself needs correction visibility before lesson entry; and the retained multi-step enrichment text advertises four task types while its retained rubric checks five and aggregates across workflows. Do not silently rewrite that historical grading contract or encourage unrelated tasks to satisfy its counter. New V5 outcome evidence and historical support/equivalence remain distinct.

**Evidence:** `artifacts/visual-review/certification-remaining-copy-2026-10-09/{backend.log,frontend.log,exporter.log,check-results.json,content-preservation.json,remaining-audit.json,source-hashes.json,fixture.json,bundle-verification.json,browser-history,browser-history-native,browser-working-governance-final,browser-working-controls-native-final,checkpoint.json}`. No live model, publication, deployment, real enrollment or GitHub issue changed. The design-authoring batch is locally committed as `8148432e`; this bounded correction batch is checkpointed before the remaining issues.


### Checkpoint 315 Show historical corrections before module descriptions on October 9 2026

**Status:** Module-header follow-up complete; C8-CONTENT-08 remains open for the remaining copy reconciliation. Counts remain 72/162 accepted and 90 open.

Historical Governance and AI Literacy now display dated guidance before their original module descriptions, correcting the Governance-only credential implication and unmeasured fixed completion times before lesson entry. Backend module projection and the panel share authored notices bound to the exact frozen manifest and module. An unknown course can match an explicitly authored description digest without inferring its course identity; a different known manifest cannot inherit the notice. Original descriptions, package bytes, assessment requirements and earned credit remain unchanged.

**Verification:** 22 backend correction/preview, 24 frontend correction/entry/reader and six exporter cases pass; targeted lint, export parity, isolated TypeScript and production build pass. Twelve 320/1440/native-200%-zoom captures pass bounds, axe, page-error, unexpected-route and no-course-write checks. Narrow Governance and enlarged course-pace guidance were visually inspected. The isolated renderer is based on `6c13a1ff` plus five enumerated frontend overrides, with 815 retained source hashes. The isolated component test run passed 20 cases but could not import ModuleDetail’s PDF worker through its dependency symlink; the same complete 24-case set passes from the checkout. This is recorded as a harness limitation, not a product failure.

**Evidence:** `artifacts/visual-review/certification-module-corrections-2026-10-09/{backend.log,frontend.log,frontend-checkout.log,exporter.log,typescript.log,build.log,fixture.json,bundle-verification.json,browser,browser-native,checkpoint.json}`. No model call, publication, deployment, original-course mutation or learner write occurred. Continue the extraction-copy corrections after this local checkpoint.


### Checkpoint 316 Correct extraction guarantees and restore historical diagram keyboard access on October 9 2026

**Status:** Extraction copy follow-up complete; the course-wide copy audit remains open. Counts remain 72/162 accepted and 90 open.

Five working lessons now explain per-pass settings and refinement fallback, optionality versus source support, permitted categories versus correctness, two-attempt consensus with possible additional voting, configured field grouping and evidence for an actual repaired result. Two noncredit practice checks use the corrected teaching. Their graded lab walkthrough and all module/assessment properties are unchanged. Corresponding draft revisions remain ahead. A dated correction for the exact five frozen lessons supplies the same distinctions without rewriting the historical package or claiming an illustrative repair was executed.

Historical-card QA exposed a separate accessibility defect: a disabled outer fieldset prevented keyboard access to its scrollable diagram. Lesson cards now give the reader an explicit read-only boundary and disable only historical practice controls. Historical navigation cannot save course progress; source reading, diagram scrolling and opening the current learning panel remain available. Other stale action cards retain their disabled boundary. Regression cases verify both boundaries, including a read-only reader whose lesson identity would otherwise match.

**Verification:** 91 backend correction/preview/field/engine, 54 frontend card/reader/correction and six exporter cases pass; targeted lint, export parity, isolated TypeScript and production builds pass. Thirty-four initial-renderer teaching captures and 29 final-renderer historical/active-practice captures pass their bounds, axe, errors and unexpected-write checks. Final historical tests use actual Tab navigation and arrow-key scrolling at narrow/desktop/native-200%-zoom sizes, while asserting practice stays disabled. Narrow consensus, enlarged optionality and visible diagram focus were inspected. Initial historical failures remain diagnostic evidence. One new test fixture initially omitted the progress module map; the complete fixture passes without changing product behavior.

**Evidence:** `artifacts/visual-review/certification-extraction-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend-final.log,exporter.log,bundle-verification.json,bundle-verification-final.json,browser-working,browser-working-native,browser-history-final,browser-history-native-final,browser-working-final,checkpoint.json}`. No live model/extraction, original graded requirement, learner state, publication or deployment changed. The module-header batch is locally committed as `04e4b795`; continue multi-step reconciliation after checkpointing this batch.


### Checkpoint 317 Reconcile connected-workflow teaching and disclose historical star limitations on October 9 2026

**Status:** Bounded copy and notice-delivery work complete. C8-CONTENT-08 and C8-M05-04 remain open; a warning does not establish an equivalent historical assessment. Counts remain 72/162 accepted and 90 open. The checklist’s stale 62/162 headline is corrected to its actual checked-item count.

Five working multi-step lessons now teach configured sources and task overrides, bounded interpretation, justified step separation, unsupported deadline/policy claims and checks after formatting. Two noncredit practice checks follow the corrected teaching. The original lab walkthrough and all graded module properties remain unchanged. The working glossary retains general recovery guidance without copying controls available only in the unpublished outcome course. Draft revisions stay ahead. A dated correction supplements the exact five frozen lessons and identifies the original worked chain as illustrative rather than the assigned subaward’s answer key.

A module notice explains the historical four-versus-five-task-type discrepancy and cross-workflow counting. It is visible in Learn, Challenge and historical module cards, including exact-overview matches with unknown course identity. The same notice reaches the read-only exercise and tutor responses; original criteria and grading behavior are untouched. It explicitly discourages adding irrelevant tasks for optional stars and states that any equivalent assessment needs a separate reviewed amendment or course release. Existing credit is preserved and no staff grading queue is introduced.

**Verification:** 59 backend correction/preview/tool-result plus 24 workflow input/override cases, 40 frontend cases and six exporter cases pass. Targeted lint, export parity, isolated TypeScript and production build pass. Fifty-nine final captures cover current teaching, historical lesson cards, module/challenge notices and unknown-history cards, including native 200% enlargement. Bounds, axe, page-error and unexpected-write checks pass. Enlarged challenge guidance and the narrow unsupported-deadline example were inspected. An initial module-card harness asserted before streaming finished; waiting for the criteria fixes that harness race, with its diagnostic run retained. The certification tool function matches the proposed scoped commit; unrelated knowledge-base edits remain excluded.

**Evidence:** `artifacts/visual-review/certification-multistep-copy-2026-10-09/{source-review.json,content-preservation.json,tool-scope-verification.json,backend.log,workflow-contracts.log,frontend.log,exporter.log,bundle-verification.json,browser-working,browser-working-native,browser-stars-final,browser-stars-native,browser-history,checkpoint.json}`. Synthetic transport omits the exercise’s lab-document list solely to inspect challenge copy without provisioning; it preserves the actual criteria. No real lab, model, learner, original course, publication or deployment changed. Extraction fixes are locally committed as `eb9dbba0`; continue the consolidated acceptance review after this checkpoint.
### Checkpoint 318 Reconcile tracker summaries and the active queue on October 9 2026

**Status:** Tracking repair complete; no acceptance item newly closed. Counts remain 72/162 accepted and 90 open.

The evidence generator now rejects missing or contradictory checklist/progress headlines and duplicate acceptance IDs before generating a report. Checked items remain authoritative. This catches the stale 62/162 checklist headline discovered at 317 rather than allowing the searchable ledger and prose to disagree. Twelve inventory tests pass, including count drift, missing summaries and duplicate IDs; Ruff passes. Original audit grades and capture evidence are untouched.

The active queue now replaces the obsolete October 2 task order and groups the remaining work by concrete dependencies: remaining control/copy corrections, missing interaction evidence, transition/release operations, deferred live practical grading, and actual accessibility/learner/release observations. Implemented mechanisms, acceptance and release verification remain separate. All 90 open requirements remain in scope; no staff grading queue or new deadline is introduced.

**Evidence:** `artifacts/visual-review/certification-tracking-reconciliation-2026-10-09/{tests.log,checkpoint.json}`. The multi-step batch is locally committed as `8b2e73c7`. Continue the remaining copy audit without rerunning unchanged whole-course captures.


### Checkpoint 319 Correct batch coverage, deliverable inputs and handoff receipts on October 9 2026

**Status:** Ten-lesson copy batch complete; the full copy audit remains open. Counts remain 72/162 accepted and 90 open.

Five working batch lessons now distinguish queued execution from sequential completion, aggregate terminal status from per-item success, a representative pilot from one easy example, verified source repair from re-uploading unreadable bytes, and partial downloads from complete coverage. Three output lessons correct the assumption that a later CSV task can recover tabular rows after a Prompt has emitted prose, require inspection of actual files/ZIP members and distinguish generation from authorized release. Two Governance lessons explain export contents/dependencies and sharing/import receipts without treating them as saved course completion or verified portability. Three noncredit practice checks follow the corrected teaching.

Module metadata, graded requirements and the frozen course remain unchanged. The Governance walkthrough keeps its original sharing requirement and separates its course completion action from the examiner’s independent review. It introduces no staff certification queue. Three dated notices supplement the exact ten historical lessons, with unchanged source bytes and earned credit. Draft bodies were already aligned; their revisions remain ahead.

**Verification:** 139 focused backend correction/preview/batch/output/model cases, 38 export/import cases, 35 isolated frontend reader/card cases and six exporter cases pass; export parity, targeted lint, isolated TypeScript and production build pass. Sixty-two captures cover all ten updated lessons at 320/1440 widths, targeted native 200% batch/output content and historical panel/known/unknown chat cards. Bounds, axe, errors and unexpected writes pass. Narrow course-completion guidance and enlarged source repair/output data-shape guidance were inspected. The broader initial backend run had 338 passing cases and nine unrelated DescribeImage failures because sandbox DNS could not resolve example.com; that engine is unchanged, and the failed run remains recorded rather than reported as a full-suite pass.

**Evidence:** `artifacts/visual-review/certification-delivery-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,backend-focused.log,export-contracts.log,frontend.log,exporter.log,bundle-verification.json,browser-batch,browser-batch-native,browser-output,browser-output-native,browser-governance,browser-history,checkpoint.json}`. No actual batch, generated deliverable, sharing action, learner credit, publication or deployment changed. Tracking consistency is locally committed as `d4bcd6f8`; continue the remaining copy and interaction acceptance work after checkpointing this batch.


### Checkpoint 320 Correct introductory model and source-evidence promises without changing old requirements on October 9 2026

**Status:** Eleven-lesson introductory copy batch complete; full copy reconciliation remains open. Counts remain 72/162 accepted and 90 open.

Six AI Literacy lessons now distinguish generated text from retrieved evidence, formatting from source truth and tool success from authorization. The twelve-proposal sequence is explicitly illustrative and no longer promises an unmeasured fifteen-minute/manual versus thirty-minute/automated comparison. Institutionally managed UI is not presented as proof of an authorized provider/data route. Five Foundations lessons explain readable source preparation, actual file/project/retrieval scope, configured operations, evidence-bound values and inspection before retries. One noncredit model-evidence practice check follows the revised teaching.

The original Foundations example remains tied to its saved three-field base and five/eight-field enrichment; expected names and amounts are teaching targets, not executed results. New-course scenario-assessment directions are not copied into the old introductory course. Module metadata, original lab walkthrough, assessed requirements and frozen package are unchanged. Two dated corrections reach exact historical lessons and old cards without inferring unknown course identity or rewriting credit. Only draft revisions advance where necessary; the already-correct V5 bodies remain intact.

**Verification:** 59 backend correction/preview/chat-tool, 21 isolated frontend reader/correction and six exporter cases pass; export parity, lint, isolated TypeScript and production build pass. Fifty-nine captures cover all eleven changed lessons at 320/1440, targeted native-200% practice/source/recovery sections and preserved panel/known/unknown chat lessons. Bounds, axe, error and unexpected-write checks pass. The narrow illustrative sequence and enlarged historical base/enrichment distinction were visually inspected.

**Evidence:** `artifacts/visual-review/certification-intro-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,exporter.log,bundle-verification.json,browser-literacy,browser-literacy-native,browser-foundations,browser-foundations-native,browser-history,checkpoint.json}`. No model execution, original grading rule, enrollment, publication or deployment changed. Delivery corrections are locally committed as `e9c6ea0e`; continue process/design/advanced wording and the remaining acceptance work after this checkpoint.


### Checkpoint 321 Correct process fit, workflow boundaries and parallel dependencies on October 9 2026

**Status:** Thirteen-lesson copy batch complete; full copy reconciliation remains open. Counts remain 72/162 accepted and 90 open.

Seven Process Mapping lessons remove unsupported work-percentage promises and distinguish method suitability, bounded scope and actual review before consequential actions. Four Workflow Design lessons explain the extract/reason/deliver pattern as a choice, configured sources and the operational meaning of approval, rejection and resumption. Two Advanced Nodes lessons remove a fixed node-count promise and distinguish parallel independence from data dependencies, failure from rollback and reasoning from checked arithmetic. Three noncredit practice checks follow the revised teaching.

The original Advanced Nodes course explicitly retains its advanced-node and parallel-task requirements and a supported internal operation route. The unpublished course's replacement assessment is not copied into these instructions. Module metadata, original lab walkthroughs, graded requirements and frozen package bytes are preserved. Three dated notices supplement the exact thirteen historical lessons. Draft revisions remain ahead without changing their already-correct bodies.

**Verification:** 75 backend correction/preview/input/parallel/approval cases, 21 isolated frontend reader/correction cases and six exporter cases pass. Export parity, targeted lint, isolated TypeScript and production build pass. Sixty-seven captures cover all changed lessons at 320/1440 widths, targeted native 200% approval/advanced content and preserved panel/known/unknown chat lessons. Final manifests contain successful completion observations after all assertions, with no blocked captures, bounds failures, axe violations, page errors or unexpected writes. Narrow review-boundary guidance and enlarged original Advanced Nodes requirements were visually inspected.

**Evidence:** `artifacts/visual-review/certification-design-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,exporter.log,bundle-verification.json,browser-process,browser-design,browser-design-native,browser-advanced,browser-advanced-native,browser-history,checkpoint.json}`. No actual workflow execution, model call, original grading change, learner write, publication or deployment occurred. Introductory corrections are locally committed as `fc49d810`; continue remaining validation copy and original lab controls, then consolidate interaction acceptance.


### Checkpoint 322 Distinguish saved validation plans from current accuracy evidence on October 9 2026

**Status:** Four-lesson validation follow-up complete; the lab-control reconciliation remains open. Counts stay 72/162 accepted and 90 open.

The remaining validation concepts now separate presence, shape, repeatability and source accuracy; require checked expectations and representative cases; and preserve the original failure and actual retest after changes. A saved plan or old green score does not establish that a current run was checked. Two existing noncredit practice checks follow these distinctions. The glossary's practice remains formative and adds no new practical submission requirement to the original course. Module metadata, graded requirements and frozen content remain unchanged; draft revisions advance without altering their bodies.

A dated notice supplies the same guidance to the exact four historical lessons in the panel, tutor and preserved cards. Verification includes 117 backend correction/preview/validation cases, 21 isolated frontend reader/correction cases and six exporter cases; export parity, lint, isolated TypeScript and production build pass. The first frontend command named the reader test at the wrong directory and ran only three correction cases; the corrected explicit reader path passes the complete 21-case set, with both logs retained.

Thirty-six captures cover the four current lessons at narrow/desktop widths, targeted actual 200% zoom and historical panel/known/unknown chat cards. Bounds, axe, errors and unexpected-write checks pass. Enlarged current-run validation and failure-preservation text was visually inspected. The walkthrough audit found an actual remaining mismatch: the batch control is labeled “Run per document,” not “Batch” mode; the original lab instructions will be reconciled next while preserving their assigned counts.

**Evidence:** `artifacts/visual-review/certification-validation-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,frontend-final.log,exporter.log,bundle-verification.json,browser-working,browser-native,browser-history,checkpoint.json}`. No model call, actual validation execution, original grading change, learner write, publication or deployment occurred. Process/design corrections are locally committed as `0c052fde`; continue the original lab-control audit and consolidated interaction acceptance.


### Checkpoint 323 Align retained lab walkthroughs with current editor controls on October 9 2026

**Status:** Four original lab walkthroughs reconciled; C8-CONTENT-08 remains open for module-level objectives and tips. Counts stay 72/162 accepted and 90 open.

Foundations now identifies Library → New → New Workflow and the Extractions task, checks actual lab readiness and explains configured input scope rather than claiming every run requires a manual selection. Extraction preserves the 15-field base while explaining precise instructions, Optional and Allowed values without equating settings with source truth. Multi-Step names Extractions, Prompts and Format and requires inspection of saved input connections. Batch identifies Run per document, accounts for terminal failures and explains a targeted single-document recovery run.

The original three-field base/enrichment, 15-field base, three-step pipeline and three assigned batch documents remain unchanged. Four exact historical lesson notices supply current controls without rewriting old packages. Only lesson body/revision and corresponding draft revision changes are made; practices, module metadata and grading contracts are preserved.

**Verification:** 50 backend correction/preview/input cases, 40 distinct frontend correction/reader/lab/input/field cases and six exporter cases pass; export parity, lint, isolated TypeScript and production build pass. The isolated frontend run passed 29 cases but its dependency symlink prevented the lab-status suite's PDF worker import; the unchanged lab-status suite passes its 11 cases from the checkout. Both logs retain this harness limitation. Thirty-three captures cover all four walkthroughs at 320/1440, native-200% batch controls and historical panel/known/unknown batch cards. Bounds, axe, errors and unexpected-write checks pass; enlarged per-document control and recovery guidance was visually inspected.

**Evidence:** `artifacts/visual-review/certification-lab-controls-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,frontend-lab-checkout.log,exporter.log,bundle-verification.json,browser-foundations,browser-extraction_engine,browser-multi_step,browser-batch,browser-native,browser-history,checkpoint.json}`. Actual editor labels and run-input rules were inspected; no learner lab or model was executed. No original grading change, learner write, publication or deployment occurred. Validation corrections are locally committed as `d0f0e9d3`. Remaining metadata includes overly strong arithmetic, optional-field and production-readiness tips and inconsistent example counts; correct those before declaring the copy audit complete.


### Checkpoint 324 Reconcile module objectives and hints with corrected teaching on October 9 2026

**Status:** Nine modules' editorial metadata reconciled; cross-module star-description review remains open under C8-CONTENT-08. Counts stay 72/162 accepted and 90 open.

Module objectives, descriptions and tips now distinguish the original field-count base from enrichment, source checks from example targets, category/optional settings from evidence, model analysis from arithmetic, configured dependencies from concurrent execution and examiner status from production readiness. Process Mapping is no longer described as supplying a workflow. Eleven unused, unmeasured completion-time estimates are removed from current metadata. All lesson bodies, practices, graded criteria and frozen course bytes remain unchanged.

Nine dated module notices supply matching guidance before preserved descriptions and on their Challenge views. Backend tests now exercise every module with notices through the actual exercise and tutor projection, while preserving original criteria and exact-identity boundaries. The Tips & Hints disclosure now exposes its expanded state and controlled list; actual keyboard expansion and collapse is verified across current and historical modules.

**Verification:** 47 backend correction/preview cases, 22 frontend correction/entry/card cases and six exporter cases pass; export parity, lint, isolated TypeScript and production build pass. An initial test assumed only one description notice; scoping its existing assertion to the named correction preserves the intended identity check when multiple notices apply. Seventy-eight captures cover nine current and historical modules at narrow/desktop sizes and selected actual 200% hints. Bounds, axe, page errors and unexpected writes pass. Enlarged advanced hints with visible focus and the narrow historical extraction notice were visually inspected. Synthetic exercise responses omit lab documents and criteria only to inspect these guidance states without provisioning; they do not verify actual lab completion or star criteria.

**Evidence:** `artifacts/visual-review/certification-module-guidance-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,frontend-final.log,exporter.log,bundle-verification.json,browser-working,browser-history,browser-native,checkpoint.json}`. No live model, learner write, grading-rule change, publication or deployment occurred. Lab controls are locally committed as `892f1fd2`. Continue the consolidated interaction-evidence review and finish star-description reconciliation; legacy field/count and cross-artifact grading limitations remain separate from V5 practical assessment acceptance.


### Checkpoint 325 Repair enlarged-text reading width and consolidate enlargement acceptance on October 9 2026

**Accepted:** C8-A11Y-09. Counts are 73/162 accepted and 89 open. This accepts browser enlargement/reflow for the implemented course surfaces; it does not close actual screen-reader, mobile OS keyboard, supported-engine, live-grading or learner-observation gates.

Consolidation maps retained native-200% and doubled-text evidence to all 74 draft lessons and practice, panel/reading/navigation, reflections and XP, assignments and source access, practical forms and recovery, graduation/certificates, bridge choices and later content changes. Seventy-three prior runs are selected by explicit surface and checked for present assets, empty axe/errors/routes, expected zoom geometry and completion observations. Superseded failed runs are excluded. Existing evidence remains tied to its original checkpoint rather than described as a fresh full-course execution.

New doubled-text inspection caught a defect that page-width checks missed: rem-based padding stacked across the panel, module, lesson, notice and answer cards, squeezing ordinary words and feedback into narrow columns. Small-screen padding now stays at eight pixels at those boundaries while larger-screen spacing remains. Answer text has an explicit shrinking/wrapping boundary. The production pre-fix renderer fails the new minimum answer-width assertion; the corrected renderer passes it and a minimum correction-paragraph width check. Final screenshots show useful line lengths without reducing the enlarged font.

**Verification:** 54 affected frontend tests, targeted ESLint, isolated TypeScript and production build pass. Fifty-four final captures cover doubled-text current/historical module guidance and practice, actual native-200% controls, plus ordinary-size panel/known/unknown historical cards. Bounds, readable-width guards, axe, errors and unexpected writes pass. Enlarged correction prose and corrected answer feedback were visually inspected. Thirty initial doubled-text captures passed the earlier automated checks but failed manual readability review; their manifests explicitly record non-acceptance. The separate pre-fix assertion failure is retained. No learner state, grading, original content, model call, publication or deployment changed.

**Evidence:** `artifacts/visual-review/certification-enlargement-reconciliation-2026-10-09/{coverage-review.json,frontend.log,typescript.log,build.log,bundle-verification.json,browser-before-width-guard,browser-module-text-final,browser-historical-text-final,browser-practice-text-final,browser-module-native-final,browser-practice-native-final,browser-history-normal-final,checkpoint.json}`. Module guidance is locally committed as `f971df43`. Continue other interaction requirements and the historical star-description audit; do not reopen this item solely because separate assistive-technology or live-course release gates remain open.


### Checkpoint 326 Reconcile all exercise directions and disclose preserved rubric limits on October 9 2026

**Status:** All eleven current exercise directions reconciled; final practice-feedback audit remains open under C8-CONTENT-08. Counts remain 73/162 accepted and 89 open.

Current exercise overviews and panel/chat instructions now use actual lesson counts and control names, distinguish proposal/save/run/source review/completion, remove internal tool-name directions and avoid promises of automatic accuracy or increasing scores. Output guidance requires the right input shape and actual file inspection; Governance separates the sharing request, examiner enrichment, saved completion and tested portability. One Governance lesson receives the same completion/monitoring clarification. Its existing practice is preserved for the separate final feedback audit.

The frozen rubric was inspected across every module. Current overviews and eleven dated historical module notices explicitly describe its limits: participation reflections, field/count checks across artifacts, execution metadata without source verification, the known multi-step four-versus-five discrepancy, output counters without inspected files, validation counts without established current accuracy, batch counts without distinct-source proof and original sharing/reviewer status. These disclosures do not repair or reinterpret old grades. All source assignments, expected fields/values, star criteria and frozen package bytes remain unchanged; equivalence and V5 assessed outcomes keep their separate gates.

**Verification:** 49 backend correction/preview cases, 55 isolated frontend reader/card/correction cases and six exporter cases pass; export parity, lint/Ruff, isolated TypeScript and production build pass. The new backend case checks actual current exercise/tutor delivery for all eleven modules and compares every non-editorial property against the frozen original. Exact historical/current text bindings and the single lesson-body/revision delta are verified. Seventy-three final captures verify exact current panel/chat directions for all eleven modules, keyboard instruction disclosure, native zoom, historical output criteria/cards and the revised Governance paragraph. Bounds, axe, errors and unexpected writes pass. Enlarged validation directions and narrow historical output guidance were visually inspected.

Two initial current-card runs intentionally reached the malformed-response guard because the harness added enrollment/version identity without its required course title. Completing that synthetic identity fixes the fixture; no product/schema relaxation was made. Both failed runs remain diagnostics. A test-append command initially used a duplicate backend directory prefix and made no change; the correctly applied test and final run pass.

**Evidence:** `artifacts/visual-review/certification-exercise-guidance-2026-10-09/{rubric-copy-audit.json,content-preservation.json,backend-complete.log,frontend.log,exporter.log,bundle-verification.json,current-fixture.json,historical-fixture.json,browser-current-final,browser-current-native-final,browser-historical,browser-historical-native,browser-governance-lesson,browser-governance-lesson-native,checkpoint.json}`. Browser transport uses a synthetic active identity and omits lab-document gating only to inspect directions; actual criteria stay intact. No model call, learner write, new staff queue, original grade, publication or deployment changed. Enlargement is locally committed as `47b0a55c`. The final feedback scan identified old practice explanations that still equate Checked with measured quality or overstate model capability; correct those before accepting the complete copy audit.


### Checkpoint 327 Correct the remaining formative practice explanations on October 9 2026

**Status:** Five existing practice checks corrected; C8-CONTENT-08 stays open for milestone wording. Counts remain 73/162 accepted and 89 open.

Practice now separates institutional authority from model fluency, checked arithmetic from repeated reasoning, actual file inspection from a download link, examiner acceptance from measured quality and successful validation from sharing status. Four historical notices cover the five exact preserved lessons. Lesson bodies, module metadata, graded exercises and frozen package bytes stay unchanged; draft revisions advance without changing draft teaching.

**Verification:** 53 backend correction/preview cases, 56 frontend correction/reader/card/practice cases and six exporter cases pass. Export parity, targeted lint, isolated TypeScript and production build pass. Forty-three successful captures cover all five practices at narrow/desktop widths, actual 200% Governance feedback and historical panel/known/unknown cards. Bounds, axe, errors and unexpected-write assertions pass. Enlarged practice feedback and the narrow historical correction were visually inspected. The first historical run encountered two applicable notice warnings; the harness now scopes its identity assertion to the intended named notice. The failed run is retained, with no product relaxation. An initial content-edit script stopped at a single-line practice object after draft revision edits; the completed preservation audit verifies exactly the intended five practices and revisions.

**Evidence:** `artifacts/visual-review/certification-practice-copy-2026-10-09/{source-review.json,content-preservation.json,backend.log,frontend.log,exporter.log,bundle-verification.json,browser-ai_literacy,browser-advanced_nodes,browser-output,browser-governance,browser-governance-native,browser-historical-final,checkpoint.json}`. No live grading, model execution, learner write, publication or deployment occurred. Exercise directions are locally committed as `09256ac6`. The final milestone scan found that the tier overlay directly renders preserved celebration copy even when `certified` is false; resolve premature certification claims before accepting the copy audit.


### Checkpoint 328 Bound tier celebrations to confirmed course status and accept copy alignment on October 9 2026

**Accepted:** C8-CONTENT-08. Counts are 74/162 accepted and 88 open. This accepts current control/count/capability wording and honest historical corrections, not new grading validity or equivalence of original stars.

The final scan confirmed a visible credential overclaim: any completed tier rendered its preserved celebration string even when the server returned `certified: false`. In an any-order course the Architect tier could therefore claim the certification before other modules were complete. The shared overlay now states that the tier's modules are complete and directs the learner to remaining requirements. The confirmed course-complete branch still uses the actual course identity and certificate action. Frozen package wording, progress, XP, rubric and issuance are unchanged.

Copy acceptance consolidates source-reviewed teaching and original-course corrections at 305–324, all eleven exercise directions and legacy rubric disclosures at 326, five formative feedback corrections at 327 and this milestone repair. The known original star mismatch remains a separate equivalence/support decision; the correction notice explicitly preserves old requirements rather than claiming to repair the old rubric. All 74 V5 lessons remain unpublished.

**Verification:** 31 overlay/panel cases, targeted lint, isolated TypeScript and production build pass. The regression supplies preserved certification-claim copy with `certified: false`. Five browser captures cover the actual completion path, narrow/desktop layout, actual 200% zoom, modal keyboard containment and dismissal with one synthetic completion write and no credential. Bounds, axe, errors and unexpected routes pass. The enlarged tier message and visible Continue focus were inspected. Existing certified-completion tests remain passing; unchanged certificate-access coverage is retained.

**Evidence:** `artifacts/visual-review/certification-milestone-copy-2026-10-09/{copy-coverage.json,frontend.log,lint.log,typescript.log,build.log,bundle-verification.json,browser-normal,browser-native,checkpoint.json}`. Formative corrections are locally committed as `ab18ba82`. No real learner, grade, credential, model execution, publication or deployment changed. Continue consolidated interaction acceptance; actual assistive technology, mobile keyboard, live grading and learner observation remain open.
