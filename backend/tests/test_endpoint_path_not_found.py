"""A 404 for the URL path is not a 404 for the model.

An OpenAI-protocol model saved with endpoint ``https://mindrouter.uidaho.edu``
(no ``/v1``) is dialed verbatim, so every call hits a path the gateway has no
route for and gets FastAPI's bare ``{'detail': 'Not Found'}`` (Sentry
7719925573). Chat showed users the raw error and paged Sentry; the admin
Test called it "Model not found — check the Model Name", which was fine.
"""

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from app.services.chat_service import _classify_stream_error
from app.services.llm_service import is_endpoint_path_not_found
from app.services.system_diagnostics import _classify_error

ROUTE_404 = ModelHTTPError(
    status_code=404, model_name="zai-org/glm-5.3-flash", body={"detail": "Not Found"},
)


def _wrapped(cause):
    try:
        raise cause
    except BaseException as e:
        try:
            raise RuntimeError("stream failed") from e
        except RuntimeError as outer:
            return outer


@pytest.mark.parametrize("body", [
    {"detail": "Not Found"},
    "404 page not found",
    "<html><body><h1>404 Not Found</h1></body></html>",
    "Cannot POST /chat/completions",
    None,
])
def test_a_404_naming_no_model_is_a_path_problem(body):
    exc = ModelHTTPError(status_code=404, model_name="m", body=body)
    assert is_endpoint_path_not_found(exc)
    assert is_endpoint_path_not_found(_wrapped(exc))


@pytest.mark.parametrize("body", [
    # vLLM / OpenAI
    {"object": "error", "message": "The model `m` does not exist.", "type": "NotFoundError"},
    {"error": {"code": "model_not_found", "message": "The model `m` does not exist"}},
    # Ollama
    {"error": 'model "m" not found, try pulling it first'},
    # OpenRouter and Azure-style gateways name no "model" at all (review of
    # #981: the old absence-of-a-word test called these path problems).
    {"message": "No endpoints found for acme/mystery-model.", "code": 404},
    {"message": "No endpoints found that support tool use.", "code": 404},
    {"code": "DeploymentNotFound", "message": "The API deployment for this resource does not exist."},
    "Deployment not found",
])
def test_a_404_naming_the_model_is_not(body):
    assert not is_endpoint_path_not_found(
        ModelHTTPError(status_code=404, model_name="m", body=body),
    )


def test_other_statuses_and_errors_are_not():
    assert not is_endpoint_path_not_found(
        ModelHTTPError(status_code=500, model_name="m", body={"detail": "Not Found"}),
    )
    assert not is_endpoint_path_not_found(Exception("404 not found"))


def test_chat_tells_the_user_what_happened_and_stays_out_of_sentry():
    severity, message = _classify_stream_error(_wrapped(ROUTE_404))
    assert severity == "warning"
    assert "misconfigured" in message and "/v1" in message
    assert "status_code" not in message


def test_chat_model_not_found_message_is_unchanged():
    exc = ModelHTTPError(
        status_code=404, model_name="m",
        body={"error": {"code": "model_not_found", "message": "The model `m` does not exist"}},
    )
    _severity, message = _classify_stream_error(exc)
    assert message.startswith("The selected model is not available right now.")


def test_the_admin_test_names_the_path_not_the_model_name():
    result = _classify_error(ROUTE_404)
    assert result["category"] == "endpoint_path"
    assert "/v1" in result["fix"]


def test_the_admin_test_still_reports_a_missing_model_as_one():
    exc = ModelHTTPError(
        status_code=404, model_name="m",
        body={"message": "The model `m` does not exist."},
    )
    assert _classify_error(exc)["category"] == "model_not_found"
