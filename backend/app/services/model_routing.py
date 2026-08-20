"""Pick a model that can actually hold the request.

Document chat puts whole documents in the prompt. When they don't fit, the
budget planner trims the middle out and the model answers from what's left —
correctly, confidently, and from part of the document. A 79-page proposal
measured at 41,213 tokens against a 32,768-token model reached it as 33 pages.

If the deployment has a model with a big enough window, using it is strictly
better than answering from a trimmed document. This module decides that, and
only that: the caller supplies both model configs and the request size.

Kept free of I/O so the decision is testable on its own — it is the piece that
must not be wrong, because it is the first place the product chooses a model on
the user's behalf.
"""

from dataclasses import dataclass
from typing import Optional

from app.services.context_budget import input_budget_for, token_safety_margin

# Lower is stricter. An unlabelled model is treated as *less* protected than
# one explicitly marked internal: `privacy` has never been enforced anywhere in
# the backend, so blank means "nobody said", not "safe". Routing is the first
# feature to choose a model without a human in the loop, and it must not be the
# thing that quietly sends a confidential proposal to a third party.
PRIVACY_RANK = {
    "internal": 0,
    "": 1,
    "external": 2,
}
_UNKNOWN_PRIVACY_RANK = 1


def _privacy_rank(config: Optional[dict]) -> int:
    value = (config or {}).get("privacy") or ""
    return PRIVACY_RANK.get(str(value).strip().lower(), _UNKNOWN_PRIVACY_RANK)


@dataclass(frozen=True)
class RoutingDecision:
    """Which model to use, and something a person can read about why."""

    model_name: str
    switched: bool
    reason: str


def _sized_for(
    input_tokens: int,
    current_name: str, current_config: Optional[dict],
    other_name: str, other_config: Optional[dict],
) -> int:
    """``input_tokens`` restated in *other*'s units, never smaller.

    The caller measures the request once, with the model the user is on. That
    number carries *that* model's safety margin — 1.0 where the count is exact
    (a local vocabulary, or OpenAI), 1.20 where it is an estimate. Comparing it
    against another model's budget silently mixes rulers: a request measured
    exactly looks like it fits a model whose own count would come out 20%
    higher, the router switches, and that model rejects it. That is the
    "estimate reads low, so we fail" failure the margin exists to prevent,
    relocated to the routing boundary.

    Re-measuring per candidate would mean re-tokenizing the whole prompt for
    each one, so the margin is rescaled instead. Where the two models tokenize
    differently the rescale is approximate — which is why it only ever rounds
    *up*: over-stating routes a request early, which costs the user nothing but
    a larger model, while under-stating hard-fails the request outright.
    """
    current_margin = token_safety_margin(current_name, current_config)
    other_margin = token_safety_margin(other_name, other_config)
    if other_margin <= current_margin or current_margin <= 0:
        return input_tokens
    return int(input_tokens / current_margin * other_margin)


def choose_document_model(
    *,
    current_name: str,
    current_config: Optional[dict],
    candidate_name: str,
    candidate_config: Optional[dict],
    input_tokens: int,
) -> RoutingDecision:
    """Route to *candidate* when the request won't fit *current* but will fit it.

    Deliberately conservative — every path that isn't a clear improvement stays
    on the model the user chose:

    * the request already fits          -> nothing to gain
    * no candidate, or it was deleted   -> nothing to route to
    * candidate is the current model    -> no-op
    * candidate would compact too       -> trimmed either way, so switching
                                           only costs the user their choice
    * candidate has weaker privacy      -> refused, however well it would fit
    """
    stay = RoutingDecision(current_name, False, "")

    if not candidate_name or not candidate_config:
        return stay
    if candidate_name == current_name:
        return stay

    current_budget = input_budget_for(current_name, current_config)
    if input_tokens <= current_budget:
        return stay

    candidate_budget = input_budget_for(candidate_name, candidate_config)
    candidate_tokens = _sized_for(
        input_tokens, current_name, current_config, candidate_name, candidate_config,
    )
    if candidate_tokens > candidate_budget:
        return RoutingDecision(
            current_name,
            False,
            f"This request is {input_tokens:,} tokens and does not fit "
            f"{candidate_name} either, so it stays on {current_name}.",
        )

    if _privacy_rank(candidate_config) > _privacy_rank(current_config):
        return RoutingDecision(
            current_name,
            False,
            f"{candidate_name} could hold this request but has weaker privacy "
            f"than {current_name}, so it was not used. Part of the document "
            "will be trimmed.",
        )

    return RoutingDecision(
        candidate_name,
        True,
        f"This request is {input_tokens:,} tokens, more than {current_name} "
        f"can hold ({current_budget:,}), so it was answered with "
        f"{candidate_name} to keep the whole document in view.",
    )


def suggest_document_model(
    *,
    current_name: str,
    current_config: Optional[dict],
    models: list[dict],
    input_tokens: int,
) -> Optional[dict]:
    """The model to offer the user when their request won't fit.

    Same privacy rule as :func:`choose_document_model` — the suggestion is
    computed here rather than in the browser precisely so the gate cannot be
    walked around by reading the model list client-side.

    Returns the *smallest* window that fits, not the largest. Jumping straight
    to the biggest model changes the thing answering the question more than the
    problem requires, and window size is not a proxy for quality.
    """
    if input_tokens <= input_budget_for(current_name, current_config):
        return None

    current_rank = _privacy_rank(current_config)
    fits = [
        m for m in models or []
        if m.get("name")
        and m.get("name") != current_name
        and _privacy_rank(m) <= current_rank
        and _sized_for(input_tokens, current_name, current_config, m.get("name", ""), m)
        <= input_budget_for(m.get("name", ""), m)
    ]
    if not fits:
        return None
    return min(fits, key=lambda m: input_budget_for(m.get("name", ""), m))
