"""Lightweight ``{{ ... }}`` substitution for workflow node string fields.

This exists so a workflow author can reference the *previous* step's output
inside a later node — most importantly an API node's URL, headers, and request
body — instead of hand-copying the upstream payload into a literal string.

Syntax::

    {{ inputs.output }}            # the whole previous-step output
    {{ output }}                   # same thing (the ``inputs.`` prefix is optional)
    {{ inputs.output.records }}    # drill into a dict key
    {{ inputs.output.items.0 }}    # drill into a list index
    {{ inputs.step_name }}         # name of the previous step

The substitution context is the dict each node receives in ``process(inputs)``
— it always carries ``output``, ``input``, and ``step_name`` keys for any node
that has an upstream step.

Two render modes, because a placeholder lands in two different kinds of text:

* ``render(..., json_encode=True)`` — used for a JSON **request body**. Each
  value is inserted as ``json.dumps(value)`` so the result is valid JSON
  regardless of the value's type. This makes the common "wrap the output in an
  envelope" pattern work::

      {"records": {{ inputs.output }}}   ->   {"records": [{"id": 1}]}

* ``render(..., json_encode=False)`` — used for **URLs and header strings**,
  where the placeholder sits inside an already-quoted string position and the
  author wants the raw scalar, not a re-quoted JSON value::

      https://api.example.com/records/{{ inputs.output.id }}
      {"Authorization": "Bearer {{ inputs.output.token }}"}
"""

import json
import re

# Matches {{ anything }} with optional surrounding whitespace; the inner
# expression is captured non-greedily so adjacent placeholders don't merge.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


class TemplateError(ValueError):
    """Raised when a placeholder references a path that cannot be resolved.

    The message is written for a workflow author reading it in the node's
    output, not for a developer reading a stack trace.
    """


def has_placeholder(text: object) -> bool:
    """True if ``text`` is a string containing at least one ``{{ ... }}``."""
    return isinstance(text, str) and "{{" in text and bool(_PLACEHOLDER_RE.search(text))


def _resolve_path(expr: str, context: dict):
    """Walk a dotted path like ``inputs.output.records.0`` through ``context``.

    The leading ``inputs.`` segment is optional, so ``output`` and
    ``inputs.output`` are equivalent. Each remaining segment indexes a dict by
    key or a list/tuple by integer position.
    """
    parts = [p for p in expr.split(".") if p != ""]
    if parts and parts[0] == "inputs":
        parts = parts[1:]
    if not parts:
        raise TemplateError(
            f"Template expression {{{{ {expr} }}}} is empty — "
            "reference an upstream value like {{ inputs.output }}."
        )

    value: object = context
    walked: list[str] = []
    for part in parts:
        if isinstance(value, dict):
            if part not in value:
                where = ".".join(walked) or "the step input"
                hint = (
                    " Is this node connected to an upstream step?"
                    if not walked and part == "output"
                    else ""
                )
                raise TemplateError(
                    f"Template variable {{{{ {expr} }}}} could not be resolved: "
                    f"no key {part!r} in {where}.{hint}"
                )
            value = value[part]
        elif isinstance(value, (list, tuple)):
            try:
                idx = int(part)
            except ValueError:
                raise TemplateError(
                    f"Template variable {{{{ {expr} }}}} could not be resolved: "
                    f"{'.'.join(walked)} is a list, so {part!r} must be a number."
                ) from None
            if idx < 0 or idx >= len(value):
                raise TemplateError(
                    f"Template variable {{{{ {expr} }}}} could not be resolved: "
                    f"index {idx} is out of range for {'.'.join(walked)} "
                    f"(length {len(value)})."
                )
            value = value[idx]
        else:
            raise TemplateError(
                f"Template variable {{{{ {expr} }}}} could not be resolved: "
                f"{'.'.join(walked) or 'the value'} is a "
                f"{type(value).__name__}, which has no {part!r} to drill into."
            )
        walked.append(part)
    return value


def _as_raw_string(value: object) -> str:
    """String form for a value placed into a URL or header (no JSON quoting)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Dicts/lists are unusual in a URL, but emit compact JSON rather than Python repr.
    return json.dumps(value)


def render(text: object, context: dict, *, json_encode: bool) -> object:
    """Replace every ``{{ ... }}`` in ``text`` using ``context``.

    Non-string ``text`` (or a string with no placeholder) is returned
    unchanged. Raises :class:`TemplateError` if any placeholder can't resolve.
    """
    if not isinstance(text, str) or "{{" not in text:
        return text

    def _sub(match: "re.Match[str]") -> str:
        value = _resolve_path(match.group(1).strip(), context)
        return json.dumps(value) if json_encode else _as_raw_string(value)

    return _PLACEHOLDER_RE.sub(_sub, text)
