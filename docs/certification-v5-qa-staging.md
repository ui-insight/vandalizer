# Certification 5.0 QA staging runbook

This runbook puts the 5.0 certification course in front of QA testers on a staging deployment. Real learners are not affected: staging has its own database, its own course catalog directory, and a release that is recorded as not production-authorized. Production processes refuse to serve that release.

The QA package marks every outcome as verified and installs the competency grading runner, so testers can earn credit. Those flags are synthetic. They are not calibration or rollout evidence, which is why the package carries a `qa-staging.json` marker and can only be published with `--qa-staging`. The production publication gate is unchanged and still blocks 5.0.

Background: `backend/certification-data/courses/README.md` (release lifecycle, QA staging publication, coherent release deployment).

## What you need

- A staging host running the Docker deployment (`DEPLOY.md`) built from the branch that carries the 5.0 course (`major/agentic-chat`). It must use a staging database, never a copy of production you intend to keep.
- `backend/.env` on that host with `JWT_SECRET_KEY` set to a real value, because the overlay sets `ENVIRONMENT=staging`.
- A checkout of the same commit on the host with the backend environment installed (`cd backend && uv sync`). Run the commands below from the repository root. They use `backend/.venv/bin/python`; `uv run --project backend python` works too.

## 1. Assemble the 5.0 package into a staging catalog

```bash
export QA_CATALOG=/srv/vandalizer/qa-catalog      # any new directory outside the repository catalog
backend/.venv/bin/python scripts/stage_certification_v5_qa.py prepare "$QA_CATALOG"
```

This assembles 5.0 from `backend/certification-data/drafts/v5.0/` (the same code as `scripts/assemble_certification_v5_preview.py`), marks it for QA, and copies the legacy continuation baseline. Both are registered as drafts. The output prints both manifest digests. The default release ID is `v5.0-qa-staging.1`; pass `--release-id v5.0-qa-staging.2` for a rebuilt package. A release ID is never reused, and `prepare` refuses to overwrite an existing directory.

To review the package before publishing:

```bash
backend/.venv/bin/python scripts/manage_certification_release.py --catalog-root "$QA_CATALOG" inspect v5.0-qa-staging.1
```

## 2. Take the staging cohort inventory

The impact check needs an aggregate inventory of the staging database, even an empty one. It reads aggregate metadata only.

```bash
CERTIFICATION_INVENTORY_MONGO_URL='mongodb://<staging-host>:27017/' \
  backend/.venv/bin/python scripts/inventory_certification_cohorts.py --database <staging-db> > "$QA_CATALOG/../inventory.json"
```

If the inventory reports inconsistent or unowned records, publication blocks with `cohort_reconciliation_required`. Reconcile those records or use a clean staging database.

## 3. Run the impact check, publish and select the default

The scripted path runs the ordinary gated commands in order:

```bash
backend/.venv/bin/python scripts/stage_certification_v5_qa.py publish "$QA_CATALOG" \
  --cohort-inventory "$QA_CATALOG/../inventory.json" \
  --reason "QA of the 5.0 course on staging" --actor "<your name>"
```

It does the following:

1. Publishes the legacy continuation baseline and selects it for learners with unknown legacy history, so existing staging users keep their earned work.
2. Writes the impact report to `$QA_CATALOG/reviews/impact-<release>.json`.
3. Publishes 5.0 in QA staging mode. Only `runtime_compatibility_evidence_required`, `rollout_evidence_required` and `qa_staging_package` are waived. Any other finding stops here with its reason and next action.
4. Selects 5.0 as the new-learner default.

The registry entry records `mode: qa_staging`, `production_authorized: false`, the impact report digest, the waived findings, the reason and the actor. Re-running `publish` after an interruption resumes and keeps the original recorded report.

The same steps by hand (useful for reviewing each one):

```bash
M="backend/.venv/bin/python scripts/manage_certification_release.py --catalog-root $QA_CATALOG"
$M publish legacy-2026-10-02.1 --expected-manifest-sha256 <legacy digest>
$M legacy-continuation legacy-2026-10-02.1
backend/.venv/bin/python scripts/inspect_certification_release_impact.py \
  --source-catalog-root "$QA_CATALOG" --target-catalog-root "$QA_CATALOG" \
  --source-release-id legacy-2026-10-02.1 --target-release-id v5.0-qa-staging.1 \
  --cohort-inventory inventory.json > impact.json   # exits 2; stderr lists changes and findings
$M publish v5.0-qa-staging.1 --expected-manifest-sha256 <5.0 digest> --impact-report impact.json \
  --cohort-inventory inventory.json --qa-staging --reason "QA of the 5.0 course" --actor "<your name>"
$M default v5.0-qa-staging.1
```

## 4. Enable the course on staging

```bash
CERTIFICATION_STAGING_CATALOG="$QA_CATALOG" \
  docker compose -f compose.yaml -f compose.qa-staging.yaml up -d api celery
```

`compose.qa-staging.yaml` sets `ENVIRONMENT=staging`, `CERTIFICATION_VERSIONING_ENABLED=true` and `CERTIFICATION_CATALOG_ROOT`, and mounts the catalog read-only into every API and Celery worker. Registry changes made later on the host are visible to all workers at once; no image rebuild is needed.

Confirm that every worker serves the same release:

```bash
for service in api celery; do
  docker compose -f compose.yaml -f compose.qa-staging.yaml exec "$service" python -c \
    "from app.services.certification_versions.release_coherence import deployment_identity as d; i=d(); print(i['fingerprint'], i['new_enrollment_default'], i['releases'])"
done
```

The fingerprints must match, and the 5.0 release must show `verified_with_installed_runner`. An administrator can also open the certification health report (`GET /api/admin/certifications/health`); it includes `release_identity` for the worker that answered and `release_incidents` for any enrolled course that worker cannot serve.

Test learners who have never started the certification are enrolled in 5.0 on their first course open. Existing staging users with legacy progress continue the legacy course with their credit intact. This runbook does not configure upgrade offers from legacy to 5.0; `optional_upgrade_offers` has no command yet.

## 5. Diagnose a course incident

- The administrator Certifications list explains a learner whose course cannot be served: unknown on this worker, an integrity failure naming the changed asset, a QA-only release in production, or a grading runner mismatch. It states that the learner's progress, answers and credentials are unchanged.
- The learner detail returns the same explanation when the enrolled course cannot load.
- Fix the cause; do not re-enroll, reset or edit records. In practice the fix is a catalog that differs between workers (compare fingerprints), a package edited after publication (restore the exact bytes from the prepared directory), or an image that does not match the package rubric (redeploy the build used to prepare it).

## 6. Roll back

```bash
backend/.venv/bin/python scripts/stage_certification_v5_qa.py rollback "$QA_CATALOG"
```

New learners return to the legacy baseline and 5.0 is retired: it is closed to new enrollment and still served to testers already enrolled, so their work stays readable. Nothing is deleted.

To turn the versioned course off entirely, restart with the flag disabled:

```bash
CERTIFICATION_VERSIONING_ENABLED=false CERTIFICATION_STAGING_CATALOG="$QA_CATALOG" \
  docker compose -f compose.yaml -f compose.qa-staging.yaml up -d api celery
```

Enrolled testers' records stay in the database unchanged. Turning the flag back on resumes them at their saved lesson. Disabling the flag alone is not a full rollback for credentials: if schema-2 credentials were issued, keep readers that support both schemas (see the credential reader boundary in the course README).

To start over, prepare a new catalog with a new `--release-id` and a fresh staging database. Never edit a published package in place.

## Rehearsal evidence

`backend/tests/integration/test_certification_release_rehearsal.py` runs this path against a disposable database using the same environment variables. It covers draft to published promotion, the default switch, an interrupted initialization that restarts cleanly, restarting the publish step, completion-notice deduplication under replay and concurrency, a worker missing the release (support diagnosis with learner work unchanged), production refusal of the QA release, and rollback with the flag off and back on. Run it with `CERTIFICATION_TEST_MONGO_URL=mongodb://127.0.0.1:27018/`.
