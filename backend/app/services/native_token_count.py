"""Ask the provider how many tokens a prompt is, or say plainly that we can't.

`context_budget` plans with tiktoken and inflates the result by
``DEFAULT_TOKEN_SAFETY_MARGIN`` (1.5) for every model whose real vocabulary is
not on disk — which is every hosted API. That margin is sized to cover the
densest content measured, so a hosted model answering flowing prose plans
against a third less window than it actually has.

Anthropic and Google publish exact counts for a prepared request. This module
fetches one. Two properties matter, and they are not the same property:

* When a figure is returned it is the provider's own, unmodified.
* When anything at all goes wrong, **nothing** is returned.

The second is the load-bearing one. The caller drops its safety margin on the
strength of a usable result, so a count that comes back zero, short, or from a
provider that only counted half the request is worse than no count at all — it
converts a conservative over-estimate into a confident under-estimate, which is
the direction that hard-fails a request. Hence: fail closed, never raise, and
report *why* in `source` rather than returning a plausible number.

Two asymmetries between the providers are baked into the result:

* Anthropic's count includes the system prompt — ``_messages_count_tokens``
  sends ``system=`` (pydantic_ai/models/anthropic.py).
* Google's does **not**. ``pydantic_ai/models/google.py`` attaches
  ``system_instruction`` to the count config only when the provider is not
  ``google-gla``, and ``GoogleProvider(api_key=...)`` *is* ``google-gla``. So a
  Gemini count silently omits the instructions — for KB chat, a multi-kilobyte
  grounding preamble. `covers_system_prompt` says so; the caller must add its
  own allowance when it is False.
"""

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.services.context_budget import (
    NativeCount,
    count_message_tokens,
    count_raw_tokens,
)
from app.services.llm_service import (
    build_thinking_model_settings,
    detect_api_protocol,
    get_agent_model,
    get_model_api_protocol,
)

logger = logging.getLogger(__name__)


# How long the pre-flight may take before it is abandoned.
#
# This runs in front of the first token of a chat response, so its budget is a
# latency budget, not a reliability one: a count that arrives late is worthless
# even when it arrives correct. Deliberately *not* the settings the real request
# uses — `build_thinking_model_settings` sets timeout=120, and the shared httpx
# client's `RateLimitRetryTransport` retries a 429 six times honouring
# Retry-After up to 60s. Inheriting either would put a two-minute stall in front
# of every message to save a fraction of a context window.
#
# Read at call time, so tests and any future config plumbing can override it.
NATIVE_COUNT_TIMEOUT_SECONDS = 5.0

# Protocol -> whether that provider's count includes the system prompt. Doubles
# as the eligibility gate: a protocol absent from this mapping cannot count, and
# is rejected before anything is built. `OpenAIModel.count_tokens` raises
# NotImplementedError, so without the gate every OpenAI-compatible model would
# construct a provider client (decrypting an API key on the way) on every single
# chat turn purely to learn that.
_COUNTABLE_PROTOCOLS: dict[str, bool] = {
    "anthropic": True,
    "google": False,
}

# Models whose count has already failed loudly, so a persistent failure reports
# once per process rather than once per chat turn. Same rationale and same shape
# as `token_estimate_check._log_failure_once` and
# `context_budget._warn_estimated_once`.
_UNAVAILABLE_LOGGED: set[str] = set()

# How many consecutive failures before a model stops being asked, and for how
# long. `_UNAVAILABLE_LOGGED` above coalesces the *log*; this coalesces the
# *work*, which is the part that costs a user their time.
NATIVE_COUNT_FAILURE_THRESHOLD = 3
NATIVE_COUNT_COOLDOWN_SECONDS = 300.0

# model name -> (consecutive failures, monotonic deadline until which to skip)
_CIRCUIT: dict[str, tuple[int, float]] = {}


def _circuit_open(model_name: str) -> bool:
    """Whether this model is in cooldown after repeated count failures.

    Without this the module retries forever: a deployment whose egress to the
    count endpoint is slow, or whose org is rate-limited there, pays the full
    timeout on *every* chat turn, ahead of the first token, indefinitely — and
    after the first occurrence it says so only at DEBUG. The estimate path it
    falls back to is the one that shipped before this feature, so skipping is
    strictly better than blocking: same budget, no added latency.

    Monotonic, so a clock adjustment cannot strand a model in cooldown.
    """
    state = _CIRCUIT.get(model_name)
    if state is None:
        return False
    failures, until = state
    if failures < NATIVE_COUNT_FAILURE_THRESHOLD:
        return False
    if time.monotonic() >= until:
        # Cooldown elapsed: let exactly one request through to re-test the
        # provider. It either succeeds and resets, or fails and re-arms.
        _CIRCUIT[model_name] = (NATIVE_COUNT_FAILURE_THRESHOLD - 1, 0.0)
        return False
    return True


def _record_failure(model_name: str) -> None:
    failures = _CIRCUIT.get(model_name, (0, 0.0))[0] + 1
    _CIRCUIT[model_name] = (failures, time.monotonic() + NATIVE_COUNT_COOLDOWN_SECONDS)
    if failures == NATIVE_COUNT_FAILURE_THRESHOLD:
        logger.warning(
            "native token count for %s failed %d times in a row; pausing it for "
            "%.0fs and using the estimated budget meanwhile",
            model_name, failures, NATIVE_COUNT_COOLDOWN_SECONDS,
        )


def _record_success(model_name: str) -> None:
    """A working provider clears the record, so an outage does not leave a
    model one failure away from a cooldown for the life of the process."""
    _CIRCUIT.pop(model_name, None)
    _UNAVAILABLE_LOGGED.discard(model_name)


@dataclass(frozen=True)
class NativeCountResult:
    """A provider's token count, or the reason there isn't one.

    Frozen because the caller makes a budgeting decision from it: the provider's
    figure should not be editable in place on its way there.
    """

    tokens: Optional[int]
    covers_system_prompt: bool
    source: str  # "anthropic" | "google" | "unavailable:<short reason>"

    @property
    def usable(self) -> bool:
        """Whether this result may be used in place of an estimate.

        ``> 0``, not ``is not None``: a provider that reports zero has told us
        nothing, and a caller reading zero as a measurement would conclude the
        prompt is free and drop its margin on that basis.
        """
        return self.tokens is not None and self.tokens > 0


def _unavailable(reason: str) -> NativeCountResult:
    """No count, and `covers_system_prompt` is False so a caller that ignores
    `usable` still errs toward adding an allowance rather than omitting one."""
    return NativeCountResult(
        tokens=None, covers_system_prompt=False, source=f"unavailable:{reason}"
    )


def _log_unavailable_once(model_name: str, reason: str, *, exc_info: bool = False) -> None:
    """Report a failed count once per model per process.

    The failures reaching here are systemic — a misconfigured ``api_protocol``,
    an expired key, a provider that is down — so they say the same thing on
    every chat turn, indefinitely. Loud once, DEBUG thereafter; the state resets
    on restart, so a deploy or a config change is visible again.

    The traceback is kept on both branches when there is one: the DEBUG line is
    the only record of occurrences two onward, and a repeat that is a *different*
    exception is exactly what a bare "already reported" would hide.

    Deliberately not called for an ineligible protocol. Most deployments are
    OpenAI-compatible, where "cannot count natively" is the normal answer, not a
    fault — logging it would be a line per chat turn describing correct
    behaviour.
    """
    first_time = model_name not in _UNAVAILABLE_LOGGED
    _UNAVAILABLE_LOGGED.add(model_name)
    log = logger.warning if first_time else logger.debug
    log(
        "no native token count for %s (%s); falling back to the estimated "
        "budget and its safety margin",
        model_name, reason, exc_info=exc_info,
    )


def _token_count(usage: Any) -> Optional[int]:
    """Read `input_tokens` off a RequestUsage, or None if it is not a count.

    Everything that is not a positive, genuinely integral count is rejected:
    a missing attribute, ``None``, zero, a negative, a numeric string, and
    ``bool`` — which passes ``isinstance(x, int)`` in Python, so ``True`` would
    otherwise arrive as a count of 1.
    """
    tokens = getattr(usage, "input_tokens", None)
    if isinstance(tokens, bool) or not isinstance(tokens, int):
        return None
    return tokens if tokens > 0 else None


def _protocol_for(
    model_name: str, model_config: Optional[dict], system_config_doc: Optional[dict]
) -> str:
    """Resolve the API protocol without touching the network.

    Prefers a model config the caller already holds — `token_safety_margin`
    takes the same dict, so the caller on this path usually has it — which makes
    the admin's explicit ``api_protocol`` authoritative and skips a second scan
    of ``available_models``. Both branches end in the same
    `detect_api_protocol`, so they cannot disagree.
    """
    if model_config is not None:
        return detect_api_protocol(model_name, model_config)
    return get_model_api_protocol(model_name, system_config_doc)


async def count_natively(
    *,
    model_name: str,
    model_config: Optional[dict],
    system_config_doc: Optional[dict],
    system_prompt: str,
    user_message: str,
    history: list,
) -> NativeCountResult:
    """Return the provider's own count for this request, or an unusable result.

    Never raises. Never blocks longer than `NATIVE_COUNT_TIMEOUT_SECONDS`. Costs
    nothing at all — no model construction, no key decryption, no request — for
    a model whose provider cannot count.

    ``history`` is not mutated: it is the caller's live chat history, and
    appending this turn in place would leave a duplicate user message in the
    real request that follows.
    """
    try:
        protocol = _protocol_for(model_name, model_config, system_config_doc)
    except Exception:
        # The gate is code, and code raises. A traceback out of the config
        # lookup must read as "no native count", not as a failed chat request.
        _log_unavailable_once(model_name, "protocol lookup failed", exc_info=True)
        return _unavailable("protocol-lookup-failed")

    if protocol not in _COUNTABLE_PROTOCOLS:
        return _unavailable(f"protocol-{protocol}")

    # Checked after the protocol gate so an ineligible model never enters the
    # circuit at all, and before any model construction, key decryption or
    # request: while open this must cost nothing.
    if _circuit_open(model_name):
        return _unavailable("circuit-open")

    covers_system_prompt = _COUNTABLE_PROTOCOLS[protocol]

    try:
        async with asyncio.timeout(NATIVE_COUNT_TIMEOUT_SECONDS):
            usage = await _ask_provider(
                model_name=model_name,
                system_config_doc=system_config_doc,
                system_prompt=system_prompt,
                user_message=user_message,
                history=history,
            )
    except (asyncio.TimeoutError, TimeoutError):
        # Ahead of TimeoutError's own base class, and ahead of the blanket
        # handler, which would otherwise report it as an opaque failure.
        _log_unavailable_once(
            model_name, f"timed out after {NATIVE_COUNT_TIMEOUT_SECONDS}s"
        )
        _record_failure(model_name)
        return _unavailable("timeout")
    except Exception as exc:
        # Blanket by necessity, not by laziness. Anthropic surfaces
        # ModelHTTPError / ModelAPIError; Google's `google.genai` errors are not
        # wrapped by pydantic-ai at all and propagate raw, alongside
        # UnexpectedModelBehavior; a misconfigured api_protocol reaches
        # OpenAIModel and gets NotImplementedError. There is no union of types
        # here that is both complete and stable, and anything missed from it
        # would surface as a failed chat response.
        #
        # asyncio.CancelledError is a BaseException and so passes through: a
        # cancelled request is the caller going away, not a count failure.
        _log_unavailable_once(
            model_name, f"{type(exc).__name__}: {exc}", exc_info=True
        )
        _record_failure(model_name)
        return _unavailable(type(exc).__name__)

    tokens = _token_count(usage)
    if tokens is None:
        _log_unavailable_once(model_name, "provider reported no input token count")
        _record_failure(model_name)
        return _unavailable("no-usage")

    _record_success(model_name)
    return NativeCountResult(
        tokens=tokens, covers_system_prompt=covers_system_prompt, source=protocol
    )


async def _ask_provider(
    *,
    model_name: str,
    system_config_doc: Optional[dict],
    system_prompt: str,
    user_message: str,
    history: list,
) -> Any:
    """Build the request the chat is about to send, and count it.

    Split out so `count_natively` reads as gate / attempt / validate, and so
    every line that can raise sits inside one handler rather than several.

    The request is assembled to match `create_chat_agent`: the prompt rides as
    ``instructions`` (not ``system_prompt`` — pydantic-ai only injects a static
    system prompt on the first request of a run), and no tools are declared,
    because the chat agent registers none. Counting tools the request will not
    carry would inflate the figure on Anthropic, where tool schemas are billable
    input.
    """
    from pydantic_ai.messages import ModelRequest
    from pydantic_ai.models import ModelRequestParameters

    model = get_agent_model(model_name, system_config_doc=system_config_doc)

    # A copy: `build_thinking_model_settings` returns the real request's
    # settings, including a 120s timeout, and mutating it would be a shared-state
    # bug even where the timeout is the only field we change. Thinking settings
    # are kept because Anthropic's count endpoint takes a `thinking` param and
    # returns a different figure with it set.
    settings = dict(
        build_thinking_model_settings(model_name, None, system_config_doc) or {}
    )
    settings["timeout"] = NATIVE_COUNT_TIMEOUT_SECONDS

    messages = list(history)
    messages.append(
        ModelRequest.user_text_prompt(user_message, instructions=system_prompt)
    )

    return await model.count_tokens(messages, settings, ModelRequestParameters())


# A model config with the safety margin pinned to 1.0, so a count taken through
# `count_message_tokens` comes back raw.
#
# The alternative was to re-implement that function's "4 tokens of role wrapper
# plus each part's content" here, which is the same logic in two places and
# would drift the moment either side changed what a message costs. Every branch
# of `token_safety_margin` returns 1.0 for a configured 1.0, and `_apply_margin`
# on an integer total is then the identity, so this is exactly the margin-free
# count with none of the duplication. The rest of the config is preserved: it
# carries `tokenizer_path` and `tokenizer_cache_root`, and dropping those would
# silently change which vocabulary did the counting.
def _baseline_config(model_config: Optional[dict]) -> dict:
    return {**(model_config or {}), "token_safety_margin": 1.0}


def native_count_for(
    result: NativeCountResult,
    *,
    model_name: str,
    model_config: Optional[dict],
    system_prompt: str,
    user_message: str,
    history: list,
) -> Optional[NativeCount]:
    """Pair the provider's figure with a local count of *exactly* the same text.

    `context_budget` turns the pair into a margin of ``tokens /
    baseline_tokens``. That division is only a measurement of tokenizer
    divergence while both numbers describe the same characters. Count something
    the provider never saw and the baseline inflates, the ratio shrinks, and —
    because the ratio is clamped at a floor of 1.0 — the planner drops a 1.5
    margin it needed onto a tiktoken figure that reads up to 45% low for
    non-OpenAI models. That is the direction that hard-fails a request, so the
    component set here is not a convenience: it is the correctness condition.

    Which components those are is a property of `_ask_provider` above, which is
    why this lives next to it rather than at the call site. It sends
    ``list(history)`` followed by this turn's user message, with the system
    prompt riding as ``instructions``:

    * Anthropic forwards the instructions as ``system=`` and counts them, so
      ``covers_system_prompt`` is True and the prompt belongs in the baseline.
    * ``google-gla`` never attaches ``system_instruction`` to the count config,
      so the prompt is on neither side. For KB chat that is a multi-kilobyte
      grounding preamble, and adding it to the baseline alone would be the
      inflation described above at its worst.

    Returns None rather than a coherent-looking zero whenever there is nothing
    to measure — an unusable result, or an empty payload.

    Not the request's *total*: the caller is buying a ratio to apply per
    component, because the planner recounts text it has trimmed. A recorded
    total stops being true at the first trim.
    """
    if not result.usable or result.tokens is None:
        return None

    baseline_config = _baseline_config(model_config)
    baseline = count_raw_tokens(user_message, model_name, model_config)
    baseline += sum(
        count_message_tokens(m, model_name, baseline_config) for m in history
    )
    if result.covers_system_prompt and system_prompt:
        baseline += count_raw_tokens(system_prompt, model_name, model_config)

    if baseline <= 0:
        # No text on our side of the ratio. `_native_margin` would reject this
        # anyway; handing it on would be handing on a divide by zero waiting to
        # be relaxed.
        return None

    return NativeCount(
        model_name=model_name, tokens=result.tokens, baseline_tokens=baseline
    )
