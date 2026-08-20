"""Tests for the OCR provider adapters in app.services.ocr_client.

Covers the contract differences that made docling-serve reject Vandalizer's
uploads with HTTP 422: the multipart field name, option encoding, and reading
the converted text out of a JSON response instead of the response body.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services import ocr_client
from app.services.ocr_client import OcrRequestError


def _response(status_code=200, json_payload=None, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_payload
    # A real dict, not a MagicMock: Retry-After parsing reads this, and a
    # MagicMock would make every response look like it carried a header.
    resp.headers = dict(headers or {})
    return resp


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return str(path)


class TestNormalizeProvider:
    def test_known_providers_pass_through(self):
        assert ocr_client.normalize_provider("docling") == "docling"
        assert ocr_client.normalize_provider("RAW") == "raw"

    def test_unknown_or_missing_falls_back_to_raw(self):
        # Existing installs have no ocr_provider field at all — they must keep
        # the request shape they already had.
        assert ocr_client.normalize_provider(None) == "raw"
        assert ocr_client.normalize_provider("") == "raw"
        assert ocr_client.normalize_provider("marker") == "raw"


class TestNormalizeEndpoint:
    def test_raw_endpoint_is_used_verbatim(self):
        assert ocr_client.normalize_endpoint("https://ocr.example/v1/ocrmd", "raw") == \
            "https://ocr.example/v1/ocrmd"

    def test_docling_root_gets_convert_path(self):
        assert ocr_client.normalize_endpoint("https://docling.example.edu/", "docling") == \
            "https://docling.example.edu/v1/convert/file"

    def test_existing_convert_path_is_respected(self):
        # Older deployments serve /v1alpha; don't rewrite what an admin set.
        url = "https://docling.example.edu/v1alpha/convert/file"
        assert ocr_client.normalize_endpoint(url, "docling") == url

    def test_convert_source_is_rewritten_to_convert_file(self):
        assert ocr_client.normalize_endpoint(
            "https://docling.example.edu/v1/convert/source", "docling"
        ) == "https://docling.example.edu/v1/convert/file"

    def test_async_suffix_added_and_not_doubled(self):
        assert ocr_client.normalize_endpoint("https://d.example", "docling", use_async=True) == \
            "https://d.example/v1/convert/file/async"
        assert ocr_client.normalize_endpoint(
            "https://d.example/v1/convert/file/async", "docling", use_async=True
        ) == "https://d.example/v1/convert/file/async"

    def test_async_suffix_stripped_for_sync_calls(self):
        assert ocr_client.normalize_endpoint(
            "https://d.example/v1/convert/file/async", "docling", use_async=False
        ) == "https://d.example/v1/convert/file"

    def test_empty_endpoint_stays_empty(self):
        assert ocr_client.normalize_endpoint("", "docling") == ""


class TestDoclingHealthUrl:
    def test_derives_root_health_from_root(self):
        assert ocr_client.docling_health_url("https://d.example.edu") == \
            "https://d.example.edu/health"

    def test_derives_root_health_from_full_convert_url(self):
        assert ocr_client.docling_health_url("https://d.example.edu/v1/convert/file") == \
            "https://d.example.edu/health"

    def test_handles_v1alpha_prefix(self):
        assert ocr_client.docling_health_url("https://d.example.edu/v1alpha/convert/file") == \
            "https://d.example.edu/health"


class TestEncodeDoclingOptions:
    def test_defaults_request_markdown_and_ocr(self):
        data = ocr_client.encode_docling_options(None)
        assert data["to_formats"] == ["md"]
        assert data["do_ocr"] == "true"

    def test_booleans_are_lowercased_json_style(self):
        # Python's str(True) == "True", which docling's form parsing rejects.
        data = ocr_client.encode_docling_options({"do_ocr": False, "include_images": True})
        assert data["do_ocr"] == "false"
        assert data["include_images"] == "true"

    def test_scalar_lists_stay_lists_for_repeated_form_fields(self):
        data = ocr_client.encode_docling_options({"ocr_lang": ["fr", "de", "es", "en"]})
        assert data["ocr_lang"] == ["fr", "de", "es", "en"]

    def test_numbers_are_stringified(self):
        data = ocr_client.encode_docling_options({"images_scale": 2})
        assert data["images_scale"] == "2"

    def test_object_options_are_json_encoded(self):
        api_config = {
            "url": "https://catchat-api.example.edu/v1/chat/completions",
            "params": {"model": "gemma4-31B-it"},
        }
        data = ocr_client.encode_docling_options({"picture_description_api": api_config})
        assert json.loads(data["picture_description_api"]) == api_config

    def test_json_string_options_pass_through_unchanged(self):
        # Admins copy this option from other platforms already JSON-encoded.
        raw = '{"url": "https://x/v1/chat/completions"}'
        data = ocr_client.encode_docling_options({"picture_description_api": raw})
        assert data["picture_description_api"] == raw

    def test_user_options_override_defaults(self):
        data = ocr_client.encode_docling_options({"do_ocr": False, "to_formats": ["json"]})
        assert data["do_ocr"] == "false"
        assert data["to_formats"] == ["json"]

    def test_none_values_are_dropped(self):
        data = ocr_client.encode_docling_options({"ocr_engine": None})
        assert "ocr_engine" not in data


class TestValidateDoclingOptions:
    def test_accepts_a_real_option_set(self):
        options = {"do_ocr": True, "ocr_lang": ["en"], "table_mode": "accurate"}
        assert ocr_client.validate_docling_options(options) == options

    def test_none_becomes_empty(self):
        assert ocr_client.validate_docling_options(None) == {}

    def test_rejects_non_objects(self):
        with pytest.raises(ValueError):
            ocr_client.validate_docling_options([{"do_ocr": True}])

    def test_rejects_blank_option_names(self):
        with pytest.raises(ValueError):
            ocr_client.validate_docling_options({"  ": True})


class TestParseDoclingResponse:
    def test_reads_markdown_content(self):
        text = ocr_client.parse_docling_response(
            {"status": "success", "document": {"md_content": "# Award Notice"}}
        )
        assert text == "# Award Notice"

    def test_falls_back_through_other_formats(self):
        text = ocr_client.parse_docling_response(
            {"status": "success", "document": {"md_content": "", "text_content": "plain"}}
        )
        assert text == "plain"

    def test_partial_success_keeps_the_text(self):
        text = ocr_client.parse_docling_response({
            "status": "partial_success",
            "document": {"md_content": "page one only"},
            "errors": ["page 2 failed"],
        })
        assert text == "page one only"

    def test_failure_status_raises(self):
        with pytest.raises(OcrRequestError):
            ocr_client.parse_docling_response({"status": "failure", "errors": ["boom"]})

    def test_missing_document_raises(self):
        with pytest.raises(OcrRequestError):
            ocr_client.parse_docling_response({"status": "success"})

    def test_empty_content_raises(self):
        with pytest.raises(OcrRequestError):
            ocr_client.parse_docling_response(
                {"status": "success", "document": {"md_content": "   "}}
            )

    def test_non_dict_payload_raises(self):
        with pytest.raises(OcrRequestError):
            ocr_client.parse_docling_response("not json")


class TestConvertRaw:
    def test_posts_file_field_and_returns_body(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(200, text="extracted text")

        result = ocr_client.convert(
            client, pdf_path=pdf, endpoint="https://ocr.example/ocrmd", provider="raw"
        )

        assert result == "extracted text"
        assert client.post.call_args[0][0] == "https://ocr.example/ocrmd"
        assert "file" in client.post.call_args[1]["files"]

    def test_non_200_raises_with_status(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(500, text="server error")

        with pytest.raises(OcrRequestError) as excinfo:
            ocr_client.convert(client, pdf_path=pdf, endpoint="https://ocr.example", provider="raw")
        assert excinfo.value.status_code == 500


class TestConvertDocling:
    def test_uses_files_field_and_returns_markdown(self, pdf):
        # The whole point of the docling provider: field name `files`, not
        # `file` — the latter is what produced 422 Unprocessable Entity.
        client = MagicMock()
        client.post.return_value = _response(
            200, json_payload={"status": "success", "document": {"md_content": "# Doc"}}
        )

        result = ocr_client.convert(
            client,
            pdf_path=pdf,
            endpoint="https://docling.example.edu",
            provider="docling",
            options={"ocr_engine": "easyocr", "ocr_lang": ["fr", "en"]},
        )

        assert result == "# Doc"
        args, kwargs = client.post.call_args
        assert args[0] == "https://docling.example.edu/v1/convert/file"
        assert "files" in kwargs["files"]
        assert kwargs["data"]["ocr_engine"] == "easyocr"
        assert kwargs["data"]["ocr_lang"] == ["fr", "en"]

    def test_422_error_names_the_options_field(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(422, text='{"detail": "field required"}')

        with pytest.raises(OcrRequestError) as excinfo:
            ocr_client.convert(
                client, pdf_path=pdf, endpoint="https://d.example", provider="docling"
            )
        assert excinfo.value.status_code == 422
        assert "OCR Options" in str(excinfo.value)

    def test_authorization_header_is_forwarded(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(
            200, json_payload={"status": "success", "document": {"md_content": "x"}}
        )

        ocr_client.convert(
            client, pdf_path=pdf, endpoint="https://d.example", provider="docling",
            headers={"Authorization": "Bearer k"},
        )

        assert client.post.call_args[1]["headers"]["Authorization"] == "Bearer k"


class TestConvertDoclingAsync:
    def test_polls_until_success_then_fetches_result(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(200, json_payload={"task_id": "t-1"})
        client.get.side_effect = [
            _response(200, json_payload={"task_status": "started"}),
            _response(200, json_payload={"task_status": "success"}),
            _response(200, json_payload={"status": "success", "document": {"md_content": "done"}}),
        ]

        with patch("app.services.ocr_client.time.sleep"):
            result = ocr_client.convert(
                client, pdf_path=pdf, endpoint="https://d.example",
                provider="docling", use_async=True,
            )

        assert result == "done"
        assert client.post.call_args[0][0] == "https://d.example/v1/convert/file/async"
        poll_url, result_url = [call[0][0] for call in client.get.call_args_list[1:]]
        assert poll_url == "https://d.example/v1/status/poll/t-1"
        assert result_url == "https://d.example/v1/result/t-1"

    def test_task_failure_raises(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(200, json_payload={"task_id": "t-2"})
        client.get.return_value = _response(200, json_payload={"task_status": "failure"})

        with patch("app.services.ocr_client.time.sleep"), pytest.raises(OcrRequestError):
            ocr_client.convert(
                client, pdf_path=pdf, endpoint="https://d.example",
                provider="docling", use_async=True,
            )

    def test_missing_task_id_raises(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(202, json_payload={})

        with pytest.raises(OcrRequestError):
            ocr_client.convert(
                client, pdf_path=pdf, endpoint="https://d.example",
                provider="docling", use_async=True,
            )

    def test_poll_deadline_raises_rather_than_hanging(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(200, json_payload={"task_id": "t-3"})
        client.get.return_value = _response(200, json_payload={"task_status": "pending"})

        with patch("app.services.ocr_client.time.sleep"), pytest.raises(OcrRequestError):
            ocr_client.convert(
                client, pdf_path=pdf, endpoint="https://d.example",
                provider="docling", use_async=True,
                poll_interval=0, max_poll_seconds=0,
            )


class TestDocumentReadersWiring:
    """SystemConfig -> request shape, the path that actually 422'd in the field."""

    def _run(self, pdf, config, client):
        import app.services.document_readers as dr

        db = MagicMock()
        db.system_config.find_one.return_value = config
        httpx_client = MagicMock()
        httpx_client.__enter__ = MagicMock(return_value=client)
        httpx_client.__exit__ = MagicMock(return_value=False)

        with patch("app.tasks.get_sync_db", return_value=db), \
             patch("app.utils.encryption.decrypt_value", side_effect=lambda v: v or ""), \
             patch("httpx.Client", return_value=httpx_client) as mock_client_factory, \
             patch("time.sleep"):
            result = dr.ocr_extract_text_from_pdf(pdf)
        return result, mock_client_factory

    def test_docling_config_produces_a_docling_request(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(
            200, json_payload={"status": "success", "document": {"md_content": "# Converted"}}
        )

        result, client_factory = self._run(pdf, {
            "ocr_endpoint": "https://docling.example.edu",
            "ocr_api_key": "",
            "ocr_provider": "docling",
            "ocr_options": {"ocr_engine": "easyocr", "ocr_lang": ["en", "fr"]},
            "ocr_timeout_seconds": 300,
        }, client)

        assert result == "# Converted"
        assert client.post.call_args[0][0] == "https://docling.example.edu/v1/convert/file"
        assert "files" in client.post.call_args[1]["files"]
        assert client.post.call_args[1]["data"]["ocr_lang"] == ["en", "fr"]
        # The configured timeout must reach the client, not the old hardcoded 120s.
        assert client_factory.call_args[1]["timeout"] == 300.0

    def test_missing_provider_keeps_the_legacy_raw_request(self, pdf):
        client = MagicMock()
        client.post.return_value = _response(200, text="legacy text")

        result, _ = self._run(pdf, {
            "ocr_endpoint": "https://ocr.example/v1/ocrmd",
            "ocr_api_key": "",
        }, client)

        assert result == "legacy text"
        assert "file" in client.post.call_args[1]["files"]

    def test_docling_config_error_degrades_without_retrying(self, pdf):
        """A 422 is docling's "your options JSON is wrong" answer — permanent.

        Still handled degradation (callers fall back to PyMuPDF), but it now
        stops after one attempt instead of three: retrying a misconfigured
        endpoint can't fix it, and against the task-level backoff added for
        #633 it would cost minutes per document rather than seconds.
        """
        client = MagicMock()
        client.post.return_value = _response(422, text="field required")

        result, _ = self._run(pdf, {
            "ocr_endpoint": "https://docling.example.edu",
            "ocr_api_key": "",
            "ocr_provider": "docling",
        }, client)

        assert result == ""
        assert client.post.call_count == 1  # permanent — no point retrying


# ---------------------------------------------------------------------------
# Retry classification and outage escalation (#633)
# ---------------------------------------------------------------------------


class TestRetryClassification:
    """Which OCR failures are worth waiting on, and which are hopeless."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_transient_statuses_are_retryable(self, status):
        from app.services.ocr_client import OcrRequestError, is_retryable

        assert is_retryable(OcrRequestError("boom", status_code=status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 413, 415, 422])
    def test_permanent_statuses_are_not_retryable(self, status):
        from app.services.ocr_client import OcrRequestError, is_retryable

        assert is_retryable(OcrRequestError("boom", status_code=status)) is False

    def test_non_http_failure_is_retryable(self):
        """A malformed body or a transport error carries no status. Treated as
        retryable: a delayed document beats a silently degraded one."""
        from app.services.ocr_client import OcrRequestError, is_retryable

        assert is_retryable(OcrRequestError("not JSON")) is True
        assert is_retryable(RuntimeError("connection reset")) is True

    def test_missing_input_file_is_not_retryable(self):
        """The upload was deleted mid-processing. OCR was never the problem and
        waiting won't bring the file back."""
        from app.services.ocr_client import is_retryable

        assert is_retryable(FileNotFoundError("no such file")) is False
        assert is_retryable(PermissionError("denied")) is False

    def test_connection_failure_stays_retryable_despite_being_an_oserror(self):
        """ConnectionError is an OSError too — but a refused connection to the
        OCR host is exactly the outage this classification exists for."""
        from app.services.ocr_client import is_retryable

        assert is_retryable(ConnectionRefusedError("refused")) is True

    @pytest.mark.parametrize(
        "raw,expected",
        [("30", 30.0), ("0", 0.0), ("2.5", 2.5), (None, None), ("", None),
         ("Wed, 21 Oct 2026 07:28:00 GMT", None), ("-5", None)],
    )
    def test_parse_retry_after(self, raw, expected):
        from app.services.ocr_client import parse_retry_after

        assert parse_retry_after(raw) == expected


class TestOutageEscalation:
    """A brief outage must not read as 'this document has no text'."""

    def _run(self, pdf, config, client):
        from app.services import document_readers as dr

        db = MagicMock()
        db.system_config.find_one.return_value = config
        httpx_client = MagicMock()
        httpx_client.__enter__ = MagicMock(return_value=client)
        httpx_client.__exit__ = MagicMock(return_value=False)

        with patch("app.tasks.get_sync_db", return_value=db), \
             patch("app.utils.encryption.decrypt_value", side_effect=lambda v: v or ""), \
             patch("httpx.Client", return_value=httpx_client), \
             patch("time.sleep"):
            return dr.ocr_extract_text_from_pdf(pdf)

    _CONFIG = {
        "ocr_endpoint": "https://ocr.example.edu",
        "ocr_api_key": "",
        "ocr_provider": "raw",
    }

    def test_service_outage_raises_rather_than_returning_empty(self, pdf):
        """Returning "" here is what let a 3-second outage be recorded as an
        unreadable document — the caller could not tell the two apart."""
        from app.services.ocr_client import OcrUnavailableError

        client = MagicMock()
        client.post.return_value = _response(503, text="GPU held by llm-svc")

        with pytest.raises(OcrUnavailableError):
            self._run(pdf, self._CONFIG, client)

        assert client.post.call_count == 3  # fast in-process attempts first

    def test_outage_error_is_a_connection_error(self):
        """Must be caught by the tasks' TRANSIENT_EXCEPTIONS tuple, which is
        what engages Celery's autoretry. OcrRequestError subclasses
        RuntimeError and never was."""
        from app.tasks import TRANSIENT_EXCEPTIONS
        from app.services.ocr_client import OcrUnavailableError

        assert issubclass(OcrUnavailableError, TRANSIENT_EXCEPTIONS)

    def test_permanent_failure_still_degrades_quietly(self, pdf):
        """415 means this file can't be OCR'd at all — falling back to PyMuPDF
        is right, and waiting 25 minutes to do it is not."""
        client = MagicMock()
        client.post.return_value = _response(415, text="unsupported media type")

        assert self._run(pdf, self._CONFIG, client) == ""
        assert client.post.call_count == 1

    def test_retry_after_is_honored_between_attempts(self, pdf):
        from app.services import document_readers as dr
        from app.services.ocr_client import OcrUnavailableError

        client = MagicMock()
        client.post.return_value = _response(
            429, text="slow down", headers={"Retry-After": "7"},
        )
        db = MagicMock()
        db.system_config.find_one.return_value = self._CONFIG
        httpx_client = MagicMock()
        httpx_client.__enter__ = MagicMock(return_value=client)
        httpx_client.__exit__ = MagicMock(return_value=False)

        with patch("app.tasks.get_sync_db", return_value=db), \
             patch("app.utils.encryption.decrypt_value", side_effect=lambda v: v or ""), \
             patch("httpx.Client", return_value=httpx_client), \
             patch("time.sleep") as mock_sleep:
            with pytest.raises(OcrUnavailableError) as exc:
                dr.ocr_extract_text_from_pdf(pdf)

        # The service's own number, not our 1s/2s exponential default.
        assert [c[0][0] for c in mock_sleep.call_args_list] == [7.0, 7.0]
        assert exc.value.retry_after == 7.0
