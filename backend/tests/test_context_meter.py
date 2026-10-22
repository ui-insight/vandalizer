"""Phase 2 of the agentic-chat harness uplift: usage-anchored estimation +
the context meter's warn/compact/block escalation ladder."""

import logging
import types

from app.services import context_budget
from app.services.chat_service import _final_request_context_tokens
from app.services.context_budget import (
    build_context_meter,
    estimate_next_request_tokens,
    METER_BLOCKED,
    METER_COMPACT,
    METER_OK,
    METER_WARNING,
    resolve_context_window,
    rough_text_tokens,
)


class TestResolveContextWindow:
    def test_config_value_wins(self):
        assert resolve_context_window("anything", {"context_window": 42_000}) == 42_000

    def test_claude_catch_all_matches_new_models(self):
        # Specific entries cover claude-3/4 families; the trailing catch-all
        # must cover newer names instead of falling to the 65k default.
        assert resolve_context_window("claude-fable-5") == 200_000
        assert resolve_context_window("anthropic/claude-sonnet-5") == 200_000

    def test_default_fallback_warns_once_per_model(self, caplog):
        context_budget._window_fallback_warned.discard("mystery/model-x")
        with caplog.at_level(logging.WARNING):
            first = resolve_context_window("mystery/model-x")
            second = resolve_context_window("mystery/model-x")
        assert first == second == context_budget.DEFAULT_CONTEXT_WINDOW
        assert caplog.text.count("No context_window configured") == 1


class TestEstimateNextRequestTokens:
    def test_anchor_plus_padded_delta(self):
        # 400 chars → 100 rough tokens → padded 4/3 → 133.
        est = estimate_next_request_tokens(anchor_tokens=50_000, new_text="x" * 400)
        assert est == 50_000 + 133

    def test_empty_delta_returns_anchor(self):
        assert estimate_next_request_tokens(anchor_tokens=1_234, new_text="") == 1_234

    def test_rough_text_tokens_floor(self):
        assert rough_text_tokens("") == 0
        assert rough_text_tokens("ab") == 1


class TestContextMeterLadder:
    def test_large_window_states_escalate(self):
        # 200k window, default reserve 8192 → effective 191,808.
        # warn at eff-20k, compact at eff-13k, block at eff-3k.
        window = 200_000
        effective = window - 8_192

        def state_at(tokens):
            return build_context_meter(
                estimated_tokens=tokens, context_window=window
            ).state

        assert state_at(100_000) == METER_OK
        assert state_at(effective - 20_000) == METER_WARNING
        assert state_at(effective - 13_000) == METER_COMPACT
        assert state_at(effective - 3_000) == METER_BLOCKED

    def test_small_window_uses_percentages(self):
        # 8k window: flat 20k/13k buffers would put every threshold below 0.
        window = 8_192
        meter = build_context_meter(estimated_tokens=0, context_window=window)
        assert 0 < meter.warn_threshold < meter.compact_threshold < meter.block_threshold
        assert meter.block_threshold <= meter.effective_window

    def test_huge_window_compact_buffer_scales(self):
        # 1M window → compact buffer is 6% (60k), not the flat 13k.
        meter = build_context_meter(estimated_tokens=0, context_window=1_000_000)
        assert meter.effective_window - meter.compact_threshold == 60_000
        assert meter.warn_threshold < meter.compact_threshold

    def test_percent_until_compact(self):
        meter = build_context_meter(estimated_tokens=0, context_window=200_000)
        assert meter.percent_until_compact == 100
        past = build_context_meter(
            estimated_tokens=meter.compact_threshold + 1, context_window=200_000
        )
        assert past.percent_until_compact == 0

    def test_to_dict_shape_matches_stream_contract(self):
        d = build_context_meter(
            estimated_tokens=10, context_window=200_000, estimate_source="usage_anchor"
        ).to_dict()
        assert d["state"] == METER_OK
        assert d["estimate_source"] == "usage_anchor"
        for key in (
            "estimated_tokens", "context_window", "effective_window",
            "warn_threshold", "compact_threshold", "block_threshold",
            "percent_until_compact",
        ):
            assert isinstance(d[key], int)


def _response(input_tokens=0, output_tokens=0, cache_read=0, cache_write=0):
    return types.SimpleNamespace(usage=types.SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    ))


def _request():
    # ModelRequest analogue: no usage attribute worth reading.
    return types.SimpleNamespace(usage=None)


class TestFinalRequestContextTokens:
    def _result(self, messages):
        return types.SimpleNamespace(new_messages=lambda: messages)

    def test_picks_the_last_response_not_the_run_total(self):
        # Tool loop: two requests. The anchor is the FINAL request's context
        # (30k), not the 50k sum a run aggregate would report.
        msgs = [
            _request(),
            _response(input_tokens=20_000, output_tokens=100),
            _request(),
            _response(input_tokens=2_000, cache_read=27_000, output_tokens=500),
        ]
        assert _final_request_context_tokens(self._result(msgs)) == 29_500

    def test_skips_trailing_zero_usage_responses(self):
        msgs = [
            _response(input_tokens=10_000, output_tokens=200),
            _response(),  # gateway reported nothing
        ]
        assert _final_request_context_tokens(self._result(msgs)) == 10_200

    def test_returns_zero_when_nothing_reported(self):
        assert _final_request_context_tokens(self._result([_request()])) == 0
        broken = types.SimpleNamespace()  # no new_messages at all
        assert _final_request_context_tokens(broken) == 0
