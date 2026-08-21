"""TRANSIENT_EXCEPTIONS must match the transient errors that actually occur.

The tuple is used as ``autoretry_for`` across the Celery task layer. The
original builtins-only tuple (ConnectionError, TimeoutError, OSError) never
matched httpx, pymongo, or redis failures — none of which inherit from the
builtins — so the retry decorators effectively never fired for the most
common production blips.
"""

import httpx
import pytest
from pymongo.errors import AutoReconnect
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.tasks import TRANSIENT_EXCEPTIONS


@pytest.mark.parametrize(
    "exc_type",
    [
        # builtins (the original tuple)
        ConnectionError,
        TimeoutError,
        OSError,
        # httpx transport-level failures
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.RemoteProtocolError,
        # database / broker blips
        AutoReconnect,
        RedisConnectionError,
        RedisTimeoutError,
    ],
)
def test_transient_error_is_retryable(exc_type):
    assert issubclass(exc_type, TRANSIENT_EXCEPTIONS)


@pytest.mark.parametrize(
    "exc_type",
    [
        # Permanent errors must never be auto-retried.
        ValueError,
        KeyError,
        TypeError,
        # An HTTP *status* error (4xx/5xx response arrived) is not a
        # transport failure — a 404 won't improve on retry.
        httpx.HTTPStatusError,
        # LLM-call errors are handled per-task (ModelHTTPError exclusion),
        # never via the shared tuple.
    ],
)
def test_permanent_error_is_not_retryable(exc_type):
    assert not issubclass(exc_type, TRANSIENT_EXCEPTIONS)


def test_pydantic_ai_errors_stay_out_of_the_shared_tuple():
    """ModelAPIError retry needs a ModelHTTPError exclusion that a plain
    ``except autoretry_for`` clause cannot express — see
    kb_validation_tasks.generate_test_queries_task for the per-task pattern."""
    from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

    assert not issubclass(ModelAPIError, TRANSIENT_EXCEPTIONS)
    assert not issubclass(ModelHTTPError, TRANSIENT_EXCEPTIONS)
