# Release Checklist

Use this checklist before tagging a release that outside operators are expected to install or upgrade to.

## 1. Prepare The Release Notes

- Update the matching `## [Unreleased]` section in [CHANGELOG.md](CHANGELOG.md) with user-facing and operator-facing changes.
- Write down any operator actions required for this release:
  - `backend/.env` changes
  - `compose.yaml` changes
  - backup/restore expectations
  - upgrade or rollback caveats
- Review config and deployment drift since the previous release:

```bash
git diff <previous-tag>..HEAD -- backend/.env.example compose.yaml README.md DEPLOY.md OPERATIONS.md
```

## 2. Run Release Validation

From a clean checkout of the release candidate:

```bash
make backend-install frontend-install
make release-check
```

Optional but recommended while the backend analysis backlog is still being cleaned up:

```bash
make backend-backlog
```

## 3. Rehearse The Install And Bootstrap Path

Use the interactive setup wizard — the same path end users will follow:

```bash
./setup.sh
```

This handles `.env` creation, secret generation, Docker builds, service startup, admin account creation, and database seeding.

Smoke checks after setup completes:

- `./status.sh` passes all checks green
- The bootstrap admin can log in
- The shared default team appears and is selectable
- A newly created user joins the default team automatically when that option is configured

The canonical `bootstrap_install.py` entrypoint is covered directly in the backend test suite, but an install rehearsal is still the best pre-tag confidence check for Compose releases.

## 4. Confirm Backup, Restore, And Rollback Readiness

- Take a fresh backup: `./setup.sh --upgrade` includes an automatic backup step, or use the manual procedure in [OPERATIONS.md](OPERATIONS.md).
- If the release changes persistence, auth, migrations, or bootstrap behavior, run a restore drill on the candidate build.
- Keep the previous known-good tag available for rollback (`./setup.sh --redeploy` after `git checkout <tag>`).

## 5. Tag And Publish

When the candidate is approved, from a clean `main` that is in sync with `origin/main`:

```bash
./scripts/cut_release.sh --dry-run   # preview the tag and commit list
./scripts/cut_release.sh             # prompts, then creates and pushes the tag
```

The script computes the next CalVer tag (`vYYYY.MM.N`), refuses to run if the tree is dirty or out of sync with origin, and pushes an annotated tag. Pushing the tag triggers the release workflow, which will:

- rerun `make release-check`
- publish versioned backend and frontend GHCR images
- create the GitHub release entry for the tag

If you need to cut a SemVer-style tag instead (`vMAJOR.MINOR.PATCH`), tag manually — the release workflow accepts both since both match `v*.*.*`.

## 6. Finalize Operator Notes

Before announcing the release, make sure the GitHub release notes or changelog entry include:

- the exact version or image tags to deploy
- required config changes
- any upgrade sequencing requirements
- any restore or rollback caveats
