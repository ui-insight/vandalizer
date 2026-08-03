"""Prompt-variant templates for the workflow optimizer.

The optimizer's search space includes a per-step ``prompt_variant`` knob —
when a variant is applied, the original task prompt is wrapped with a prefix
and/or suffix that nudges the LLM toward a different style. Variants are
intentionally light: the user's authored prompt remains the core instruction,
and the wrapper is short enough that the optimizer can attribute lift to the
variant rather than to a wholesale prompt rewrite.

Why wrapping rather than rewriting:
- Preserves the user's intent verbatim — the optimizer can't accidentally
  delete a critical constraint the user wrote.
- Apply-back is trustworthy: a variant string is a one-token override; a
  fully rewritten prompt would couple the override to the original prompt's
  contents and break on user edits.
- Makes lift attribution clean: same prompt × different wrapper isolates the
  variant's effect.

Variants are applied to ``Prompt``, ``Formatter``, ``ResearchNode``, ``FormFiller``
tasks — anything that takes a free-text instruction. ``Extraction`` tasks are
ignored (their instruction shape is structured, not free-text).
"""

from __future__ import annotations

# Supported variant names. ``default`` means "no wrapper — use the user's
# original prompt as-is", and is the implicit baseline.
PROMPT_VARIANTS: list[str] = ["default", "concise", "detailed", "cot", "strict"]


# Per-variant (prefix, suffix) pair. Keep these short — the goal is to nudge,
# not to override.
_VARIANT_WRAPPERS: dict[str, tuple[str, str]] = {
    "default": ("", ""),
    "concise": (
        "Be concise and direct. ",
        "\n\nOutput only the requested result with no preamble or commentary.",
    ),
    "detailed": (
        "Take your time and be thorough. ",
        "\n\nProvide a complete, detailed response. Do not omit relevant context.",
    ),
    "cot": (
        "Think step by step before answering. ",
        "\n\nReason through the problem internally, then give a clear final answer.",
    ),
    "strict": (
        "Follow these instructions strictly and literally. ",
        "\n\nDo not add commentary, caveats, or content beyond what is requested.",
    ),
}


def apply_prompt_variant(prompt: str, variant: str | None) -> str:
    """Wrap ``prompt`` with the named variant's prefix/suffix.

    Returns the original prompt unchanged when ``variant`` is None, empty,
    "default", or an unrecognized name. We don't raise on unknown variants —
    the optimizer must be tolerant of stale overrides that reference variant
    names that have since been retired.
    """
    if not prompt:
        return prompt
    if not variant or variant == "default":
        return prompt
    wrapper = _VARIANT_WRAPPERS.get(variant)
    if not wrapper:
        return prompt
    prefix, suffix = wrapper
    return f"{prefix}{prompt}{suffix}"
