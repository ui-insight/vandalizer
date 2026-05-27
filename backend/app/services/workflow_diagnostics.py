"""Deterministic static + runtime diagnostics for workflows.

The LLM-as-judge in :mod:`workflow_service.validate_workflow` is good at
"does the output read right?" but it silently waves through a class of
structural problems a quick programmatic walk would catch — dangling
search-set references, prompts that mention fields no upstream step
produces, empty/error-shaped step outputs, and "claimed JSON" outputs
that don't parse. Those are the diagnostics here.

These are pure, synchronous helpers. No LLM calls, no DB writes — the
caller is responsible for hydrating ``wf_data`` and ``steps_output``.
The aggregator :func:`run_diagnostics` returns a flat list of
:class:`Diagnostic` dicts that the validator surfaces under
``static_diagnostics`` in the response.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypedDict


class Diagnostic(TypedDict, total=False):
    code: str
    level: str  # "error" | "warning" | "info"
    message: str
    target_step: str | None
    details: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extraction_fields(task_data: dict) -> list[str]:
    """Field keys produced by an Extraction task, regardless of legacy shape."""
    out: list[str] = []
    for ext in task_data.get("extractions", []) or []:
        if isinstance(ext, str):
            key = ext.strip()
        elif isinstance(ext, dict):
            key = str(ext.get("key", "")).strip()
        else:
            key = ""
        if key:
            out.append(key)
    return out


def _step_tasks(step: dict) -> list[dict]:
    return [t for t in (step.get("tasks") or []) if isinstance(t, dict)]


def _normalize_field_name(name: str) -> str:
    """Casefold + strip non-alphanumeric for fuzzy field-name matching.

    Prompts reference fields with all sorts of decoration — ``{{ award_amount }}``,
    ``"Award Amount"``, ``the awardAmount``. We normalize both sides before
    comparing so editing cosmetics don't trigger false positives.
    """
    return re.sub(r"[^a-z0-9]", "", name.lower())


# Common error-shaped patterns. Conservative — we'd rather miss a real error
# than mark a legitimate "Error report: …" extraction as broken.
_ERROR_SHAPED = re.compile(
    r"^\s*("
    r"error\s*[:\-]"
    r"|exception\s*[:\-]"
    r"|traceback"
    r"|\{[\"']?error[\"']?\s*:"
    r"|http\s*\d{3}"
    r"|429\b|503\b|504\b"
    r"|rate\s*limit"
    r"|api\s*key"
    r"|model\s*not\s*found"
    r"|context\s*length"
    r")",
    re.IGNORECASE,
)


def _looks_like_error(text: str) -> bool:
    """Heuristic: is this output text an error message rather than real output?

    Limited to short outputs — a 5KB document with the word "Error" in it is
    not an error message. Long outputs that happen to begin with "Error:" do
    still match, because that's how a degraded LLM response often opens.
    """
    if not text:
        return False
    snippet = text[:500].strip()
    if not snippet:
        return False
    return bool(_ERROR_SHAPED.match(snippet))


# ---------------------------------------------------------------------------
# Individual diagnostics
# ---------------------------------------------------------------------------


def check_dangling_search_set_references(
    wf_data: dict | None,
    *,
    valid_search_set_uuids: set[str] | None = None,
) -> list[Diagnostic]:
    """Extraction tasks that reference a search_set UUID that doesn't exist.

    ``valid_search_set_uuids`` is the set of UUIDs known to exist in MongoDB —
    the caller does the DB lookup once (the diagnostic stays synchronous). If
    ``None``, the check is skipped (no false positives when the caller can't
    or chose not to verify).
    """
    out: list[Diagnostic] = []
    if not wf_data or valid_search_set_uuids is None:
        return out

    for step in wf_data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()
        for task in _step_tasks(step):
            if task.get("name") != "Extraction":
                continue
            ss_uuid = (task.get("data") or {}).get("search_set_uuid")
            if not ss_uuid:
                continue
            if ss_uuid not in valid_search_set_uuids:
                out.append(Diagnostic(
                    code="dangling_search_set",
                    level="error",
                    message=(
                        f"Step '{step_name}' references a search set ({ss_uuid}) "
                        f"that no longer exists. The workflow will fail at runtime."
                    ),
                    target_step=step_name,
                    details={"search_set_uuid": ss_uuid},
                ))
    return out


def check_prompt_references_unproduced_fields(
    wf_data: dict | None,
) -> list[Diagnostic]:
    """Prompt/Formatter steps that mention a field no upstream step produces.

    Walks steps in order. For each Prompt or Formatter step, looks at the
    prompt/template text for ``{{ field }}`` Jinja-style references and for
    direct field-name mentions, then checks the union of fields produced by
    upstream Extraction steps. Anything mentioned but never produced is
    flagged as a warning (not error — sometimes prompts mention concepts that
    aren't extracted fields).
    """
    out: list[Diagnostic] = []
    if not wf_data:
        return out

    produced: set[str] = set()  # normalized field names produced so far
    produced_display: dict[str, str] = {}  # normalized → original

    jinja_re = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

    for step in wf_data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()

        for task in _step_tasks(step):
            task_name = task.get("name", "")
            data = task.get("data") or {}

            if task_name == "Extraction":
                for field in _extraction_fields(data):
                    norm = _normalize_field_name(field)
                    if norm:
                        produced.add(norm)
                        produced_display.setdefault(norm, field)

            elif task_name in ("Prompt", "Formatter"):
                text = (data.get("prompt") or data.get("format_template") or "")
                if not isinstance(text, str) or not text.strip():
                    continue

                # Only flag Jinja-style references — direct mentions
                # ("the award amount") are too noisy to flag reliably.
                jinja_refs = jinja_re.findall(text)
                missing: list[str] = []
                for ref in jinja_refs:
                    norm = _normalize_field_name(ref)
                    if norm and norm not in produced and ref not in missing:
                        missing.append(ref)

                if missing:
                    out.append(Diagnostic(
                        code="prompt_unproduced_field",
                        level="warning",
                        message=(
                            f"Step '{step_name}' references "
                            f"{', '.join(repr(m) for m in missing)} "
                            f"but no upstream step produces "
                            f"{'this field' if len(missing) == 1 else 'these fields'}. "
                            f"The template will render empty values."
                        ),
                        target_step=step_name,
                        details={
                            "missing_fields": missing,
                            "produced_so_far": sorted(produced_display.values()),
                        },
                    ))
    return out


_JSON_CLAIM_KEYWORDS = ("json",)


def _claims_json_output(task: dict) -> bool:
    name = task.get("name", "")
    data = task.get("data") or {}
    if name == "DataExport":
        return str(data.get("format", "")).lower() == "json"
    if name in ("Prompt", "Formatter"):
        text = (data.get("prompt") or data.get("format_template") or "").lower()
        # "return as JSON" / "JSON array" / "JSON object" — heuristic but tight.
        if not text:
            return False
        return any(
            phrase in text
            for phrase in ("as json", "json array", "json object", "valid json", "in json format", "return json")
        )
    return False


def check_json_validity(
    wf_data: dict | None,
    steps_output: dict | None,
) -> list[Diagnostic]:
    """Steps that claim to produce JSON but emit text that doesn't parse."""
    out: list[Diagnostic] = []
    if not wf_data or not steps_output:
        return out

    for step in wf_data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()
        if not any(_claims_json_output(t) for t in _step_tasks(step)):
            continue

        raw = steps_output.get(step_name)
        if isinstance(raw, dict):
            output_text = raw.get("output", raw)
        else:
            output_text = raw
        if output_text is None:
            continue
        if isinstance(output_text, (dict, list)):
            continue  # already structured — implicitly valid

        text = str(output_text).strip()
        if not text:
            continue  # caught by the empty-output diagnostic

        # Tolerate a Markdown ```json fence the LLM sometimes adds.
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()

        try:
            json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            out.append(Diagnostic(
                code="invalid_json_output",
                level="error",
                message=(
                    f"Step '{step_name}' claims to produce JSON but the output "
                    f"does not parse ({e.__class__.__name__}: {str(e)[:80]})."
                ),
                target_step=step_name,
                details={"snippet": text[:200]},
            ))
    return out


# ---------------------------------------------------------------------------
# Source-grounding (substring presence)
# ---------------------------------------------------------------------------


_NOT_FOUND_TOKENS = {
    "", "n/a", "na", "none", "null", "not found", "not present",
    "not specified", "not mentioned", "unknown", "unspecified", "-",
}


def _normalize_for_grounding(text: str) -> str:
    """Lowercase + collapse whitespace + strip punctuation noise.

    We want fuzzy substring matching: "Award Amount: $1,250,000" should
    ground against source text that says "received $1,250,000 in award funds."
    Aggressive enough to match formatting drift; conservative enough that
    a genuinely fabricated value still misses.
    """
    cleaned = re.sub(r"[^\w\s.,$%/-]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_extraction_output(text: str) -> list[tuple[str, str]]:
    """Pull (field, value) pairs from a markdown-bullet extraction output.

    Matches the format produced by
    :func:`app.services.workflow_engine.format_extraction_results`:
    ``- **field**: value``. Multi-line values are folded onto one line.
    """
    pairs: list[tuple[str, str]] = []
    if not isinstance(text, str):
        return pairs
    for match in re.finditer(
        r"-\s*\*\*([^*]+)\*\*:\s*(.+?)(?=\n-\s*\*\*|\n####|\Z)",
        text,
        flags=re.DOTALL,
    ):
        field = match.group(1).strip()
        value = match.group(2).strip()
        if field and value:
            pairs.append((field, value))
    return pairs


def _source_text(steps_output: dict | None) -> str:
    """Pull the source document text from a Document/AddDocument step.

    Mirrors :func:`workflow_service._extract_source_text_from_steps` so the
    grounding check sees exactly what the LLM judge sees.
    """
    if not steps_output:
        return ""
    for step_name, step_data in steps_output.items():
        name_lower = (step_name or "").lower()
        is_loader = name_lower in ("document", "adddocument") or (
            isinstance(step_data, dict)
            and step_data.get("step_name") in ("Document", "AddDocument")
        )
        if not is_loader:
            continue
        raw = step_data.get("output", step_data) if isinstance(step_data, dict) else step_data
        if isinstance(raw, str) and raw.strip():
            return raw
        if isinstance(raw, list):
            return "\n---\n".join(str(item) for item in raw[:10])
    return ""


def check_source_grounding(
    wf_data: dict | None,
    steps_output: dict | None,
) -> list[Diagnostic]:
    """Extracted values that don't appear in the source document.

    Deterministic complement to the LLM judge's hallucination check. For
    each extracted (field, value) pair, normalize both the value and the
    source text, then look for the value as a substring. Skip placeholder
    values ("N/A", "not found", etc.) and Extraction steps that didn't run.

    Emits one ``ungrounded_extracted_value`` warning per ungrounded value,
    plus one rolled-up ``low_source_grounding`` error when more than half
    the values on a single step are ungrounded — that pattern is much more
    likely to be a real hallucination than a single fuzzy miss.
    """
    out: list[Diagnostic] = []
    if not wf_data or not steps_output:
        return out

    source_raw = _source_text(steps_output)
    if not source_raw:
        return out
    source_norm = _normalize_for_grounding(source_raw)
    if not source_norm:
        return out

    for step in wf_data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()
        if not step_name:
            continue
        if not any(t.get("name") == "Extraction" for t in _step_tasks(step)):
            continue

        raw_out = steps_output.get(step_name)
        if isinstance(raw_out, dict):
            output_text = raw_out.get("output", raw_out)
        else:
            output_text = raw_out
        if not isinstance(output_text, str):
            continue

        pairs = _parse_extraction_output(output_text)
        if not pairs:
            continue

        ungrounded_fields: list[str] = []
        checked = 0
        for field, value in pairs:
            val_lower = value.lower().strip()
            # Skip placeholder values — they're not claims about source content.
            if val_lower in _NOT_FOUND_TOKENS:
                continue
            checked += 1
            val_norm = _normalize_for_grounding(value)
            if not val_norm:
                continue
            if val_norm in source_norm:
                continue
            ungrounded_fields.append(field)
            out.append(Diagnostic(
                code="ungrounded_extracted_value",
                level="warning",
                message=(
                    f"Step '{step_name}' field '{field}' = {value!r} does not "
                    f"appear in the source document. Possible hallucination."
                ),
                target_step=step_name,
                details={"field": field, "value": value[:200]},
            ))

        # Pattern-level signal — many ungrounded values on the same step is
        # qualitatively different from one stray miss. Promote to error.
        if checked >= 3 and len(ungrounded_fields) / checked > 0.5:
            out.append(Diagnostic(
                code="low_source_grounding",
                level="error",
                message=(
                    f"Step '{step_name}' has {len(ungrounded_fields)}/{checked} "
                    f"extracted values that don't appear in the source document. "
                    f"The extraction may be hallucinating."
                ),
                target_step=step_name,
                details={
                    "ungrounded_fields": ungrounded_fields,
                    "total_checked": checked,
                },
            ))
    return out


# ---------------------------------------------------------------------------
# Plan staleness
# ---------------------------------------------------------------------------


def check_plan_staleness(
    wf_data: dict | None,
    validation_plan: list[dict] | None,
) -> list[Diagnostic]:
    """Plan checks whose ``target_step`` no longer matches any current step.

    Lighter-weight version of full plan-vs-workflow drift detection: when a
    step has been renamed or deleted since the plan was generated, any
    check pointing at that name is silently miscategorized in the
    step_breakdown (and arguably no longer evaluates what its author
    intended). Surfaces as a warning per orphaned check, with a
    higher-level error when the orphans dominate the plan.
    """
    out: list[Diagnostic] = []
    if not wf_data or not validation_plan:
        return out

    current_steps = {
        (s.get("name") or "").strip()
        for s in (wf_data.get("steps") or [])
        if isinstance(s, dict)
    }
    current_steps.discard("")
    if not current_steps:
        return out

    orphaned: list[tuple[str, str]] = []  # (check_name, missing_step)
    for c in validation_plan:
        if not isinstance(c, dict):
            continue
        target = (c.get("target_step") or "").strip()
        if not target or target in current_steps:
            continue
        orphaned.append((c.get("name", "<unnamed check>"), target))

    if not orphaned:
        return out

    for check_name, missing_step in orphaned:
        out.append(Diagnostic(
            code="plan_stale_target_step",
            level="warning",
            message=(
                f"Check '{check_name}' targets step '{missing_step}' which no "
                f"longer exists. Regenerate the validation plan to refresh."
            ),
            target_step=None,
            details={"check_name": check_name, "missing_step": missing_step},
        ))

    # Rolled-up signal — >50% orphans means the workflow has been substantially
    # restructured since the plan was generated. Promote to error so the UI can
    # show a more prominent "regenerate plan" banner.
    if len(orphaned) / max(len(validation_plan), 1) > 0.5:
        out.append(Diagnostic(
            code="plan_substantially_stale",
            level="error",
            message=(
                f"{len(orphaned)} of {len(validation_plan)} validation checks "
                f"reference steps that no longer exist. The plan is stale — "
                f"validation results will not reflect the current workflow."
            ),
            target_step=None,
            details={"orphan_count": len(orphaned), "plan_size": len(validation_plan)},
        ))
    return out


def check_step_output_disagrees_with_final(
    wf_data: dict | None,
    steps_output: dict | None,
) -> list[Diagnostic]:
    """Extraction step produced X for field F, but final output contains Y for F.

    Common silent failure mode: an Extraction step pulls the correct value
    from the source, then a downstream Prompt/Formatter step paraphrases or
    fabricates a different value into the final output. The judge often
    can't catch this without a side-by-side because it sees only the final
    output as the answer of record.

    Heuristic match: compares normalized (case- and whitespace-insensitive)
    values for the same field name. Multi-value fields and free-form
    paraphrases are out of scope — this catches the "extracted '$1,250,000'
    but final says '$1.5M'" class of discrepancy.
    """
    out: list[Diagnostic] = []
    if not wf_data or not steps_output:
        return out

    steps = wf_data.get("steps") or []
    if len(steps) < 2:
        return out

    # Find the final step's output text. Prefer the step marked is_output;
    # fall back to the last step.
    final_step_name = ""
    for s in reversed(steps):
        if isinstance(s, dict) and s.get("is_output") and s.get("name"):
            final_step_name = s["name"]
            break
    if not final_step_name and isinstance(steps[-1], dict):
        final_step_name = steps[-1].get("name", "")
    if not final_step_name:
        return out

    final_raw = steps_output.get(final_step_name)
    final_text = ""
    if isinstance(final_raw, dict):
        inner = final_raw.get("output", final_raw)
        if isinstance(inner, str):
            final_text = inner
        elif isinstance(inner, (dict, list)):
            import json as _json
            final_text = _json.dumps(inner, default=str)
    elif isinstance(final_raw, str):
        final_text = final_raw
    if not final_text:
        return out

    final_norm = _normalize_for_grounding(final_text)
    if not final_norm:
        return out

    # Walk each pre-final extraction step and check its (field, value) pairs.
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()
        if not step_name or step_name == final_step_name:
            continue
        if not any(t.get("name") == "Extraction" for t in _step_tasks(step)):
            continue

        raw_out = steps_output.get(step_name)
        if isinstance(raw_out, dict):
            step_text = raw_out.get("output", raw_out)
        else:
            step_text = raw_out
        if not isinstance(step_text, str):
            continue

        pairs = _parse_extraction_output(step_text)
        if not pairs:
            continue

        for field, extracted_value in pairs:
            val_lower = extracted_value.lower().strip()
            if val_lower in _NOT_FOUND_TOKENS:
                continue
            # Skip very long extracted values — paraphrase comparison gets noisy.
            if len(extracted_value) > 120:
                continue

            extracted_norm = _normalize_for_grounding(extracted_value)
            if not extracted_norm or len(extracted_norm) < 2:
                continue

            # Does the final output mention this field name? If not, that's a
            # completeness issue, caught by the LLM judge — skip here.
            field_lower = field.lower().strip()
            if field_lower not in final_norm:
                continue

            # The field is referenced in the final output. Does the extracted
            # value also appear? If yes, faithful carry-through. If no, the
            # final output may have replaced it with a different value.
            if extracted_norm in final_norm:
                continue

            out.append(Diagnostic(
                code="step_output_disagrees_with_final",
                level="warning",
                message=(
                    f"Step '{step_name}' extracted {field!r} = {extracted_value!r}, "
                    f"but the final output mentions '{field}' without that value. "
                    f"Downstream step may have paraphrased or replaced it."
                ),
                target_step=final_step_name,
                details={
                    "source_step": step_name,
                    "field": field,
                    "extracted_value": extracted_value[:200],
                },
            ))
    return out


def check_step_output_quality(
    wf_data: dict | None,
    steps_output: dict | None,
) -> list[Diagnostic]:
    """Empty or error-shaped step outputs that the LLM judge would silently ignore.

    Skips the very first step (typically a Document/AddDocument loader whose
    output shape isn't a free-form string) and steps whose output is a dict
    (structured carriers — pass them through).
    """
    out: list[Diagnostic] = []
    if not wf_data or not steps_output:
        return out

    steps = wf_data.get("steps") or []
    first_step_name = (steps[0].get("name") if steps and isinstance(steps[0], dict) else "") or ""

    for step in steps:
        if not isinstance(step, dict):
            continue
        step_name = (step.get("name") or "").strip()
        if not step_name or step_name == first_step_name:
            # Loader / initial step — output shape isn't comparable
            continue
        raw = steps_output.get(step_name)
        if raw is None:
            continue
        # Unwrap {step_name: {"output": "..."}}
        if isinstance(raw, dict):
            inner = raw.get("output", raw)
        else:
            inner = raw
        # Structured outputs are caught by JSON validity check separately
        if not isinstance(inner, str):
            continue

        stripped = inner.strip()
        if not stripped:
            out.append(Diagnostic(
                code="empty_step_output",
                level="error",
                message=(
                    f"Step '{step_name}' produced an empty output. The LLM "
                    f"judge cannot distinguish this from a missing answer."
                ),
                target_step=step_name,
                details={},
            ))
            continue
        if _looks_like_error(stripped):
            out.append(Diagnostic(
                code="error_shaped_step_output",
                level="error",
                message=(
                    f"Step '{step_name}' output looks like an error message, "
                    f"not a real result. Check the model/API for failures."
                ),
                target_step=step_name,
                details={"snippet": stripped[:200]},
            ))
    return out


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def run_diagnostics(
    wf_data: dict | None,
    steps_output: dict | None = None,
    *,
    valid_search_set_uuids: set[str] | None = None,
    validation_plan: list[dict] | None = None,
) -> list[Diagnostic]:
    """Run every diagnostic and return the flat list.

    Static checks (dangling refs, prompt-field cross-ref, plan staleness)
    can run on workflow definition + plan alone — useful for pre-execution
    editor warnings. Runtime checks (step-output quality, JSON validity,
    source grounding) need ``steps_output`` from a completed run.
    """
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(check_dangling_search_set_references(
        wf_data, valid_search_set_uuids=valid_search_set_uuids,
    ))
    diagnostics.extend(check_prompt_references_unproduced_fields(wf_data))
    diagnostics.extend(check_plan_staleness(wf_data, validation_plan))
    diagnostics.extend(check_step_output_quality(wf_data, steps_output))
    diagnostics.extend(check_json_validity(wf_data, steps_output))
    diagnostics.extend(check_source_grounding(wf_data, steps_output))
    diagnostics.extend(check_step_output_disagrees_with_final(wf_data, steps_output))
    return diagnostics
