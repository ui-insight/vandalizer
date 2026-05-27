"""Tests for ``backend/app/services/workflow_diagnostics.py``.

These cover the four deterministic checks the LLM-judge can't reliably catch:
dangling search-set refs, prompt references to fields no upstream step
produces, empty / error-shaped step outputs, and "claims JSON" outputs that
don't parse. Each test pins one diagnostic so a regression points at the
exact rule that broke.
"""

import pytest

from app.services.workflow_diagnostics import (
    check_dangling_search_set_references,
    check_json_validity,
    check_plan_staleness,
    check_prompt_references_unproduced_fields,
    check_source_grounding,
    check_step_output_disagrees_with_final,
    check_step_output_quality,
    run_diagnostics,
)


# ---------------------------------------------------------------------------
# check_dangling_search_set_references
# ---------------------------------------------------------------------------


def test_dangling_search_set_skips_when_allow_list_unknown():
    """Without a verified allow-list we'd false-flag every workflow.

    The diagnostic must explicitly skip when the caller couldn't enumerate
    valid UUIDs (DB lookup failed, etc.) — not flag everything as dangling.
    """
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"search_set_uuid": "abc"}},
        ]},
    ]}
    assert check_dangling_search_set_references(wf, valid_search_set_uuids=None) == []


def test_dangling_search_set_flags_unknown_uuid():
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"search_set_uuid": "missing-uuid"}},
        ]},
    ]}
    out = check_dangling_search_set_references(
        wf, valid_search_set_uuids={"some-other-uuid"},
    )
    assert len(out) == 1
    assert out[0]["code"] == "dangling_search_set"
    assert out[0]["level"] == "error"
    assert out[0]["target_step"] == "Extract"
    assert "missing-uuid" in out[0]["details"]["search_set_uuid"]


def test_dangling_search_set_passes_when_uuid_exists():
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"search_set_uuid": "exists"}},
        ]},
    ]}
    assert check_dangling_search_set_references(
        wf, valid_search_set_uuids={"exists"},
    ) == []


def test_dangling_search_set_ignores_non_extraction_tasks():
    wf = {"steps": [
        {"name": "Prompt", "tasks": [
            {"name": "Prompt", "data": {"prompt": "hi"}},
        ]},
    ]}
    assert check_dangling_search_set_references(
        wf, valid_search_set_uuids=set(),
    ) == []


# ---------------------------------------------------------------------------
# check_prompt_references_unproduced_fields
# ---------------------------------------------------------------------------


def test_prompt_unproduced_field_flags_missing_reference():
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"extractions": [
                {"key": "applicant_name"},
            ]}},
        ]},
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": (
                "Write a summary about {{ applicant_name }} who requested "
                "{{ award_amount }}."
            )}},
        ]},
    ]}
    out = check_prompt_references_unproduced_fields(wf)
    assert len(out) == 1
    assert out[0]["code"] == "prompt_unproduced_field"
    assert out[0]["level"] == "warning"
    assert out[0]["target_step"] == "Summarize"
    assert out[0]["details"]["missing_fields"] == ["award_amount"]


def test_prompt_unproduced_field_passes_when_all_referenced():
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"extractions": [
                {"key": "applicant_name"}, {"key": "amount"},
            ]}},
        ]},
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": (
                "About {{ applicant_name }} and {{ amount }}."
            )}},
        ]},
    ]}
    assert check_prompt_references_unproduced_fields(wf) == []


def test_prompt_unproduced_field_normalizes_field_names():
    """Field names match across cosmetic differences (case, underscores)."""
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"extractions": [
                {"key": "Award Amount"},
            ]}},
        ]},
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": "Amount: {{ award_amount }}"}},
        ]},
    ]}
    assert check_prompt_references_unproduced_fields(wf) == []


def test_prompt_unproduced_field_does_not_flag_natural_language():
    """Natural-language mentions of a field name shouldn't flag — only
    explicit {{ field }} references. Otherwise every prompt that says
    "summarize the award" would trip false positives."""
    wf = {"steps": [
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"extractions": [{"key": "title"}]}},
        ]},
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": "Write about the award amount."}},
        ]},
    ]}
    assert check_prompt_references_unproduced_fields(wf) == []


def test_prompt_unproduced_field_handles_formatter_templates():
    wf = {"steps": [
        {"name": "Step1", "tasks": [
            {"name": "Extraction", "data": {"extractions": [{"key": "a"}]}},
        ]},
        {"name": "Step2", "tasks": [
            {"name": "Formatter", "data": {"format_template": "{{ a }} {{ b }}"}},
        ]},
    ]}
    out = check_prompt_references_unproduced_fields(wf)
    assert len(out) == 1
    assert out[0]["details"]["missing_fields"] == ["b"]


# ---------------------------------------------------------------------------
# check_step_output_quality
# ---------------------------------------------------------------------------


def test_step_output_quality_flags_empty_output():
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {"extractions": [{"key": "x"}]}},
        ]},
    ]}
    steps_output = {"Document": "the doc text", "Extract": ""}
    out = check_step_output_quality(wf, steps_output)
    assert len(out) == 1
    assert out[0]["code"] == "empty_step_output"
    assert out[0]["target_step"] == "Extract"


def test_step_output_quality_flags_error_shaped_output():
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
    ]}
    steps_output = {"Document": "doc", "Extract": "Error: rate limit exceeded"}
    out = check_step_output_quality(wf, steps_output)
    assert len(out) == 1
    assert out[0]["code"] == "error_shaped_step_output"
    assert out[0]["target_step"] == "Extract"


def test_step_output_quality_skips_first_step():
    """The first step is typically a document loader — its 'output' is the
    raw doc text, which we don't want to flag as 'too long' or 'wrong shape'."""
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
    ]}
    steps_output = {"Document": ""}
    assert check_step_output_quality(wf, steps_output) == []


def test_step_output_quality_passes_normal_text():
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
    ]}
    steps_output = {"Document": "doc", "Extract": "Field A: value\nField B: value"}
    assert check_step_output_quality(wf, steps_output) == []


def test_step_output_quality_unwraps_dict_output():
    """Steps sometimes write {"output": "..."} instead of a bare string."""
    wf = {"steps": [
        {"name": "Doc", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Step2", "tasks": [{"name": "Prompt", "data": {}}]},
    ]}
    steps_output = {"Doc": "x", "Step2": {"output": "   "}}
    out = check_step_output_quality(wf, steps_output)
    assert len(out) == 1
    assert out[0]["code"] == "empty_step_output"


def test_step_output_quality_ignores_long_text_with_error_word():
    """A 5KB extraction that contains the word 'Error' isn't an error message."""
    wf = {"steps": [
        {"name": "Doc", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Step2", "tasks": [{"name": "Extraction", "data": {}}]},
    ]}
    long_text = "Award details: this proposal references error rates in past trials. " * 100
    assert check_step_output_quality(wf, {"Doc": "x", "Step2": long_text}) == []


# ---------------------------------------------------------------------------
# check_json_validity
# ---------------------------------------------------------------------------


def test_json_validity_flags_invalid_json_from_data_export():
    wf = {"steps": [
        {"name": "Export", "tasks": [
            {"name": "DataExport", "data": {"format": "json"}},
        ]},
    ]}
    steps_output = {"Export": "{not json"}
    out = check_json_validity(wf, steps_output)
    assert len(out) == 1
    assert out[0]["code"] == "invalid_json_output"
    assert out[0]["target_step"] == "Export"


def test_json_validity_passes_valid_json():
    wf = {"steps": [
        {"name": "Export", "tasks": [
            {"name": "DataExport", "data": {"format": "json"}},
        ]},
    ]}
    steps_output = {"Export": '{"a": 1}'}
    assert check_json_validity(wf, steps_output) == []


def test_json_validity_tolerates_markdown_fence():
    """The LLM often wraps JSON in a ```json fence — that's still valid."""
    wf = {"steps": [
        {"name": "Format", "tasks": [
            {"name": "Prompt", "data": {"prompt": "return as JSON"}},
        ]},
    ]}
    steps_output = {"Format": '```json\n{"a": 1}\n```'}
    assert check_json_validity(wf, steps_output) == []


def test_json_validity_detects_prompt_claim():
    wf = {"steps": [
        {"name": "Format", "tasks": [
            {"name": "Prompt", "data": {"prompt": "Output a JSON array of items"}},
        ]},
    ]}
    out = check_json_validity(wf, {"Format": "this is not json"})
    assert len(out) == 1


def test_json_validity_ignores_steps_not_claiming_json():
    wf = {"steps": [
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": "Write a paragraph."}},
        ]},
    ]}
    assert check_json_validity(wf, {"Summarize": "not json but also not claimed"}) == []


def test_json_validity_skips_dict_outputs():
    """A step that already produced a dict is implicitly valid structure."""
    wf = {"steps": [
        {"name": "Export", "tasks": [
            {"name": "DataExport", "data": {"format": "json"}},
        ]},
    ]}
    assert check_json_validity(wf, {"Export": {"output": {"a": 1}}}) == []


# ---------------------------------------------------------------------------
# run_diagnostics aggregator
# ---------------------------------------------------------------------------


def test_run_diagnostics_returns_empty_for_nothing():
    assert run_diagnostics(None) == []
    assert run_diagnostics({}) == []
    assert run_diagnostics({"steps": []}) == []


# ---------------------------------------------------------------------------
# check_source_grounding
# ---------------------------------------------------------------------------


def _grounding_workflow():
    return {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
    ]}


def test_source_grounding_passes_when_values_appear_in_source():
    wf = _grounding_workflow()
    source = "The applicant John Doe received an award of $50,000 on 2025-01-15."
    extraction = (
        "- **Name**: John Doe\n"
        "- **Amount**: $50,000\n"
        "- **Date**: 2025-01-15\n"
    )
    assert check_source_grounding(wf, {"Document": source, "Extract": extraction}) == []


def test_source_grounding_flags_value_not_in_source():
    wf = _grounding_workflow()
    source = "The applicant John Doe received an award."
    extraction = (
        "- **Name**: John Doe\n"
        "- **Amount**: $99,999\n"
    )
    out = check_source_grounding(wf, {"Document": source, "Extract": extraction})
    codes = [d["code"] for d in out]
    assert "ungrounded_extracted_value" in codes
    ungrounded = next(d for d in out if d["code"] == "ungrounded_extracted_value")
    assert ungrounded["details"]["field"] == "Amount"


def test_source_grounding_skips_placeholder_values():
    """N/A and 'not found' aren't claims, they're disclaimers — never flag."""
    wf = _grounding_workflow()
    source = "Some text."
    extraction = (
        "- **Field1**: N/A\n"
        "- **Field2**: not found\n"
        "- **Field3**: not specified\n"
    )
    assert check_source_grounding(wf, {"Document": source, "Extract": extraction}) == []


def test_source_grounding_promotes_to_error_when_majority_ungrounded():
    wf = _grounding_workflow()
    source = "The applicant John Doe applied for a research grant."
    extraction = (
        "- **Name**: John Doe\n"     # grounded
        "- **Amount**: $99,999\n"     # NOT grounded
        "- **Date**: 2025-12-31\n"    # NOT grounded
        "- **Title**: Quantum Widgets\n"  # NOT grounded
    )
    out = check_source_grounding(wf, {"Document": source, "Extract": extraction})
    codes = [d["code"] for d in out]
    assert "low_source_grounding" in codes
    rolled_up = next(d for d in out if d["code"] == "low_source_grounding")
    assert rolled_up["level"] == "error"
    assert rolled_up["details"]["total_checked"] == 4


def test_source_grounding_skips_when_no_source_text():
    """Without a Document/AddDocument loader we have no ground truth."""
    wf = {"steps": [
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
    ]}
    extraction = "- **Field**: anything\n"
    assert check_source_grounding(wf, {"Extract": extraction}) == []


def test_source_grounding_tolerates_formatting_drift():
    """Source: 'received $1,250,000.' Extracted: '$1,250,000' — should match."""
    wf = _grounding_workflow()
    source = "The grant in the amount of $1,250,000.00 was approved."
    extraction = "- **Amount**: $1,250,000.00\n"
    assert check_source_grounding(wf, {"Document": source, "Extract": extraction}) == []


# ---------------------------------------------------------------------------
# check_step_output_disagrees_with_final
# ---------------------------------------------------------------------------


def _disagreement_workflow():
    """Document → Extract → Summarize, where Summarize is the final step."""
    return {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
        {"name": "Summarize", "tasks": [{"name": "Prompt", "data": {"prompt": "Summarize"}}]},
    ]}


def test_disagreement_passes_when_value_carried_through():
    """Extract found $50,000, final mentions $50,000 — no diagnostic."""
    wf = _disagreement_workflow()
    extraction = "- **Amount**: $50,000\n- **Name**: John Doe\n"
    summary = "The applicant John Doe received an award of $50,000 from the foundation."
    out = check_step_output_disagrees_with_final(wf, {
        "Document": "Source text",
        "Extract": extraction,
        "Summarize": summary,
    })
    assert out == []


def test_disagreement_flags_replaced_value():
    """Extract found $50,000 but final says $5,000 — value got mangled downstream."""
    wf = _disagreement_workflow()
    extraction = "- **Amount**: $50,000\n"
    summary = "The applicant received an Amount of $5,000."
    out = check_step_output_disagrees_with_final(wf, {
        "Document": "Source",
        "Extract": extraction,
        "Summarize": summary,
    })
    codes = [d["code"] for d in out]
    assert "step_output_disagrees_with_final" in codes
    diag = next(d for d in out if d["code"] == "step_output_disagrees_with_final")
    assert diag["details"]["field"] == "Amount"
    assert diag["target_step"] == "Summarize"


def test_disagreement_skips_placeholder_values():
    """N/A and similar placeholders shouldn't trigger comparisons."""
    wf = _disagreement_workflow()
    extraction = "- **Amount**: N/A\n- **Name**: not found\n"
    summary = "Amount was not provided. Name was not specified."
    assert check_step_output_disagrees_with_final(wf, {
        "Document": "Source",
        "Extract": extraction,
        "Summarize": summary,
    }) == []


def test_disagreement_skips_when_field_not_in_final():
    """If the final doesn't mention the field at all, that's a completeness
    issue caught by the LLM judge — this diagnostic only fires when the field
    IS mentioned but the value differs."""
    wf = _disagreement_workflow()
    extraction = "- **InternalRef**: ABC-123\n"
    summary = "The award was processed successfully."
    out = check_step_output_disagrees_with_final(wf, {
        "Document": "Source",
        "Extract": extraction,
        "Summarize": summary,
    })
    assert out == []


def test_disagreement_skips_when_steps_output_missing():
    """No runtime context, no diagnostic."""
    wf = _disagreement_workflow()
    assert check_step_output_disagrees_with_final(wf, None) == []
    assert check_step_output_disagrees_with_final(wf, {}) == []


def test_disagreement_uses_is_output_marker_when_present():
    """A step explicitly marked is_output beats positional 'last step' inference."""
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [{"name": "Extraction", "data": {}}]},
        {"name": "PrimaryOut", "is_output": True, "tasks": [{"name": "Prompt", "data": {"prompt": "x"}}]},
        {"name": "SecondaryOut", "tasks": [{"name": "Prompt", "data": {"prompt": "y"}}]},
    ]}
    extraction = "- **Amount**: $50,000\n"
    out = check_step_output_disagrees_with_final(wf, {
        "Document": "src",
        "Extract": extraction,
        "PrimaryOut": "The Amount was $5,000.",  # disagreement → flag
        "SecondaryOut": "The Amount was $50,000.",
    })
    codes = [d["code"] for d in out]
    # Flagged because PrimaryOut (the marked output) disagrees
    assert "step_output_disagrees_with_final" in codes
    diag = next(d for d in out if d["code"] == "step_output_disagrees_with_final")
    assert diag["target_step"] == "PrimaryOut"


# ---------------------------------------------------------------------------
# check_plan_staleness
# ---------------------------------------------------------------------------


def test_plan_staleness_passes_when_targets_exist():
    wf = {"steps": [{"name": "Extract"}, {"name": "Format"}]}
    plan = [
        {"id": "c1", "name": "completeness", "target_step": "Extract"},
        {"id": "c2", "name": "formatting", "target_step": "Format"},
    ]
    assert check_plan_staleness(wf, plan) == []


def test_plan_staleness_flags_orphaned_check():
    wf = {"steps": [{"name": "Extract"}, {"name": "Format"}]}
    plan = [
        {"id": "c1", "name": "completeness", "target_step": "Extract"},
        {"id": "c2", "name": "old check", "target_step": "DeletedStep"},
    ]
    out = check_plan_staleness(wf, plan)
    assert len(out) == 1
    assert out[0]["code"] == "plan_stale_target_step"
    assert out[0]["details"]["missing_step"] == "DeletedStep"


def test_plan_staleness_promotes_to_error_when_majority_orphans():
    wf = {"steps": [{"name": "Step1"}]}
    plan = [
        {"id": "c1", "name": "check1", "target_step": "OldStep1"},
        {"id": "c2", "name": "check2", "target_step": "OldStep2"},
        {"id": "c3", "name": "check3", "target_step": "Step1"},
    ]
    out = check_plan_staleness(wf, plan)
    codes = [d["code"] for d in out]
    assert codes.count("plan_stale_target_step") == 2
    assert "plan_substantially_stale" in codes
    error = next(d for d in out if d["code"] == "plan_substantially_stale")
    assert error["level"] == "error"


def test_plan_staleness_ignores_checks_without_target_step():
    """Older plans may not have target_step at all — don't flag those."""
    wf = {"steps": [{"name": "Step1"}]}
    plan = [{"id": "c1", "name": "legacy", "target_step": None}]
    assert check_plan_staleness(wf, plan) == []


# ---------------------------------------------------------------------------
# run_diagnostics aggregator with new checks
# ---------------------------------------------------------------------------


def test_run_diagnostics_aggregates_all_diagnostics():
    wf = {"steps": [
        {"name": "Document", "tasks": [{"name": "AddDocument", "data": {}}]},
        {"name": "Extract", "tasks": [
            {"name": "Extraction", "data": {
                "search_set_uuid": "ghost",
                "extractions": [{"key": "title"}],
            }},
        ]},
        {"name": "Summarize", "tasks": [
            {"name": "Prompt", "data": {"prompt": "About {{ unknown }}"}},
        ]},
        {"name": "Export", "tasks": [
            {"name": "DataExport", "data": {"format": "json"}},
        ]},
    ]}
    steps_output = {
        "Document": "doc text",
        "Extract": "",
        "Summarize": "ok",
        "Export": "not-json",
    }
    out = run_diagnostics(
        wf, steps_output, valid_search_set_uuids={"only-this-one-exists"},
    )
    codes = sorted(d["code"] for d in out)
    assert codes == [
        "dangling_search_set",
        "empty_step_output",
        "invalid_json_output",
        "prompt_unproduced_field",
    ]
