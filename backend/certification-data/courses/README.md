# Certification course releases

This catalog prepares optional course upgrades while preserving existing enrollment requirements. Chat and certification API/panel delivery are connected behind `certification_versioning_enabled`, which defaults to false. The normal application therefore still uses the original course. The continuation package is a draft, and no enrollment defaults are configured. Do not enable a learner transition through the internal repository activation method until reviewed credit transfer, remaining enrollment-aware supporting paths and interrupted-attempt reconciliation are implemented.

## Package identity

Each release contains a manifest, chat lessons and reflection questions, panel modules, exercises, sample PDFs and a preserved grading module. The registry pins the manifest digest; the manifest pins every packaged asset. Readers reject missing, changed or mismatched assets. A loaded package retains immutable bytes across concurrent requests and returns fresh parsed values to callers.

The preserved grader has a static, installed runner. Its source must match the packaged rubric byte for byte, and its module order and reward rules must agree with the manifest. Adding a new rubric requires a supported runner and tests; a Python file inside a package is never dynamically executed.

`legacy-2026-10-02.1` is a continuation baseline with 11 modules and 74 stable lesson identities. It retains current assessed requirements, including known grading weaknesses. It does not establish which historical requirements an existing learner completed, nor does it claim a completed Vandalizer 5.0 competency upgrade. The earlier full repository snapshot remains under `backend/certification-releases`.

## Author and verify

Run Python commands with the backend environment. From the repository root:

```bash
cd frontend
node scripts/export-lessons.mjs
cd ..
backend/.venv/bin/python scripts/create_certification_release.py candidate-1 --title "Candidate course" --description "Review draft" --provenance authored-release
backend/.venv/bin/python scripts/check_certification_releases.py --base-ref HEAD
backend/.venv/bin/python scripts/manage_certification_release.py inspect candidate-1
```

The creator verifies a staged package before registering it and refuses to overwrite an existing identity. A failed validation leaves no registered partial release. A process failure after the package rename may leave an unregistered directory; inspect that directory before reusing the identity. Registry writes are atomic and local authoring operations share a file lock.

Use a new release identity for changed published content. Drafts are not enrollable. CI compares the registry with the base commit and rejects changes to published or retired manifests, their removal, or silent removal of existing-learner support.

## Release lifecycle

Publication requires the digest inspected during review. Authored or outcome-based releases additionally require the exact current impact report and its cohort inventory:

```bash
backend/.venv/bin/python scripts/inspect_certification_release_impact.py --source-release-id SUPPORTED_SOURCE --target-release-id candidate-1 --cohort-inventory REVIEWED_INVENTORY.json > REVIEWED_IMPACT.json
backend/.venv/bin/python scripts/manage_certification_release.py publish candidate-1 --expected-manifest-sha256 REVIEWED_SHA256 --impact-report REVIEWED_IMPACT.json --cohort-inventory REVIEWED_INVENTORY.json
```

Publication does not select an enrollment default. The separate `default` command selects a published course for future initializations. `legacy-continuation` selects a supported continuation baseline for records with unknown historical provenance. Neither changes an existing learner's active selection. `retire` closes a release to new enrollment while keeping its assets and requirements available to existing learners; it refuses to retire the new-learner default until a replacement has been chosen.

These commands edit repository metadata only. They do not deploy a release, migrate records, notify learners or enable the staged application integration.

The inspector exits 2 while release gates remain unresolved. Publication recomputes the comparison under the authoring lock and rejects missing, edited or stale reports. The current implementation always blocks new competency publication pending live compatibility and rollout evidence; synthetic readiness flags cannot authorize it. A frozen continuation baseline uses its separate preservation path. If source and target catalogs are separate, pass the same `--source-catalog-root` to inspection and publication, and use the target catalog root for each command.

The comparison also runs the actual certificate renderer in memory using the target title, release identity and credential promise. Text that exceeds the certificate areas, or unavailable renderer assets, produces `target_certificate_unrenderable`. A successful preflight verifies these course fields render with a synthetic identity; visually inspect the PDF and validate learner-name behavior separately. It does not issue, store or send a credential.

### Credential reader deployment boundary

New competency issuance preserves the original credential promise in schema 2. Existing schema-1 records retain their exact shape and meaning; neither a read nor an upgrade fills in a newer scope. Before enabling an outcome-based course, every credential reader and recovery/notification worker must support both schemas. Record the deployed revisions and verify original downloads, interrupted issuance and notice replay across all serving workers. Local single-process tests are not that deployment evidence.

After any schema-2 issuance, rolling back to a schema-1-only reader is unsafe. Disable new course writes/offers while retaining compatible history/download/recovery readers, then repair forward or deploy a rollback that still supports both schemas. Preserve issuance records and original notice hashes; do not downgrade, delete or relabel them. No competency release or actual schema-2 learner issuance has been authorized by these local checks.

## Enrollment boundaries

An enrollment owns a course version, manifest digest, progress reference and provenance. A separate unique selection records the learner's active choice. Restartable initialization uses deterministic IDs and insert-only writes; legacy credit, dates, reflections and lab references remain in the original record. Duplicates, missing records and mismatched ownership fail closed for reconciliation.

Writes are serialized per active enrollment. Their durable marker records the operation, enrollment, course and rubric. Switching while work is in flight or submitting through a stale enrollment is rejected. A failed worker cleanup leaves the marker in place. It must be reconciled before a transition; no automatic timeout assumes that external work stopped.

Course delivery resolves teaching by the enrollment's verified package. Saved positions use lesson identity and revision with stale-session conflict detection. Chat and panel share the cursor; navigation writes do not award credit. The staged delivery and grading tests exercise actual MongoDB persistence, not a mocked progress store.

Keep a lesson's authored ID when its concept is retained, including after a title change or reorder. Never regenerate an existing ID from its current title or numeric position. A new or replacement concept gets a new ID. Changes to retained teaching, objectives, diagrams, presentation variant or practice questions/feedback advance that lesson's positive integer revision in both renderers. The publication impact check blocks changed retained lessons whose revision did not advance. Reordering otherwise unchanged lessons preserves their revisions and is still reported as a module-definition change.

Published packages and existing enrollments keep their original IDs, revisions, answers and cursor. New-version lesson order does not move an existing learner or transfer assessed credit. An unknown or removed identity fails rather than selecting the lesson now occupying its old numeric index. The unversioned browser cursor remains a separate legacy format until an explicit versioned enrollment is used.

## Preserved credentials

Versioned graduation saves a frozen pending issuance with earned progress, then inserts a unique credential and completes the enrollment. Replaying an interrupted insertion returns the original payload without duplicating XP or changing its name/date. Authenticated history downloads use the stored issuance independently of current progress and the catalog. Records are immutable through the repository; PDF bytes use the current renderer. Legacy preservation is an explicit migration primitive, never a read side effect, and labels unknown historical versions/dates honestly.

Course activation holds the source write boundary through preservation checks and selection. It rejects pending issuance and certified enrollments without preserved credentials. This internal guard does not replace the still-required reviewed credit preview, decision receipt and migration recovery workflow.

## Staged completion journal

Versioned completion journals a stable request identity, the exact course/asset/rubric digests, submitted reflection answers and prior credit. Grading results are stored before credit; a receipt saved atomically with progress can recover a lost response without regrading or awarding XP twice. HTTP and chat accept the same request identity. Browser completion retains it across uncertain responses and panel reloads; a definite failed assessment ends that submission.

This is not full lab-attempt isolation: external artifact/run revisions are still mutable, and jobs are not pinned from launch. Interrupted evaluation and lost boundary cleanup use explicit internal reconciliation; no automatic timeout clears a possibly live worker. Every staged progress mutation compares a database fence in the same write. Revocation therefore rejects a slow worker’s later progress save, cursor update or cleanup. Completion intent is bound before journal insertion so recovery also covers a delayed insert. An unresolved journal entry blocks changing courses. Keep rollout disabled until recovery, lab evidence and migration are complete.

## Completion recovery boundary

`CompletionRecovery.recover_worker` requires the reviewed learner/enrollment, exact active write ID, selection revision and a reason. It supports only fenced completion operations. It replaces the marker atomically, revokes the old progress token and reconciles the stored attempt: preserve awarded credit/results, retry the original saved grade, or record an interrupted evaluation requiring a new submission. It does not grade again or transfer XP. A failed recovery retains its marker and resumes with the same original write ID. If ordinary cleanup already released the boundary, `reconcile_attempt` handles the explicitly selected pending journal under a new write boundary.

The administrator Certifications screen wraps these primitives in a reviewed recovery workflow. Staff can inspect; only a full administrator can apply a snapshot-matched action with a recorded reason. Durable operator intent precedes effects, and the same request replays its original receipt after a lost response. Recent history can resume the original operator’s interrupted request. Preserved enrollment history is read-only. This is a completion recovery tool, not a course rollout or transfer action. A changed review snapshot, mismatched course/receipt, changed answers behind an uncommitted grade, or unknown progress ownership fails closed. Provisioning and external jobs need their own side-effect reconciliation. Pre-fence/legacy workers are not recoverable through this primitive and must be removed before rollout. Pending credential issuance completes through the original completion retry. Version-specific notifications, fleet-wide recovery reporting and authorized cohort rehearsal remain open.

## Staged V5 teaching, scenarios and practical evidence

The separate `../drafts/v5.0/` directory defines 33 required outcomes and unpublished teaching replacements; it is not enrollable. Seventeen recognition scenarios across AI Literacy, Validation & QA and Governance have authenticated, enrollment-pinned receipt coverage and a learner choice/retry interface. All 74 unpublished teaching replacements now have presentation evidence. Public definitions omit answer keys. These results award no XP or completion and block a course switch until their disposition is implemented.

Owned assigned lab inputs can be captured as immutable source/configuration snapshots. An internal saved-text adapter records its model/configuration/code identity and dispatches once from that snapshot, preserving completed, failed or uncertain receipts. Tests stub the provider. The adapter has no learner-facing dispatch or practical grading; uncertain calls do not retry automatically. The old completion runner still does not establish these new outcomes.

Internal optional-upgrade preparation separates original earned credit from target requirements and transfers zero outcomes until equivalence is verified. It inventories saved inputs, scenarios and execution states without exposing their contents. Changes during inspection invalidate the preview. Activation protects execution records on either enrollment even when an input reference is unavailable. Learner decisions, run disposition/recovery, reviewed equivalence and actual transition/rollback remain open. Saved automatic reviews are also included in upgrade preparation and protected on both enrollments. Internal grading pins evidence/rubric/model identity, saves results once and supports explicit linked retries for technical failures without learner failure or staff routing. Authenticated practical decision receipts now bind saved prompts, inputs and run results; they capture judgment without granting credit. The staged practical learner UI displays saved inputs/results and preserves exact submissions through response recovery; it does not grade or dispatch runs. Trusted saved-run evidence assembly and original-packet grading/retry are staged. Expired automatic grading can be reconciled on a subsequent internal request without staff or repeated model execution; real-model calibration and learner-facing delivery remain required. Execution requires the latest explicit learner approval when the package declares a scope gate; the frozen consent remains bound to its result. A packaged authored proposal can require explicit learner source correction; its original mismatch and authorized choice are preserved in the plan and decision receipt. An internal owned-record collector builds the grading evidence and reports missing coverage without granting credit. The deterministic Foundations execution check remains separate from model judgments. See implementation checkpoints 17–46 for bounded evidence.

## Source ownership and project access

New evidence captures require learner-owned artifacts and learner-owned assigned sources. A guessed ID, another person's shared artifact or transferred ownership cannot satisfy that requirement. Sources also pass the application's current document/project access check, including ancestor projects and current team or project membership. Ownership of a document alone does not override an inaccessible enclosing project. Source capture checks access again after storage reads, before saving evidence; live assigned-source delivery applies the same boundary.

Shared-project participation is permitted for individually owned work when the learner has current read access to its sources. A project viewer can capture an already assigned, owned source without editing it. Provisioning requires contribution access to the lab folder in both legacy and versioned courses; owner, editor and permitted team access follow the application's ordinary rules. Shared artifacts owned by someone else do not earn personal credit. Certification supplies the authenticated learner identity and does not substitute staff privileges for that learner's access.

An original authorized snapshot and its identical-request replay remain personal assessment history after workspace deletion, ownership transfer or membership revocation. They do not authorize a new capture or expose new live source text. Original assessment, credit and credential records remain bound to their saved evidence.

Legacy field-count assessments retain their original sharing and counting rules, but linked and creator-selected extractions must be currently readable through the ordinary extraction/library ACL. Inaccessible fields are excluded without discarding the learner's own inline fields. A per-invocation read adapter applies this boundary to both the unversioned and frozen legacy runners without changing their rubric bytes, field-merging rules, counts or star thresholds. Current authorized global, team and library sources remain permitted by that historical rubric; they do not establish personal V5 competency. A refused new legacy assessment does not revoke earlier earned credit. Checkpoints 224 and 227–229 record isolated persistence verification; live grading calibration and release rollout remain separate gates.

## Remaining rollout gates

- Complete enrollment lifecycle, outcome evidence, credential supersession and legacy cohort preservation. Versioned credential downloads now use issuance records; the rollout-disabled legacy download retains its prior behavior. Chat/API and administrator writes are enrollment-pinned; home/feedback preserve earlier earned status and background readers respect selection.
- Rehearse initialization with synthetic and authorized copied cohorts; reconcile duplicate, missing and unknown-provenance records. Replace unversioned writers before enabling initialization.
- Implement saved practice/drafts, durable assessed attempts, idempotency and interrupted-operation reconciliation. Issuance insertion and fenced completion recovery are restartable; other operation types still need reconciliation, and completion notifications are not yet durable per issuance.
- Replace the old fixed onboarding drip and once-per-user completion notice with reviewed version-specific notifications. The fixed drip defers versioned enrollments without advancing its cursor.
- Build outcome-based credit previews and an explicit optional-upgrade decision. Keep source enrollments and original credentials available.
- Extend browser and real HTTP/chat contract evidence to full labs, transitions and live-model journeys before activation. Current captures use synthetic API responses; integration tests use disposable MongoDB databases. Rehearse rollout and rollback: simply disabling the flag after initialization is not a verified rollback.

The authoritative acceptance status and evidence are in [the implementation log](../../../docs/certification-v5-implementation-progress.md).

## Administrator access changes

An administrator access change affects only the prerequisite-access flag. It cannot supply an outcome, completion, XP or a credential, and courses with the explicit any-order policy reject the override. Each new request requires a reason and a stable retry identity; the authenticated server-side administrator supplies its actor. The flag and its private course audit event are written in the same atomic update. An audit-write failure cannot leave an unrecorded override. Replaying a request preserves its original reason and actor and cannot reverse a later access change.

The read-only support summary shows the latest ten recorded changes and whether older events exist. The private journal is excluded from learner progress serialization; ordinary learner saves preserve it. A historical unlock flag without an event in the course record does not establish a reason or authorizing actor. Generic historical admin logs may contain additional context, but none is invented from the flag alone. This is an exceptional access-support operation, not a grading queue. Verification and acceptance remain tracked separately in the implementation log.

## Optional course comparison

The staged authenticated comparison API reads the current owned enrollment without initializing or switching it. `optional_upgrade_offers` is an optional registry mapping from a source release ID to distinct target release IDs. Every ID must be registered; only explicitly offered, published targets with an outcome contract appear to learners. Draft, retired and withdrawn offers remain unavailable. No offers are configured in this repository.

The learner can inspect remaining outcomes, original earned credit, saved-work counts and preservation warnings, then close the comparison and continue learning. Closing does not record a permanent decline. Source changes or withdrawn offers invalidate the comparison. Target requirements do not establish credit equivalence; activation remains unavailable. Unfinished answers, raw evidence and internal state fingerprints are not returned by the learner API. Checkpoint 47 records the bounded verification.

## Read-only cohort inventory

`scripts/inventory_certification_cohorts.py --database EXPLICIT_DATABASE` requires a separately configured `CERTIFICATION_INVENTORY_MONGO_URL`. Use authorized read-only credentials for the intended environment. It never inherits the application database, starts the application, creates indexes, initializes enrollments or changes records. Its stdout is an aggregate JSON report; do not put connection strings in command arguments or checked-in files.

The tool reads projected metadata from certification collections. Module answers, names, credential payloads, model evidence and decision text are excluded at the database projection. The report excludes user and record IDs. It counts unstarted records, active courses, completed courses and inconsistencies, with overlapping flags for historical completion, unknown provenance, prerequisite overrides, unfinished work, issuance and in-flight operations. Missing owners are counted separately. A person with no certification record is outside this inventory, so unstarted is not a count of all registered people who have never begun.

Two matching metadata reads are required; changes fail the report. This is not a transactionally consistent snapshot or a migration eligibility check. A bounded record limit fails instead of producing truncated counts. Catalog integrity, credential payload validation and external-job reconciliation remain separate gates. Checkpoint 48 uses synthetic, disposable databases only; an actual authorized cohort inventory remains required before rollout.

## Saved draft assessment delivery

Authenticated GET-only history and result endpoints expose owned assessments collected from trusted saved practical records. They verify the original enrollment, package/contract identity and stored receipt digests. History reads remain independent of the currently selected course and never initialize an enrollment, dispatch a model, reconcile a worker or retry grading. The recent list is bounded; an older receipt can be opened by its full reference.

The learner view separates deterministic execution checks from semantic judgments, shows scoped evidence quotations and revision instructions, and treats unavailable grading as a technical non-failure. Prepared/evaluating work has no final result. Provider configuration, exception details and full evidence packets are not returned. All displayed results remain drafts without XP, completion eligibility or staff routing. Live-model calibration and explicit assessment/retry actions are still release gates. The interface is staged with versioned course delivery and has not been published. Owned saved-result reads remain available when that delivery flag is disabled, matching the preserved-history boundary; they still require explicit enrollment ownership and verified original requirements.

The saved-text executor now resolves captured applied optimizer settings through the same helper as ordinary workspace extraction. Empty or absent overrides fall back to authored settings. Unsupported applied modes, images and unconfigured models are rejected instead of silently using the base settings. The resolver source is included in the execution implementation digest; a changed implementation requires a newly reviewed run. Later edits to the live extraction cannot rewrite a prepared snapshot or a terminal receipt.


Practical preparation is an explicit authenticated POST to
`/modules/{module_id}/practical-runs` with `enrollment_id` and a stable
`request_id`/`artifact_id` body. It captures assigned inputs and prepares a plan;
it does not execute or grade. Supported pinned Foundations packages require their outcome, scope-decision
and original-proposal assets. Extraction Engine additionally requires the exact
NIH repair case, exercise, source and decision bindings. Only these packages
advertise preparation; the repair assignment is available before preparing work. No current registry offer or legacy course is enabled by this code.
`GET /practical-preparations/{request_id}?enrollment_id=...` is an owned,
read-only recovery receipt even when course delivery is disabled. An
`inputs_saved` receipt resumes under the same request after a planning outage.
A saved run with missing original inputs fails closed instead of recapturing
current work. Definite unsaved capture rejections return 422; other failures
retain the reference for recovery. Public receipts omit runtime routing,
credentials and raw source text. No staff queue or model dispatch occurs here.

Explicit execution is a separate POST to
`/practical-runs/{run_id}/execution?enrollment_id=...`, requiring
`plan_sha256`, `scope_decision_id`, `scope_decision_sha256` and
`consent: "execute_saved_inputs"`. The linked approval and corrected source
must match the frozen plan; the dispatch claim rechecks the displayed approval.
The matching GET only reports owned state/readiness and remains readable with
delivery disabled or another enrollment selected. It never creates settings,
initializes enrollment or dispatches. Terminal/in-flight replay cannot execute
again, and technical failure is not a failed assessment. The learner action is
separate from saving a decision and from grading; no XP or completion is awarded.

Automatic assessment is an explicit POST to
`/practical-runs/{run_id}/automatic-reviews?enrollment_id=...`, with
`request_id` and `consent: "assess_saved_work"`. It collects trusted saved
records, freezes the system judge and evaluates the original packet once.
Client evidence, actor metadata and model selection are rejected. A separate
POST to `/automatic-reviews/{attempt_id}/retry` requires a new `request_id`
and `consent: "retry_saved_assessment"`; it preserves the original packet and
allows only one linked child per technical failure. Existing owned GETs remain
read-only and delivery-independent. These are draft automatic assessments,
without staff routing, earned credit or a live-calibration/release claim.

Owned practical run lists and decision context now require an explicit enrollment and remain readable after selection changes or disabled delivery. They return a read-only reason when writes are unavailable; they never initialize an enrollment or reconstruct missing saved inputs. This preserves the read boundary, not optional transfer activation.

Owned course-history discovery is bounded to 50 enrollments with direct older-reference access. Original practical prompts and recognition definitions are verified before display. Scenario receipt history preserves saved choices/feedback (including receipts not linked to progress), never regrades, and remains readable while delivery is disabled. Legacy unknown provenance remains explicit. These reads do not enable course transfer.


The Extraction Engine path uses the same explicit preparation, execution and automatic-assessment controls. Learners compare an authored flawed specimen with their real saved revision and output; both scope and source checks bind that exact specimen. The old course exercise remains unchanged. Technical retry preserves the original packet, and source absence stays distinct from unresolved checks. Checkpoint 68 verifies connected staged delivery with isolated test authentication and stubbed models; this does not authorize rollout, credit, live grading or migration.

Thinking in Workflows now uses explicit enrollment-owned `/modules/process_mapping/process-designs` saving/listing and `/process-designs/{submission_id}` retrieval. Automatic review is requested against that exact submission; `/process-automatic-reviews/{attempt_id}/retry` preserves the original packet. These controls do not invent a run, execute a workflow or award credit. The staged panel supports immutable linked revisions and original read-only history, including recovery of lost replies without resubmission/regrading. Checkpoint 73 verifies local connected delivery with fixed test authentication and a stubbed judge. Course rollout remains disabled.


### Unversioned continuation safety

The legacy fallback binds one learner progress snapshot to a request and compares its original fields plus a private revision before saving. Stale saves return a conflict; retry from refreshed state. First reads create one stable progress identity, and ambiguous historical records are not selected arbitrarily. No enrollment or course upgrade is implied.

Identified legacy completions save their original result atomically with credit and retain an insert-only receipt in `certification_legacy_completion_receipts`. Retry the same reference after uncertainty; corrected evidence uses a new request. Panel requests retain a learner/progress-scoped reference in tab storage, and live chat derives one from the original conversation turn and tool call. Older direct callers without references retain compatibility but not an immutable replay guarantee. Receipt storage is part of account deletion. Release rollout must replace or drain workers still running the old unguarded fallback.
