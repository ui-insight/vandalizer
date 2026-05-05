# Vandalizer Management API

Read-only-ish surface designed for service consumers — dashboards, agentic coding tools (Claude Code, Cursor, etc.), and other automation. Authenticated with **scoped, named API keys** that are independent of any user's session and revocable individually.

> **Not the same as the per-user `x-api-key` in [`api.md`](./api.md).** That key inherits the issuing user's full role and is meant for `POST /api/extractions/run-integrated`-style integrations. The management keys documented here have explicit scopes and are mounted under `/api/mgmt/v1`.

## Issuing a key

Only **superadmins** (`is_admin=True`, not `is_staff`) can issue management keys.

### From the Admin UI

`Admin → API Keys → New key`. Set a human name, pick the scopes, optionally set an expiry. The full token is shown **once** at creation — copy it immediately and store it like a password. Only the prefix (`vk_live_AbCd…`) is recoverable afterward.

### From the API

```bash
curl -X POST "$BASE/api/admin/api-keys" \
  -H "Content-Type: application/json" \
  --cookie "access_token=$ADMIN_JWT;csrf_token=$CSRF" \
  -H "X-CSRF-Token: $CSRF" \
  -d '{
    "name": "claude-code-readonly",
    "scopes": ["metrics:read", "users:read", "validation:read"],
    "expires_at": "2027-01-01T00:00:00Z"
  }'
```

Response includes `token` (full key, returned once) and `prefix` (saved for display).

## Using a key

```
X-API-Key: vk_live_<the-rest-of-the-token>
```

```bash
curl "$BASE/api/mgmt/v1/stats" -H "X-API-Key: $VK_KEY"
```

Every call writes an `AuditLog` entry with `actor_type=api_key`, `actor_user_id=<key id>`, the request path, and the requesting IP. Inspect with `GET /api/mgmt/v1/audit?actor_type=api_key`.

## Scopes

A key authorizes only what its scopes list includes. The wildcard `*` grants everything (use sparingly).

| Scope | What it allows |
|---|---|
| `metrics:read` | `GET /stats` (system-wide counts, active users, run health) |
| `users:read` | `GET /users`, `GET /users/{id}` |
| `teams:read` | `GET /teams` |
| `workflows:read` | `GET /workflows`, `GET /workflows/runs` |
| `documents:read` | `GET /documents` (metadata only, no content) |
| `activity:read` | `GET /activity` |
| `audit:read` | `GET /audit` |
| `config:read` | `GET /config` (secrets redacted) |
| `validation:read` | `GET /validation/runs`, `/validation/test-cases`, `/validation/extractions/{ss}/plan`, `/validation/workflows/{wf}/plan` |
| `validation:write` | `POST/PUT/DELETE` on test cases; `PUT` on cross-field rules and workflow validation plans |
| `validation:run` | `POST /validation/run` (spends LLM tokens) |
| `workflows:run` | `POST /workflows/{id}/run` (spends LLM tokens, kicks off Celery work) |
| `extractions:run` | `POST /extractions/run` (spends LLM tokens) |

## Rate limits

Limits are bucketed **per key**, not per IP, so a noisy automation gets throttled by its key without affecting other consumers from the same network.

| Endpoint | Limit |
|---|---|
| `POST /validation/run` | 10/minute |
| `POST /workflows/{id}/run` | 20/minute |
| `POST /extractions/run` | 30/minute |
| All read endpoints | (none currently — global FastAPI defaults apply) |

A throttled call returns `429 Rate limit exceeded.`

## Endpoint reference

Full schemas are served by OpenAPI at `$BASE/api/openapi.json` (or `$BASE/api/docs` in non-production environments) under tag `mgmt`.

### Read

```bash
curl "$BASE/api/mgmt/v1/stats"                           -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/users?limit=50&skip=0"           -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/teams"                           -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/workflows"                       -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/workflows/runs?status=failed"    -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/documents?team_id=…"             -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/activity?since=2026-01-01"       -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/audit?action=mgmt.workflows:run" -H "X-API-Key: $K"
curl "$BASE/api/mgmt/v1/config"                          -H "X-API-Key: $K"
```

### Validation — read

```bash
# All validation runs for a single search set, newest first:
curl "$BASE/api/mgmt/v1/validation/runs?item_kind=search_set&item_id=$SS&limit=20" \
  -H "X-API-Key: $K"

# Full snapshot (score breakdown + result snapshot + extraction config used):
curl "$BASE/api/mgmt/v1/validation/runs/$RUN_UUID" -H "X-API-Key: $K"

# Test cases + cross-field rules in one call:
curl "$BASE/api/mgmt/v1/validation/extractions/$SS/plan" -H "X-API-Key: $K"

# Workflow validation plan + inputs:
curl "$BASE/api/mgmt/v1/validation/workflows/$WORKFLOW_ID/plan" -H "X-API-Key: $K"
```

### Validation — write

```bash
# Create a single test case
curl -X POST "$BASE/api/mgmt/v1/validation/test-cases" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{
    "search_set_uuid": "'"$SS"'",
    "label": "Q1 invoice golden case",
    "source_type": "text",
    "source_text": "Invoice total: $1,234.56  Due: 2026-04-30",
    "expected_values": {"total": "$1,234.56", "due_date": "2026-04-30"}
  }'

# Bulk upload from a JSON file
curl -X POST "$BASE/api/mgmt/v1/validation/test-cases/bulk" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  --data @cases.json     # { "cases": [ {...}, {...} ] }

# Update cross-field rules wholesale
curl -X PUT "$BASE/api/mgmt/v1/validation/extractions/$SS/cross-field-rules" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{"rules": [{"if": "...", "then": "..."}]}'

# Update a workflow's validation plan
curl -X PUT "$BASE/api/mgmt/v1/validation/workflows/$WORKFLOW_ID/plan" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{"validation_plan": [{"step": "...", "checks": [...]}]}'
```

### Run

```bash
# Run a validation pass on a search set
curl -X POST "$BASE/api/mgmt/v1/validation/run" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{
    "search_set_uuid": "'"$SS"'",
    "sources": [{"document_uuid": "'"$DOC"'"}],
    "num_runs": 3,
    "model": "claude-opus-4-7"
  }'

# Run a workflow against documents
curl -X POST "$BASE/api/mgmt/v1/workflows/$WORKFLOW_ID/run" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{"document_uuids": ["'"$DOC"'"], "model": "claude-opus-4-7"}'

# Run an extraction
curl -X POST "$BASE/api/mgmt/v1/extractions/run" \
  -H "X-API-Key: $K" -H "Content-Type: application/json" \
  -d '{"search_set_uuid": "'"$SS"'", "document_uuids": ["'"$DOC"'"]}'
```

Authorization for run/write endpoints uses the **issuing admin's** access scope. If that admin is later deleted, the key returns `403 API key issuer no longer exists; revoke this key.` — revoke and reissue.

## Using from Claude Code

Two reasonable patterns:

**1. Shell aliases.** Set the env vars once and let the model curl directly:

```bash
export VK_BASE="https://vandalizer.example.edu"
export VK_KEY="vk_live_…"
alias vk='curl -s -H "X-API-Key: $VK_KEY"'
```

Then in a Claude Code session, the model can run `vk "$VK_BASE/api/mgmt/v1/stats" | jq` itself.

**2. Pre-pull context into the conversation.** Before asking Claude Code to investigate, dump the relevant slices into a file it reads:

```bash
mkdir -p .vk-context
vk "$VK_BASE/api/mgmt/v1/validation/runs?item_kind=search_set&item_id=$SS" > .vk-context/runs.json
vk "$VK_BASE/api/mgmt/v1/validation/extractions/$SS/plan"                  > .vk-context/plan.json
```

Then: *"Look at .vk-context/runs.json and .vk-context/plan.json. Why is accuracy regressing on field X? Propose a test-case bulk upload that would catch it earlier."*

Whichever pattern, **start with a read-only key**. Add `validation:write` once you've reviewed what the model actually wants to do, and only add `*:run` keys when you're ready to spend tokens.

## Auditing usage

```bash
# Everything a specific key has done:
vk "$VK_BASE/api/mgmt/v1/audit?actor_user_id=$KEY_ID&limit=200" | jq

# Just the run actions across all keys, last 24h:
vk "$VK_BASE/api/mgmt/v1/audit?action=mgmt.workflows:run&since=2026-05-04T00:00:00Z" | jq
```

Each audit entry has `action` (e.g. `mgmt.validation:write`), `resource_id` (the request path), `ip_address`, and a `detail` block with the HTTP method and the key's display name.

## Revoking

```bash
curl -X DELETE "$BASE/api/admin/api-keys/$KEY_ID" \
  --cookie "access_token=$ADMIN_JWT;csrf_token=$CSRF" \
  -H "X-CSRF-Token: $CSRF"
```

Revocation is immediate; the key returns `401 API key revoked` on the next call. Revoked keys remain in `GET /api/admin/api-keys?include_revoked=true` for audit continuity.
