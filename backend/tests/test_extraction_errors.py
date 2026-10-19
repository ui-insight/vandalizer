"""A failed extraction run tells the user why.

Support ticket: an NSF award extraction showed only "Request failed". The run
endpoint re-raised the model server's error, and production has no catch-all
handler, so the browser got a plain-text 500 — while History held "422 …
could not be processed by the inference engine … most often a malformed JSON
schema in response_format" for the same run.
"""

from unittest.mock import AsyncMock

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from app.models.activity import ActivityStatus
from app.services.extraction_engine import ExtractionError
from app.services.extraction_errors import describe_extraction_failure
from tests.test_extractions_no_fields import _auth, _make_user, _run_sync_patches, client  # noqa: F401

_REJECTED_BODY = {"detail": {"error": {
    "message": (
        "This request could not be processed by the inference engine and was not retried on other "
        "backends, because the same failure would recur. This usually means the request itself is "
        "invalid — most often a malformed JSON schema in response_format."
    ),
    "type": "invalid_request_error",
    "code": "request_rejected_by_backend",
}}}


def _wrapped(cause: BaseException) -> ExtractionError:
    """The engine's shape: ExtractionError raised from the provider error."""
    try:
        try:
            raise cause
        except Exception as e:
            raise ExtractionError(f"Extraction failed: {e}") from e
    except ExtractionError as wrapped:
        return wrapped


class TestDescribe:
    def test_rejected_structured_output_names_the_model(self):
        status, message = describe_extraction_failure(
            _wrapped(ModelHTTPError(422, "qwen/qwen3.8-27b", _REJECTED_BODY)),
        )
        assert status == 502
        assert "(qwen/qwen3.8-27b) rejected this extraction's structured-output request" in message
        assert "different model" in message and "System Config → Test" in message

    def test_connection_error_is_temporary(self):
        status, message = describe_extraction_failure(_wrapped(ModelAPIError("qwen/qwen3.8-27b", "Connection error.")))
        assert status == 503 and "couldn't be reached" in message

    def test_gateway_error_is_temporary(self):
        status, _ = describe_extraction_failure(_wrapped(ModelHTTPError(503, "m", "Service Unavailable")))
        assert status == 503

    def test_missing_endpoint_path(self):
        status, message = describe_extraction_failure(_wrapped(ModelHTTPError(404, "m", {"detail": "Not Found"})))
        assert status == 502 and "misconfigured" in message

    def test_unknown_model(self):
        _, message = describe_extraction_failure(
            _wrapped(ModelHTTPError(404, "m", {"error": {"code": "model_not_found"}})),
        )
        assert "(m) is not available" in message

    def test_context_too_long(self):
        status, message = describe_extraction_failure(
            _wrapped(ModelHTTPError(400, "m", "This model's maximum context length is 32768 tokens")),
        )
        assert status == 422 and "too long" in message

    def test_a_400_that_is_not_about_the_schema_is_not_called_one(self):
        status, message = describe_extraction_failure(_wrapped(ModelHTTPError(400, "m", "temperature out of range")))
        assert status == 500 and "structured-output" not in message
        assert message.startswith("The extraction failed: Extraction failed: status_code: 400")

    def test_anything_else_quotes_the_error(self):
        status, message = describe_extraction_failure(RuntimeError("x" * 1000))
        assert status == 500 and message == "The extraction failed: " + "x" * 300


class TestRoute:
    @pytest.mark.asyncio
    async def test_failed_run_returns_the_reason_as_json(self, client):  # noqa: F811
        error = _wrapped(ModelHTTPError(422, "qwen/qwen3.8-27b", _REJECTED_BODY))
        resp, mock_activity, mock_svc = await _post_run_failing(client, error)

        assert resp.status_code == 502
        assert "qwen/qwen3.8-27b" in resp.json()["detail"]
        # History still holds the raw provider text.
        mock_activity.activity_finish.assert_awaited_once_with(
            "activity-1", ActivityStatus.FAILED, error=str(error),
        )

    @pytest.mark.asyncio
    async def test_a_trial_limit_keeps_its_own_status(self, client):  # noqa: F811
        from app.exceptions import TrialBudgetExceededError

        resp, _, _ = await _post_run_failing(client, TrialBudgetExceededError("Your trial budget is used up."))
        assert resp.status_code == TrialBudgetExceededError("x").status_code
        assert resp.json()["detail"] == "Your trial budget is used up."


async def _post_run_failing(client, error):  # noqa: F811
    """POST run-sync with the extraction service raising ``error``."""
    from contextlib import ExitStack

    user = _make_user()
    cookies, headers = _auth(user.user_id)
    ctx, activity, _, _ = _run_sync_patches(user, keys=["award_number"], results=[])
    with ExitStack() as stack:
        mocks = [stack.enter_context(c) for c in ctx]
        MockUser, mock_activity, mock_svc, mock_metered = mocks[1], mocks[5], mocks[6], mocks[7]
        MockUser.find_one = AsyncMock(return_value=user)
        mock_activity.activity_start = AsyncMock(return_value=activity)
        mock_activity.activity_finish = AsyncMock()
        mock_svc.get_extraction_keys = AsyncMock(return_value=["award_number"])
        mock_svc.run_extraction_sync = AsyncMock(side_effect=error)
        mock_metered.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_metered.return_value.__aexit__ = AsyncMock(return_value=False)
        resp = await client.post(
            "/api/extractions/run-sync",
            json={"search_set_uuid": "ss-1", "document_uuids": ["doc-1"]},
            cookies=cookies, headers=headers,
        )
    return resp, mock_activity, mock_svc
