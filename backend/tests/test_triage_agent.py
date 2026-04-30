"""Tests for app.services.triage_agent.

The agent's LLM call is mocked — we only verify context assembly, the
caching behavior, and the pydantic result schema.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.triage_agent import (
    TriageResult,
    create_triage_agent,
    triage_work_item_sync,
)


class TestTriageResult:
    def test_minimal_valid_result_shape(self):
        result = TriageResult(
            category="transcript_request",
            confidence=0.9,
            summary="A request for an academic transcript.",
            suggested_action="process",
            reasoning="Subject line matches pattern",
        )
        assert result.category == "transcript_request"
        assert result.tags == []
        assert result.sensitivity_flags == []

    def test_confidence_bounds_enforced(self):
        with pytest.raises(Exception):
            TriageResult(
                category="c", confidence=1.5, summary="s",
                suggested_action="process", reasoning="r",
            )
        with pytest.raises(Exception):
            TriageResult(
                category="c", confidence=-0.1, summary="s",
                suggested_action="process", reasoning="r",
            )


class TestCreateTriageAgent:
    def test_agent_caching_returns_same_instance(self):
        with patch("app.services.triage_agent._triage_agent_cache", {}), \
             patch("app.services.triage_agent.get_agent_model") as mock_get_model, \
             patch("app.services.triage_agent.Agent") as MockAgent:
            mock_get_model.return_value = MagicMock()
            MockAgent.return_value = MagicMock(name="AgentInstance")

            first = create_triage_agent("gpt-4o")
            second = create_triage_agent("gpt-4o")

            assert first is second
            # Agent only constructed once because of caching
            assert MockAgent.call_count == 1

    def test_different_models_get_different_agents(self):
        with patch("app.services.triage_agent._triage_agent_cache", {}), \
             patch("app.services.triage_agent.get_agent_model") as mock_get_model, \
             patch("app.services.triage_agent.Agent") as MockAgent:
            mock_get_model.return_value = MagicMock()
            MockAgent.side_effect = lambda *a, **kw: MagicMock(name=kw.get("_id", "x"))

            a = create_triage_agent("gpt-4o")
            b = create_triage_agent("claude-opus")

            assert a is not b
            assert MockAgent.call_count == 2


class TestTriageWorkItemSync:
    def _work_item(self, **overrides) -> dict:
        base = {
            "source": "email",
            "subject": "Request for transcript",
            "sender_name": "Jane Smith",
            "sender_email": "jane@example.edu",
            "received_at": "2026-03-01",
            "body_text": "Please send my official transcript.",
            "attachment_count": 0,
        }
        base.update(overrides)
        return base

    def _expected_output(self) -> TriageResult:
        return TriageResult(
            category="transcript_request",
            confidence=0.92,
            summary="Student asking for a transcript.",
            suggested_action="process",
            reasoning="Clear subject and body match the transcript_request pattern.",
        )

    def test_uses_provided_model_name_directly(self):
        agent = MagicMock()
        expected = self._expected_output()
        agent.run_sync.return_value = MagicMock(output=expected)

        with patch("app.services.triage_agent.create_triage_agent", return_value=agent) as mk:
            result = triage_work_item_sync(self._work_item(), model_name="gpt-4o")

        mk.assert_called_once_with("gpt-4o")
        assert result is expected
        # The context passed to the agent should include the subject and body.
        context = agent.run_sync.call_args.args[0]
        assert "Request for transcript" in context
        assert "Please send my official transcript." in context

    def test_resolves_model_from_system_config_when_missing(self):
        agent = MagicMock()
        agent.run_sync.return_value = MagicMock(output=self._expected_output())

        sys_cfg = {"available_models": [{"name": "claude-sonnet"}]}

        with patch("app.services.triage_agent.create_triage_agent", return_value=agent) as mk:
            triage_work_item_sync(self._work_item(), system_config_doc=sys_cfg)

        mk.assert_called_once_with("claude-sonnet")

    def test_missing_subject_renders_placeholder(self):
        agent = MagicMock()
        agent.run_sync.return_value = MagicMock(output=self._expected_output())

        with patch("app.services.triage_agent.create_triage_agent", return_value=agent):
            triage_work_item_sync(
                self._work_item(subject=""),
                model_name="m",
            )

        context = agent.run_sync.call_args.args[0]
        assert "(no subject)" in context

    def test_long_body_truncated_to_5000_chars(self):
        agent = MagicMock()
        agent.run_sync.return_value = MagicMock(output=self._expected_output())
        # Use a marker unlikely to appear elsewhere in the envelope.
        big_body = "ZZ" * 3000  # 6000 chars total

        with patch("app.services.triage_agent.create_triage_agent", return_value=agent):
            triage_work_item_sync(
                self._work_item(body_text=big_body),
                model_name="m",
            )

        context = agent.run_sync.call_args.args[0]
        z_count = context.count("Z")
        # Context should contain at most 5000 chars of the body, not all 6000.
        assert z_count <= 5000
        assert z_count > 0  # body made it in at all
