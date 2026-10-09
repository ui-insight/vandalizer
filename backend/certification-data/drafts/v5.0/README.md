# Vandalizer 5.0 competency design

**State: unpublished design draft.** The current course, grading and enrollments are unchanged. This directory is outside the course registry; it cannot enroll a learner.

`outcomes.json` is the authoritative design data for 33 required outcomes and 66 passing/failing calibration examples. All 33 outcomes now reference authored teaching in the 74 unpublished lesson replacements. All 33 outcomes have implemented draft assessment mechanisms: five recognition outcomes plus the practical outcomes across all ten practical modules, including Collaboration and Governance. **None is marked release-verified.** The 66 calibration examples remain authored expectations; synthetic fixtures and stubbed judges are not live grading-validity evidence.

`authored` means the referenced teaching draft exists. `implemented` means the staged authenticated assessment and feedback mechanism exists; it does not mean calibrated grading, earned-credit integration, release approval or an 8/10 score. `verified` remains reserved for completed outcome release evidence. The contract remains `design_draft`, all 33 outcome release gates remain open, and publication still requires an authored, verified release candidate. This reconciles earlier conservative placeholders without changing any assessed requirement.

Run `backend/.venv/bin/python scripts/check_certification_outcomes.py` from the repository root to check module coverage, teaching references and structural integrity. The outcome schema rejects missing evidence, duplicate identities, missing failure calibration and unsupported readiness claims. A course package may include this contract only under its exact rubric identity; publication requires an authored, verified release candidate.

## Required outcomes

| Module | Required outcome IDs | Grading design |
| --- | --- | --- |
| ai_literacy | `ai_literacy.source_support`; `ai_literacy.scope_and_authority`; `ai_literacy.human_decision` | scenario choice |
| foundations | `foundations.scoped_proposal`; `foundations.executed_extraction`; `foundations.verified_values` | deterministic, structured review |
| process_mapping | `process_mapping.method_choice`; `process_mapping.human_checkpoint`; `process_mapping.bounded_scope` | structured review |
| workflow_design | `workflow_design.data_flow`; `workflow_design.approval_boundary`; `workflow_design.reviewable_design` | structured review |
| extraction_engine | `extraction_engine.field_semantics`; `extraction_engine.assigned_run`; `extraction_engine.quality_repair` | deterministic, structured review |
| multi_step | `multi_step.connected_execution`; `multi_step.intermediate_review`; `multi_step.bounded_reasoning` | deterministic, structured review |
| advanced_nodes | `advanced_nodes.appropriate_method`; `advanced_nodes.checked_computation`; `advanced_nodes.parallel_safety` | structured review |
| output_delivery | `output_delivery.usable_artifact`; `output_delivery.release_decision`; `output_delivery.delivery_outcome` | structured review |
| validation_qa | `validation_qa.quality_meaning`; `validation_qa.representative_tests`; `validation_qa.repair_and_retest` | scenario choice, structured review |
| batch_processing | `batch_processing.assigned_coverage`; `batch_processing.targeted_recovery`; `batch_processing.resource_choice` | deterministic, structured review |
| governance | `governance.accountable_handoff`; `governance.capstone_supervision`; `governance.review_and_revision` | scenario choice, structured review |

## Implementation boundaries

Scenario choices require versioned cases and learner submissions. Deterministic checks require server-recorded inputs, revisions and execution evidence. Structured review requires a versioned decision rubric, reviewer mechanism and calibration before it can award credit. Neither prose presence, keyword matching nor an agent assertion proves a learner decision. Authenticated recognition submission/history and Foundations preparation, explicit approved execution, saved value checks, automatic-review requests/retry and saved feedback now have staged implementations. Checkpoints 61–62 connect the production browser to real certification HTTP handlers and disposable persistence using synthetic authentication/providers. All-module practical delivery, calibrated grading and earned-credit integration remain open.

The internal `TransitionPreview.inspect` uses a packaged outcome contract to show current earned credit separately from target requirements. It makes no writes and has no activation endpoint. It conservatively transfers zero outcomes until an equivalence rule and assessed evidence are verified. Matching names, XP and legacy credentials do not establish new supervision skills. Draft targets can be inspected for preparation but cannot be selected. External-job reconciliation, full draft handling, actual equivalence and activation/rollback remain open.

## AI Literacy implementation draft

`ai-literacy-teaching.json` contains all nine lesson replacements at revision 2 and revised module metadata for a future course; `ai-literacy-scenarios.json` contains nine recognition scenarios. The deterministic scenario kernel has regression coverage for every wrong choice and exact bank identity. These files are outside the course registry. Authenticated, enrollment-pinned scenario receipts and a learner answer/retry interface are implemented behind the disabled course rollout. Public definitions exclude answer keys, replay preserves the original choices, and scenario results award no XP or completion. The recognition mechanism is marked `implemented`; earned-credit integration and outcome release verification remain open. See checkpoints 20–24, 46, 60 and 62 in the implementation progress log for evidence and limits.


The internal saved-text execution adapter consumes immutable input snapshots and preserves a pinned dispatch plan and terminal result. Its provider is stubbed in persistence tests. Its explicit learner dispatch endpoint and recovery controls are implemented in checkpoints 54–55 and connected in checkpoint 61. Uncertain execution is never automatically retried. Live-provider execution, calibrated grading and complete recovery/credit acceptance remain release gates.

## Foundations and Process Mapping teaching drafts

`foundations-teaching.json` replaces six lessons and aligns the five-field practice with scope review, template inspection, actual execution and source checking. `process-mapping-teaching.json` replaces seven lessons with method choice, bounded scope, review evidence, exception handling and explicit stopping conditions. Both retain original lesson identities at revision 2, include formative questions and remain outside the catalog. They do not change the legacy lab rubric or implement structured assessment. Foundations presentation is verified in checkpoint 25 and Process Mapping in checkpoint 26.

`workflow-design-teaching.json` contains eight unpublished replacements covering actual input-source wiring, creation-preview limits, configured approval pauses, reviewer settings and output evidence. Presentation and formative feedback are verified in checkpoint 28. All draft authoring remains distinct from packaged teaching readiness and verified assessment; the outcome contract is not advanced to a release candidate.

## Automatic-only assessment policy

The user selected automatic-only grading on October 5, explicitly allowing LLM assistance and excluding a routine staff burden. `assessment-policy.json` records that choice. Unclear evidence returns to the learner with revision instructions. Provider/schema failures remain technical failures eligible for a grading retry, not failed learner performance. Institutional review decisions inside the curriculum remain distinct from certification grading.

The internal `automatic_review.py` adapter requires all structured-review outcomes, exact evidence citations and every required evidence kind before accepting a supported result. It has no action tools, staff routing or credit award. The staged learner HTTP request/retry boundary is implemented in checkpoint 56; no chat tool supplies learner decisions. The internal review repository now saves pinned inputs/results and explicit technical retries; checkpoint 30 verifies persistence and upgrade protection. The staged Foundations collector now derives evidence from owned, integrity-checked saved runs and decisions, with missing proposal evidence reported explicitly (checkpoint 34). The saved-run review entry point now freezes the internally collected packet and its provenance for replay and technical retry (checkpoint 36). Automatic reconciliation of expired grading on a subsequent internal request is verified in checkpoint 37. It preserves saved results or records retryable technical unavailability without staff routing or automatic regrading. The Foundations deterministic execution outcome now has a pinned checker saved separately from the two model-reviewed outcomes (checkpoint 39). Learner-facing Foundations delivery is implemented in checkpoints 52–57 and connected in checkpoint 61. Live-model calibration and earned-credit integration remain required. `foundations-review-calibration.json` contains six synthetic positive/negative/unclear/adversarial cases. The calibration harness measures false support and technical unavailability separately. Its tests use synthetic responses; no real model has been calibrated, and a matching small suite never by itself declares release readiness. See checkpoint 29.


## Saved practical decisions

`foundations-decisions.json` defines two unpublished prompts: review the saved scope before execution, then check all five required values against the saved source after completion. The staged HTTP endpoints derive the actor from authentication and record the server timestamp, exact prompt/answers, input and run identities. They reject fabricated source quotations and preserve unresolved answers without asserting failure or success. Persistence, replay and upgrade guards are verified in checkpoint 31. No chat tool supplies learner decisions. The learner review UI and response recovery are verified in checkpoint 32 using synthetic browser fixtures and separately verified HTTP persistence. The latest saved explicit scope approval now authorizes only its exact run; later revise/decline decisions block dispatch, and the execution receipt preserves the consent (checkpoint 33). `foundations-proposal.json` now defines an authored NIH/NSF source mismatch; saved run plans preserve it and the learner explicitly selects a source before approval. Wrong-source approval blocks execution. Capture, binding and responsive controls are verified in checkpoint 35. Trusted grading handoff is verified in checkpoint 36; calibrated grading and earned-credit integration remain open. Saving an approval does not start a run or prove an outcome.


`extraction-engine-teaching.json` replaces six lessons on strategy choice, missing values, exact assigned execution, consensus, evidence-based repair and guided verification. It removes unsupported guarantees about accuracy, optionality, fixed repetition cost and automatic field grouping. All six replacements have responsive visual and formative-feedback evidence in checkpoint 38; actual assessed NIH runs and grading remain required. There are now 36 unpublished replacements across five modules, with 38 lessons still to revise.


`multi-step-teaching.json` replaces six lessons on configured input context, bounded interpretation, linked execution, intermediate review and preservation of meaning through formatting. Checkpoint 40 verifies its responsive presentation and formative feedback. The draft set now covers 42 lessons across six modules; 32 lessons remain. Actual subaward execution and outcome assessment are still required.


`advanced-nodes-teaching.json` replaces six lessons on appropriate methods, checked calculation and safe parallel dependencies. It removes the claim that Deep Analysis substitutes for deterministic arithmetic. Checkpoint 41 verifies responsive presentation and formative feedback; real calculation and parallel-work assessment remain open. The draft set now covers 48 lessons across seven modules, with 26 lessons remaining.


`output-delivery-teaching.json` replaces five lessons on supported formats, actual file inspection, explicit release scope and confirmed delivery. Checkpoint 42 verifies responsive presentation and formative feedback, including the worked example's explicit source routing. The draft set now covers 53 lessons across eight modules, with 21 lessons remaining. Real artifacts and delivery assessment remain open.


`validation-qa-teaching.json` replaces eight lessons on representative cases, checked expectations, quality-signal limits, finalized guided verification and linked repair/retest evidence. Checkpoint 43 verifies responsive presentation and formative feedback after fixing invalid style variants; the shared contract now checks supported variants. The draft set covers 61 lessons across nine modules, with 13 lessons remaining. Real validation and assessment remain open.


`batch-processing-teaching.json` replaces six lessons on exact assigned-input coverage, per-item correctness, pilot resource choices and targeted recovery. Checkpoint 44 verifies responsive presentation and formative feedback. The draft set covers 67 lessons across ten modules; Governance's seven lessons remain. Real batch and recovery assessment remain open.


`governance-teaching.json` replaces seven lessons on accountable internal handoff, scoped permissions, portable dependencies, learner supervision and preserved earned history. Checkpoint 45 verifies responsive presentation and formative feedback. **All 74 lessons across eleven modules now have unpublished replacements with browser evidence.** This completes the teaching rewrite pass, not practical assessment or release acceptance. Connected labs, calibrated grading, optional transition delivery and learner/accessibility observation remain required.


`validation-qa-scenarios.json` and `governance-scenarios.json` add four recognition cases each. With AI Literacy, all five declared scenario-choice outcomes now have draft banks (17 questions total). Checkpoint 46 verifies deterministic negative cases, authenticated receipts and responsive submission/recovery. Passing these banks does not establish the modules' separate practical outcomes, award credit or make the course enrollable.


## Extraction Engine repair assessment draft

`extraction-engine-repair.json` and `extraction-engine-decisions.json` define an authored flawed baseline and explicit before/after decisions for all three Extraction Engine outcomes. The baseline is not an actual run. Learners must repair the fields, approve and execute a real saved revision, then verify its values against sources. The new `documents/nih-r01-neuroscience.pdf` preserves the original synthetic content while fixing misaligned tables and embedding fonts. `scripts/build_certification_nih_draft.py` rebuilds only this separate unpublished file. It never replaces the legacy source or updates the registry.

Checkpoint 64 verifies source/content/schema integrity and both rendered pages. Private expected answers are omitted from the public case definition. This is authored assessment material, not an implemented grading mechanism: run binding was subsequently verified in checkpoint 65; learner delivery and assessment remain open. No new course is enrollable. The later delivery checkpoint below supersedes the initial `not_implemented` status.

Checkpoint 65 freezes the authored public example inside internal saved runs and requires its exact reference in authenticated scope/value decisions. Private expected answers stay out of learner run context; the baseline never claims to be an execution. Real disposable persistence tests cover stale/missing references, declines, missing approval, absence, invalid quotes, replay and workspace deletion. Preparation eligibility remains Foundations-only until the repair view and trusted assessment are ready.

Checkpoint 66 adds the internal NIH evidence collector and automatic-review handoff. Its draft evidence requirements now explicitly include the authored baseline, assigned source and revised output. Deterministic execution completeness stays separate from field/value quality; a favorable judge cannot override an incomplete run. Original evidence survives technical retry. These mechanisms are verified with stubbed providers and disposable persistence; the authenticated learner path and live calibration remain open, so the three Extraction Engine readiness statuses are unchanged.


Checkpoints 67–68 add learner comparison/source checks and the complete staged preparation → approval → execution → automatic assessment path. `extraction-engine-exercise.json` replaces legacy field-count instructions only in a future repair package; it binds the four required fields and authored case without exposing expected answers. Chat uses the same pinned exercise. The public assignment is visible before preparation; original history uses the example captured with its run. Real HTTP/persistence and connected browser verification use fixed test authentication and stubbed models. All three Extraction Engine mechanisms are now `implemented`, not `verified`; live calibration and earned-credit integration remain open. The registry and existing learners are unchanged.


## Thinking in Workflows design assessment draft

`process-mapping-case.json` supplies a fictional monthly report-review brief, three contrasting working-method situations and an intentionally flawed proposal. Its three questions require a method/rationale, corrected ordered map and bounded delegation brief. The case asks for no personal documents, real execution or staff grading. `process-mapping-exercise.json` binds the exact case and removes legacy reflection-presence/count credit for a future package. Private review guidance preserves the declared outcome rubric and permits justified alternative methods; the public definition omits it. Checkpoint 69 verifies authoring contracts only. Authenticated saving, original-map handoff, automatic assessment and learner delivery remain open; its three outcomes remain `not_implemented`.

Checkpoint 70 adds internal immutable authenticated process submissions and linked revisions. Saved originals are included in transition guards and metadata-only inventory. Saving a map is not a pass and dispatches no model. The case and its three outcomes remain unavailable to learners until collection, assessment and UI delivery are complete.

Checkpoint 71 adds trusted process-design evidence collection and internal automatic review/retry. Authored scenario/private guidance, the saved map and authenticated decisions remain distinct. Review replay and technical retry preserve the original packet; oversized evidence is rejected without truncation. Models are stubbed in verification and learner HTTP/UI delivery remains open.

Checkpoint 72 exposes explicit enrollment-owned process saving/history and automatic assessment/technical retry through staged HTTP controls. Shared feedback distinguishes a saved design from an execution. Original maps remain readable with delivery disabled or another course selected. Verification uses stubbed models; learner UI and full connected browser delivery remain open, so readiness statuses do not advance.

Checkpoint 73 connects the fictional assignment, three-answer draft, immutable saving, lost-reply recovery, linked revisions and explicit automatic assessment to the learner panel. Original course history is read-only and retains the exact saved map. Thirty-six normal/doubled-text browser states pass using real HTTP/MongoDB with fixed test authentication and a stubbed judge. All three process-mapping mechanisms are now `implemented`; none is `verified`. Original-map handoff to Workflow Design, live grading calibration and earned credit remain open. Earlier checkpoint limits above describe their historical state.

## Workflow Design assignment draft

`workflow-design-case.json` and `workflow-design-exercise.json` define the next saved-artifact assessment. The case pins the Thinking in Workflows input/scope and offers an explicit choice of an owned original submission or an authored supplied map. Selection never implies transferred credit. Learners must inspect a saved workflow revision, correct a flawed input/destination proposal, trace data through actual configuration and explain a review/stop path. A focused prompt may replace unnecessary extraction; step counts and filled reflections cannot substitute for the artifact. The automated portion ends at an internal draft, so this exercise requires no run, external action, real reviewer or staff queue. Private guidance preserves the exact three outcome rubrics and evidence kinds. Checkpoint 74 verifies authoring contracts only; artifact capture, handoff and learner assessment delivery remain open, and all three outcomes stay `not_implemented`.

Checkpoint 75 adds internal owned workflow/step/task configuration capture with an explicit saved-map or supplied-example choice. The original map is embedded with its verified identity; replay does not recollect newer workflow or map content. Snapshots survive workspace deletion and enter existing transition protection. Capture records neither a grade nor a run, and extraction dispatch explicitly rejects design snapshots. This is configuration capture only: referenced documents, extraction sets and integrations are not resolved as assessment evidence. Trusted collection, automatic review and learner delivery remain open; Workflow Design readiness does not advance.

Checkpoint 76 extends configuration capture to owned extraction templates referenced by workflow tasks. The exact fields, optional/category settings, field order, rules and base/override configuration are frozen with the workflow. Replay survives template deletion; field edits change the captured identity, and racing edits are rejected. Missing, foreign, duplicate or ambiguous definitions fail before saving. Source documents and other resources remain unresolved references, not assessed source or execution evidence. Workflow Design learner decisions, grading and UI remain open.

Checkpoint 77 saves authenticated Workflow Design approval and all three decisions against the exact captured revision and case. Each receipt embeds the original configuration/map; revised answers create a linked receipt. Approval grants neither execution authority nor competence. Replay survives deletion of original capture/workspace records. Independent approval records have their own upgrade guard, metadata-only preview/inventory and account-deletion registration. This is internal persistence; learner delivery and grading remain open.

Checkpoint 78 connects trusted automatic review to the approved revision. Authored proposal/private guidance, captured artifact configuration, original map and authenticated decisions remain distinct evidence. Unsupported resource dependencies are rejected before preparing a review, without a learner failure or truncation. Review replay and explicit technical retry retain the original packet after approval deletion. Verification uses a stubbed judge, not live grading calibration. No execution receipt is invented and no credit or staff queue is created.

Checkpoint 79 exposes explicit owned workflow selection/capture, immutable approval, automatic assessment and technical retry through authenticated HTTP controls. Read-only original approvals and feedback survive deletion of live workflow/input/map records and disabled delivery. The shared saved-feedback format distinguishes a workflow approval from a practical run. Tests use fixed synthetic authentication and a stubbed judge; learner UI and connected browser verification remain open.


Checkpoint 80 connects workflow and map selection, immutable capture, configuration inspection, explicit approval, automatic assessment, lost-reply recovery, linked revisions and original read-only course history. Both supplied-map and owned-original-map paths were exercised through real HTTP/MongoDB with synthetic authentication and a stubbed judge. Forty-four normal/doubled-text browser states pass at 320, 390 and 1440 pixels. Workflow Design's three mechanisms are now `implemented`, not `verified`; the draft has 17 implemented and 16 remaining mechanisms, with all 33 awaiting release verification. Chat/editor continuity, live calibration and earned-credit integration remain open. No course was published, no existing learner moved and no staff queue was introduced.

## Multi-Step Workflows source draft

Checkpoint 81 repairs the original subaward's misaligned budget table and stranded heading in `documents/subaward-agreement.pdf`. The builder `scripts/build_certification_subaward_draft.py` reuses every original substantive string, embeds the fonts used and produces a deterministic two-page unpublished source. Both pages were rendered and inspected; source-text identity, bounds and original/legacy bytes were verified. This does not implement the Multi-Step Workflows assessment or enable delivery; its three outcomes remain `not_implemented`.

Checkpoint 82 adds `multi-step-case.json` and `multi-step-exercise.json`. The authored Formatter-routing and unsupported-reasoning faults are not execution evidence. The contract requires original/corrected owned runs, explicit approval, same-run stage connections, actual intermediate/final checks and assigned-source support. Recovery preserves completed outputs and cannot automatically replay completed writes. Private anchors/guidance stay out of the public definition. All 31 new case tests pass; runtime capture, execution, grading and UI remain open, so readiness does not advance.

Checkpoint 83 adds internal immutable connected-workflow input capture: owned configuration and referenced extraction definitions plus the exact assigned subaward and ingested text. Capture does not authorize a run. Catalog checks bind the source/case/exercise; extraction preparation and execution refuse these workflow snapshots. Original records survive workspace deletion and remain guarded during optional upgrades. Twenty-nine new persistence cases pass; connected execution and assessment remain open.

Checkpoint 84 aligns case revision 2 with actual Step Input / Workflow Documents behavior. The incorrect Formatter re-reads the assigned source; the repair selects the incoming reasoning result and checks task overrides. Four tests execute the real workflow engine with stubbed providers to verify both contexts and input precedence. Earlier case/exercise definitions are archived in QA evidence. This is runtime contract verification, not the connected certification executor or an assessed learner run.


## Connected execution and budget assessment delivery

Checkpoints 85–96 complete the staged Multi-Step Workflows path: owned original/corrected executions, actual stage inputs and results, scope approval, source-bound comparison, automatic feedback and immutable history. Seventy browser states include recovery and final readable evidence. Its three mechanisms are implemented; failed-run assessment, live calibration, credit and release verification remain open.

Checkpoints 98–108 complete the staged Advanced Nodes path: a readable unpublished budget source, authored method/arithmetic/dependency case, source-bound calculation records, owned workflow capture, explicit scope approval, actual per-task receipts, saved-result finalization and automatic feedback. Exact arithmetic checks can veto a model pass but cannot upgrade uncertainty. The learner interface preserves linked corrections, pending requests and original read-only history. Ninety-five browser states cover normal and doubled text at 320/390/1440px, including nine final focus-handoff checks. Providers and judges are stubbed; no earned credit, live calibration or release readiness is claimed. The three Advanced Nodes mechanisms are now implemented, bringing the total to 23/33; all 33 still require release verification.

## Output and Delivery source draft

Checkpoint 109 repairs the progress report's viewer-dependent blank text and misaligned budget table in a separate `documents/progress-report-year2.pdf`. Embedded fonts, fixed columns and two inspected pages preserve every substantive source string and amount. The original and legacy sources remain unchanged. This source repair does not implement artifact assessment or authorize any delivery.


Checkpoints 110–112 add the authored two-file inspection/private-handoff case, exact generated-file/ZIP preservation and authenticated owned workflow/source capture. Required fields distinguish Year 2 and cumulative spending; the contained learner-only destination will deliberately reject its first approved write for recovery practice. This is explicit training behavior, not evidence of a real external outage. Workflow report text styles now embed fonts after visual QA exposed a substitution failure in real generated output. Bounded generation, learner inspection/approval, actual private handoff and automatic assessment are still open, so Output and Delivery remains unimplemented.


Checkpoints 113–114 add exact four-stage generation planning, separate saved scope approval, durable actual stage/file receipts, and explicit finalization from complete saved results without provider reexecution. Original PDF/CSV bytes and the actual download bundle remain inspectable; invalid CSV stays repair evidence. Ninety-seven persistence/artifact/planning checks pass with stub providers. File inspection/release choice, contained handoff/retry, automatic assessment and learner UI are still open, so the module's three mechanisms remain unimplemented.


Checkpoints 113–119 complete Output and Delivery’s saved plan, explicit scope approval, durable actual file generation, exact-file inspection, private first-failure/retry, automatic evidence review, authenticated downloads and learner history. The final responsive run covers 96 states at normal/doubled text; 102 earlier states are retained. Each of three journeys verifies nine downloaded files against their original hashes with no duplicate dispatch after lost replies. Workflow editing and all model judgments are synthetic fixtures, so live calibration and earned credit remain open. The three mechanisms are implemented, bringing the total to 26/33; all 33 remain unverified for release.

Checkpoint 120 adds a separate readable NSF proposal draft for Validation. Its embedded fonts and fixed five-column budget table preserve every original substantive word/value. This does not modify the legacy source or existing enrollments. Representative suite execution and assessment remain subsequent work.


Checkpoints 121–122 bind `validation-qa-case.json` and its exercise to two complete readable assigned proposals, all six field/source expectations and preserved same-artifact repair/retest requirements. Private answers are excluded from public discovery. Owned capture retains both PDFs and exact field instructions, rejects source/configuration races and survives workspace deletion. The 77 contract and 26 persistence tests pass; execution and learner delivery remain open, so Validation readiness does not advance.

### Validation learner delivery through checkpoint 129

Checkpoints 123–129 preserve the learner's six expectations before running, execute both complete sources with durable per-case receipts, require a real original mismatch and changed revision of the same extraction for retest, and bind automatic feedback to the unchanged suite and both actual results. Source checks veto incorrect expectations or retest values. Saved interpretations, original PDFs and linked revisions survive workspace deletion. The UI retains recognition separately, recovers ambiguous requests without duplicate dispatch and exposes read-only history. The final 78-state browser journey, 83 frontend checks, 37 delivery/review regressions and 77 readiness contracts pass. Providers and judges remain stubbed; extraction editing is a synthetic fixture. The two mechanisms are implemented, bringing the total to 28/33; five Batch/Governance mechanisms remain unimplemented and all 33 require release verification.

### Batch sources and case through checkpoint 133

The three unpublished Batch proposal PDFs now render with embedded fonts while preserving every original substantive string and proposal number. The authored case requires a source-checked two-document pilot, a separate scale decision, exact assigned-ID inventory, a disclosed contained first-attempt rejection and recovery of only confirmed failed work. Private answers and legacy document-count stars are excluded from learner delivery. Capture preserves the five-field owned extraction and all three complete sources; deterministic checks distinguish terminal coverage, usable values and targeted recovery. Case/catalog, capture and source-check suites pass. Execution claims, concurrency-safe targeted retries, automatic interpretation review and learner UI remain open, so all three Batch outcomes remain unimplemented.


### Current implementation through checkpoints 149–167

Batch delivery now includes the saved pilot, explicit scale decision, bounded execution, targeted failed-work recovery, deterministic coverage checks and automatic interpretation review. Governance includes the saved scope and approval, actual bounded execution, source findings, explicit revision/recovery, accountable handoff and automatic capstone feedback. Together with the five recognition outcomes, all 33 draft mechanisms are implemented. Synthetic provider/judge and responsive UI evidence are recorded in the implementation progress log; none establishes release calibration or earned-credit integration.

Checkpoint 167 adds an authenticated read-only combined module preview. The learner's exact selected automatic-review and scenario receipt IDs determine the result; no latest/best historical attempt is chosen implicitly. All required outcomes must be supported, and saved execution/source vetoes remain effective. Missing selections, pending reviews, technical failures and needed revisions remain explicit. Receipt and requirement digests bind the preview to original saved evidence. The preview creates no completion authorization, XP, credential or staff task. Final credit, learner-facing receipt selection, live-model calibration and publication remain open.


### Foundations exercise alignment through checkpoint 168

`foundations-exercise.json` replaces the legacy field-count/extra-star directions only for a future scoped-assessment package. Its case digest and five required fields match the saved proposal and value-review prompts. It includes the explicit approval/execution/source-check sequence, repair and automatic feedback without exposing expected answers. The complete assignment is available in the practical-review panel and chat; original courses keep their original instructions. Catalog, saved-scope persistence and 54 responsive/zoom/text captures pass. No package registration, enrollment, earned credit or live-model validity is implied.


Checkpoint 169 adds `scripts/assemble_certification_v5_preview.py` for deterministic isolated full-course inspection. Its output includes all eleven authored module/assignment definitions, 74 revised lessons and all 33 draft mechanisms, with private answers excluded from the public payload. Output inside the application catalog is rejected. Its catalog has no supported/default course and its rubric intentionally cannot award credit. Preview prerequisites and XP/star policy are unfinished inspection settings. Thirty-five assembly/catalog tests and 69 entry/teaching/assessment browser captures pass; live grading, final credit, learner transition and release verification remain open.


Checkpoints 170–172 connect current chat module cards directly to their bound assessments, permit reading new directions before lab setup, and present explicit selected-receipt outcomes in the Challenge panel. Missing, failed, pending and unavailable results remain distinct; no latest/best attempt is inferred and no credit is awarded. The selection interface was checked against actual saved MongoDB receipts with no data or judge-call changes. New outcome modules omit legacy three-star indicators while old earned stars remain unchanged. These improvements do not close live calibration, final-credit or release gates.


Checkpoints 173–174 preserve explicit original assessment references in the completion journal/recovery intent and add a separately gated all-required-outcome validator. The runner requires verified release-candidate metadata, exact pinned runner bytes and single-threshold/no-enrichment policy; the assembled preview retains its nonfunctional placeholder and remains unavailable for credit. Unit and disposable saved-receipt checks use synthetic release flags/providers/judges. Completion API wiring and full competency evidence in credentials remain open, as do live calibration and all release-verification gates.


Checkpoints 175–176 connect explicitly selected receipts to gated HTTP/module completion and freeze complete original outcome evidence in credentials. The learner must separately request completion; interrupted requests retain their original evidence and cannot duplicate XP or issuance. Seventeen connected browser captures verify a synthetic one-module/three-outcome course with real saved receipts and stubbed judging. All-course outcome coverage is unit-tested with synthetic inputs; all 33 live grading/release gates remain open. The isolated assembled preview remains read-only and unpublished.


## Pinned draft progression and journey language

`progression-policy.json` records `required-outcomes-flexible-order.1`: any study order, all required outcomes in all modules, base XP once, one completion threshold without star enrichment, unlimited learner revision, automatic-only assessment, technical recovery without learner failure, and no assessment timer or speed scoring. Required errors cannot be compensated by XP or optional work. This is an unpublished design draft; release verification and acceptance remain open.

The separate draft `course-structure.json` preserves the XP milestone thresholds and grouping but replaces inherited claims of intermediate certification. Journey-group completion points to overall course requirements. The assembler pins both artifacts, validates policy against module XP/order, prerequisites and reachable levels, and exposes the same readable policy in the public course definition. A design-draft policy cannot be published merely because outcome flags were changed. Old immutable packages receive no inferred new policy.


## Publication impact preparation

Checkpoint 197 adds `scripts/inspect_certification_release_impact.py`, a read-only comparison of a source release and an assembled target. Pass explicit `--source-release-id`, `--target-release-id` and, when separate, `--source-catalog-root` / `--target-catalog-root`. An optional `--cohort-inventory` accepts the aggregate output from the existing read-only inventory script; it does not connect to a database.

The report binds exact package/registry digests, lists changed modules, lessons/revisions, outcomes and lab assets, and shows zero inferred credit transfer. It identifies outcomes requiring compatibility review even when unchanged outcome wording hides changed shared exercises or rubric assets. Counts and observation timestamps are preserved without claiming present-day cohort membership or migration safety. Arbitrary extra input payloads are omitted. Exit 2 means blocking findings remain, while exit 1 means invalid inputs prevented a report. Neither code changes any package or learner.

The local publish command now requires this exact report for authored/outcome courses. Pass `--impact-report`, the same `--cohort-inventory` when supplied, and `--source-catalog-root` when different from the target. It regenerates the comparison under the authoring lock and refuses stale or edited reports and remaining findings. No force option clears those findings. Initial preservation of the frozen continuation baseline retains its existing path.

Live model/tool compatibility and actual cohort/accessibility/learner/release evidence remain explicit blockers even with synthetic release-candidate flags. The inspector has no verifier to clear those gates yet, so this is a publication refusal boundary rather than a complete release authorization workflow. The current 74-lesson / 33-outcome preview remains unpublished and unverified for release. Evidence verification and actual rollout reconciliation remain open under C8-OPS-02.


Checkpoint 206 exposes the exact credential promise, assistance rules and exclusions in the course introduction and preserves them in new schema-2 competency issuance. The original promise also appears in its PDF. Existing schema-1 credentials keep their original serialized shape and notice identity, without inferred scope. Checkpoint 208 includes shared promises/assistance/evidence rules in publication impact: a change requires review across all affected outcomes even when individual outcome text is unchanged. These are delivery and integrity safeguards; the draft still has zero release-verified outcomes.


The design checker also emits `outcome_matrix`: one row per required outcome with authored lesson revisions, practice, assessed home, evidence, passing conditions, critical failures and rubric identity. Recognition rows include assigned scenario IDs. CI runs the checker and retains this matrix as `certification-outcome-matrix`. Shared teaching/evidence does not merge passing criteria or transfer credit, and an implemented row is not a release-verified outcome.
