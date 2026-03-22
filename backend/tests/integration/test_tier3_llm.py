"""Tier 3 integration tests — requires a configured LLM.

These validate that prompts produce parseable output with a real LLM.
Assertions are generous (non-null, expected keys) not exact-match.

Configuration via environment variables:
    INTEGRATION_LLM=1           Gate flag (required to run these tests)
    INTEGRATION_LLM_MODEL       Model name as registered in system config
    INTEGRATION_LLM_API_KEY     API key for the model
    INTEGRATION_LLM_ENDPOINT    API endpoint URL (optional — omit for OpenAI-hosted models)
    INTEGRATION_LLM_PROTOCOL    API protocol: openai|ollama|vllm (default: openai)
"""

import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_LLM"),
        reason="Set INTEGRATION_LLM=1 (plus INTEGRATION_LLM_MODEL, INTEGRATION_LLM_API_KEY) to run LLM integration tests",
    ),
    pytest.mark.integration_tier3,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm_model() -> str:
    return os.environ.get("INTEGRATION_LLM_MODEL", "gpt-4o-mini")


def _system_config_doc() -> dict:
    """Build a minimal system_config_doc that mirrors what SystemConfig
    stores in MongoDB, using env-var overrides for the test model."""
    model_name = _llm_model()
    api_key = os.environ.get("INTEGRATION_LLM_API_KEY", "")
    endpoint = os.environ.get("INTEGRATION_LLM_ENDPOINT", "")
    protocol = os.environ.get("INTEGRATION_LLM_PROTOCOL", "openai")

    model_entry: dict = {"name": model_name, "api_key": api_key, "api_protocol": protocol}
    if endpoint:
        model_entry["endpoint"] = endpoint

    return {
        "available_models": [model_entry],
        "llm_endpoint": endpoint,
    }


# ---------------------------------------------------------------------------
# 1. Full structured extraction pipeline
# ---------------------------------------------------------------------------

class TestExtractionStructuredReal:
    """Exercise _extract_structured with a real LLM call."""

    def test_extraction_structured_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        result = engine._extract_structured(
            content="Alice is 30 years old and works at Acme Corp.",
            keys=["Name", "Age", "Company"],
            model_name=_llm_model(),
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert isinstance(entity, dict)
        # All keys present with non-null values
        for key in ["Name", "Age", "Company"]:
            assert key in entity, f"Missing key: {key}"
            assert entity[key] is not None, f"Null value for: {key}"


# ---------------------------------------------------------------------------
# 2. Fallback JSON extraction pipeline
# ---------------------------------------------------------------------------

class TestExtractionFallbackJsonReal:
    """Exercise _extract_fallback_json with a real LLM call."""

    def test_extraction_fallback_json_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        result = engine._extract_fallback_json(
            content="Bob is 25 years old and works at Globex.",
            keys=["Name", "Age", "Company"],
            model_name=_llm_model(),
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert isinstance(entity, dict)
        for key in ["Name", "Age", "Company"]:
            assert key in entity, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 3. PromptNode with real LLM
# ---------------------------------------------------------------------------

class TestPromptNodeReal:
    """Exercise PromptNode.process() with a real LLM call."""

    def test_prompt_node_real(self):
        from app.services.workflow_engine import PromptNode

        sys_cfg = _system_config_doc()
        node = PromptNode(data={
            "prompt": "Respond with exactly one word: the color of grass.",
            "model": _llm_model(),
        })
        node._sys_cfg = sys_cfg

        output = node.process({"output": None, "step_name": "test"})

        assert output is not None
        assert isinstance(output["output"], (str, dict))
        # Should be a non-empty response
        if isinstance(output["output"], str):
            assert len(output["output"].strip()) > 0
        elif isinstance(output["output"], dict):
            answer = output["output"].get("answer", output["output"].get("formatted_answer", ""))
            assert len(str(answer).strip()) > 0


# ---------------------------------------------------------------------------
# 4. Extraction with enum constraint
# ---------------------------------------------------------------------------

class TestExtractionEnumConstraintReal:
    """Verify Literal enum constraints propagate to the LLM and
    the response respects them."""

    def test_extraction_enum_constraint_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        meta_map = {"Status": {"enum_values": ["Active", "Inactive"]}}

        result = engine._extract_structured(
            content="The project is currently active and running smoothly.",
            keys=["Status"],
            model_name=_llm_model(),
            meta_map=meta_map,
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert "Status" in entity
        assert entity["Status"] in ("Active", "Inactive"), \
            f"Expected Active or Inactive, got: {entity['Status']}"
