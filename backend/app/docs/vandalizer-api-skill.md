---
name: vandalizer-api
description: Talk to the Vandalizer Management API — `/api/mgmt/v1`. Use when the user says "/vandalizer-api", asks to query the management API, pastes a `vk_live_…` key, asks to check Vandalizer dev/prod stats, validation runs, workflows, audit log, or wants to run a workflow/validation/extraction via the management surface.
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(mkdir *)
  - Bash(chmod *)
  - Bash(curl *)
  - Bash(jq *)
  - Bash(ls *)
  - Bash(cat *)
  - AskUserQuestion
---

# /vandalizer-api — Talk to the Vandalizer Management API

Helps the user authenticate against a Vandalizer instance and make calls against
`/api/mgmt/v1`. The API uses scoped, named API keys (header `X-API-Key`) —
**not** the per-user `x-api-key` for `POST /api/extractions/run-integrated-style`.

Config lives at `~/.claude/vandalizer/config.json` (chmod 600). Each server has
its own base URL and key, so the user can flip between dev/prod without
re-pasting credentials.

---

## On invocation

### 1. Load or bootstrap config

Read `~/.claude/vandalizer/config.json`. Schema:

```json
{
  "active": "dev",
  "servers": {
    "dev":  { "base_url": "https://oauthdev.nkn.uidaho.edu", "key": "vk_live_…" },
    "prod": { "base_url": "https://…",                       "key": "vk_live_…" }
  }
}
```

If the file is missing **or** the active server has no key, bootstrap:

1. **Pick a server.** Use `AskUserQuestion` with header `"Server"`:
   - "Dev (oauthdev.nkn.uidaho.edu)" — UIdaho dev instance
   - "Production" — user supplies URL
   - "Other" — user supplies URL
   (Skip if `$ARGUMENTS` already contains a URL or a known alias like `dev`/`prod`.)

2. **Get a key.** Ask the user for the `vk_live_…` token if not already saved
   for the chosen server. Don't echo it back in full — show only the prefix
   (`vk_live_AbCd…`) when confirming. If they pasted it directly into the
   prompt, accept it and skip asking.

3. **Save.**
   ```bash
   mkdir -p ~/.claude/vandalizer
   # Write/update config.json — preserve other servers' entries.
   chmod 600 ~/.claude/vandalizer/config.json
   ```

4. **Smoke test.** `curl -sS -H "X-API-Key: $KEY" "$BASE/api/mgmt/v1/audit?limit=1"` —
   if it returns `{"items":[…]}` the key is live. Report scope on failure:
   a 403 with `insufficient_scope` tells the user which scopes their key
   actually has.

### 2. Switching servers

If `$ARGUMENTS` is `dev`, `prod`, `use dev`, `switch to prod`, or similar:
update `active` in the config and confirm with the new base URL. Don't ask for
a new key if one is already stored for that server.

If `$ARGUMENTS` is `forget` / `logout` / `clear <server>`: remove that server's
entry (or the whole file). Confirm.

If `$ARGUMENTS` is `status`: show active server + base URL + masked key prefix +
which other servers are configured.

### 3. Otherwise — answer the user's question against the API

Translate the user's natural-language request into one or more `curl` calls.
**Read endpoints are free; run/write endpoints have side effects.** Default
to read-only unless the user explicitly asks to run, create, or modify.

Always pipe through `jq` for readable output. Save large responses to
`/tmp/vk-<topic>.json` and show a summary + the path, rather than dumping
multi-KB JSON into the conversation.

---

## Reference — bake this into responses so you don't re-read it every time

### Authentication

```bash
curl -sS -H "X-API-Key: $VK_KEY" "$VK_BASE/api/mgmt/v1/<path>"
```

Every call writes an `AuditLog` row with `actor_type=api_key`,
`actor_user_id=<key id>`, the request path, and IP. Inspect with
`GET /api/mgmt/v1/audit?actor_type=api_key`.

### Scopes

| Scope | Allows |
| --- | --- |
| `metrics:read` | `GET /stats` |
| `users:read` | `GET /users`, `GET /users/{id}` |
| `teams:read` | `GET /teams` |
| `workflows:read` | `GET /workflows`, `GET /workflows/runs` |
| `documents:read` | `GET /documents` (metadata only) |
| `activity:read` | `GET /activity` |
| `audit:read` | `GET /audit` |
| `config:read` | `GET /config` (secrets redacted) |
| `validation:read` | `GET /validation/runs`, `/validation/test-cases`, `/validation/extractions/{ss}/plan`, `/validation/workflows/{wf}/plan` |
| `validation:write` | `POST/PUT/DELETE` test cases, cross-field rules, workflow plans |
| `validation:run` | `POST /validation/run` (spends LLM tokens) |
| `workflows:run` | `POST /workflows/{id}/run` (spends LLM tokens) |
| `extractions:run` | `POST /extractions/run` (spends LLM tokens) |
| `*` | everything (use sparingly) |

### Rate limits (per key, not per IP)

| Endpoint | Limit |
| --- | --- |
| `POST /validation/run` | 10/min |
| `POST /workflows/{id}/run` | 20/min |
| `POST /extractions/run` | 30/min |
| Read endpoints | (none — FastAPI defaults) |

A throttled call returns `429 Rate limit exceeded`.

### Documented mgmt endpoints (`tag: mgmt` in OpenAPI)

Read:
- `GET /api/mgmt/v1/stats`
- `GET /api/mgmt/v1/users` · `GET /api/mgmt/v1/users/{user_id}`
- `GET /api/mgmt/v1/teams`
- `GET /api/mgmt/v1/workflows` · `GET /api/mgmt/v1/workflows/runs`
- `GET /api/mgmt/v1/documents`
- `GET /api/mgmt/v1/activity`
- `GET /api/mgmt/v1/audit`
- `GET /api/mgmt/v1/config`
- `GET /api/mgmt/v1/validation/runs` · `GET /api/mgmt/v1/validation/runs/{uuid}`
- `GET /api/mgmt/v1/validation/test-cases` · `GET /api/mgmt/v1/validation/test-cases/{uuid}`
- `GET /api/mgmt/v1/validation/extractions/{search_set_uuid}/plan`
- `GET /api/mgmt/v1/validation/workflows/{workflow_id}/plan`

Write / run:
- `POST /api/mgmt/v1/validation/test-cases` · `POST /api/mgmt/v1/validation/test-cases/bulk`
- `PUT /api/mgmt/v1/validation/extractions/{ss}/cross-field-rules`
- `PUT /api/mgmt/v1/validation/workflows/{wf}/plan`
- `POST /api/mgmt/v1/validation/run`
- `POST /api/mgmt/v1/workflows/{id}/run`
- `POST /api/mgmt/v1/extractions/run`

Full schemas at `$VK_BASE/api/openapi.json` (filter to `tag: mgmt`) or
`$VK_BASE/api/docs` in non-prod.

---

## Behavior rules

- **Confirm before any token-spending call.** Show the user the exact `curl`
  you're about to run (URL + body) and wait for an explicit "yes" before
  hitting `/validation/run`, `/workflows/{id}/run`, or `/extractions/run`.
  These mint Celery tasks and burn LLM tokens.
- **Confirm before any write.** Same rule for `POST/PUT/DELETE` on test cases,
  cross-field rules, or workflow plans.
- **Never paste the full key into the conversation transcript.** When
  confirming or debugging, mask everything after the `vk_live_` prefix.
- **Mask redacted secrets in `/config`.** The endpoint already returns
  `enc:gAAAA…` blobs for encrypted values; don't try to decode them and don't
  echo `client_secret` or token fields.
- **Errors to expect:**
  - `401 API key revoked` — key was deleted; bootstrap a new one.
  - `403 API key issuer no longer exists; revoke this key.` — admin who issued
    the key was deleted. The key needs to be revoked and reissued by another
    admin.
  - `403 insufficient_scope` — the requested endpoint isn't covered by the
    key's scopes. Tell the user which scope is missing and stop.
  - `429 Rate limit exceeded` — back off; mention the limit table above.
- **Sample-size penalty.** Validation run scores include a
  `score_breakdown.sample_size_factor` < 1 when there are too few test cases
  or runs. A "low score" with only 1–2 test cases may be reflecting sparse
  data, not a bad workflow.

---

## Suggested first prompts after setup

Offer these as starting points once the user is connected:

- "Show me the most recent failed workflow runs."
- "Which workflows have the worst validation scores?"
- "Pull the validation plan for workflow `<name>` — does it look stale vs. the
   actual output?"
- "List API key activity in the last 24 hours."
- "Dump `/config` and tell me which models are configured."

---

## Install

Drop this file at one of:

- `~/.claude/skills/vandalizer-api/SKILL.md` — available in every Claude Code
  session on this machine.
- `<your-repo>/.claude/skills/vandalizer-api/SKILL.md` — checked into a repo so
  teammates get it on `git pull`.

Then in Claude Code, type `/vandalizer-api` to start.
