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
the findings and requires a separate server/API migration.

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
3,098; the current follow-up reduces it to 2,693 across 524 source files. The
models, schemas, database helpers, URL helpers and observability setup pass their
focused type check. Workflow execution, automatic review, review persistence and
review recovery now have no mypy diagnostics either. The full check remains
advisory; the backlog is not clear.

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
