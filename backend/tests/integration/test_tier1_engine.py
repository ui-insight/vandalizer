"""Tier 1 integration tests — no external services required.

These call real production code paths — field sanitization, create_model,
ExtractionModel validation, Celery eager dispatch, and ThreadPoolExecutor
parallel execution. Only the LLM call (Agent.run_sync) is mocked.
"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration_tier1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockResult:
    """Mimics a pydantic-ai RunResult with no usage data."""

    def __init__(self, output):
        self.output = output

    def usage(self):
        raise AttributeError


def _mock_agent_cls(raw_llm_response):
    """Return a mock Agent class that validates raw_llm_response through the
    real output_type (ExtractionModel), exactly as pydantic-ai would.

    Everything upstream of the LLM call — field sanitization, create_model,
    ExtractionModel with coerce_entities validator — runs for real.
    """

    class _MockAgent:
        def __init__(self, model, **kwargs):
            self._output_type = kwargs.get("output_type")

        def run_sync(self, prompt, **kwargs):
            validated = self._output_type.model_validate(raw_llm_response)
            return _MockResult(validated)

    return _MockAgent


def _run_extract(keys, raw_response, meta_map=None):
    """Call the real ExtractionEngine._extract_structured with only Agent mocked."""
    from app.services.extraction_engine import ExtractionEngine

    MockAgent = _mock_agent_cls(raw_response)
    with patch("app.services.extraction_engine.Agent", MockAgent):
        engine = ExtractionEngine(system_config_doc={})
        return engine._extract_structured(
            content="Test document text.",
            keys=keys,
            model_name="test-model",
            meta_map=meta_map,
        )


# ---------------------------------------------------------------------------
# 1. _extract_structured with special characters and field dedup
# ---------------------------------------------------------------------------

class TestExtractStructuredSpecialChars:
    """Call the real _extract_structured pipeline — field sanitization,
    create_model with aliases, model_dump(by_alias=True)."""

    def test_special_chars_and_dedup(self):
        result = _run_extract(
            keys=["PI Name", "Cost ($)", "Field", "Field"],
            raw_response=[{"PI Name": "Alice", "Cost ($)": "$50k", "Field": "val"}],
        )
        assert len(result) == 1
        assert result[0]["PI Name"] == "Alice"
        assert result[0]["Cost ($)"] == "$50k"
        assert result[0]["Field"] == "val"

    def test_digit_prefixed_key_raises(self):
        """Digit-prefixed keys cause NameError in create_model. This
        propagates because create_model is outside the try/except."""
        from app.services.extraction_engine import ExtractionEngine

        with pytest.raises(NameError, match="leading underscores"):
            ExtractionEngine(system_config_doc={})._extract_structured(
                content="text",
                keys=["123 Field"],
                model_name="test-model",
            )


# ---------------------------------------------------------------------------
# 2. _extract_structured with enum / Literal constraints
# ---------------------------------------------------------------------------

class TestExtractStructuredEnum:
    """Verify Optional[Literal[tuple(enum_vals)]] works end-to-end through
    the real _extract_structured pipeline."""

    def test_enum_accepted(self):
        result = _run_extract(
            keys=["Status"],
            raw_response=[{"Status": "Active"}],
            meta_map={"Status": {"enum_values": ["Active", "Inactive"]}},
        )
        assert result[0]["Status"] == "Active"

    def test_enum_rejected_triggers_fallback(self):
        """Invalid enum value causes ValidationError inside run_sync.
        _extract_structured catches it and falls back to _extract_fallback_json."""
        from app.services.extraction_engine import ExtractionEngine

        # Agent whose run_sync always raises ValidationError (bad enum)
        BadAgent = _mock_agent_cls([{"Status": "Unknown"}])

        # Mock the fallback path to avoid a real LLM call
        mock_chat = MagicMock()
        mock_chat.run_sync.return_value = MagicMock(output='[{"Status": "Active"}]')

        with patch("app.services.extraction_engine.Agent", BadAgent), \
             patch("app.services.extraction_engine.create_chat_agent", return_value=mock_chat):
            engine = ExtractionEngine(system_config_doc={})
            result = engine._extract_structured(
                content="The project is active.",
                keys=["Status"],
                model_name="test-model",
                meta_map={"Status": {"enum_values": ["Active", "Inactive"]}},
            )
            # Falls back to _extract_fallback_json which returns the mock result
            assert isinstance(result, list)
            assert len(result) >= 1


# ---------------------------------------------------------------------------
# 3. coerce_entities through _extract_structured with various LLM shapes
# ---------------------------------------------------------------------------

class TestCoerceEntitiesViaExtractStructured:
    """Pass different raw LLM response shapes through the real
    _extract_structured pipeline. The coerce_entities model_validator
    normalizes each shape before Pydantic validates."""

    def test_coerce_from_list(self):
        """LLM returns a list of entities (most common)."""
        result = _run_extract(
            keys=["Name"],
            raw_response=[{"Name": "Alice"}],
        )
        assert result[0]["Name"] == "Alice"

    def test_coerce_from_bare_dict(self):
        """LLM returns a bare dict — coerced to [dict]."""
        result = _run_extract(
            keys=["Name"],
            raw_response={"Name": "Alice"},
        )
        assert result[0]["Name"] == "Alice"

    def test_coerce_from_json_string(self):
        """LLM returns a JSON string — parsed, then coerced."""
        result = _run_extract(
            keys=["Name"],
            raw_response='{"Name": "Alice"}',
        )
        assert result[0]["Name"] == "Alice"

    def test_coerce_entities_as_single_dict(self):
        """LLM returns {"entities": {single}} — coerced to [dict]."""
        result = _run_extract(
            keys=["Name"],
            raw_response={"entities": {"Name": "Alice"}},
        )
        assert result[0]["Name"] == "Alice"

    def test_coerce_entities_as_list(self):
        """LLM returns {"entities": [multiple]}."""
        result = _run_extract(
            keys=["Name"],
            raw_response={"entities": [{"Name": "Alice"}, {"Name": "Bob"}]},
        )
        assert len(result) == 2

    def test_empty_entities_filtered(self):
        """Entities with all-null values are filtered out by _filter_empty_entities."""
        result = _run_extract(
            keys=["Name", "Age"],
            raw_response=[{"Name": None, "Age": None}, {"Name": "Alice", "Age": "30"}],
        )
        assert len(result) == 1
        assert result[0]["Name"] == "Alice"


# ---------------------------------------------------------------------------
# 4. Celery eager dispatch
# ---------------------------------------------------------------------------

class TestCeleryEagerDispatch:
    """Verify Celery task decorator configuration (bind=True, autoretry_for)
    works under eager mode with .delay() dispatch."""

    def test_celery_eager_dispatch(self, celery_eager):
        from bson import ObjectId
        from app.tasks.workflow_tasks import execute_workflow_task

        wf_oid = ObjectId()
        wr_oid = ObjectId()

        mock_db = MagicMock()
        mock_db.workflow.find_one.return_value = {
            "_id": wf_oid,
            "steps": [],
            "user_id": "user1",
        }
        mock_db.workflow_result.find_one.return_value = {
            "_id": wr_oid,
            "status": "running",
        }
        mock_db.system_config.find_one.return_value = {}

        mock_engine = MagicMock()
        mock_engine.execute.return_value = ("Final output", [])
        mock_engine.usage = MagicMock(tokens_in=10, tokens_out=5)

        with patch("app.tasks.workflow_tasks._get_db", return_value=mock_db), \
             patch("app.services.workflow_engine.build_workflow_engine", return_value=mock_engine), \
             patch("app.tasks.quality_tasks.auto_validate_workflow") as mock_auto_val:
            mock_auto_val.delay = MagicMock()
            result = execute_workflow_task.delay(
                str(wr_oid), str(wf_oid), {"doc_uuids": ["doc1"]}, "test-model"
            )

            # In eager mode, .delay() executes synchronously
            assert result.successful()
            assert result.result["status"] == "completed"
            mock_engine.execute.assert_called_once()


# ---------------------------------------------------------------------------
# 5. Real engine with parallel tasks via ThreadPoolExecutor
# ---------------------------------------------------------------------------

class TestRealEngineParallel:
    """Use build_workflow_engine with AddDocument tasks that run in parallel
    through a real ThreadPoolExecutor."""

    def test_parallel_add_document_tasks(self):
        from app.services.workflow_engine import build_workflow_engine, UsageAccumulator

        steps_data = [
            {
                "name": "Document",
                "data": {"doc_uuids": ["doc1", "doc2"]},
                "tasks": [],
            },
            {
                "name": "Step1",
                "data": {},
                "tasks": [
                    {"name": "AddDocument", "data": {"doc_texts": ["Text from doc A"]}},
                    {"name": "AddDocument", "data": {"doc_texts": ["Text from doc B"]}},
                ],
            },
        ]

        engine = build_workflow_engine(
            steps_data=steps_data,
            model="test-model",
            user_id="test_user",
            system_config_doc={},
        )

        final_output, step_data = engine.execute()

        assert len(step_data) == 2  # Document + Step1
        step1_output = step_data[1]["output"]
        assert step1_output is not None
        # Two AddDocument tasks → collected as list
        if isinstance(step1_output, list):
            assert len(step1_output) == 2

        assert isinstance(engine.usage, UsageAccumulator)
        assert engine.usage.tokens_in >= 0

    def test_usage_accumulator_thread_safety(self):
        from app.services.workflow_engine import UsageAccumulator

        acc = UsageAccumulator()
        num_threads = 50
        adds_per_thread = 100

        def worker():
            for _ in range(adds_per_thread):
                acc.add(1, 2)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert acc.tokens_in == num_threads * adds_per_thread
        assert acc.tokens_out == num_threads * adds_per_thread * 2
