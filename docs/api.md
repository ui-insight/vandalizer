# Vandalizer External API

For integrating Vandalizer extractions, workflows, and automations into other tools. Authenticated with an API key (no session cookie or CSRF needed).

## Authentication

Generate an API key from **My Account → API Tokens** in the Vandalizer UI. Pass it in the `x-api-key` header on every request:

```
x-api-key: YOUR_API_KEY
```

The key inherits the permissions of the user that created it. Treat it like a password.

## Base URL

Whatever host serves the Vandalizer UI for your deployment, e.g. `https://vandalizer.example.edu`. All endpoints below are rooted at `/api`.

---

## `POST /api/extractions/run-integrated`

Run an extraction against a search set. Accepts files, existing document UUIDs, raw text, or any combination. Runs synchronously and returns results in the response. Rate-limited to 10 requests/minute per user.

### Request

`multipart/form-data` with these fields:

| Field             | Required | Description |
|-------------------|----------|-------------|
| `search_set_uuid` | yes      | UUID of the search set to run. |
| `files`           | one of   | One or more file uploads. |
| `document_uuids`  | one of   | Comma-separated UUIDs of documents already in Vandalizer. |
| `text`            | one of   | Raw text to extract from. |
| `text_title`      | no       | Optional title for the `text` payload (defaults to `"API text input"`). |
| `ephemeral`       | no       | `true` (default) deletes API-supplied `files` and `text` after the run so they don't accumulate in your library. Existing `document_uuids` are never touched. Set to `false` to retain them in your root folder. |

At least one of `files`, `document_uuids`, or `text` must be provided.

### Document lifecycle

By default, anything you submit as `files` or `text` is treated as an
ephemeral payload: the document is created, extracted against, and then
deleted (Mongo record + uploaded file + any embeddings) before the response
returns. The UUIDs still appear in the `documents` diagnostic block so you
can read per-document status, but the records are gone afterward.

If you want API uploads to stick around — for example, you're seeding a
library from a script and want the files visible in the UI — pass
`ephemeral=false`. The documents will land in your root folder (the legacy
behavior). Documents referenced via `document_uuids` are never deleted
regardless of this flag.

### Response

```json
{
  "status": "completed",
  "activity_id": "...",
  "results": [
    { "field_name": "extracted value", "...": "..." }
  ],
  "documents": [
    {
      "uuid": "...",
      "title": "document.pdf",
      "task_status": "complete",
      "processing": false,
      "raw_text_len": 12345,
      "error_message": null
    }
  ]
}
```

`results` is the flat list of extracted entities. `documents` is a per-document diagnostic block — see the troubleshooting section below for how to read it.

### Examples

#### curl — file upload

```bash
curl -X POST "https://vandalizer.example.edu/api/extractions/run-integrated" \
  -H "x-api-key: YOUR_API_KEY" \
  -F "search_set_uuid=YOUR_SEARCH_SET_UUID" \
  -F "files=@/absolute/path/to/document.pdf"
```

> **Use an absolute path.** With `-F "files=@document.pdf"` (bare filename), curl resolves the path against your current working directory. If the file isn't there, curl prints a warning to stderr but still POSTs an empty body. The server will reject empty uploads with a 400, but you'll save yourself the round trip by using an absolute path.

#### curl — raw text

```bash
curl -X POST "https://vandalizer.example.edu/api/extractions/run-integrated" \
  -H "x-api-key: YOUR_API_KEY" \
  -F "search_set_uuid=YOUR_SEARCH_SET_UUID" \
  -F "text=Paste the document text here." \
  -F "text_title=Invoice 1234"
```

#### curl — existing documents

```bash
curl -X POST "https://vandalizer.example.edu/api/extractions/run-integrated" \
  -H "x-api-key: YOUR_API_KEY" \
  -F "search_set_uuid=YOUR_SEARCH_SET_UUID" \
  -F "document_uuids=UUID1,UUID2"
```

#### curl — keep API uploads in your library

```bash
curl -X POST "https://vandalizer.example.edu/api/extractions/run-integrated" \
  -H "x-api-key: YOUR_API_KEY" \
  -F "search_set_uuid=YOUR_SEARCH_SET_UUID" \
  -F "ephemeral=false" \
  -F "files=@/absolute/path/to/document.pdf"
```

#### Python — file upload

```python
import requests

with open("/absolute/path/to/document.pdf", "rb") as f:
    response = requests.post(
        "https://vandalizer.example.edu/api/extractions/run-integrated",
        headers={"x-api-key": "YOUR_API_KEY"},
        data={"search_set_uuid": "YOUR_SEARCH_SET_UUID"},
        files=[("files", ("document.pdf", f, "application/pdf"))],
    )
print(response.json())
```

---

## `GET /api/extractions/status/{activity_id}`

Look up the status of a previous extraction run. Useful if the original request timed out client-side or if you want a summary later.

```bash
curl "https://vandalizer.example.edu/api/extractions/status/ACTIVITY_ID" \
  -H "x-api-key: YOUR_API_KEY"
```

Returns `status`, `started_at`, `finished_at`, `error`, `documents_touched`, and `result_snapshot`.

---

## `POST /api/workflows/run-integrated`

Run a workflow against uploaded files. Unlike extractions, this queues the run and returns immediately — poll `GET /api/workflows/status` for the result. Rate-limited to 10 requests/minute per user.

The API key comes from **My Account → API Tokens** (see [Authentication](#authentication)). A key expires 365 days after it is generated; an expired key returns `401 "API key expired"`. Generating a new key replaces the old one.

### Request

`multipart/form-data`:

| Field         | Required | Description |
|---------------|----------|-------------|
| `workflow_id` | yes      | ID of the workflow to run (from the workflow's URL or the API panel in the Workflow editor). |
| `files`       | yes      | One or more file uploads. Repeat the field for several files; they all go to the same run. |

Uploaded files are kept in your root folder (there is no `ephemeral` option here, unlike extractions).

### Response

```json
{
  "status": "queued",
  "activity_id": "...",
  "session_id": "..."
}
```

Keep the `session_id` — it is what you poll. `activity_id` only reports that the run is `running`/`complete`; it does not carry the workflow output.

A `workflow_id` that doesn't exist or that your key's user can't access returns `404 "Workflow not found"`. No files returns `400 "No files provided"`.

```bash
curl -X POST "https://vandalizer.example.edu/api/workflows/run-integrated" \
  -H "x-api-key: YOUR_API_KEY" \
  -F "workflow_id=YOUR_WORKFLOW_ID" \
  -F "files=@/absolute/path/to/proposal.pdf" \
  -F "files=@/absolute/path/to/budget.xlsx"
```

---

## `GET /api/workflows/status`

Poll a queued workflow run and read its output.

```bash
curl "https://vandalizer.example.edu/api/workflows/status?session_id=SESSION_ID" \
  -H "x-api-key: YOUR_API_KEY"
```

`GET /api/workflows/status/stream?session_id=...` returns the same payload as a server-sent event stream: one `data:` event each time the payload changes, closing once the run reaches a terminal status.

### Status values

| `status`           | Terminal | Meaning |
|--------------------|----------|---------|
| `queued`           | no       | Accepted; no worker has picked it up yet. |
| `running`          | no       | A worker is executing steps. `num_steps_completed` / `num_steps_total` and `current_step_name` show progress. |
| `pending_approval` | no       | Paused at an approval step (`approval_request_id` names the request). It continues once someone approves it in Vandalizer; keep polling. |
| `completed`        | yes      | Finished. Check `delivery_failures` before treating it as fully done. |
| `error`            | yes      | The run failed. `error` says why; `error_payload` may suggest a fix. |
| `failed`           | yes      | Treat like `error`. Workflow runs record failure as `error`; `failed` is the spelling other run records use, so check for both. |
| `canceled`         | yes      | Someone canceled it. |

### Response fields

| Field | Description |
|-------|-------------|
| `final_output` | The run's result: the output of its last step. Its shape depends on that step (text, a JSON object, a list of rows). |
| `steps_output` | Every step's output, keyed by step name. |
| `output_step_names` | The steps the workflow marks as its outputs, in order. When there are two or more, read those entries of `steps_output` rather than `final_output`. |
| `error` | A human-readable failure reason, or `null`. |
| `error_payload` | A machine-readable failure, when there is a suggested action — e.g. `{"code": "context_over_budget", "suggested_action": "convert_to_kb", "oversize_documents": [...]}`. Otherwise `null`. |
| `delivery_failures` | Outputs the run was configured to deliver (library write, notification, webhook) that failed **after** it completed. A `completed` run with entries here has results but didn't deliver them. |
| `retrieved_sources` | Citations from every knowledge-base step that ran: `{document_id, document_title, page, sheet, chunk_id, score, content_preview}`. |
| `workflow_name`, `document_title`, `start_time` | Labels for logging. |
| `run_metadata` | What the run used and how it was configured — see below. `null` for runs from before this was recorded, and for a run no worker has picked up yet. |

### `run_metadata`

For evaluation work that has to log the exact model and settings behind each run.

| Field | Description |
|-------|-------------|
| `models_used` | Every model that answered a call in this run, most tokens first. These are the names the provider was called with. |
| `model_usage[]` | One row per step and model: `step_index`, `step`, `model`, `tokens_input`, `tokens_output`, `requests`, and `settings[]`. |
| `model_usage[].settings[]` | Each distinct request configuration sent: `configured_model` (the System Config name), `provider`, `endpoint` (host only), `output_mode`, and whichever of `temperature`, `top_p`, `max_tokens`, `seed`, `presence_penalty`, `frequency_penalty`, `stop_sequences`, `thinking`, `extra_body`, `anthropic_thinking`, `openai_reasoning_effort` were set. Two-pass extraction sends one model two configurations, so it has two entries. |
| `model_configs[]` | The System Config entry for each model called, as it stood when the run ended: `name`, `configured`, `tag`, `external`, `thinking`, `temperature`, `context_window`, `response_reserve_tokens`, `supports_structured`, `multimodal`, `supports_pdf`, `api_protocol`, `request_timeout_seconds`, `endpoint` (host only). `configured: false` means no model with that name is configured any more. |
| `default_model` | The run's default model. Steps with their own model, an optimizer override or a fallback retry can each replace it — `model_usage` is what actually ran. |
| `vandalizer_version` | The server version that ran it. |
| `workflow` | `id`, `name`, `version`, `definition_hash`, and `config_override` (an applied optimizer override, or `null`). |
| `steps[]` | Each step's `index`, `name` and `tasks[]` — each task's `type`, and the `model`, `fallback_model` and `prompt_variant` it was built with, when set. |
| `extraction_config` | The System Config extraction settings in effect when the run started. |
| `documents[]` | Each input document: `uuid`, `title`, `extension`, `text_chars`, `text_sha256`. `found: false` if it was deleted before the run was recorded. |
| `captured_at` | When the configuration snapshot was taken (the run's first pass). |

### How far to rely on it

- **A setting missing from `settings` was not sent.** No `temperature` means the provider's default applied — it does not mean 0.
- **Endpoints are host only and API keys never appear.** Model configs are copied through an allow-list.
- **`definition_hash` covers the fully resolved steps** — prompts, saved extraction fields, per-task models and prompt variants — and not the documents. Two runs with the same `definition_hash` and the same `text_sha256` values ran the same configuration on the same text.
- **Two model names.** `model_usage[].model` and `models_used` are the provider-facing names; the name in your System Config is `settings[].configured_model`.
- **Retries and approval resumes add to the record.** Each pass appends its usage, so `requests` counts every attempt. The configuration snapshot is from the first pass.
- **Not captured:** a provider updating the model behind the same name, and the run-to-run variation of any temperature above 0. Identical metadata does not guarantee identical output.

### Example: one evaluation-log row per run

```python
import csv
import json
import time

import requests

BASE = "https://vandalizer.example.edu/api"
HEADERS = {"x-api-key": "YOUR_API_KEY"}
TERMINAL = {"completed", "error", "failed", "canceled"}


def run(workflow_id, path):
    with open(path, "rb") as f:
        queued = requests.post(
            f"{BASE}/workflows/run-integrated",
            headers=HEADERS,
            data={"workflow_id": workflow_id},
            files=[("files", f)],
        )
    queued.raise_for_status()
    session_id = queued.json()["session_id"]
    while True:
        status = requests.get(
            f"{BASE}/workflows/status",
            headers=HEADERS,
            params={"session_id": session_id},
        ).json()
        if status["status"] in TERMINAL:
            return session_id, status
        time.sleep(3)


session_id, status = run("YOUR_WORKFLOW_ID", "/absolute/path/to/proposal.pdf")
meta = status.get("run_metadata") or {}
settings = [s for row in meta.get("model_usage", []) for s in row.get("settings", [])]

with open("eval_log.csv", "a", newline="") as f:
    csv.writer(f).writerow([
        session_id,
        status["status"],
        ";".join(meta.get("models_used", [])),
        json.dumps(settings, sort_keys=True),
        meta.get("workflow", {}).get("definition_hash"),
        ";".join(d.get("text_sha256") or "" for d in meta.get("documents", [])),
        meta.get("vandalizer_version"),
        ";".join(status.get("delivery_failures") or []),
        json.dumps(status.get("final_output")),
    ])
```

---

## Troubleshooting

### `results` is `[]`

Check the `documents` array. The combination of fields tells you why:

| `task_status`   | `processing` | `raw_text_len` | What happened |
|-----------------|--------------|----------------|---------------|
| `"complete"`    | `false`      | `> 0`          | Text extracted fine; the LLM just didn't find any of your search keys. Verify the search set fields against the document content. |
| `"complete"`    | `false`      | `0`            | Text extraction returned empty. Common for scanned PDFs when the OCR service is unavailable. Try a digital PDF or contact your admin to verify OCR is configured. |
| `"error"`       | `false`      | `0`            | Text extraction failed. See `error_message`. Re-upload may help for transient errors. |
| `"extracting"`  | `true`       | `0`            | The text-extraction worker didn't finish within the 90-second timeout. Retry the request — by then the document will likely be cached. |
| `null` / other  | varies       | varies         | Unusual state; report to your admin with the `activity_id`. |

### HTTP 400 — "Uploaded file 'X' is empty"

Your client sent the file part with zero bytes. The most common cause is curl resolving `-F files=@<filename>` against the wrong working directory. Use an absolute path.

### HTTP 401 — "Not authenticated"

Your request reached an endpoint without credentials. Check the header name is `x-api-key` — a workflow `session_id` polled without it returns this rather than a 403.

### HTTP 404 — "SearchSet not found"

Either the UUID is wrong, or your API key's user doesn't have access to that search set (e.g. it belongs to another team). Verify in the UI.

### HTTP 429 — rate limit

The endpoint is rate-limited to 10 requests/minute per user. Back off and retry.

---

## Other endpoints

- **`POST /api/automations/{id}/trigger`** — Fire a configured automation. See the Automations editor in the UI for trigger-specific input formats.
- **`GET /api/automations/runs/{trigger_event_id}`** — Poll an automation run for completion.

The Extraction and Workflow editors in the UI have copy-paste-ready snippets for the search set or workflow you have open — use those when you're integrating against a specific one.
