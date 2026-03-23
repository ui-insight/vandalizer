# Operations Guide

This guide is the operator runbook for the default self-hosted Docker Compose deployment in [compose.yaml](compose.yaml). It covers backup, restore, upgrade, rollback, and basic health checks for the current FastAPI + React package.

It is intentionally narrower than [DEPLOY.md](DEPLOY.md): use this document for ongoing operations of the current package, not the older Flask-to-FastAPI migration path.

## Scope

These instructions assume:

- the stack is running with `docker compose` from the repo root
- persistent data lives in the default named volumes from [compose.yaml](compose.yaml)
- secrets are stored in `backend/.env`

## Persistent Data Map

Back up all of these before upgrades:

| Component | Where it lives | Why it matters |
| --- | --- | --- |
| MongoDB application data | `mongo-data` volume / `/data/db` in the `mongo` container | users, teams, workflows, audit data, document metadata |
| Uploaded files | `uploads` volume / `/app/static/uploads` in the `api` and `celery` containers | source PDFs and generated files |
| ChromaDB embeddings | `chroma-data` volume / `/app/static/db` in the `api` and `celery` containers | vector index for chat and retrieval |
| Environment secrets | [`backend/.env`](backend/.env) | JWT secret, provider keys, auth configuration |

Redis is not treated as durable state in this deployment. Losing Redis will drop in-flight queue state, but application data remains in MongoDB, uploaded files, and ChromaDB.

## Health Checks

Run the status script before and after any maintenance window:

```bash
./status.sh
```

This checks Docker services, API health, database connectivity, admin accounts, seed data, and storage volumes. Expected baseline: all checks pass green.

For targeted debugging:

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 celery
```

## Backup Procedure

Recommended cadence:

- MongoDB: daily and before every upgrade
- uploads: daily and before every upgrade
- ChromaDB: daily or at minimum before every upgrade
- `backend/.env`: every time secrets or auth settings change

Create a timestamped backup directory:

```bash
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$PWD/backups/$STAMP"
mkdir -p "$BACKUP_DIR"
```

Record the exact application revision:

```bash
git rev-parse HEAD > "$BACKUP_DIR/git-revision.txt"
docker compose config > "$BACKUP_DIR/compose.resolved.yaml"
cp backend/.env "$BACKUP_DIR/backend.env"
```

Back up MongoDB:

```bash
docker compose exec -T mongo \
  sh -lc 'mongodump --archive --gzip --db="${MONGO_DB:-osp}"' \
  > "$BACKUP_DIR/mongo.archive.gz"
```

Back up uploaded files:

```bash
docker compose exec -T api \
  sh -lc 'tar czf - -C /app/static/uploads .' \
  > "$BACKUP_DIR/uploads.tgz"
```

Back up the ChromaDB persistent directory:

```bash
docker compose exec -T api \
  sh -lc 'tar czf - -C /app/static/db .' \
  > "$BACKUP_DIR/chroma.tgz"
```

Recommended validation:

```bash
ls -lh "$BACKUP_DIR"
gzip -t "$BACKUP_DIR/mongo.archive.gz"
tar tzf "$BACKUP_DIR/uploads.tgz" >/dev/null
tar tzf "$BACKUP_DIR/chroma.tgz" >/dev/null
```

## Restore Procedure

Restore into a clean checkout of the same tag or commit that created the backup whenever possible.

1. Stop application traffic and background execution:

```bash
docker compose stop frontend api celery
```

2. Ensure the data services are running:

```bash
docker compose up -d mongo redis chromadb
```

3. Restore secrets if needed:

```bash
cp "$BACKUP_DIR/backend.env" backend/.env
```

4. Restore MongoDB:

```bash
cat "$BACKUP_DIR/mongo.archive.gz" | docker compose exec -T mongo \
  sh -lc 'mongorestore --drop --archive --gzip --db="${MONGO_DB:-osp}"'
```

5. Restore uploaded files:

```bash
cat "$BACKUP_DIR/uploads.tgz" | docker compose run --rm -T api \
  sh -lc 'mkdir -p /app/static/uploads && rm -rf /app/static/uploads/* && tar xzf - -C /app/static/uploads'
```

6. Restore ChromaDB data:

```bash
cat "$BACKUP_DIR/chroma.tgz" | docker compose run --rm -T api \
  sh -lc 'mkdir -p /app/static/db && rm -rf /app/static/db/* && tar xzf - -C /app/static/db'
```

7. Start the full stack:

```bash
docker compose up -d
```

8. Verify:

```bash
curl http://localhost:8001/api/health
docker compose logs --tail=100 api
docker compose logs --tail=100 celery
```

Suggested smoke checks after restore:

- log in as an existing admin
- open the document browser and confirm uploads are visible
- run one chat query against an existing document
- run one small workflow

## Upgrade Procedure

The recommended way to upgrade is the interactive setup wizard:

```bash
./setup.sh --upgrade
```

This will:

1. Show current branch/commit and fetch available updates
2. Offer to pull latest, checkout a specific tag, or skip (rebuild only)
3. Take a full backup (MongoDB, uploads, ChromaDB, .env, git revision)
4. Check for `.env.example` config drift and warn if new variables were added
5. Rebuild the backend and frontend Docker images
6. Recreate application containers with new images (infrastructure stays untouched)
7. Wait for health checks to pass
8. Print rollback instructions with the exact commit to revert to

### Manual upgrade (if you prefer raw commands)

Use tagged releases when available. At minimum, record the exact commit SHA before changing anything.

1. Take a fresh backup using the procedure above.
2. Fetch the target release:

```bash
git fetch --tags
git checkout <release-tag-or-commit>
```

3. Review config drift:

```bash
git diff <previous-tag>..<release-tag> -- backend/.env.example compose.yaml
```

4. Apply any explicit migration steps called out in release notes.
5. Rebuild the shipped services:

```bash
docker compose build api celery frontend
docker compose up -d
```

6. Verify with:

```bash
./status.sh
```

If a release introduces a schema or data migration, treat the backup as mandatory and do not skip release-note review.

## Rollback Procedure

If the new release is unhealthy and no irreversible migration has been applied:

```bash
# The upgrade command prints the exact previous commit. Use it here:
git checkout <previous-known-good-commit>
./setup.sh --redeploy
```

If an incompatible migration was already applied, do a full restore from the pre-upgrade backup instead of only switching code versions.

## Redeploy (After Local Changes)

To rebuild and restart after editing code locally (without pulling from git):

```bash
./setup.sh --redeploy
```

This rebuilds the Docker images from the current working tree and restarts all application containers. Infrastructure services (Redis, MongoDB, ChromaDB) are left untouched.

## Repair

If services are crashed, images are missing, or seed data is incomplete:

```bash
./setup.sh --repair
```

This scans the full deployment state and fixes what it finds — restarts crashed containers, rebuilds missing images, generates missing secrets, and re-runs bootstrap if the admin account or verified catalog is missing.

## Restore Drill Expectations

Run a restore drill before calling the package broadly deployable:

- restore the latest backup into a fresh environment
- verify login, document access, chat, and one workflow run
- record the elapsed time for:
  - MongoDB restore
  - uploads restore
  - ChromaDB restore
  - application bring-up
- save the drill date and recovery time in your internal ops notes

## Current Gaps

This guide improves the current operator path, but a few roadmap items are still open:

- no built-in automated backup scheduler ships with the repo yet
- no S3-backed storage backup flow is documented yet
- no release-specific upgrade notes or rollback matrix ship with tags yet
- no automated restore drill exists in CI
