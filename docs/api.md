# Vandalizer External API

For integrating Vandalizer extractions and automations into other tools. Authenticated with an API key (no session cookie or CSRF needed).

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

At least one of `files`, `document_uuids`, or `text` must be provided.

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

### HTTP 404 — "SearchSet not found"

Either the UUID is wrong, or your API key's user doesn't have access to that search set (e.g. it belongs to another team). Verify in the UI.

### HTTP 429 — rate limit

The endpoint is rate-limited to 10 requests/minute per user. Back off and retry.

---

## Other endpoints

- **`POST /api/automations/{id}/trigger`** — Fire a configured automation. See the Automations editor in the UI for trigger-specific input formats.
- **`GET /api/automations/runs/{trigger_event_id}`** — Poll an automation run for completion.

The Extraction editor in the UI has copy-paste-ready snippets for the search set you have open — use those when you're integrating against a specific search set.
