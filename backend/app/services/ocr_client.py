"""OCR endpoint adapters.

Vandalizer's OCR endpoint points at whatever conversion service an institution
already runs, and those services do not share a request contract. Two are
supported:

``raw``
    POST the PDF as multipart field ``file``; the response *body* is the
    extracted text/markdown. This is the shape Vandalizer shipped with (UIPDF,
    Marker/Surya wrappers, a Tesseract wrapper, a cloud-OCR proxy).

``docling``
    `docling-serve <https://github.com/docling-project/docling-serve>`_'s
    convert API: multipart field ``files``, conversion options as sibling form
    fields, and a JSON response whose markdown lives at
    ``document.md_content``. Posting the ``raw`` shape at docling-serve fails
    validation with **HTTP 422** — the file field is named wrong and no options
    are sent — which is exactly what sites running the prebuilt docling-serve
    image saw before this module existed.

Provider-specific request building and response parsing live here so
``document_readers.ocr_extract_text_from_pdf`` keeps owning the one thing that
is provider-independent: config lookup, retries, and graceful degradation to
PyMuPDF.
"""

import json
import logging
import os
import time
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

OCR_PROVIDERS = ("raw", "docling")
DEFAULT_OCR_PROVIDER = "raw"
DEFAULT_OCR_TIMEOUT = 120

# Only the two options Vandalizer actually depends on. Everything else is left
# to docling-serve's own defaults so a Vandalizer upgrade can't silently change
# how a site's documents are converted; the admin UI documents the full set.
DOCLING_DEFAULT_OPTIONS: dict[str, Any] = {"to_formats": ["md"], "do_ocr": True}

# Preference order for reading converted text out of a docling response. We ask
# for markdown, but honor a site that configured different to_formats rather
# than returning nothing.
_DOCLING_CONTENT_FIELDS = (
    "md_content",
    "text_content",
    "html_content",
    "doctags_content",
)

_ASYNC_POLL_INTERVAL_SECONDS = 2.0
_ASYNC_MAX_POLL_SECONDS = 900.0


class OcrRequestError(RuntimeError):
    """A single OCR attempt failed. Retryable — the caller decides."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: str = "",
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        # Seconds the service asked us to wait, parsed from a Retry-After
        # header. Only 429 and 503 normally carry one.
        self.retry_after = retry_after


class OcrUnavailableError(ConnectionError):
    """OCR could not be reached, and waiting is the right response.

    Subclasses ``ConnectionError`` deliberately: the Celery tasks already
    declare ``autoretry_for=TRANSIENT_EXCEPTIONS``, which includes it, so an
    OCR outage engages the retry machinery that was previously bypassed —
    ``OcrRequestError`` subclasses ``RuntimeError`` and was never caught.

    Raised only after the in-process attempts are exhausted *and* the failure
    looks transient. A permanent failure (see ``PERMANENT_STATUS_CODES``) still
    degrades to PyMuPDF rather than retrying for tens of minutes.
    """

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


# Statuses where retrying cannot help: the request itself is wrong, the file is
# rejected, or we aren't authorized. Retrying these would burn the whole task
# backoff budget per document against a misconfigured endpoint.
PERMANENT_STATUS_CODES = frozenset({400, 401, 403, 413, 415, 422})


# Reading the *input* file failed. The OCR service was never the problem, and
# no amount of waiting brings a deleted upload back — a document removed
# mid-processing (retention sweeps, E2E teardown) lands here.
_LOCAL_INPUT_ERRORS = (
    FileNotFoundError,
    PermissionError,
    IsADirectoryError,
    NotADirectoryError,
)


def is_retryable(exc: Exception) -> bool:
    """Whether another attempt at this OCR failure could plausibly succeed.

    A non-HTTP failure carries no ``status_code`` (a malformed response body, a
    poll timeout, a transport error). Those are treated as retryable: the
    common cause is a service that is up but unhealthy, and the cost of being
    wrong is a delayed document rather than a silently degraded one.

    Note ``ConnectionError`` and friends stay retryable even though they are
    ``OSError`` subclasses — a refused connection to the OCR host is precisely
    the outage this exists for. Only the local-input failures above are
    permanent.
    """
    if isinstance(exc, _LOCAL_INPUT_ERRORS):
        return False
    status = getattr(exc, "status_code", None)
    if status is None:
        return True
    return status not in PERMANENT_STATUS_CODES


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header, or None if absent/unparseable.

    Only the delta-seconds form is honored. The HTTP-date form is legal but
    rare from OCR services, and mis-parsing a date into a huge sleep is worse
    than ignoring it.
    """
    if not value:
        return None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def normalize_provider(provider: str | None) -> str:
    """Coerce a stored provider value to a supported one."""
    value = (provider or "").strip().lower()
    return value if value in OCR_PROVIDERS else DEFAULT_OCR_PROVIDER


def normalize_endpoint(endpoint: str, provider: str, use_async: bool = False) -> str:
    """Resolve the configured endpoint to the URL an attempt should POST to.

    For ``raw`` the configured URL is used verbatim — it is whatever the site's
    wrapper exposes. For ``docling`` admins commonly paste the service root
    (``https://docling.example.edu``), so the convert path is appended when
    absent; a URL that already names a convert path is respected, which keeps
    older ``/v1alpha/`` deployments working. ``/convert/source`` is rewritten to
    ``/convert/file`` because we upload the PDF rather than pass a URL.
    """
    url = (endpoint or "").strip().rstrip("/")
    if not url or normalize_provider(provider) != "docling":
        return url

    if url.endswith("/async"):
        url = url[: -len("/async")]
    if "/convert/" not in url:
        url = f"{url}/v1/convert/file"
    elif url.endswith("/convert/source"):
        url = f"{url[: -len('source')]}file"

    return f"{url}/async" if use_async else url


def docling_health_url(endpoint: str) -> str:
    """Health-probe URL for a docling-serve deployment (``/health`` at the root)."""
    convert_url = normalize_endpoint(endpoint, "docling")
    if not convert_url:
        return ""
    root = convert_url.split("/convert/", 1)[0]
    for version_prefix in ("/v1alpha", "/v1"):
        if root.endswith(version_prefix):
            root = root[: -len(version_prefix)]
            break
    return f"{root.rstrip('/')}/health"


def _api_prefix(convert_url: str) -> str:
    """Versioned API prefix (``https://host/v1``) derived from a convert URL."""
    return convert_url.split("/convert/", 1)[0].rstrip("/")


def _encode_option_value(value: Any) -> str:
    """Render one scalar option as a multipart form value.

    docling-serve parses form values with the same coercion FastAPI applies to
    query params, so booleans must be ``true``/``false`` (not Python's
    ``True``), and object-valued options (``picture_description_api``) are
    passed as JSON strings — which is how they appear in the config anyway when
    an admin copies them from another platform.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value)
    if value is None:
        return ""
    return str(value)


def encode_docling_options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    """Turn the stored options dict into httpx multipart ``data``.

    List-valued options (``ocr_lang``, ``to_formats``, ``from_formats``) are
    left as lists of strings — httpx emits one form field per element, which is
    the repeated-key encoding docling-serve expects. Nested lists/objects are
    JSON-encoded as single values.
    """
    merged: dict[str, Any] = dict(DOCLING_DEFAULT_OPTIONS)
    for key, value in (options or {}).items():
        if value is None:
            continue
        merged[key] = value

    data: dict[str, Any] = {}
    for key, value in merged.items():
        if isinstance(value, (list, tuple)) and all(
            not isinstance(item, (dict, list, tuple)) for item in value
        ):
            data[key] = [_encode_option_value(item) for item in value]
        else:
            data[key] = _encode_option_value(value)
    return data


def validate_docling_options(options: Any) -> dict[str, Any]:
    """Validate an admin-supplied options object, raising ``ValueError``.

    Rejects at save time what would otherwise surface as a 422 on every upload
    hours later, when the failure is far from the config change that caused it.
    """
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise ValueError("OCR options must be a JSON object")
    for key in options:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("OCR option names must be non-empty strings")
    try:
        encode_docling_options(options)
    except (TypeError, ValueError) as e:
        raise ValueError(f"OCR options are not encodable as form fields: {e}") from e
    return options


def parse_docling_response(payload: Any) -> str:
    """Pull converted text out of a docling-serve convert/result payload.

    A ``failure`` status raises so the caller retries; ``partial_success``
    keeps whatever text came back and logs the per-document errors, because
    partial text still beats falling all the way back to PyMuPDF.
    """
    if not isinstance(payload, dict):
        raise OcrRequestError("Docling response was not a JSON object")

    status = str(payload.get("status") or "").lower()
    errors = payload.get("errors") or []
    if status == "failure":
        raise OcrRequestError(f"Docling conversion failed: {str(errors)[:500]}")

    document = payload.get("document")
    if not isinstance(document, dict):
        raise OcrRequestError(
            f"Docling response had no document (status={status or 'unknown'})"
        )

    for field in _DOCLING_CONTENT_FIELDS:
        content = document.get(field)
        if isinstance(content, str) and content.strip():
            if errors:
                logger.warning(
                    "Docling conversion reported errors but returned %s: %s",
                    field, str(errors)[:500],
                )
            return content

    raise OcrRequestError(
        f"Docling response carried no text content (status={status or 'unknown'})"
    )


def _post_pdf(client, url: str, headers: dict, pdf_path: str, field: str, data=None):
    """POST the PDF as multipart, returning the httpx response.

    The file handle is opened per attempt so a retry re-reads from the start.
    """
    with open(pdf_path, "rb") as f:
        return client.post(
            url,
            headers=headers,
            files={field: (os.path.basename(pdf_path), f, "application/pdf")},
            data=data,
        )


def _await_docling_task(
    client,
    convert_url: str,
    headers: dict,
    task_id: str,
    poll_interval: float,
    max_poll_seconds: float,
) -> str:
    """Poll an async docling task to completion and return its converted text."""
    prefix = _api_prefix(convert_url)
    deadline = time.monotonic() + max_poll_seconds

    while True:
        resp = client.get(f"{prefix}/status/poll/{task_id}", headers=headers)
        if resp.status_code != 200:
            raise OcrRequestError(
                f"Docling status poll returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
                retry_after=parse_retry_after(resp.headers.get("Retry-After")),
            )
        status = str((resp.json() or {}).get("task_status") or "").lower()
        if status == "success":
            break
        if status == "failure":
            raise OcrRequestError(f"Docling task {task_id} failed")
        if time.monotonic() >= deadline:
            raise OcrRequestError(
                f"Docling task {task_id} still {status or 'pending'} after "
                f"{int(max_poll_seconds)}s"
            )
        time.sleep(poll_interval)

    result = client.get(f"{prefix}/result/{task_id}", headers=headers)
    if result.status_code != 200:
        raise OcrRequestError(
            f"Docling result fetch returned HTTP {result.status_code}",
            status_code=result.status_code,
            body=result.text[:500],
            retry_after=parse_retry_after(result.headers.get("Retry-After")),
        )
    return parse_docling_response(result.json())


def convert(
    client,
    *,
    pdf_path: str,
    endpoint: str,
    headers: dict | None = None,
    provider: str = DEFAULT_OCR_PROVIDER,
    options: Mapping[str, Any] | None = None,
    use_async: bool = False,
    poll_interval: float = _ASYNC_POLL_INTERVAL_SECONDS,
    max_poll_seconds: float = _ASYNC_MAX_POLL_SECONDS,
) -> str:
    """Run one OCR attempt against ``endpoint`` and return the extracted text.

    Raises ``OcrRequestError`` on a failed attempt; the caller retries.
    """
    provider = normalize_provider(provider)
    headers = dict(headers or {})

    if provider == "raw":
        resp = _post_pdf(client, endpoint, headers, pdf_path, "file")
        if resp.status_code != 200:
            raise OcrRequestError(
                f"OCR endpoint returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
                retry_after=parse_retry_after(resp.headers.get("Retry-After")),
            )
        return resp.text

    url = normalize_endpoint(endpoint, provider, use_async=use_async)
    data = encode_docling_options(options)
    resp = _post_pdf(client, url, headers, pdf_path, "files", data=data)
    if resp.status_code not in (200, 201, 202):
        detail = resp.text[:500]
        hint = ""
        if resp.status_code == 422:
            hint = (
                " — docling rejected the request options; check the OCR Options "
                "JSON in Admin -> System Config -> Endpoints"
            )
        raise OcrRequestError(
            f"Docling endpoint returned HTTP {resp.status_code}{hint}",
            status_code=resp.status_code,
            body=detail,
            retry_after=parse_retry_after(resp.headers.get("Retry-After")),
        )

    payload = resp.json()
    if not use_async:
        return parse_docling_response(payload)

    task_id = (payload or {}).get("task_id")
    if not task_id:
        raise OcrRequestError("Docling async response carried no task_id")
    return _await_docling_task(
        client, url, headers, str(task_id), poll_interval, max_poll_seconds
    )
