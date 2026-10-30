# v5 release readiness

Reviewed 2026-10-29. PR [#1054](https://github.com/ui-insight/vandalizer/pull/1054)
must remain draft and unmerged. This record distinguishes code checks from
deployment QA and observed user outcomes.

## Dependencies and security

- Dependabot PRs #1060–#1064 are merged into main and incorporated in v5.
- Both shipped nginx runtime bases upgrade Alpine packages before final image
  assembly. CI scans these same base stages. The main-branch fix is #1065.
- The frontend lockfile audit reports zero vulnerabilities.
- The Python lockfile upgrades the packages with published fixes, including
  MSAL/cryptography, FastAPI/Starlette, the Prometheus instrumentator,
  pydantic-ai 1.x, and LangChain text splitters. PyPDF2 is replaced by pypdf;
  a regression test fills an actual PDF form and reads its saved value.
- `pip-audit` still reports Chroma 0.5.23 under PYSEC-2026-3813,
  PYSEC-2026-3814 and PYSEC-2026-3815, with no fixed version listed. The audit
  remains advisory and these findings are **not waived or suppressed**.

The corresponding advisories are
[cross-tenant access](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr),
[collection-update code injection](https://github.com/advisories/GHSA-36p7-vc44-83pf),
and [RBAC scope enforcement](https://github.com/advisories/GHSA-xph7-9rjv-w5fr).
[Upstream tracking](https://github.com/chroma-core/chroma/issues/7909) also
reports no patched release; upgrading to the current 1.x line does not clear
the findings and requires a separate server/API migration. Rechecked on
2026-10-29: all three advisories still have `first_patched_version: null`,
[1.5.9 remains the latest upstream release](https://github.com/chroma-core/chroma/releases/tag/1.5.9),
and [the relevant remediation PR](https://github.com/chroma-core/chroma/pull/7602)
remains open and unmerged.

Chroma must stay behind the application boundary: Compose production does not
publish its port, the development override binds it to `127.0.0.1`, and Helm
enables datastore ingress restrictions to backend pods by default. A cluster
must enforce NetworkPolicy for that control to work. The application does not
expose Chroma collection configuration or enable `trust_remote_code` for users.
These controls reduce exposure; they do not establish that the dependency is
patched. Re-audit before release and retain this as an unresolved security item.

The follow-up review of `chromadb/chroma:0.6.3` checked both the published wheel
and the running image. The wheel SHA-256 is
`4851258489a3612b558488d98d09ae0fe0a28d5cad6bd1ba64b96fdc419dc0e5`.
Its collection configuration accepts only `hnsw_configuration`; the collection
update model accepts only name and metadata. The reviewed source contains no
`trust_remote_code`, embedding `build_from_config`, or remote model loading
path. A disposable server test confirms that remote embedding configuration is
rejected and an unknown update configuration is not applied. This is evidence
about these artifacts, not an upstream correction of the advisory's affected
version range. The legacy RBAC provider still lacks resource-scope checks.

Compose now separates Chroma from the frontend on an internal network, and
Helm explicitly denies Chroma egress when NetworkPolicy is enabled. The local
container check passes for backend access, denied frontend access (DNS and
direct IP), and denied Chroma access to a listening peer on a separate network.
Run `python3 scripts/check_chroma_isolation.py --pull` to reproduce it; CI runs
the same check in the Chroma job. It uses the v2 routes actually used by the
locked client. No live application volumes or published ports are involved.
Helm lint and schema validation pass for all five chart fixtures. Actual staging
network-policy enforcement and deployment identity still need deployed QA.

## Typing

The original mypy baseline was 3,141 errors. The dependency pass reduced it to
3,098; the current follow-up reduces it to 498 across 524 source files. The
models, schemas, database helpers, URL helpers and observability setup pass their
focused type check. Workflow execution, automatic review, review persistence and
review recovery, and the knowledge-base, admin, workflow and Home/config APIs
now have no mypy diagnostics either. The main certification API, course-operation
decorator, preparation/execution services, design delivery and saved-review
delivery also pass their checks. The six module delivery APIs, project, team,
organization and Skill contracts are now clean, and 131 additional JSON-object
HTTP endpoints have explicit return types. Invalid principals fail before learner storage
is accessed; 18 regressions cover internal, HTTP and tool error handling. The full check remains
advisory; the backlog is not clear. LLM configuration, extraction, run metadata,
knowledge ingestion, management and workflow services now pass their focused checks.
The LLM wrappers use the current SDK model and retry contracts. Extraction's
source fallback now accepts bare entity lists without treating them as mappings;
OpenRouter clients send the application title header. Management config redaction
covers the current `available_models` credentials and OCR/web-search keys without
mutating stored configuration. Catalog entries, quality reporting and the workflow,
extraction, document, knowledge-base, passive, quality and retention task modules
now pass mypy. The generic async task runner preserves its coroutine's result
contract, and worker MongoDB handles are explicit. Delivery records distinguish
storage outcomes from notification/webhook lists; extraction storage accepts both
its existing mapping and entity-list shapes. Upgrade/credit-transfer delivery,
selection replay journals, course health, enrollment readers, credential snapshots,
completion journals and legacy access wrappers now pass mypy. Captured batch,
validation and governance inputs, plus saved reviews and generated output artifact
verification, have explicit model/storage contracts. PDF, workbook and DOCX readers
use their actual library result types.
Execution plans, batch/validation checks, governance journals, release-impact reports,
legacy backfill/completion and selection-recovery contracts now pass the full check.
Artifact, automation, extraction, verification and library APIs have explicit return
contracts; raw response serialization is preserved. Artifact storage, workflow output,
source grounding and query-import helpers are typed. UTC serialization overloads
preserve the distinction between missing timestamps and actual datetimes. Feedback
eligibility still runs its nine independent observations concurrently.

The follow-up adds validator, database, record-reader and execution contracts,
separates shared repository storage from incompatible submission signatures,
and preserves the distinct credential schema versions. It checks missing
records explicitly at enrollment, recovery and execution boundaries. Previously
unchecked bodies exposed additional issues, which were corrected rather than
suppressed. Frozen legacy rubric artifacts are unchanged. No global checks have
been disabled and no blanket error suppression added.

The workflow pass found a real retry defect: updating the fallback model in task
configuration did not update the cached model used by several concrete nodes.
Nodes now read and validate the current model when calling it. A regression
checks that the first call uses the primary model and the retry uses the fallback.
Automatic-review completion and recovery also reject a disappeared saved receipt
instead of returning `None` as a successful assessment. Structured review uses
the SDK's explicit tool/output retry budgets, preserving one citation repair.

API response contracts retain the previous FastAPI serialization settings.
Knowledge-base access gates preserve optional organization ancestry; source
version selection preserves full-record versus summary types. Admin analytics
use explicit counter and identity-set types. Chat source-health summaries now
handle validation records without a timestamp instead of failing the listing.
Home reads remain concurrent in typed gather groups. Workflow dispatch verifies
that its activity was persisted before starting work; validation plans and inputs
continue to use their existing Pydantic validation at the API boundary.

## Verification

- First follow-up full local backend suite: 8,870 passed, 2,130 skipped.
  The workflow/review pass: 8,869 passed, 2,041 skipped, 89 deselected; three
  additional failures were model-less test fixtures, corrected and verified
  in the focused rerun. Skipped persistence/provider cases are not deployment
  QA evidence.
- Foundation regressions: 107 passed. Certification regressions after the
  repository contracts: 1,556 passed; the subsequent focused selection,
  recovery, batch and workflow checks: 236 passed. Ruff passes.
- Execution persistence after the typed read contracts: 92 passed against a
  disposable MongoDB across validation, connected failure practice, batch,
  output, governance and advanced workflow execution. The container was removed.
  Published-course preservation, Bandit and endpoint-map checks also pass.
- Workflow/context/template regressions: 1,181 passed in the sandbox; the
  remaining public-host DNS test passed with network access. Automatic-review
  regressions: 38 passed. Review persistence, recovery, deduplication, result
  integrity and grading correction checks: 70 passed against disposable MongoDB.
- Admin and knowledge-base contract regressions (including optimizer, chat,
  source-history and validation-task checks): 403 passed.
- Workflow, Home, config and project-context contract regressions: 1,038 passed.
- Certification API and module-delivery regressions: 1,574 passed, including
  18 invalid-principal checks and preserved owned-review conflict responses.
- Project, team, organization, Skill and exception regressions: 211 passed,
  two skipped.
- After the API contracts: 8,888 passed and 2,130 skipped in the full backend
  run. Three tests required public DNS unavailable in the sandbox; all three
  pass with network access (8,891 passing cases combined).
- SDK and extraction contract checks: 309 and 475 passed, respectively (86
  provider-dependent extraction cases skipped). Case/catalog/fallback checks:
  396 passed; run metadata: 51 passed; knowledge, documents, reviews and management:
  953 passed. The management redaction regression and API checks: 22 passed.
- Workflow and chat-workflow regressions: 1,011 passed, including one DNS-dependent
  test rerun with network access. CI passed at `5b1ab444`; subsequent changes
  require a fresh CI run.
- Catalog/verification regressions: 116 passed, two skipped. Quality, drift and
  regression reporting: 122 passed, one skipped. Task boundary checks: 44 passed;
  the subsequent worker/output/retry suite: 449 passed with network access.
- Course upgrade, selection replay, credit transfer and course-health persistence:
  105 passed against disposable MongoDB. Course write/access, legacy evidence,
  completion replay/concurrency and support persistence: 122 passed. Containers
  were removed. The subsequent certification unit suite: 1,574 passed.
- Saved batch/validation/governance input and output-review/handoff persistence:
  230 passed against disposable MongoDB, removed afterward.
- Document-reader contracts: 221 passed across PDF table/unread-page/hidden-text,
  workbook damage and format detection, and DOCX/helper checks.
- CI at `edfb6e1a` passed every job except Python 3.11 backend tests: 8,893
  cases passed but the sandbox-cleanup assertion failed when an unrelated thread
  exited (the count fell from three to two). The test now checks newly surviving
  thread identities, which also catches a leak masked by another thread's exit.
  Eight focused checks pass on Python 3.12; all five cleanup checks and an explicit
  background-thread-exit reproduction pass on Python 3.11. Both Python jobs passed
  at `29be876b`; that run failed only a credit-transfer persistence test because
  three routes still passed bound methods to the new lazy dispatch helper. Those
  routes now pass factories, with route-level coverage for preview, apply, saved
  reads and disabled-rollout construction. The complete CI run at `ed47b294`
  passed, including both Python versions, all four persistence shards, Chroma,
  Helm, frontend, release checks and Docker. Mypy and dependency audit remain
  advisory, so their green status does not close those backlogs.
- Execution, governance, transition, recovery and legacy preservation persistence:
  221 passed against disposable MongoDB. A final run with stable implementation
  fingerprints passed all 107 execution/credit-transfer checks, including the
  previously failing credit-transfer HTTP integration. Both containers were removed.
- This contract batch also passed 301 release/preservation unit tests, 138
  PDF/source/import checks, 96 artifact/output checks, 151 automation checks,
  243 extraction/library checks (88 optional cases skipped), and 85 focused
  dispatch/artifact/webhook regressions. Catalog route tests passed 141 cases
  (four optional cases skipped); the nine-query feedback concurrency test passed.
  Every changed application file is checked
  against the full mypy output before committing, rather than only its original errors.
- The next contract batch types chat streaming/tools, KB judging and optimizers,
  authentication/support/trial APIs, Page templates/exports, notifications and
  selection confirmation. KB/judge tests passed 752 cases; optimizer tests 244;
  auth/browser tests 349 (three skipped); support/trial/template tests 163;
  Page/export tests 105; certification/obligation tests 1,661; and notification/
  print tests 98. The final combined chat, approval, cross-field validation,
  template and trial suite passed 897 cases. Missing judge scores remain unmeasured; malformed extension
  responses are rejected; an unconfirmed template save can retry its stable ID.
- Selection confirmation, saved-course switching, completion concurrency and
  credential completion passed 100 persistence cases against disposable MongoDB.
  The container was removed afterward.
- Certification enrollment and practical delivery persistence: 518 passed
  against a disposable MongoDB container, removed after the run.
- Chroma's disposable container check passes locally and is included in CI.
  Its Compose renderer uses an empty temporary environment fixture so it
  never depends on or reads an operator's real `backend/.env`.

- Focused backend regressions: 171 passed, including real PDF form filling,
  budget reconciliation, page provenance, scheduling, source checks and
  certificate rendering. Ruff passes.
- The additional malformed-schedule regression passes (37 schedule tests).
- PDF upload/export/task and Sentry startup regressions pass (29 tests),
  including filling a real form through the export endpoint. Sentry 2.73 handles
  Starlette's optional template dependency without requiring Jinja2 for this API.
- Frontend production build passes. Four suites that timed out under concurrent
  local workloads pass in isolation (110 tests, one worker and a 30-second
  local timeout). The broad local duplicate runs were stopped; full-suite
  results are taken from CI with its unchanged timeout settings.
- Local certification release rehearsal: passed against a disposable MongoDB
  and temporary catalog. It exercises publication, default selection, existing
  learner preservation, worker release mismatch, production refusal,
  notification deduplication and rollback.
- Full dependency regression suites and final branch CI must pass before this
  follow-up is complete.
- Deployment certification QA remains outstanding. The historical dev host
  `vandalizer-dev.insight.uidaho.edu` responds healthy, but that health response
  does not verify the current branch, catalog coherence or learner flows.
  Follow [the staging runbook](certification-v5-qa-staging.md) with an explicitly
  identified QA deployment and separate catalog. Synthetic QA publication is
  never production authorization.

## Release checklist reconciliation

The PR's old list was checked against issue bodies and completion comments.
#994–#999, #1005–#1009 and #1011–#1014 are closed. #1013 and #1014 are no longer
partly open code tasks: their comments identify the landed changes and checks.
Historical model runs and their limitations are recorded under `docs/reviews/`.
They are not a fresh evaluation of this dependency update.

Remaining catalog model baselines, workflow-path evaluations, RA observation
and Home usefulness measurements were consolidated in
[#1056](https://github.com/ui-insight/vandalizer/issues/1056), then closed as
**not planned** on 2026-10-26 because they are research/evaluation work. They are
not completed acceptance evidence. Do not claim measured RA time savings or
comprehensive workflow accuracy from issue closure or synthetic tests.

Before release:

- [ ] Resolve or explicitly assess the remaining Chroma security findings.
- [ ] Complete deployment certification QA and preserve its evidence.
- [ ] Review current CI and the advisory typing backlog.
- [ ] Review release notes and set the release date only when publishing.
- [ ] Obtain a separate instruction to merge/release v5; the current instruction
  is to keep it unmerged. Retain the PR's squash-merge recommendation to avoid
  bringing removed generated evidence into main's history.
