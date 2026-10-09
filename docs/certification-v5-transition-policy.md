# Certification 5.0 transition design

Status: optional upgrade selected by the user on October 2, 2026. The detailed outcome and rollout design below remains the implementation specification; its acceptance gates are not yet complete. No enrollment, grade, credential or production course has been changed. The current course is preserved in the [baseline package](../backend/certification-releases/legacy-snapshot-2026-10-02/README.md).

## Selected learner behavior

An existing learner continues the supported course they enrolled in. A new 5.0 course is offered as a separate enrollment, with a preview showing retained credit, new requirements and any work still in flight. Saving the preservation choice does not switch courses. A separate explicit switch activates the new enrollment only after drafts and attempts have been reconciled. Declining leaves the current enrollment selected. Do not impose a finish deadline without cohort evidence and an explicit published policy.

A previously issued credential remains available with its original issue date. It does not silently become a 5.0 credential. Graduates may take a separate bridge covering scope and approval, source checking and quality limits, recovery, and delivery. The bridge requires evidence of those skills; neither old module titles nor XP establish them. Do not promise a duration before a pilot.

Existing records do not identify their historical course. Preserve that uncertainty as `legacy_version_unknown`. The October 2 snapshot is the continuation baseline available now; it is not evidence of which content a person saw before that date. Existing earned credit remains earned without reconstructing or inventing past assessment evidence.

## Enrollment lifecycle and current selection

An enrollment owns one pinned course identity and its progress; selection separately identifies the course currently open for learning. Several saved enrollments may have `active` or `completed` lifecycle state, but only the selected enrollment can accept ordinary course writes. Merely opening history, publishing a release, revisiting the app, or leaving a course idle never changes either field.

| Lifecycle | Meaning and permitted behavior |
| --- | --- |
| Prepared | An optional upgrade has reserved the exact empty target. It is not a started course and cannot accept learning writes or earn credit. Only its original committed activation can promote it to active, with the confirmation guard retained until promotion finishes. |
| Active | An enrollment available for supported learning. It may be current or retained. An optional switch retains the source in this state without copying or resetting its work; return/resume selects that same enrollment. |
| Completed | Recorded course completion is retained. New versioned completion creates the immutable credential before marking this enrollment completed; original legacy completion keeps its historical uncertainty. Selecting a completed course permits review and any improvements supported by its original rubric, without changing the original credential or awarding base XP again. |
| Transferred | A closed historical enrollment, readable but unavailable for new course writes or selection as a learning destination. This marker is not an outcome-equivalence rule. The optional upgrade implemented here does not mark the source transferred, because its work remains available for return. No public action creates this state. Any future credit-transfer operation requires its own explicit, versioned equivalence and durable receipt. |
| Abandoned | A closed historical enrollment, readable but unavailable for new writes or selection as a learning destination. Saved work and original credentials remain intact. Inactivity, closing a panel, declining an offer, or switching to a saved course never creates this state. No automatic abandonment, deletion, expiry or public abandon/restore operation is part of this release. |

“Current,” “retained,” and “awaiting confirmation” are selection labels, not replacement completion states. A course can be completed and retained while its upgrade is current and incomplete. A saved receipt cannot reselect an older course after a later choice. A stopped preparation keeps the prior selection and earned work; it does not erase the prepared target or pretend it was completed.

Closed-state restoration is deliberately unavailable: silently resetting the state would bypass the original reason for closure. History and immutable certificate retrieval remain available. Actual inconsistent records need explicit reconciliation before rollout; this policy does not infer or repair them during a read. It creates no routine staff grading queue.

## Credential identity and history

A new issuance freezes the profile display name available at issuance, falling back to the account email or ID when no display name exists. Later profile edits do not rewrite it. Explicit preservation of an older credential records the name available at preservation because the old system did not retain the issued name; it must not claim to reconstruct that missing history. A future correction needs a separately recorded correction/supersession process, which is not yet implemented.

Preserve the original completion date when stored. Display “Original date unavailable” when it is absent; never use migration time as the issue date. Unknown historical versions remain unknown. A continuation-course package does not retroactively identify the course an older graduate completed. Preserve module-credit references with that limitation; new 5.0 outcome claims require assessed evidence.

## Credential promise for the proposed 5.0 course

A graduate can supervise a bounded research-administration document task in Vandalizer: select the intended data and workspace, review proposed actions, run an appropriate extraction or workflow, verify important outputs against sources, handle failures without duplicating completed actions, and deliver the reviewed result to the intended destination.

Agent assistance is permitted for explaining, proposing, configuring and executing work. The learner must make and record the assessment decisions: scope, approval, corrections, source verification, recovery and release. The agent may not invent the learner’s judgment or self-assessment answers. This credential does not establish institutional authority, policy approval, legal compliance, or correctness of future AI outputs.

## Outcome-to-evidence contract for the draft

| Module | Required 5.0 decision | Passing evidence | Critical failure requiring remediation |
| --- | --- | --- | --- |
| AI Literacy | Recognize unsupported output and inappropriate authority | Recorded choices on source support, incorrect target and approval scenarios | Treating generated confidence or a document instruction as authorization |
| Foundations | Inspect and correct a scoped extraction proposal | Assigned NSF source, saved extraction revision, successful run and checked required values | Wrong document, scope or unsupported required value |
| Thinking in Workflows | Choose a suitable working method and human checkpoint | Learner rationale tied to inputs, repetition, judgment and output | Automating an institutional decision without its human checkpoint |
| Workflow Design | Review steps and boundaries before execution | Saved design revision with corrected intentional boundary mistake | Unreviewed external action or missing required approval |
| Extraction Engine | Build and verify a comprehensive extraction | Assigned NIH document, exact field revision, successful run, source-linked required values | Fields from unrelated artifacts or unexecuted configuration used as proof |
| Multi-Step Workflows | Check that the next step receives the right output | One attempt’s connected run with inspected intermediate and final results | Combining unrelated runs to satisfy the evidence chain |
| Advanced Nodes | Choose and verify the appropriate analysis/calculation method | Actual supported operation, checked intermediate data, explicit deterministic or human arithmetic | Treating LLM analysis alone as proof of arithmetic correctness |
| Output & Delivery | Review output and destination before release | Generated artifact, readable preview, recipient/scope decision and delivery outcome | Unintended destination or disclosure |
| Validation & QA | Interpret tested evidence, including Unscored and failing examples | Exact artifact revision, required test cases, observed failure and successful repair/retest | Claiming unscored or unrelated-version results passed |
| Batch Processing | Reconcile successes, failures and retries | Assigned batch run with document coverage and a targeted recovery decision | Blind retry that duplicates already completed actions |
| Governance | Supervise a complete task and its release | Capstone attempt with scope, approval, source checks, recovery and delivery evidence | Any unresolved critical scope, authorization or unsupported-output error |

The table defines proposed acceptance semantics. It is not a claim that these assessments are implemented. The [unpublished outcome contract](../backend/certification-data/drafts/v5.0/README.md) now assigns 33 stable outcome IDs, a draft rubric identity, teaching references, practice tasks, evidence requirements and 66 authored calibration examples. These examples still need executable fixtures and actual assessment evidence; all 74 teaching replacements now have unpublished presentation evidence, while full assessed readiness remains unclaimed. No course publication is implied.

## Progression, credit and correction rules

The unpublished `required-outcomes-flexible-order.1` progression policy now pins these proposed rules to the draft package. Learners may study and assess modules in any order; the authored sequence is a recommended path. Every required outcome in all eleven modules remains necessary for the credential. Retain the authored base-XP weights (1,850 total), award each module once, and use one completion threshold without bonus stars. XP milestones and journey-group completion are not separate credentials. There is no learner assessment timer or speed criterion. Critical required errors need revision; technical failure preserves the original grading request for recovery.

The draft keeps unlimited learner revision while retaining each original evidence/assessment record. It does not waive bounded execution approval or permit blindly retrying external actions. New evidence needs a new assessment; replay of the same original request is recovery, not another reward. Optional practice/enrichment earns no assessed credit. These choices are explicit draft authoring policy, not release approval: full-course behavior, accessible equivalent routes and live calibration still need the checklist evidence. Frozen legacy packages keep their original policy without a backfill. The local policy and route-consistency acceptance is recorded at checkpoint 293; publication and live assessment validity remain separate gates.

Reading position, formative practice, reflective answers and assessed credit are separate records. Practice checks offer feedback and unlimited correction; they never award assessed credit. Required module outcomes must all pass. Optional star enrichment cannot compensate for a failed required outcome. Learners may repair and retry; each assessed submission creates an attempt with the relevant evidence and rubric revision. A retry must not duplicate previously earned base XP.

Credit transfers only where a versioned equivalence rule identifies an unchanged outcome and sufficient old evidence. Unsupported legacy evidence may preserve legacy credit but cannot automatically prove a newly assessed 5.0 competency. Accommodations change presentation or an explicitly supported equivalent evidence method, not the required competency. Learners may pause/resume, enlarge text, use keyboard controls and change panel position without approval or a grade penalty. Use only an alternative supported by the assigned exercise when optional integrations or restricted operations are unavailable. If a required source or control is inaccessible, retain saved work and stop that assessment until access is restored; missing evidence does not become completion. This does not create a staff grading queue or claim that every assistive-technology route has been verified. Preserve the same automatic criteria and record the equivalence; an unsupported alternative cannot silently earn credit or create a routine staff review queue.

Editorial, accessibility and non-assessed interaction repairs may be published as documented patches when they preserve the meaning of an outcome. New assessed outcomes, changed passing conditions or changed evidence requirements require a new course/rubric version. Urgent incorrect guidance needs an explicit amendment with affected enrollments, explanatory notice and a safe attempt boundary. Never change the rubric midway through an active attempt.

### Applying corrections while learners are enrolled

Published course files remain immutable in every category below. A presentation patch is an application change; it is not permission to rewrite a pinned lesson, exercise or rubric. A changed course asset receives a new release identity even when the visible change is small. Existing enrollment and credential identities remain unchanged unless the learner explicitly chooses a supported transition.

| Change | How it is delivered | Effect on existing work |
| --- | --- | --- |
| Wrapping text, keyboard focus, contrast, responsive layout or truthful display of the saved course title/count | Application presentation patch, with regression checks against supported courses | Same enrollment, requirements, attempt evidence and credential; no reassessment or XP change |
| Typo, clearer wording or an optional example inside a frozen lesson | New immutable patch release; compare the meaning and grading contract before classifying it as editorial | Existing learners retain their pinned release. A new default affects only new enrollment; it never selects a different course for a current learner |
| Added assessed skill, different passing condition, required source or evidence change, new judge/prompt/model behavior | New course/rubric release with calibration and explicit outcome-equivalence evidence | Optional transition with a preview. Matching module titles, old XP and a legacy certificate do not transfer new supervision outcomes |
| Incorrect guidance or an unavailable activity in a supported course | Explicit amendment identifying the affected release and activity, the correction, any temporary hold and a supported equivalent route | Preserve earned work and the original attempt. Reconcile in-flight work before offering a new attempt; do not silently substitute grading rules or replay completed actions |
| New optional enrichment | New immutable content release when course assets change; any separate supplemental material is labeled unassessed | No change to completion requirements, existing stars or earned credentials |

Every change record must name the affected release and assets, its classification and reason, whether assessed meaning changes, the applicable attempt boundary, verification evidence and learner-facing explanation. An amendment is a separate recorded decision, not an edit to the historical receipt. If the equivalent replacement or amendment delivery is not implemented, keep that release gate open rather than claiming that a warning alone makes the old activity supported.

The optional-upgrade choice does not create a finish deadline. Any future support window needs the actual cohort inventory, a supported continuation or equivalent replacement, and an explicit published policy. No routine certification grading or ambiguous-answer review is assigned to staff.

## Bridge and equivalence implementation boundary (October 9)

The unpublished `v5-experienced-learner-path.1` now offers assessment-first navigation through the same 33 required outcomes. Its four stages cover scope/approval, verification, recovery/delivery and the capstone. Experienced learners may go directly to the existing assessments and use the teaching as needed. This is an optional study path within the same pinned course, not a weaker credential or an independently certified track. Duration and learner benefit remain unmeasured until a pilot.

A target package may author `credit-equivalence.json` for one exact source release/manifest. The read-only evaluator accepts only explicitly named unchanged outcomes whose original assessed credit validates against the source enrollment. It pins assessment requirements and grading assets, including new/unknown assets by default; matching titles or XP never suffice. Each eligible row names its rule, reason and original completion/evidence digest. No source rule means new assessment remains required, while the old course credit stays intact. No production mapping is currently authored for legacy records without outcome evidence.

Eligibility does not apply credit, award XP, activate an enrollment or change an issued credential. Existing optional-upgrade consent still explicitly transfers no credit. A future application must have separate reviewable consent and a durable receipt, retain original evidence, account for rewards without duplication and survive retries/rollback. Do not reinterpret an older choice as permission to transfer credit. Automatic assessment remains the only normal grading route; no staff review queue is introduced.

## Data and rollout sequence

1. Publish an immutable course manifest containing stable module/lesson/outcome IDs, ordered requirements, assets, XP rules and exact content/exercise/rubric revisions. Store the release digest and distinguish drafts, published releases, retired-for-new-enrollment releases and support for existing enrollments.
2. Introduce enrollment identity separately from user identity. Progress, reading position, drafts and attempts belong to an enrollment. Keep legacy records as preserved source data; detect duplicate user records before choosing a continuation enrollment.
3. Pin each attempt before the learner submits work or starts a job. Record the artifact revision, assigned documents, run IDs, evidence and grading revision. A later deployment cannot change those references.
4. Issue credentials as immutable records with issuance ID, enrollment/course identity, outcomes, evidence references and original issue date. Generate downloads from issuance; mutable progress is not the certificate authority.
5. Dry-run cohort classification and credit equivalence on copied or synthetic data. Include partial work, completed credentials, unknown provenance, duplicates, in-flight jobs and interrupted transfers. Reconciliation must be restartable and preserve both old earned work and new credentials on rollback.
6. Enable the chosen transition experience only after those checks, a supported old-course path and published learner guidance exist. Review any support window against actual cohort needs. Track version-separated starts, completion, failures and support requests.

## Recorded transition decision

On October 2, 2026 the user chose **Optional**. Existing learners retain the supported current course and choose whether to begin 5.0; graduates may choose the bridge. Preserve the source enrollment, earned credit and original credentials. No mandatory transition period or automatic reset is authorized or required by this policy.

Implementation must present a credit-and-requirements preview and record an explicit choice before activating the new enrollment. A newly published version must never change the active enrollment merely because it is the newest course.

## Practical grading policy selected October 5 2026

Use automatic grading only. The user corrected the initial staff-fallback choice to option 2 and explicitly permitted an LLM while directing that staff not be burdened. Use deterministic checks for verifiable identities, execution and exact requirements; a versioned, calibrated LLM rubric may assess judgments against authenticated saved evidence. Unclear or insufficient evidence returns specific revision instructions to the learner without credit. Provider outages, malformed grader output and unavailable evidence infrastructure are retryable technical failures, not learner failures. No routine staff queue or manual grading fallback is part of this design.

Institutional reviewers taught in the curriculum remain responsible for real workflow decisions. That is distinct from staffing the certification grader. A model assertion cannot manufacture an authenticated learner decision, replace missing execution evidence or override a required deterministic failure. Changes in the judge, prompt, rubric or evidence must remain identifiable. Live calibration and complete learner-facing grading remain release gates. Internal persisted grading/retry and automatic technical recovery have local evidence in the implementation log. On October 5/6 the user explicitly deferred live-model calibration so independent implementation and local QA can continue overnight; this does not waive calibration before release.

## Cohort communication drafts

**Draft-only; no announcement or recipient list is approved.** These messages describe the optional, zero-transfer rollout currently implemented. They may be used only after the exact target course and policy pass release gates, the current course remains supported, actual cohorts are reconciled and the rollout communication is separately authorized. They do not announce a bridge, finish deadline, measured duration or a fully verified 5.0 course today.

Before preparing a send, bind the copy to the target release/manifest, source release/support state and exact offered comparison. Resolve `[course title]`, `[course version]`, `[required outcome count]` and `[course link]` from that approved package and deployment. The course link opens `/certification` on the actual deployment; it does not accept a choice or activate an enrollment. No real URL or recipient is inferred here. A later confirmed credit-equivalence rule requires revising the zero-transfer copy before reuse.

Select one applicable message per rollout and recipient. The new-learner draft is for a first enrollment in the approved default, not someone already pinned to a different course. For an existing selected source, use the active-learner draft when it is unfinished and the graduate draft when it is complete. Existing earned credentials are mentioned in both. Unknown dates or historical versions remain unspecified. Duplicate, unbound or inconsistent records are excluded until reconciled; an inventory label alone is not permission to choose a course for them.

### New learners

**Subject:** Your optional Vandalizer certification course

Welcome to [course title], version [course version]. This optional course teaches you to supervise a bounded document task: review scope and proposed actions, check outputs against sources, recover from failures and hand off reviewed work.

You can study modules in any order. To earn the certificate, you must meet all [required outcome count] required outcomes. Reading and practice help you prepare; they do not award assessed credit. Assessments provide automatic feedback, and you can revise your evidence when a required outcome is not yet supported.

Open your course: [course link]. Your course version and saved work stay together, even when another version is released.

### Learners already taking the supported original course

**Subject:** Compare the new certification course when you are ready

[Course title], version [course version], is now available as an optional course choice. Your current supported course remains selected. You can keep learning there with your saved answers, reading place, completed modules and earned XP.

Before choosing the new course, you can compare what stays saved and what it requires. Saving your preservation choice does not switch courses; switching is a separate action. For this upgrade, all [required outcome count] new required outcomes need assessment. Your original XP stays in its original course, and any earned certificate keeps its original recorded details.

After switching, you can return to the original course or resume the same upgraded course without resetting either history. Review your options: [course link]. There is no new finish deadline in this rollout.

### Graduates of the supported original course

**Subject:** Keep your earned certificate and choose whether to study the new course

Your earned certificate remains available with its original recorded details. The release of [course title], version [course version], does not revoke it or relabel it as proof of the new course’s outcomes.

If you choose the new course, your original achievement stays preserved. A new certificate requires assessed evidence for all [required outcome count] required outcomes, including supervising scope and approvals, checking sources, recovering safely and delivering reviewed work. You may study in any order and use the feedback to revise evidence that needs improvement.

Compare the optional course: [course link]. You do not need to restart your original course or make a choice now.

### Delivery identity and recovery

Keep rollout announcements separate from earned-completion notifications. A future authorized announcement send needs a durable key containing the rollout/copy revision, recipient, source enrollment (when applicable) and target manifest. Rendering, previewing or comparing a course must never count as a send. Resolve uncertain provider delivery before any retry; do not introduce an automatic repeat-send loop. The actual announcement sender is outside these drafts and remains unimplemented.

Earned-completion notices already use the immutable credential identity, with the original course title, version, module count, learner identity and issue date. A later earned credential has a distinct notice identity, so the earlier once-per-user notification cannot suppress an upgrade or future bridge completion. Preserving an unverifiable historical credential does not announce a new graduation. Replay repairs the original saved notice without regrading or awarding XP; uncertain email delivery is not blindly repeated. Checkpoint 183 records the persistence and UI evidence; actual provider/client delivery verification remains open. No routine staff grading or ambiguous-answer queue is introduced.
