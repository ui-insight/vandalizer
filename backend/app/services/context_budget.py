"""Context-budget planning and compaction for chat requests.

Sizes every component of a prompt, decides what to trim when the total
exceeds the model's input budget, and returns compacted pieces the caller
can safely send to the LLM.  All compaction is logged as structured
``CompactionAction`` entries so the caller can surface them to the user
and to Sentry.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

_CHAR_TO_TOKEN_RATIO = 4

# Fallback only: how much to inflate a tiktoken estimate for a model whose real
# vocabulary we do not have. Models we can tokenize exactly get no margin at
# all — see `resolve_exact_tokenizer`.
#
# tiktoken is OpenAI's tokenizer, and for anything else it is a proxy that
# reads *low* — the direction that hard-fails. Measured against the models'
# own `prompt_tokens`, the divergence is driven by content, not request size:
#
#   flowing prose                    1.000
#   project description              1.019
#   real budget justification        1.171
#   synthetic dense currency table   1.455
#
# So no single constant is right, and the two ways of being wrong do not cost
# the same. Guessing high routes a request early and wastes part of the window.
# Guessing low hard-fails it and returns no answer at all. Given that asymmetry
# this covers the worst case measured above rather than the typical one: 1.5
# clears the 1.455 currency table, which is the digit-dense shape this product's
# budget documents actually take.
#
# The cost is real and is accepted deliberately — a hosted model answering
# flowing prose (1.000) now plans against a third less window than it has. A
# deployment that knows its content skews prose should set `token_safety_margin`
# on the model config and take that window back.
#
# This value only governs models where exactness is unavailable (hosted APIs).
# Exact tokenization remains the actual fix, and applies wherever a local
# vocabulary exists — see `resolve_exact_tokenizer`. A configured value below
# 1.0 is refused, since that re-creates the original bug by configuration.
DEFAULT_TOKEN_SAFETY_MARGIN = 1.5


# Where a self-hosted server leaves the vocabulary for every model it serves.
# Tokenizing needs the vocabulary, not the weights and not the GPU, so this is
# pure local CPU work — roughly 1.5 ms for a 36-page proposal, against 0.3 ms
# for the tiktoken call it replaces.
#
# Only the last-resort default. It is a property of how a particular host
# mounts its model cache, so it is overridable per model
# (``tokenizer_cache_root`` on the model config) and per deployment
# (``TOKENIZER_CACHE_ROOT``). Resolution order is model config, then settings,
# then this.
DEFAULT_TOKENIZER_CACHE_ROOT = "/hf-cache"


@lru_cache(maxsize=1)
def _settings_tokenizer_cache_root() -> str | None:
    """The deployment-wide cache root, or None when settings cannot be read.

    None means "no answer", not "no root". Settings already carries the default,
    so an empty string here is an operator explicitly turning discovery off —
    collapsing the two made ``TOKENIZER_CACHE_ROOT=`` fall through to the
    hardcoded default and quietly ignore the opt-out.

    Cached because this is consulted on every token count. Deliberately
    forgiving: a settings failure degrades to the default rather than taking
    down the budget planner and with it chat.
    """
    try:
        from app.config import Settings

        return Settings().tokenizer_cache_root
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not read tokenizer_cache_root from settings")
        return None

# Tokens a request costs beyond the text it carries.
#
# The server wraps every request in a chat template, and the agent framework
# adds its own preamble around the instructions. Neither appears in any string
# we count, so even a perfectly exact text count comes in short — in the unsafe
# direction.
#
# Measured, twice over. Against a bare server the chat template is a flat 13
# tokens and stays 13 across a 5000x payload range. End to end through the app
# the true overhead is 37 tokens, and it came out identical on a 25,000-token
# request and a 50,000-token one — so this is a fixed cost, not a multiplier.
#
# 512 is deliberately far above the measured 37. It is a flat 2% of a 32k
# model's input budget, which is a cheap price for absorbing whatever the
# framework adds around `instructions` in a future version, and for history-
# heavy turns where per-message wrappers accumulate. Tightening it buys
# almost nothing and re-opens the direction that hard-fails.
#
# This is the piece the old margin was incidentally covering. Making it
# explicit is what allows the margin to be dropped for models we can tokenize
# exactly.
REQUEST_SCAFFOLD_TOKENS = 512

# Models already warned about, so the fallback is reported once per process
# rather than once per request. Per-request logging would be noise at chat
# volume; per-process is enough to be seen after a deploy or a config change,
# and resets naturally on restart.
_ESTIMATED_MODELS_WARNED: set[str] = set()


def _warn_estimated_once(model_name: str) -> None:
    """Say plainly that this model's budget is a guess, not a measurement.

    Silence here is the alias bug: a model registered as "Qwen-30b" rather
    than its full name resolves no vocabulary and drops to the default
    margin, silently planning against less window than the model has. The
    guess is a reasonable last resort; not saying so is not.
    """
    if model_name in _ESTIMATED_MODELS_WARNED:
        return
    _ESTIMATED_MODELS_WARNED.add(model_name)
    logger.warning(
        "token counts for %r are estimated, not exact: no local vocabulary "
        "and no stored calibration. Budgets use a default margin of %.2f, "
        "sized to cover the densest content measured (a currency table at "
        "1.455) — so a prose-heavy deployment is giving up window it could "
        "reclaim with token_safety_margin on the model config.",
        model_name, DEFAULT_TOKEN_SAFETY_MARGIN,
    )


@lru_cache(maxsize=32)
def _load_tokenizer(path: str):
    """Load a `tokenizer.json` from disk, or return None if it is unusable.

    Cached: a real vocabulary is several megabytes and takes milliseconds to
    parse, so loading it per request would make this the performance problem it
    exists to avoid.

    Two things are settled here rather than at the call site, because callers
    read the *presence* of a tokenizer as proof the count will be exact:

    ``tokenizer.json`` can carry truncation and padding stanzas, and
    ``Tokenizer.from_file`` restores them. A file specifying ``max_length: 512``
    would silently cap every count at 512 — a far worse under-count than the
    estimate this replaces, and one nothing downstream could detect, since a
    resolved tokenizer suppresses the safety margin. Both are cleared.

    The tokenizer is then exercised on a probe string. A vocabulary that loads
    but cannot encode would otherwise satisfy ``resolve_exact_tokenizer`` —
    which sets the margin to 1.0 — while ``_count_raw_tokens`` quietly fell
    back to tiktoken, producing a raw estimate with the safety margin switched
    off. That is exactly the hard-failing under-count this module exists to
    prevent, so an unusable tokenizer must be no tokenizer at all.
    """
    try:
        from tokenizers import Tokenizer

        tok = Tokenizer.from_file(path)
        # Order matters: no_truncation/no_padding must run before the probe, or
        # the probe would validate a configuration we are about to change.
        try:
            tok.no_truncation()
            tok.no_padding()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "could not clear truncation/padding on tokenizer at %s (%s); "
                "falling back to estimation", path, exc,
            )
            return None
        tok.encode("probe", add_special_tokens=False).ids
        return tok
    except Exception as exc:
        logger.warning(
            "could not load tokenizer at %s (%s); falling back to estimation",
            path, exc,
        )
        return None


@lru_cache(maxsize=32)
def _find_vocabulary(model_name: str, cache_root: str) -> Optional[str]:
    """Locate a model's `tokenizer.json` inside an HF-style cache.

    "Qwen/Qwen3-VL-8B-Instruct" lives at
    ``<root>/hub/models--Qwen--Qwen3-VL-8B-Instruct/snapshots/<rev>/``.
    Newest snapshot wins at the time of lookup.

    Note the lookup is cached on ``(model_name, cache_root)``, and the loader on
    the resolved path, so a model re-pulled while the process is running keeps
    serving the snapshot found first. Picking up a new one needs a restart —
    which is worth knowing before relying on "newest wins" operationally.
    """
    if not model_name or not cache_root:
        return None
    slug = "models--" + model_name.replace("/", "--")
    for base in (Path(cache_root) / "hub", Path(cache_root)):
        snapshots = base / slug / "snapshots"
        try:
            if not snapshots.is_dir():
                continue
            found = sorted(
                snapshots.glob("*/tokenizer.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            continue
        if found:
            return str(found[0])
    return None


def resolve_exact_tokenizer(model_name: str, model_config: Optional[dict] = None):
    """This model's real tokenizer, or None when we do not have it.

    None is an ordinary outcome, not an error: hosted models (Claude, and any
    provider we call over an API) have no local vocabulary, and those keep the
    estimate-plus-margin path.

    Priority: an explicit ``tokenizer_path`` on the model config, then
    discovery in the deployment's model cache.
    """
    cfg = model_config or {}
    explicit = cfg.get("tokenizer_path")
    if explicit:
        return _load_tokenizer(str(explicit))

    root = cfg.get("tokenizer_cache_root")
    if root is None:
        settings_root = _settings_tokenizer_cache_root()
        root = settings_root if settings_root is not None else DEFAULT_TOKENIZER_CACHE_ROOT
    if not root:
        # Explicitly emptied, at either level: discovery is off. Falling back to
        # the default here is what made the opt-out unreachable.
        return None
    path = _find_vocabulary(model_name or "", str(root))
    return _load_tokenizer(path) if path else None


@lru_cache(maxsize=8)
def _get_encoder(encoding_name: str):
    try:
        import tiktoken

        return tiktoken.get_encoding(encoding_name)
    except Exception as exc:
        logger.warning("tiktoken unavailable (%s); falling back to char heuristic", exc)
        return None


def _encoding_for(model_name: str) -> str:
    name = (model_name or "").lower()
    if any(tok in name for tok in ("gpt-4o", "gpt-4.1", "o1", "o3", "o4")):
        return "o200k_base"
    return "cl100k_base"


def _is_openai_model(name: str) -> bool:
    """True when tiktoken is this model's *real* tokenizer, not a proxy.

    Prefix-matching the o-series rather than substring-matching it: "o1" as a
    substring matches far too much to be safe on a registry of self-hosted
    model names.
    """
    n = (name or "").lower()
    if n.startswith(("gpt-", "o1", "o3", "o4")):
        return True
    return any(tok in n for tok in ("gpt-3.5", "gpt-4"))


@dataclass(frozen=True)
class NativeCount:
    """A provider's own token count, next to our local count of the same text.

    Deliberately carries both numbers rather than a ready-made ratio, so the
    pair can be checked for coherence at the point of use — a count with no
    baseline, or a baseline of zero, is not a measurement of anything.

    ``model_name`` is not decoration. Vocabularies differ per model, so a count
    measured against one model says nothing about another; carrying it across is
    the same wrong-ruler mistake the safety margin exists to correct.
    """

    model_name: str        # the model this was measured for
    tokens: int            # the provider's count of some text
    baseline_tokens: int   # _count_raw_tokens over the SAME text, taken locally


def _native_margin(
    model_name: str, native: Optional[NativeCount]
) -> Optional[float]:
    """The provider's own divergence from our estimate, or None when unusable.

    A ratio and not a total, because the margin is applied per component (see
    :func:`estimate_input_tokens`) and the planner recounts on mutated text
    inside its trim loop. A recorded total stops being true the moment anything
    is trimmed; a ratio stays approximately valid.

    Clamped at 1.0 on purpose. A provider counting *below* tiktoken may only
    reduce over-inflation, never reclaim window: counting low is the direction
    that hard-fails, and this ratio is measured over one sample of text rather
    than the request being planned.
    """
    if native is None:
        return None
    if native.model_name != model_name:
        # A count for another model is not a count for this one.
        return None
    if not (native.baseline_tokens > 0) or not (native.tokens > 0):
        return None
    ratio = native.tokens / native.baseline_tokens
    if not math.isfinite(ratio):
        # Nothing validates the dataclass, and a nan/inf reaching `_apply_margin`
        # would either raise inside `math.ceil` or produce a budget no request
        # could fit. Fall through to the ladder instead.
        return None
    return max(1.0, ratio)


def token_safety_margin(
    model_name: str,
    model_config: Optional[dict] = None,
    *,
    native: Optional[NativeCount] = None,
) -> float:
    """Multiplier that turns a tiktoken estimate into a safe upper bound.

    Returns 1.0 for OpenAI models, where the count is exact and inflating it
    would only trigger premature routing.

    An explicit ``token_safety_margin`` on the model config wins for any model
    whose count is an *estimate*, so a deployment can tune against its own
    measurements. A configured value below 1.0 is refused — that re-creates the
    original bug by configuration, leaving the planner optimistic in the
    direction that hard-fails.

    Exactness beats a configured margin. The guidance for a model with no local
    vocabulary is to set this value; when that deployment later mounts its model
    cache, those models start counting exactly and the configured number becomes
    a stale second correction applied on top of a figure that needs none —
    inflating every budget, and making every trim over-aggressive by the same
    factor through ``raw_usable``. ``stored_count_margin`` still honours the
    configured value: it corrects a tiktoken figure taken at ingestion, which is
    not the same question.

    ``native`` is a count the provider itself returned, paired with a local
    baseline over the same text. It sits immediately above the default, so it
    only ever displaces the 1.5 guess: exactness, a deployment's own configured
    number, and tiktoken-is-the-real-tokenizer all still win. When it does
    supply the margin the estimate is measured rather than guessed, so the
    "estimated" warning stays quiet.
    """
    # An exact count needs no correction. Inflating it would only route early.
    if resolve_exact_tokenizer(model_name, model_config) is not None:
        return 1.0

    configured = _configured_margin(model_name, model_config)
    if configured is not None:
        return configured

    if _is_openai_model(model_name):
        return 1.0

    measured = _native_margin(model_name, native)
    if measured is not None:
        return measured

    _warn_estimated_once(model_name or "<unnamed>")
    return DEFAULT_TOKEN_SAFETY_MARGIN


def _configured_margin(
    model_name: str, model_config: Optional[dict]
) -> Optional[float]:
    """A deployment's own measured margin, or None when it set none.

    Shared by both margin functions: a deployment that measured its own
    divergence knows better than either default, whichever question is being
    asked.
    """
    if not model_config:
        return None
    raw = model_config.get("token_safety_margin")
    if isinstance(raw, bool):
        raw = None  # bool is an int subclass; never a meaningful margin
    try:
        value = float(raw) if raw not in (None, "") else 0.0
    except (TypeError, ValueError):
        value = 0.0
    if value >= 1.0:
        return value
    if value:
        logger.warning(
            "ignoring token_safety_margin=%r for %s: a margin below 1.0 "
            "would under-count the request",
            raw,
            model_name,
        )
    return None


def stored_count_margin(
    model_name: str, model_config: Optional[dict] = None
) -> float:
    """Allowance for a token count taken with tiktoken and stored earlier.

    Deliberately not :func:`token_safety_margin`. That one answers "how safe
    is a count I am about to take?", and returns 1.0 once the model's own
    vocabulary is on disk, because the planner then counts the text exactly.

    This answers a different question: "how safe is a count someone else took
    earlier, with tiktoken, when I do not have the text to recount?" A stored
    ``token_count`` is a tiktoken figure whatever we could compute now, so the
    divergence is still there and still has to be allowed for. Reusing the
    other function here made the oversize check pass a raw tiktoken count
    straight through for exactly the models exact tokenization serves,
    under-warning by the divergence it exists to remove.
    """
    configured = _configured_margin(model_name, model_config)
    if configured is not None:
        return configured
    # tiktoken *is* the tokenizer for these, so the stored figure is exact.
    if _is_openai_model(model_name):
        return 1.0
    return DEFAULT_TOKEN_SAFETY_MARGIN


def _apply_margin(raw_tokens: int, margin: float) -> int:
    """Round up — a fractional token still has to be paid for."""
    if raw_tokens <= 0:
        return 0
    return math.ceil(raw_tokens * margin)


def _count_raw_tokens(
    text: str, model_name: str = "", model_config: Optional[dict] = None
) -> int:
    """Token count with no safety margin applied.

    Uses the model's own vocabulary when the deployment has it, which makes the
    count exact and the margin unnecessary. Falls back to tiktoken, and then to
    a character heuristic.

    Internal: callers sizing a request want :func:`count_tokens`. This exists so
    the margin is applied exactly once per aggregate, and so truncation can
    convert a margin-inflated budget back into real token offsets for slicing.
    """
    if not text:
        return 0

    tokenizer = resolve_exact_tokenizer(model_name, model_config)
    if tokenizer is not None:
        try:
            return len(tokenizer.encode(text, add_special_tokens=False).ids)
        except Exception:
            logger.warning(
                "exact tokenizer failed for %s; falling back to estimation",
                model_name, exc_info=True,
            )

    encoder = _get_encoder(_encoding_for(model_name))
    if encoder is not None:
        try:
            return len(encoder.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, len(text) // _CHAR_TO_TOKEN_RATIO)


def count_raw_tokens(
    text: str, model_name: str = "", model_config: Optional[dict] = None
) -> int:
    """Count with no safety margin, for values *stored* rather than spent.

    A document's ``token_count`` is written once at ingestion and read later
    against whichever model the user happens to pick, but the safety margin is
    a property of that model, not of the document. Baking a margin into the
    stored value would freeze one model's correction into every future
    comparison — and would still leave every already-ingested document holding
    an uncorrected number. So the stored figure stays a raw baseline and the
    margin is applied at comparison time, by :func:`find_oversize_documents`.
    """
    return _count_raw_tokens(text, model_name, model_config)


def count_tokens(
    text: str,
    model_name: str = "",
    model_config: Optional[dict] = None,
    *,
    native: Optional[NativeCount] = None,
) -> int:
    """Estimate token count for ``text``, erring high for non-OpenAI models."""
    raw = _count_raw_tokens(text, model_name, model_config)
    margin = token_safety_margin(model_name, model_config, native=native)
    return _apply_margin(raw, margin)


def count_message_tokens(
    message: Any,
    model_name: str = "",
    model_config: Optional[dict] = None,
    *,
    native: Optional[NativeCount] = None,
) -> int:
    """Estimate tokens for one pydantic-ai ``ModelMessage``.

    The margin covers the role wrapper too. The per-message overhead below is a
    flat guess at chat-template scaffolding that real templates exceed, and
    under-counting it is most of why small requests showed the *largest*
    proportional error in measurement.
    """
    total = 4  # per-message overhead for role wrapping
    for part in getattr(message, "parts", ()):
        content = getattr(part, "content", None)
        if content is None:
            content = str(part)
        total += _count_raw_tokens(str(content), model_name, model_config)
    return _apply_margin(
        total, token_safety_margin(model_name, model_config, native=native)
    )


# ---------------------------------------------------------------------------
# Model context window
# ---------------------------------------------------------------------------

# Order matters — the first substring match wins, so more specific entries
# must appear before broader ones.
_CONTEXT_WINDOW_FALLBACKS: list[tuple[str, int]] = [
    ("gpt-4.1", 1_000_000),
    ("gpt-4o-mini", 128_000),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-4-32k", 32_768),
    ("gpt-4", 8_192),
    ("gpt-3.5", 16_385),
    ("o1-mini", 128_000),
    ("o1", 200_000),
    ("o3", 200_000),
    ("o4", 200_000),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("claude-3-7", 200_000),
    ("claude-3-5", 200_000),
    ("claude-3", 200_000),
    ("llama-3", 131_072),
    ("llama3", 131_072),
    ("mixtral", 32_768),
    ("mistral", 32_768),
    ("qwen", 131_072),
    ("gemma", 8_192),
]

DEFAULT_CONTEXT_WINDOW = 65_536


def resolve_context_window(
    model_name: str, model_config: Optional[dict] = None
) -> int:
    """Return the max input-context length for a model, in tokens.

    Priority: ``model_config['context_window']`` → fallback registry → default.
    """
    if model_config:
        raw = model_config.get("context_window")
        try:
            value = int(raw) if raw not in (None, "") else 0
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value

    name = (model_name or "").lower()
    for pattern, window in _CONTEXT_WINDOW_FALLBACKS:
        if pattern in name:
            return window
    return DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# Budgeting + compaction
# ---------------------------------------------------------------------------


@dataclass
class DocumentSegment:
    """A single compactable chunk of context (doc body, KB block, attachment)."""

    label: str
    text: str
    required: bool = False  # required segments are never trimmed


@dataclass
class CompactionAction:
    """A single edit the planner applied to fit the budget."""

    kind: str  # "history_trimmed" | "documents_trimmed" | "attachments_trimmed" | "over_budget"
    detail: str
    tokens_dropped: int = 0

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "tokens_dropped": self.tokens_dropped,
        }


@dataclass
class BudgetPlan:
    model: str
    context_window: int
    response_reserve: int
    input_budget: int

    system_tokens: int = 0
    user_message_tokens: int = 0
    history_tokens: int = 0
    documents_tokens: int = 0
    attachments_tokens: int = 0
    # Chat template + framework preamble: sent on every request, present in
    # none of the strings above. See REQUEST_SCAFFOLD_TOKENS.
    scaffold_tokens: int = REQUEST_SCAFFOLD_TOKENS

    @property
    def total_input_tokens(self) -> int:
        return (
            self.scaffold_tokens
            + self.system_tokens
            + self.user_message_tokens
            + self.history_tokens
            + self.documents_tokens
            + self.attachments_tokens
        )

    @property
    def over_budget(self) -> bool:
        return self.total_input_tokens > self.input_budget

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "context_window": self.context_window,
            "response_reserve": self.response_reserve,
            "input_budget": self.input_budget,
            "total_input_tokens": self.total_input_tokens,
            "system_tokens": self.system_tokens,
            "user_message_tokens": self.user_message_tokens,
            "history_tokens": self.history_tokens,
            "documents_tokens": self.documents_tokens,
            "attachments_tokens": self.attachments_tokens,
            "scaffold_tokens": self.scaffold_tokens,
            "headroom_tokens": self.input_budget - self.total_input_tokens,
        }


@dataclass
class CompactedContext:
    documents: list[DocumentSegment]
    attachments: list[DocumentSegment]
    history: list  # list[pydantic_ai.messages.ModelMessage]
    plan: BudgetPlan
    actions: list[CompactionAction] = field(default_factory=list)

    @property
    def fatal(self) -> bool:
        """True when we could not shrink the request below the input budget."""
        return self.plan.over_budget


def _default_response_reserve(context_window: int) -> int:
    """Reserve tokens for the model's response.

    Scales with window size so tiny models don't lose all their budget to the
    reserve and large models don't overreserve.
    """
    return max(1024, min(8192, context_window // 4))


def resolve_response_reserve(
    context_window: int, model_config: Optional[dict] = None
) -> int:
    """Tokens reserved for the model's answer, honoring the per-model override.

    This is the single definition of the reserve. It doubles as the generation
    cap (llm_service sends it as ``max_tokens``) and as the slice the input
    budget gives up, so every caller must agree on it — a pre-flight that
    assumed the scaled default while the request used an admin's override would
    accept prompts the model then rejects.
    """
    if model_config:
        try:
            override = int(model_config.get("response_reserve_tokens") or 0)
        except (TypeError, ValueError):
            override = 0
        if override > 0:
            return override
    return _default_response_reserve(context_window)


def _split_head_tail(ids, budget: int, decode) -> Optional[tuple[str, str]]:
    """Take ``budget`` tokens from ``ids`` as a 75/25 head and tail.

    Returns None when ``budget`` already covers the whole list. That is not a
    trim: the two slices would overlap and together reproduce — or, once the
    marker is added, exceed — the original text, which is the opposite of
    truncating. It means only that this vocabulary disagrees with the one that
    decided a trim was needed, and the caller should leave the text alone
    rather than report a negative loss.
    """
    if budget >= len(ids):
        return None
    budget = max(0, budget)
    head_n = int(budget * 0.75)
    tail_n = max(0, budget - head_n)
    head_text = decode(ids[:head_n]) if head_n else ""
    tail_text = decode(ids[-tail_n:]) if tail_n else ""
    return head_text, tail_text


def _truncate_text_to_tokens(
    text: str,
    max_tokens: int,
    model_name: str,
    marker: str = "\n\n…[truncated]…\n\n",
    model_config: Optional[dict] = None,
    *,
    native: Optional[NativeCount] = None,
) -> tuple[str, int]:
    """Truncate ``text`` to ≤ ``max_tokens``, preserving head and tail.

    ``max_tokens`` is a margin-inflated budget, but slicing happens by real
    token offsets, so the budget is converted back to raw token space first.
    Slicing by an inflated count would take *more* text than the budget allows
    and leave the caller still over, which the last-ditch loop would then have
    to iterate its way out of.

    The budget must be converted into the units of whichever vocabulary does
    the slicing, and that has to be the same one that did the counting. When a
    model's own tokenizer is available the margin is 1.0, so ``raw_usable`` is
    denominated in *its* tokens — slicing a tiktoken list by that number is a
    unit error, and a silent one: the two rulers differ by up to 1.45x on the
    numeric content this product handles, so head and tail overlap and the
    "truncated" text comes back longer than the original. ``dropped`` then goes
    negative and the caller's ``loss <= 0`` check reads it as an untrimmable
    segment and discards the whole document.

    Returns ``(truncated_text, dropped_tokens)``, both in inflated space.
    """
    margin = token_safety_margin(model_name, model_config, native=native)
    original_tokens = count_tokens(text, model_name, model_config, native=native)
    if max_tokens <= 0:
        return "", original_tokens
    if original_tokens <= max_tokens:
        return text, 0

    marker_tokens = count_tokens(marker, model_name, model_config, native=native)
    usable = max(1, max_tokens - marker_tokens)
    raw_usable = max(1, int(usable / margin))

    # Prefer the model's own vocabulary, which is what counted above.
    exact = resolve_exact_tokenizer(model_name, model_config)
    if exact is not None:
        try:
            ids = exact.encode(text, add_special_tokens=False).ids
            halves = _split_head_tail(ids, raw_usable, exact.decode)
            if halves is None:
                return text, 0
            new_text = halves[0] + marker + halves[1]
            return new_text, max(
                0,
                original_tokens
                - count_tokens(new_text, model_name, model_config, native=native),
            )
        except Exception:
            logger.warning(
                "exact tokenizer failed while truncating for %s; "
                "falling back to estimation", model_name, exc_info=True,
            )

    encoder = _get_encoder(_encoding_for(model_name))
    if encoder is not None:
        try:
            toks = encoder.encode(text, disallowed_special=())
            halves = _split_head_tail(toks, raw_usable, encoder.decode)
            if halves is None:
                return text, 0
            new_text = halves[0] + marker + halves[1]
            return new_text, max(
                0,
                original_tokens
                - count_tokens(new_text, model_name, model_config, native=native),
            )
        except Exception:
            pass

    approx_chars = raw_usable * _CHAR_TO_TOKEN_RATIO
    head_chars = int(approx_chars * 0.75)
    tail_chars = max(0, approx_chars - head_chars)
    if head_chars + tail_chars >= len(text):
        return text, 0
    new_text = text[:head_chars] + marker + (text[-tail_chars:] if tail_chars else "")
    return new_text, max(
        0,
        original_tokens - count_tokens(new_text, model_name, model_config, native=native),
    )


def input_budget_for(
    model_name: str,
    model_config: Optional[dict] = None,
    response_reserve: Optional[int] = None,
) -> int:
    """Tokens available for input on this model, after the output reserve.

    The same arithmetic ``plan_and_compact_context`` uses to decide whether a
    request is over budget, exposed so callers can ask "would this fit?"
    without building and trimming a whole context first.

    The reserve comes from ``resolve_response_reserve`` so an admin's per-model
    ``response_reserve_tokens`` is honored here too. Assuming the scaled default
    while the request uses the override is the drift this module now has one
    definition to prevent — a routing decision made against the wrong budget
    sends a request the model then rejects.
    """
    context_window = resolve_context_window(model_name, model_config)
    reserve = (
        response_reserve
        if response_reserve is not None
        else resolve_response_reserve(context_window, model_config)
    )
    return max(1, context_window - reserve)


def estimate_input_tokens(
    *,
    model_name: str,
    system_prompt: str,
    user_message: str,
    history: list,
    documents: list[DocumentSegment],
    attachments: list[DocumentSegment],
    model_config: Optional[dict] = None,
    native: Optional[NativeCount] = None,
) -> int:
    """Input size of a request before any trimming.

    Mirrors what ``plan_and_compact_context`` counts into
    ``BudgetPlan.total_input_tokens``, including the same
    ``REQUEST_SCAFFOLD_TOKENS`` allowance for prompt scaffolding, so a caller
    can ask "would this fit?" without building
    a context and having the very documents it wants to measure trimmed out
    from under it. Kept next to the planner so the two stay in step.

    Carries the model's safety margin, so the answer is an upper bound rather
    than an optimistic guess. Routing depends on this: a router that trusts an
    estimate which reads low will decline to move a request that does not fit.

    ``native`` is threaded to every component so the margin is chosen once for
    the whole aggregate, exactly as the model_config path already is — a
    per-component disagreement about the ruler is the unit error this module
    keeps having to defend against.
    """
    return (
        REQUEST_SCAFFOLD_TOKENS
        + (
            count_tokens(system_prompt, model_name, model_config, native=native)
            if system_prompt
            else 0
        )
        + count_tokens(user_message, model_name, model_config, native=native)
        + sum(
            count_message_tokens(m, model_name, model_config, native=native)
            for m in history
        )
        + sum(
            count_tokens(d.text, model_name, model_config, native=native)
            for d in documents
        )
        + sum(
            count_tokens(a.text, model_name, model_config, native=native)
            for a in attachments
        )
    )


def plan_and_compact_context(
    *,
    model_name: str,
    model_config: Optional[dict],
    system_prompt: str,
    user_message: str,
    history: list,
    documents: list[DocumentSegment],
    attachments: list[DocumentSegment],
    response_reserve: Optional[int] = None,
    native: Optional[NativeCount] = None,
) -> CompactedContext:
    """Plan a context budget for this request and compact oversize components.

    Returns the same pieces (possibly trimmed) plus a ``BudgetPlan`` and the
    list of ``CompactionAction``s the planner applied.  The caller should
    check ``result.fatal`` — if true, sending the request will still fail.
    """
    documents = list(documents)
    attachments = list(attachments)
    history = list(history)

    context_window = resolve_context_window(model_name, model_config)
    reserve = (
        response_reserve
        if response_reserve is not None
        else _default_response_reserve(context_window)
    )
    input_budget = max(1, context_window - reserve)

    plan = BudgetPlan(
        model=model_name,
        context_window=context_window,
        response_reserve=reserve,
        input_budget=input_budget,
    )
    actions: list[CompactionAction] = []

    # Bound to this model, its config and any native count once, so no call site
    # below can silently size a segment with a different (optimistic) ruler than
    # the one the budget was planned against.
    def _ct(text: str) -> int:
        return count_tokens(text, model_name, model_config, native=native)

    def _cmt(message: Any) -> int:
        return count_message_tokens(message, model_name, model_config, native=native)

    def _trunc(text: str, max_tokens: int) -> tuple[str, int]:
        return _truncate_text_to_tokens(
            text, max_tokens, model_name, model_config=model_config, native=native
        )

    plan.system_tokens = _ct(system_prompt) if system_prompt else 0
    plan.user_message_tokens = _ct(user_message)
    plan.history_tokens = sum(_cmt(m) for m in history)
    plan.documents_tokens = sum(_ct(d.text) for d in documents)
    plan.attachments_tokens = sum(
        _ct(a.text) for a in attachments
    )

    if not plan.over_budget:
        return CompactedContext(
            documents=documents,
            attachments=attachments,
            history=history,
            plan=plan,
            actions=actions,
        )

    # Non-compactable floor covers the system prompt, user message, and an
    # allowance for prompt scaffolding ("--- BEGIN REFERENCE DOCUMENTS ---" etc.).
    floor = plan.system_tokens + plan.user_message_tokens + plan.scaffold_tokens
    if floor >= input_budget:
        actions.append(
            CompactionAction(
                kind="over_budget",
                detail=(
                    f"System prompt + your message alone ({floor} tokens) already "
                    f"exceed this model's input budget ({input_budget} tokens). "
                    "Shorten the message or pick a larger model."
                ),
            )
        )
        return CompactedContext(
            documents=documents,
            attachments=attachments,
            history=history,
            plan=plan,
            actions=actions,
        )

    remaining = input_budget - floor
    doc_target = int(remaining * 0.65)
    hist_target = int(remaining * 0.25)
    attach_target = remaining - doc_target - hist_target

    # 1. Drop oldest history messages until under target.
    if plan.history_tokens > hist_target:
        dropped = 0
        while history and sum(
            _cmt(m) for m in history
        ) > hist_target:
            m = history.pop(0)
            dropped += _cmt(m)
        plan.history_tokens = sum(_cmt(m) for m in history)
        if dropped:
            actions.append(
                CompactionAction(
                    kind="history_trimmed",
                    detail=f"Dropped {dropped} tokens of older conversation history.",
                    tokens_dropped=dropped,
                )
            )

    # 2. Trim attachments proportionally.
    if plan.attachments_tokens > attach_target and attachments:
        dropped = 0
        scale = attach_target / max(1, plan.attachments_tokens)
        for i, a in enumerate(attachments):
            if a.required:
                continue
            raw = _ct(a.text)
            allowed = max(256, int(raw * scale))
            if allowed >= raw:
                continue
            new_text, loss = _trunc(a.text, allowed)
            dropped += loss
            attachments[i] = DocumentSegment(
                label=a.label, text=new_text, required=a.required
            )
        plan.attachments_tokens = sum(
            _ct(a.text) for a in attachments
        )
        if dropped:
            actions.append(
                CompactionAction(
                    kind="attachments_trimmed",
                    detail=f"Trimmed {dropped} tokens from attached files.",
                    tokens_dropped=dropped,
                )
            )

    # 3. Trim documents proportionally.
    if plan.documents_tokens > doc_target and documents:
        dropped = 0
        scale = doc_target / max(1, plan.documents_tokens)
        for i, d in enumerate(documents):
            if d.required:
                continue
            raw = _ct(d.text)
            allowed = max(512, int(raw * scale))
            if allowed >= raw:
                continue
            new_text, loss = _trunc(d.text, allowed)
            dropped += loss
            documents[i] = DocumentSegment(
                label=d.label, text=new_text, required=d.required
            )
        plan.documents_tokens = sum(
            _ct(d.text) for d in documents
        )
        if dropped:
            actions.append(
                CompactionAction(
                    kind="documents_trimmed",
                    detail=f"Trimmed {dropped} tokens from reference documents.",
                    tokens_dropped=dropped,
                )
            )

    # 4. Last-ditch: aggressively shrink or drop segments until we fit.
    _MIN_USEFUL_TOKENS = 64  # smaller than this is not worth keeping
    safety_counter = 0
    while plan.over_budget and safety_counter < 50:
        safety_counter += 1
        overflow = plan.total_input_tokens - input_budget
        candidate: Optional[DocumentSegment] = None
        bucket_name: Optional[str] = None
        container: Optional[list[DocumentSegment]] = None
        for bucket_name_try, bucket in (
            ("documents", documents),
            ("attachments", attachments),
        ):
            for seg in bucket:
                if seg.required:
                    continue
                if candidate is None or _ct(seg.text) > _ct(candidate.text):
                    candidate = seg
                    bucket_name = bucket_name_try
                    container = bucket
        if candidate is None or container is None:
            actions.append(
                CompactionAction(
                    kind="over_budget",
                    detail=(
                        f"Compaction could not reduce input below {input_budget} "
                        f"tokens (still at {plan.total_input_tokens}). "
                        "Remove some documents or switch to a larger model."
                    ),
                )
            )
            break

        raw = _ct(candidate.text)
        target = raw - overflow - 8  # shave 8 extra tokens of slack
        if target < _MIN_USEFUL_TOKENS:
            # Not worth keeping a tiny sliver — drop the segment entirely.
            container.remove(candidate)
            actions.append(
                CompactionAction(
                    kind=f"{bucket_name}_trimmed",
                    detail=f"Dropped '{candidate.label}' to fit budget ({raw} tokens).",
                    tokens_dropped=raw,
                )
            )
        else:
            new_text, loss = _trunc(candidate.text, target)
            if loss <= 0:
                # No forward progress possible on this segment; drop it.
                container.remove(candidate)
                actions.append(
                    CompactionAction(
                        kind=f"{bucket_name}_trimmed",
                        detail=f"Dropped '{candidate.label}' to fit budget ({raw} tokens).",
                        tokens_dropped=raw,
                    )
                )
            else:
                candidate.text = new_text
                actions.append(
                    CompactionAction(
                        kind=f"{bucket_name}_trimmed",
                        detail=(
                            f"Additional trim of {loss} tokens from "
                            f"'{candidate.label}' to fit budget."
                        ),
                        tokens_dropped=loss,
                    )
                )
        plan.documents_tokens = sum(
            _ct(d.text) for d in documents
        )
        plan.attachments_tokens = sum(
            _ct(a.text) for a in attachments
        )

    return CompactedContext(
        documents=documents,
        attachments=attachments,
        history=history,
        plan=plan,
        actions=actions,
    )


# ---------------------------------------------------------------------------
# Pre-flight oversize check (no LLM call required)
# ---------------------------------------------------------------------------


@dataclass
class OversizeDocument:
    uuid: str
    title: str
    token_count: int

    def to_dict(self) -> dict:
        return {"uuid": self.uuid, "title": self.title, "token_count": self.token_count}


def find_oversize_documents(
    *,
    documents: list[dict],
    model_name: str,
    model_config: Optional[dict] = None,
    overhead_tokens: int = 1024,
) -> list[OversizeDocument]:
    """Return docs whose token_count alone would not fit the model's input budget.

    A doc is "oversize" if its `token_count` exceeds the per-request budget
    after reserving room for the response and a small overhead (system prompt,
    user message, scaffolding). Returns docs sorted largest-first. The caller
    uses this to recommend "Convert to Knowledge Base" rather than running
    compaction and silently truncating.

    ``documents`` is a list of dicts each with at least ``uuid``, ``title``,
    ``token_count``. Accepting dicts (not the Beanie model) keeps this usable
    from sync Celery code.

    ``token_count`` is a raw tiktoken figure (see :func:`count_raw_tokens`), so
    a divergence allowance is applied here rather than trusted from storage.
    Without it this check under-warns by the same 4–17% the planner did, and a
    workflow that will fail is not flagged before it runs. Applying it at read
    time also corrects documents ingested before any of this existed.

    The allowance comes from :func:`stored_count_margin`, not
    :func:`token_safety_margin` — this consumer never sees the document text,
    only a count taken with tiktoken, so having the model's real vocabulary on
    disk does not make that stored number exact.
    """
    budget = input_budget(model_name, model_config, overhead_tokens=overhead_tokens)
    # Stored counts are raw tiktoken figures, so the margin is applied at read
    # time rather than trusted from storage. That also corrects documents
    # ingested before any of this existed, without a backfill.
    margin = stored_count_margin(model_name, model_config)
    oversize = [
        OversizeDocument(
            uuid=d.uuid,
            title=d.title,
            token_count=_apply_margin(d.token_count, margin),
        )
        for d in _as_documents(documents)
    ]
    oversize = [d for d in oversize if d.token_count > budget]
    oversize.sort(key=lambda o: o.token_count, reverse=True)
    return oversize


def _as_documents(documents: list[dict]) -> list[OversizeDocument]:
    return [
        OversizeDocument(
            uuid=str(d.get("uuid") or ""),
            title=str(d.get("title") or d.get("uuid") or "Untitled"),
            token_count=int(d.get("token_count") or 0),
        )
        for d in documents
    ]


def input_budget(
    model_name: str,
    model_config: Optional[dict] = None,
    *,
    overhead_tokens: int = 1024,
) -> int:
    """Tokens available for prompt content: window minus answer reserve minus overhead."""
    context_window = resolve_context_window(model_name, model_config)
    reserve = resolve_response_reserve(context_window, model_config)
    return max(1, context_window - reserve - overhead_tokens)


@dataclass
class ContextOverflow:
    """A set of documents that cannot fit one request's input budget."""

    kind: str  # "single" — one doc is too big | "combined" — only the total is
    documents: list[OversizeDocument]  # largest first
    total_tokens: int
    budget: int

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "documents": [d.to_dict() for d in self.documents],
            "total_tokens": self.total_tokens,
            "budget": self.budget,
        }


def find_context_overflow(
    *,
    documents: list[dict],
    model_name: str,
    model_config: Optional[dict] = None,
    overhead_tokens: int = 1024,
) -> Optional[ContextOverflow]:
    """Check whether ``documents`` fit one request, individually *and* together.

    ``find_oversize_documents`` only ever asked "is any single doc too big",
    which a package of individually-modest documents passes — and then the
    gateway rejects the concatenated prompt mid-run. Callers that send several
    documents in one prompt should use this instead.

    Returns None when everything fits. A "single" overflow names only the docs
    that are individually too large; a "combined" overflow names the whole set.

    Stored ``token_count`` values are raw tiktoken figures, so the same
    divergence allowance :func:`find_oversize_documents` applies is applied
    here — for the same reason and from the same source
    (:func:`stored_count_margin`). Without it this check under-warns by the
    divergence it exists to catch, and the combined case is where that bites
    hardest: a budget workbook is both the document most likely to push a
    package over the line and the content tiktoken under-counts worst.
    """
    budget = input_budget(model_name, model_config, overhead_tokens=overhead_tokens)
    margin = stored_count_margin(model_name, model_config)
    docs = sorted(
        (
            OversizeDocument(
                uuid=d.uuid,
                title=d.title,
                token_count=_apply_margin(d.token_count, margin),
            )
            for d in _as_documents(documents)
        ),
        key=lambda d: d.token_count,
        reverse=True,
    )
    total = sum(d.token_count for d in docs)

    oversize = [d for d in docs if d.token_count > budget]
    if oversize:
        return ContextOverflow(
            kind="single", documents=oversize, total_tokens=total, budget=budget,
        )
    if total > budget:
        return ContextOverflow(
            kind="combined", documents=docs, total_tokens=total, budget=budget,
        )
    return None
