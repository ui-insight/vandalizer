"""Tests for app.utils.fetch_errors.

The contract that matters: every failure mode of the web fetcher maps to a
non-empty, plain-English reason, and the "site blocks automated access"
cases (403s from WAFs, silent timeout stalls) say so explicitly — that is
what the KB source inspector shows users instead of a bare "error".
"""

import httpx

from app.utils.fetch_errors import describe_empty_fetch, describe_fetch_error


def _status_error(code: int, reason: str = "") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.gov/doc.pdf")
    response = httpx.Response(code, request=request, extensions={
        "reason_phrase": reason.encode(),
    })
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


class TestHttpStatusErrors:
    def test_403_names_blocked_automated_access(self):
        msg = describe_fetch_error(_status_error(403, "Forbidden"))
        assert "HTTP 403" in msg
        assert "refused automated access" in msg
        assert "uploading it directly" in msg

    def test_401_and_406_and_451_also_read_as_blocked(self):
        for code in (401, 406, 451):
            assert "refused automated access" in describe_fetch_error(_status_error(code))

    def test_429_mentions_rate_limiting(self):
        msg = describe_fetch_error(_status_error(429))
        assert "HTTP 429" in msg
        assert "rate-limited" in msg

    def test_404_reads_as_not_found(self):
        msg = describe_fetch_error(_status_error(404, "Not Found"))
        assert "HTTP 404" in msg
        assert "not found" in msg.lower()

    def test_5xx_reads_as_server_error(self):
        msg = describe_fetch_error(_status_error(503))
        assert "HTTP 503" in msg
        assert "server error" in msg


class TestNetworkErrors:
    def test_timeout_with_empty_str_still_produces_reason(self):
        # httpx timeout exceptions frequently stringify to "" — the original
        # bug that left KB sources showing a bare "error" with no message.
        e = httpx.ReadTimeout("")
        assert str(e) == ""
        msg = describe_fetch_error(e)
        assert msg
        assert "did not respond" in msg
        assert "bot protection" in msg

    def test_connect_timeout_covered_by_timeout_branch(self):
        assert "did not respond" in describe_fetch_error(httpx.ConnectTimeout(""))

    def test_connect_error(self):
        msg = describe_fetch_error(httpx.ConnectError(""))
        assert "Could not connect" in msg

    def test_ssl_connect_error_mentions_secure_connection(self):
        msg = describe_fetch_error(
            httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        )
        assert "secure connection" in msg

    def test_remote_protocol_error(self):
        msg = describe_fetch_error(httpx.RemoteProtocolError("peer closed connection"))
        assert "closed the connection" in msg

    def test_generic_request_error_keeps_detail(self):
        msg = describe_fetch_error(httpx.ProxyError("proxy says no"))
        assert "proxy says no" in msg


class TestFallbacks:
    def test_ssrf_value_error_passes_through(self):
        msg = describe_fetch_error(ValueError("URL resolves to a private address"))
        assert msg == "URL resolves to a private address"

    def test_exception_with_empty_str_never_yields_empty_message(self):
        msg = describe_fetch_error(RuntimeError())
        assert msg
        assert "RuntimeError" in msg


class TestEmptyFetch:
    def test_includes_status_code_and_block_hint(self):
        msg = describe_empty_fetch(200)
        assert "HTTP 200" in msg
        assert "no text could be extracted" in msg
        assert "block page" in msg

    def test_no_status_code(self):
        msg = describe_empty_fetch(None)
        assert "no text could be extracted" in msg
        assert "HTTP" not in msg
