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

## Typing

The starting mypy run reports 3,141 errors, including 2,345 missing-annotation
errors. After this pass, 3,098 errors remain; all ten modified modules are clear.
The workflow remains advisory. The initial cleanup corrects concrete
types and narrowing in budget reconciliation, page locators, attachment source
tracking, extraction generation filters, catalog descriptions, templates,
certificate rendering, scheduling and certification outcome contracts.
No global checks have been disabled and no blanket error suppression added.
Clearing the whole backend remains a separate, substantial refactor.

## Verification

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
