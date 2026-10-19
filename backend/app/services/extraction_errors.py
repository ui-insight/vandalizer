"""What to tell a user whose extraction run failed.

The run endpoint records the raw failure on the run's activity and used to
re-raise it. Production registers no catch-all handler (see app/main.py), so
the browser got a plain-text 500 and showed "Request failed" — while History
held "422 … the request could not be processed by the inference engine …
most often a malformed JSON schema in response_format" for the same run
(support ticket: an NSF award extraction that failed with no reason given).

``describe_extraction_failure`` turns the common model-server failures into a
sentence the user can act on, naming the model. The raw text stays on the run.
"""

from __future__ import annotations

from typing import Optional

# Shown with the raw text for anything not recognized below, so a user can
# quote it to support instead of "Request failed".
_RAW_SNIPPET = 300


def _model_http_error(exc: BaseException):
    """The ``ModelHTTPError`` in ``exc``'s cause chain, if any."""
    try:
        from pydantic_ai.exceptions import ModelHTTPError
    except ImportError:  # pragma: no cover
        return None
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ModelHTTPError):
            return current
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return None


def describe_extraction_failure(exc: BaseException) -> tuple[int, str]:
    """``(http_status, message)`` for a failed extraction run."""
    from app.services.llm_service import is_endpoint_path_not_found
    from app.tasks import is_transient_llm_error

    http_error = _model_http_error(exc)
    model = getattr(http_error, "model_name", None)
    named = f" ({model})" if model else ""
    text = str(exc)
    lower = text.lower()

    if http_error is not None and http_error.status_code in (400, 422) and (
        "response_format" in lower or "json schema" in lower or "request_rejected_by_backend" in lower
    ):
        return 502, (
            f"The model server{named} rejected this extraction's structured-output request, "
            "so no values were extracted. Run it again with a different model selected, and "
            "let your administrator know: System Config → Test on this model checks structured output."
        )

    if is_endpoint_path_not_found(exc):
        return 502, (
            f"The selected model's server address{named} is misconfigured, so it can't be reached. "
            "Pick a different model and let your administrator know: this model's endpoint in "
            "System Config needs fixing (OpenAI-compatible endpoints usually end in /v1)."
        )

    if "model_not_found" in lower or "does not exist" in lower:
        return 502, f"The selected model{named} is not available right now. Pick a different model and try again."

    if "maximum context length" in lower or "context length" in lower:
        return 422, (
            f"These documents are too long for the selected model{named}. Select fewer documents, "
            "or pick a model with a larger context window."
        )

    if is_transient_llm_error(exc) or "connection error" in lower:
        return 503, "The model service couldn't be reached. Wait a moment and run the extraction again."

    raw = text.strip()[:_RAW_SNIPPET] or type(exc).__name__
    return 500, f"The extraction failed: {raw}"
