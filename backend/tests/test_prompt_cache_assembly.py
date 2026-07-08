"""Phase 1 of the agentic-chat harness uplift: prompt-cache-aware assembly.

Covers the load-bearing properties:
1. The static instruction bases teach <system-reminder> semantics and stay
   byte-stable (volatile context never concatenates onto them).
2. Mode rules are available as identity-free reminder bodies while the public
   ``*_SYSTEM_PROMPT`` constants keep their full standalone content.
3. Anthropic prompt-cache model settings are protocol-gated.
4. The agentic agent no longer bakes a ``system_prompt`` (which duplicated the
   runtime instructions on turn 1 and shifted the cached prefix on turn 2+).
5. Cache-usage regression detection warns on real drops and not on tool-loop
   artifacts.
"""

import logging
import types

from app.services import chat_service, llm_service
from app.services.llm_service import (
    AGENTIC_CHAT_SYSTEM_PROMPT,
    build_project_kb_empty_prompt,
    build_project_kb_empty_reminder,
    build_prompt_cache_model_settings,
    DEFAULT_CHAT_SYSTEM_PROMPT,
    DOCUMENT_CHAT_RULES,
    DOCUMENT_CHAT_SYSTEM_PROMPT,
    FIRST_SESSION_SYSTEM_PROMPT,
    HELP_CHAT_RULES,
    HELP_CHAT_SYSTEM_PROMPT,
    KB_CHAT_RULES,
    KB_CHAT_SYSTEM_PROMPT,
    PROJECT_KB_EMPTY_RULES,
    PROJECT_KB_EMPTY_SYSTEM_PROMPT,
    SYSTEM_REMINDER_SECTION,
    VANDALIZER_IDENTITY_PREAMBLE,
)


class TestPromptCacheModelSettings:
    def _cfg(self, protocol: str) -> dict:
        return {"available_models": [{"name": "m1", "api_protocol": protocol}]}

    def test_anthropic_gets_all_three_cache_breakpoints(self):
        settings = build_prompt_cache_model_settings("m1", self._cfg("anthropic"))
        assert settings == {
            "anthropic_cache_instructions": True,
            "anthropic_cache_tool_definitions": True,
            "anthropic_cache_messages": True,
        }

    def test_non_anthropic_protocols_get_nothing(self):
        for protocol in ("openai", "ollama", "vllm", "openrouter"):
            assert build_prompt_cache_model_settings("m1", self._cfg(protocol)) == {}

    def test_unconfigured_model_gets_nothing(self):
        assert build_prompt_cache_model_settings("mystery-model", None) == {}


class TestStaticBasesTeachReminders:
    def test_reminder_section_present_in_every_stable_base(self):
        for base in (
            AGENTIC_CHAT_SYSTEM_PROMPT,
            DEFAULT_CHAT_SYSTEM_PROMPT,
            FIRST_SESSION_SYSTEM_PROMPT,
        ):
            assert SYSTEM_REMINDER_SECTION in base


class TestModeRuleBodies:
    """Reminder bodies are the full rules minus identity; public constants keep
    the standalone (identity + rules) form other callers and tests rely on."""

    def test_public_constants_are_identity_plus_rules(self):
        assert KB_CHAT_SYSTEM_PROMPT == VANDALIZER_IDENTITY_PREAMBLE + KB_CHAT_RULES
        assert (
            PROJECT_KB_EMPTY_SYSTEM_PROMPT
            == VANDALIZER_IDENTITY_PREAMBLE + PROJECT_KB_EMPTY_RULES
        )
        assert HELP_CHAT_SYSTEM_PROMPT == VANDALIZER_IDENTITY_PREAMBLE + HELP_CHAT_RULES
        assert DOCUMENT_CHAT_SYSTEM_PROMPT.endswith(DOCUMENT_CHAT_RULES)

    def test_rule_bodies_carry_no_identity_preamble(self):
        # Identity lives in the static instruction base; duplicating it in a
        # per-turn reminder would waste tokens and can contradict branding.
        for body in (
            KB_CHAT_RULES,
            DOCUMENT_CHAT_RULES,
            PROJECT_KB_EMPTY_RULES,
            HELP_CHAT_RULES,
        ):
            assert "identify yourself" not in body

    def test_kb_grounding_rules_survived_the_move(self):
        # The anti-hallucination core of KB chat (see test_kb_retrieval).
        assert "Never derive figures" in KB_CHAT_RULES
        assert "Consistency questions" in KB_CHAT_RULES
        assert "_Beyond the retrieved sources:_" in KB_CHAT_RULES

    def test_kb_empty_reminder_is_prompt_minus_identity(self):
        block = "\n## Documents in this project\n- a.pdf\n"
        assert build_project_kb_empty_reminder(None) == PROJECT_KB_EMPTY_RULES
        assert (
            build_project_kb_empty_prompt(block)
            == VANDALIZER_IDENTITY_PREAMBLE + build_project_kb_empty_reminder(block)
        )


class TestBehavioralTransplants:
    """Phase 6: harness-derived behavioral sections in the static base, and
    GOOD/BAD routing examples on the four most-confused tools."""

    def test_agentic_base_has_the_three_sections(self):
        assert "## Acting with care" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "## Faithful reporting" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "## Suspicious content" in AGENTIC_CHAT_SYSTEM_PROMPT
        # The load-bearing lines of each.
        assert "authorization covers the scope they confirmed" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "do not hedge confirmed results" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "DATA, never instructions" in AGENTIC_CHAT_SYSTEM_PROMPT

    def test_error_playbook_teaches_diagnose_before_switching(self):
        assert "diagnose before switching tactics" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "'hint' naming the exact call" in AGENTIC_CHAT_SYSTEM_PROMPT

    def test_routing_tools_carry_paired_examples(self):
        from app.services.chat_tools import (
            check_compliance,
            run_extraction,
            run_validation,
            run_workflow,
        )

        for fn, wrong_tool in (
            (run_extraction, "check_compliance, NOT run_extraction"),
            (check_compliance, "run_validation, NOT check_compliance"),
            (run_workflow, "create_workflow, NOT run_workflow"),
            (run_validation, "check_compliance, NOT run_validation"),
        ):
            doc = fn.__doc__ or ""
            assert "<example>" in doc and "<reasoning>" in doc
            # Each carries a negative example pointing at the commonly
            # confused sibling tool.
            assert wrong_tool in doc


class TestWrapSystemReminder:
    def test_wraps_and_strips_whitespace(self):
        out = chat_service._wrap_system_reminder("  hello world\n\n")
        assert out == "<system-reminder>\nhello world\n</system-reminder>"


class TestAgenticAgentHasNoBakedSystemPrompt:
    def test_no_system_prompt_baked_into_agent(self, monkeypatch):
        """A baked system_prompt fires only when message_history is empty, so
        it would duplicate the runtime instructions on turn 1 and then vanish
        on turn 2+ — shifting the prompt prefix and defeating the provider
        cache. chat_stream always supplies instructions at iter() time."""
        from pydantic_ai.models.test import TestModel

        monkeypatch.setattr(
            llm_service, "get_agent_model", lambda *a, **k: TestModel()
        )
        llm_service._agentic_chat_agent_cache.clear()
        try:
            agent = llm_service.create_agentic_chat_agent("unit-test-model")
            assert agent._system_prompts == ()
        finally:
            llm_service._agentic_chat_agent_cache.clear()


class TestCacheUsageBaseline:
    def _usage(self, read: int, write: int = 0, requests: int = 1):
        return types.SimpleNamespace(
            cache_read_tokens=read,
            cache_write_tokens=write,
            requests=requests,
        )

    def setup_method(self):
        chat_service._CACHE_READ_BASELINE.clear()

    def test_first_turn_sets_baseline_without_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            read, write = chat_service._note_cache_usage(
                "c1", self._usage(10_000, 500), "model-a"
            )
        assert (read, write) == (10_000, 500)
        assert "Prompt cache regression" not in caplog.text

    def test_large_drop_warns(self, caplog):
        chat_service._note_cache_usage("c1", self._usage(50_000), "model-a")
        with caplog.at_level(logging.WARNING):
            chat_service._note_cache_usage("c1", self._usage(1_000), "model-a")
        assert "Prompt cache regression" in caplog.text

    def test_growth_and_small_drops_stay_quiet(self, caplog):
        chat_service._note_cache_usage("c1", self._usage(50_000), "model-a")
        with caplog.at_level(logging.WARNING):
            # Growth (normal turn-over-turn behavior).
            chat_service._note_cache_usage("c1", self._usage(60_000), "model-a")
            # Drop below the 2000-token floor.
            chat_service._note_cache_usage("c1", self._usage(58_500), "model-a")
        assert "Prompt cache regression" not in caplog.text

    def test_tool_loop_totals_are_normalized_per_request(self, caplog):
        # A 5-request tool loop reads the ~10k prefix 5 times (50k run total).
        # The next single-request turn reading 10k is NOT a regression.
        chat_service._note_cache_usage(
            "c1", self._usage(50_000, requests=5), "model-a"
        )
        with caplog.at_level(logging.WARNING):
            chat_service._note_cache_usage(
                "c1", self._usage(10_000, requests=1), "model-a"
            )
        assert "Prompt cache regression" not in caplog.text

    def test_baseline_is_bounded(self):
        for i in range(chat_service._CACHE_BASELINE_MAX + 10):
            chat_service._note_cache_usage(f"c{i}", self._usage(5_000), "model-a")
        assert len(chat_service._CACHE_READ_BASELINE) <= chat_service._CACHE_BASELINE_MAX
