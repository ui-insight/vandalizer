"""Tests for ExtractionEngine core execution methods — extract(), dispatch,
single-pass, two-pass, consensus, and config resolution.

These tests mock the LLM layer (pydantic-ai agents) to verify orchestration logic.
"""

import json
from copy import deepcopy
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.extraction_engine import SOURCE_KEY, ExtractionEngine, ExtractionError


def _make_mock_agent_result(output, request_tokens=10, response_tokens=5):
    """Create a mock pydantic-ai RunResult."""
    mock = MagicMock()
    mock.output = output
    mock_usage = MagicMock()
    mock_usage.request_tokens = request_tokens
    mock_usage.response_tokens = response_tokens
    mock.usage.return_value = mock_usage
    return mock


def _make_structured_result(entities_data):
    """Create a mock result for structured extraction."""
    mock = MagicMock()

    class FakeEntity:
        def __init__(self, data):
            self._data = data
        def model_dump(self, by_alias=False):
            return self._data

    class FakeOutput:
        def __init__(self, entities):
            self.entities = [FakeEntity(e) for e in entities]

    mock.output = FakeOutput(entities_data)
    mock_usage = MagicMock()
    mock_usage.request_tokens = 10
    mock_usage.response_tokens = 5
    mock.usage.return_value = mock_usage
    return mock


# ---------------------------------------------------------------------------
# ExtractionEngine.extract() - text-based extraction
# ---------------------------------------------------------------------------

class TestExtractTextBased:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_basic_extraction_returns_entities(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Name": "Alice", "Age": "30"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        result = engine.extract(
            extract_keys=["Name", "Age"],
            doc_texts=["Alice is 30 years old."],
            model="gpt-4o",
        )
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"
        assert result[0]["Age"] == "30"

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_extraction_with_full_text(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Title": "Report"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        result = engine.extract(
            extract_keys=["Title"],
            full_text="This is the report titled Report.",
            model="gpt-4o",
        )
        assert len(result) == 1
        assert result[0]["Title"] == "Report"

    def test_extraction_with_no_text(self):
        engine = ExtractionEngine(system_config_doc={})
        result = engine.extract(extract_keys=["Name"], model="gpt-4o")
        assert result == []

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_comma_separated_keys(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"A": "1", "B": "2"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        result = engine.extract(
            extract_keys="A, B",
            full_text="some text",
            model="gpt-4o",
        )
        assert len(result) == 1
        assert "A" in result[0]
        assert "B" in result[0]

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_multiple_documents(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = [
            _make_structured_result([{"Name": "Alice"}]),
            _make_structured_result([{"Name": "Bob"}]),
        ]
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        result = engine.extract(
            extract_keys=["Name"],
            doc_texts=["Alice doc", "Bob doc"],
            model="gpt-4o",
        )
        assert len(result) == 2
        names = {r["Name"] for r in result}
        assert names == {"Alice", "Bob"}

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_token_tracking(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result(
            [{"X": "1"}],
        )
        # Override usage on the result
        result_mock = _make_structured_result([{"X": "1"}])
        mock_agent.run_sync.return_value = result_mock
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        engine.extract(extract_keys=["X"], full_text="text", model="gpt-4o")
        assert engine.tokens_in > 0
        assert engine.tokens_out > 0


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

class TestConfigResolution:
    def test_default_config_when_no_sys_config(self):
        engine = ExtractionEngine(system_config_doc={})
        cfg = engine._resolve_config()
        assert "mode" in cfg
        assert "one_pass" in cfg
        assert "two_pass" in cfg

    def test_config_override_applied(self):
        engine = ExtractionEngine(system_config_doc={})
        cfg = engine._resolve_config({"mode": "one_pass"})
        assert cfg["mode"] == "one_pass"

    def test_sys_config_extraction_config_merged(self):
        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "use_images": True}
        })
        cfg = engine._resolve_config()
        assert cfg["mode"] == "one_pass"
        assert cfg["use_images"] is True

    def test_legacy_strategy_applied(self):
        engine = ExtractionEngine(system_config_doc={
            "extraction_strategy": "one_pass_thinking"
        })
        cfg = engine._resolve_config()
        assert cfg["mode"] == "one_pass"
        assert cfg["one_pass"]["thinking"] is True

    def test_legacy_model_applied(self):
        engine = ExtractionEngine(system_config_doc={
            "extraction_model": "custom-model"
        })
        cfg = engine._resolve_config()
        assert cfg["model"] == "custom-model"


# ---------------------------------------------------------------------------
# Key chunking in extraction
# ---------------------------------------------------------------------------

class TestKeyChunking:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_chunking_enabled(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        # Two chunks: [A, B] and [C]
        mock_agent.run_sync.side_effect = [
            _make_structured_result([{"A": "1", "B": "2"}]),
            _make_structured_result([{"C": "3"}]),
        ]
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {
                "mode": "one_pass",
                "one_pass": {"thinking": False, "structured": True},
                "chunking": {"enabled": True, "max_keys_per_chunk": 2},
            },
        })
        result = engine.extract(
            extract_keys=["A", "B", "C"],
            full_text="text",
            model="gpt-4o",
        )
        # Should merge chunks
        assert len(result) == 1
        assert result[0] == {"A": "1", "B": "2", "C": "3"}

    def test_chunking_disabled(self):
        engine = ExtractionEngine(system_config_doc={})
        chunks = engine._resolve_key_chunks(["A", "B", "C"], {"chunking": {"enabled": False}})
        assert chunks == [["A", "B", "C"]]

    def test_chunking_no_config(self):
        engine = ExtractionEngine(system_config_doc={})
        chunks = engine._resolve_key_chunks(["A", "B"], {})
        assert chunks == [["A", "B"]]


# ---------------------------------------------------------------------------
# Dispatch layer
# ---------------------------------------------------------------------------

class TestDispatchExtraction:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_one_pass_structured(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"X": "val"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        config = {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True, "model": ""}}
        result = engine._dispatch_extraction("text", ["X"], "gpt-4o", config)
        assert len(result) == 1

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_one_pass_unstructured(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result('{"X": "val"}')
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        config = {"mode": "one_pass", "one_pass": {"thinking": False, "structured": False, "model": ""}}
        result = engine._dispatch_extraction("text", ["X"], "gpt-4o", config)
        assert len(result) == 1
        assert result[0]["X"] == "val"

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_two_pass_default(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = [
            # Pass 1: fallback JSON (unstructured by default)
            _make_mock_agent_result('{"Name": "Draft"}'),
            # Pass 2: structured
            _make_structured_result([{"Name": "Final"}]),
        ]
        mock_agent_cls.return_value = mock_agent

        # Need to also mock create_chat_agent for the unstructured pass 1
        with patch("app.services.extraction_engine.create_chat_agent") as mock_chat:
            mock_chat_agent = MagicMock()
            mock_chat_agent.run_sync.return_value = _make_mock_agent_result('{"Name": "Draft"}')
            mock_chat.return_value = mock_chat_agent

            engine = ExtractionEngine(system_config_doc={})
            config = {
                "mode": "two_pass",
                "two_pass": {
                    "pass_1": {"model": "", "thinking": True, "structured": False},
                    "pass_2": {"model": "", "thinking": False, "structured": True},
                },
            }
            result = engine._dispatch_extraction("text", ["Name"], "gpt-4o", config)
            assert len(result) >= 1


# ---------------------------------------------------------------------------
# Consensus extraction
# ---------------------------------------------------------------------------

class TestConsensusExtraction:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_consensus_with_agreement(self, mock_get_model, mock_agent_cls):
        """When two parallel extractions agree, no third pass needed."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        # Both runs return the same result
        mock_agent.run_sync.side_effect = [
            _make_structured_result([{"Name": "Alice"}]),
            _make_structured_result([{"Name": "Alice"}]),
        ]
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        config = {
            "mode": "one_pass",
            "one_pass": {"thinking": False, "structured": True, "model": ""},
            "repetition": {"enabled": True},
        }
        result = engine.extract(
            extract_keys=["Name"],
            full_text="Alice doc",
            model="gpt-4o",
            extraction_config_override=config,
        )
        assert len(result) >= 1
        assert result[0].get("Name") == "Alice"
        # Should only be 2 calls (no third pass needed)
        assert mock_agent.run_sync.call_count == 2

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_consensus_with_disagreement(self, mock_get_model, mock_agent_cls):
        """When two runs disagree, a third pass is triggered for majority vote."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = [
            _make_structured_result([{"Name": "Alice"}]),
            _make_structured_result([{"Name": "Bob"}]),
            _make_structured_result([{"Name": "Alice"}]),  # Tie-breaker
        ]
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        config = {
            "mode": "one_pass",
            "one_pass": {"thinking": False, "structured": True, "model": ""},
            "repetition": {"enabled": True},
        }
        result = engine.extract(
            extract_keys=["Name"],
            full_text="doc",
            model="gpt-4o",
            extraction_config_override=config,
        )
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"  # majority wins
        assert mock_agent.run_sync.call_count == 3


# ---------------------------------------------------------------------------
# Fallback extraction
# ---------------------------------------------------------------------------

class TestFallbackExtraction:
    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_json_parsing(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result('{"Name": "Alice", "Age": "30"}')
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine._extract_fallback_json("text about Alice", ["Name", "Age"], "gpt-4o")
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"
        assert result[0]["Age"] == "30"

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_strips_code_blocks(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result(
            '```json\n{"Name": "Alice"}\n```'
        )
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine._extract_fallback_json("text", ["Name"], "gpt-4o")
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_raises_on_invalid_json(self, mock_create_agent):
        """Unparseable model output raises — it must never read as "nothing found"."""
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result("not json at all")
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        with pytest.raises(ExtractionError):
            engine._extract_fallback_json("text", ["Name"], "gpt-4o")

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_accepts_literal_newlines_in_strings(self, mock_create_agent):
        """The prompt asks for supporting passages copied character-for-
        character; a passage that spans lines comes back with a raw newline
        inside the JSON string, which strict json.loads rejects ("Invalid
        control character", Sentry VANDALIZER-BACKEND-2Y). That's a usable
        answer, not a failed run."""
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result(
            '{"Name": "Alice",\n "_sources": {"Name": "PI:\tAlice Smith\nDept of Biology"}}'
        )
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine._extract_fallback_json(
            "text", ["Name"], "gpt-4o", capture_sources=True
        )
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"
        assert result[0][SOURCE_KEY]["Name"]["quote"] == "PI:\tAlice Smith\nDept of Biology"

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_raises_on_exception(self, mock_create_agent):
        """A dead LLM call raises so callers mark the run FAILED, not completed."""
        mock_create_agent.side_effect = RuntimeError("LLM down")

        engine = ExtractionEngine(system_config_doc={})
        with pytest.raises(ExtractionError):
            engine._extract_fallback_json("text", ["Name"], "gpt-4o")

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_fallback_list_response(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result(
            '[{"Name": "Alice"}, {"Name": "Bob"}]'
        )
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine._extract_fallback_json("text", ["Name"], "gpt-4o")
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Structured extraction error handling
# ---------------------------------------------------------------------------

class TestStructuredExtractionErrors:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_validation_error_falls_back(self, mock_get_model, mock_agent_cls):
        """When structured extraction fails validation, falls back to JSON."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = Exception("output validation failed after retries")
        mock_agent_cls.return_value = mock_agent

        with patch("app.services.extraction_engine.create_chat_agent") as mock_chat:
            mock_chat_agent = MagicMock()
            mock_chat_agent.run_sync.return_value = _make_mock_agent_result('{"Name": "Fallback"}')
            mock_chat.return_value = mock_chat_agent

            engine = ExtractionEngine(system_config_doc={})
            result = engine._extract_structured("text", ["Name"], "gpt-4o")
            assert len(result) == 1
            assert result[0]["Name"] == "Fallback"

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_non_validation_error_raises(self, mock_get_model, mock_agent_cls):
        """Provider/network errors raise so the run is marked FAILED — an
        empty result must mean "nothing found", never "the call died"."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = ConnectionError("network error")
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        with pytest.raises(ExtractionError, match="network error"):
            engine._extract_structured("text", ["Name"], "gpt-4o")

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_none_output_returns_empty(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = None
        mock_usage = MagicMock()
        mock_usage.request_tokens = 0
        mock_usage.response_tokens = 0
        mock_result.usage.return_value = mock_usage
        mock_agent.run_sync.return_value = mock_result
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine._extract_structured("text", ["Name"], "gpt-4o")
        assert result == []

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_fallback_disabled(self, mock_get_model, mock_agent_cls):
        """When allow_fallback=False, validation errors raise instead of
        silently shipping an empty result."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = Exception("output validation failed")
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        with pytest.raises(ExtractionError):
            engine._extract_structured("text", ["Name"], "gpt-4o", allow_fallback=False)


# ---------------------------------------------------------------------------
# Failure-degradation semantics
# ---------------------------------------------------------------------------

class TestFailureDegradation:
    def test_two_pass_falls_back_to_draft_when_pass2_fails(self):
        """A pass-2 refinement failure ships the pass-1 draft, not a crash."""
        engine = ExtractionEngine(system_config_doc={})
        draft = [{"Name": "Alice"}]

        def fake_extract(content, keys, model, **kwargs):
            if kwargs.get("allow_fallback") is False:  # pass 2
                raise ExtractionError("pass 2 died")
            return deepcopy(draft)

        with patch.object(engine, "_extract_structured", side_effect=fake_extract):
            result = engine._execute_two_pass(
                "text", ["Name"], "gpt-4o",
                pass_1_cfg={"structured": True},
                pass_2_cfg={"structured": True},
            )
        assert result == draft

    def test_two_pass_raises_when_pass1_fails(self):
        """No draft, no dishonest empty result — pass-1 failure propagates."""
        engine = ExtractionEngine(system_config_doc={})
        with patch.object(
            engine, "_extract_structured", side_effect=ExtractionError("pass 1 died"),
        ):
            with pytest.raises(ExtractionError):
                engine._execute_two_pass(
                    "text", ["Name"], "gpt-4o",
                    pass_1_cfg={"structured": True},
                    pass_2_cfg={"structured": True},
                )

    def test_consensus_raises_when_all_replicates_fail(self):
        engine = ExtractionEngine(system_config_doc={})
        with patch.object(
            engine, "_dispatch_extraction", side_effect=ExtractionError("down"),
        ):
            with pytest.raises(ExtractionError):
                engine._extract_with_consensus("text", ["Name"], "gpt-4o", {})

    def test_consensus_survives_one_failed_replicate(self):
        engine = ExtractionEngine(system_config_doc={})
        calls = {"n": 0}

        def fake_dispatch(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ExtractionError("replicate 1 died")
            return [{"Name": "Alice"}]

        with patch.object(engine, "_dispatch_extraction", side_effect=fake_dispatch):
            result = engine._extract_with_consensus("text", ["Name"], "gpt-4o", {})
        assert result and result[0]["Name"] == "Alice"


# ---------------------------------------------------------------------------
# Multimodal extraction guard
# ---------------------------------------------------------------------------

class TestMultimodalExtraction:
    def test_non_multimodal_model_uses_text(self):
        """When use_images=True but model isn't multimodal, text path is used."""
        engine = ExtractionEngine(system_config_doc={
            "available_models": [{"name": "text-only"}],
            "extraction_config": {
                "mode": "one_pass",
                "one_pass": {"thinking": False, "structured": False},
                "use_images": True,
            },
        })
        result = engine.extract(
            extract_keys=["Name"],
            doc_texts=[],
            doc_file_paths=["/fake/path.pdf"],
            model="text-only",
        )
        assert result == []

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_multimodal_model_with_image_files(self, mock_get_model, mock_agent_cls):
        """When model is multimodal and use_images=True, image path is attempted."""
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Name": "Visual"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "available_models": [{"name": "gpt-4o", "multimodal": True}],
            "extraction_config": {
                "mode": "one_pass",
                "one_pass": {"thinking": False, "structured": True},
                "use_images": True,
            },
        })

        # Mock _load_file_content to return fake binary content
        with patch.object(engine, "_load_file_content") as mock_load:
            from pydantic_ai import BinaryContent
            mock_load.return_value = [BinaryContent(data=b"fake", media_type="image/png")]
            result = engine.extract(
                extract_keys=["Name"],
                doc_file_paths=["/fake/img.png"],
                model="gpt-4o",
            )
            assert len(result) >= 1
            mock_load.assert_called_once()


# ---------------------------------------------------------------------------
# build_from_documents
# ---------------------------------------------------------------------------

class TestBuildFromDocuments:
    @patch("app.services.extraction_engine.create_chat_agent")
    def test_generates_entities(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result(
            '{"entities": ["Name", "Date", "Amount"]}'
        )
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine.build_from_documents(["Some document text"], "gpt-4o")
        assert result is not None
        assert "entities" in result
        assert "Name" in result["entities"]

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_returns_none_on_invalid_json(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result("not json")
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine.build_from_documents(["text"], "gpt-4o")
        assert result is None

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_strips_code_blocks(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result(
            '```json\n{"entities": ["Title"]}\n```'
        )
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={})
        result = engine.build_from_documents(["text"], "gpt-4o")
        assert result is not None
        assert "Title" in result["entities"]

    @patch("app.services.extraction_engine.create_chat_agent")
    def test_uses_config_model_override(self, mock_create_agent):
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_mock_agent_result('{"entities": ["X"]}')
        mock_create_agent.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"model": "override-model"}
        })
        engine.build_from_documents(["text"], "gpt-4o")
        # Should use the override model, not gpt-4o
        call_args = mock_create_agent.call_args
        assert call_args[0][0] == "override-model"


# ---------------------------------------------------------------------------
# Field metadata handling
# ---------------------------------------------------------------------------

class TestFieldMetadata:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_enum_field_in_extraction(self, mock_get_model, mock_agent_cls):
        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Status": "Active"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc={
            "extraction_config": {"mode": "one_pass", "one_pass": {"thinking": False, "structured": True}},
        })
        result = engine.extract(
            extract_keys=["Status"],
            full_text="The status is active",
            model="gpt-4o",
            field_metadata=[{"key": "Status", "enum_values": ["Active", "Inactive"]}],
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _serialize_output (from workflow_service.py, used in validation)
# ---------------------------------------------------------------------------

class TestSerializeOutput:
    """Test the _serialize_output helper from workflow_service."""

    def test_none_returns_empty(self):
        from app.services.workflow_service import _serialize_output
        assert _serialize_output(None) == ""

    def test_dict_output(self):
        from app.services.workflow_service import _serialize_output
        result = _serialize_output({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_file_download_text(self):
        import base64
        from app.services.workflow_service import _serialize_output
        data = base64.b64encode(b"hello world").decode()
        output = {"type": "file_download", "data_b64": data, "file_type": "csv"}
        result = _serialize_output(output)
        assert result == "hello world"

    def test_file_download_binary(self):
        from app.services.workflow_service import _serialize_output
        output = {"type": "file_download", "data_b64": "xxx", "file_type": "zip"}
        result = _serialize_output(output)
        assert result is None

    def test_string_output(self):
        from app.services.workflow_service import _serialize_output
        result = _serialize_output("plain text output")
        assert result == "plain text output"

    def test_list_output(self):
        from app.services.workflow_service import _serialize_output
        result = _serialize_output([1, 2, 3])
        parsed = json.loads(result)
        assert parsed == [1, 2, 3]


# ---------------------------------------------------------------------------
# vLLM-protocol structured output mode
# ---------------------------------------------------------------------------

class TestVllmStructuredOutputMode:
    """vllm-protocol models must request server-side schema enforcement via
    pydantic-ai's NativeOutput (the standard OpenAI ``response_format``
    parameter), not vLLM's proprietary ``structured_outputs`` extra-body —
    OpenAI-compatible gateways silently drop unknown extra-body fields,
    which quietly loses schema enforcement."""

    def _config(self, protocol):
        return {
            "available_models": [
                {"name": "local-model", "api_protocol": protocol,
                 "endpoint": "http://inference.local:8000"},
            ],
            "extraction_config": {
                "mode": "one_pass",
                "one_pass": {"thinking": False, "structured": True},
            },
        }

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_vllm_protocol_uses_native_output(self, mock_get_model, mock_agent_cls):
        from pydantic_ai import NativeOutput

        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Name": "Alice"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc=self._config("vllm"))
        result = engine.extract(
            extract_keys=["Name"], full_text="Alice.", model="local-model",
        )

        assert result == [{"Name": "Alice"}]
        output_type = mock_agent_cls.call_args.kwargs["output_type"]
        assert isinstance(output_type, NativeOutput)
        settings = mock_agent.run_sync.call_args.kwargs.get("model_settings") or {}
        assert "structured_outputs" not in (settings.get("extra_body") or {})

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_openai_protocol_keeps_default_output_mode(self, mock_get_model, mock_agent_cls):
        from pydantic_ai import NativeOutput

        mock_get_model.return_value = MagicMock()
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = _make_structured_result([{"Name": "Alice"}])
        mock_agent_cls.return_value = mock_agent

        engine = ExtractionEngine(system_config_doc=self._config("openai"))
        engine.extract(extract_keys=["Name"], full_text="Alice.", model="local-model")

        output_type = mock_agent_cls.call_args.kwargs["output_type"]
        assert not isinstance(output_type, NativeOutput)
        assert isinstance(output_type, type)


class TestSkippedDocumentTracking:
    """A document that contributes zero entities because its content could not
    be loaded used to be indistinguishable from "ran fine, zero matches" — the
    run completed green (#805). The engine now records which inputs it had to
    skip so callers can disclose them.
    """

    def _engine(self):
        from app.services.extraction_engine import ExtractionEngine

        return ExtractionEngine(system_config_doc={
            "available_models": [{"name": "m1", "multimodal": True}],
        })

    def test_empty_text_documents_are_recorded_and_skipped(self):
        from unittest.mock import patch

        engine = self._engine()
        with patch.object(engine, "_extract_document", return_value=[{"F": "v"}]) as ex:
            results = engine.extract(["F"], doc_texts=["real text", "", "   "], model="m1")
        assert engine.skipped_doc_indices == [1, 2]
        # The real document still extracted; no model call was spent on the
        # empty ones.
        assert ex.call_count == 1
        assert results == [{"F": "v"}]

    def test_image_mode_unloadable_file_with_no_text_is_recorded(self):
        from unittest.mock import patch

        engine = self._engine()
        with patch.object(engine, "_load_file_content", return_value=None), \
             patch.object(engine, "_extract_document", return_value=[]):
            engine.extract(
                ["F"], model="m1",
                doc_texts=["", "fallback text"],
                doc_file_paths=["/gone/a.pdf", "/gone/b.pdf"],
                extraction_config_override={"use_images": True},
            )
        # Doc 0: no image, no text -> skipped. Doc 1: fell back to text.
        assert engine.skipped_doc_indices == [0]

    def test_tracking_resets_between_calls(self):
        from unittest.mock import patch

        engine = self._engine()
        with patch.object(engine, "_extract_document", return_value=[]):
            engine.extract(["F"], doc_texts=[""], model="m1")
            assert engine.skipped_doc_indices == [0]
            engine.extract(["F"], doc_texts=["text"], model="m1")
        assert engine.skipped_doc_indices == []
