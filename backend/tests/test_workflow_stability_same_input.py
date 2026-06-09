"""Tests for the Bug B fix (``_compute_output_stability`` filters to
same-input runs) and the deterministic-FAIL injection that overrides
LLM judge verdicts when a step's output is empty or error-shaped.
"""

from types import SimpleNamespace

from app.services.workflow_service import (
    _compute_output_stability,
    _inject_step_output_fails,
    _input_doc_key,
)


def _make_result(doc_uuids, output_text):
    """Minimal WorkflowResult stand-in — only the fields the helper reads."""
    return SimpleNamespace(
        input_context={"doc_uuids": doc_uuids},
        final_output={"output": output_text},
    )


def test_input_doc_key_is_stable_across_order():
    """The key must be order-independent so [A,B] groups with [B,A]."""
    a = _make_result(["x", "y"], "out")
    b = _make_result(["y", "x"], "out")
    assert _input_doc_key(a) == _input_doc_key(b)


def test_input_doc_key_distinguishes_different_doc_sets():
    a = _make_result(["x"], "out")
    b = _make_result(["y"], "out")
    assert _input_doc_key(a) != _input_doc_key(b)


def test_input_doc_key_empty_when_missing_context():
    r = SimpleNamespace(input_context=None, final_output={})
    assert _input_doc_key(r) == ""


def test_stability_suppressed_when_inputs_all_differ():
    """All three runs used different documents — variance is meaningless."""
    results = [
        _make_result(["doc1"], "output one"),
        _make_result(["doc2"], "output two"),
        _make_result(["doc3"], "output three"),
    ]
    out = _compute_output_stability(results)
    assert out["stability_score"] is None
    assert "different inputs" in out["detail"].lower()
    assert out["num_input_groups"] == 3


def test_stability_measured_when_same_input_set_repeats():
    """Two runs against the same doc set — that's measurable variance."""
    results = [
        _make_result(["doc1"], "identical output text"),
        _make_result(["doc2"], "totally different doc output"),  # ignored
        _make_result(["doc1"], "identical output text"),
    ]
    out = _compute_output_stability(results)
    assert out["stability_score"] == 1.0
    assert out["num_outputs_compared"] == 2
    assert out["compared_same_input"] is True


def test_stability_picks_largest_same_input_group():
    """When multiple input sets show up, pick the bucket with the most runs."""
    results = [
        _make_result(["solo"], "ignored"),
        _make_result(["pair"], "shared text"),
        _make_result(["pair"], "shared text"),
        _make_result(["pair"], "different text here"),
    ]
    out = _compute_output_stability(results)
    assert out["stability_score"] is not None
    assert out["num_outputs_compared"] == 3


# ---------------------------------------------------------------------------
# _inject_step_output_fails — deterministic override of LLM judge verdicts
# ---------------------------------------------------------------------------


def test_inject_overrides_pass_to_fail_when_step_was_broken():
    """The LLM judge can mark a check PASS even when the targeted step
    produced no output. The deterministic override flips it to FAIL with
    the original judge text preserved for debugging."""
    checks = [
        {"check_id": "c1", "status": "PASS", "detail": "looks fine"},
        {"check_id": "c2", "status": "PASS", "detail": "also fine"},
    ]
    plan = [
        {"id": "c1", "target_step": "Broken"},
        {"id": "c2", "target_step": "Healthy"},
    ]
    diagnostics = [
        {"code": "empty_step_output", "target_step": "Broken"},
    ]
    _inject_step_output_fails(checks, plan, diagnostics)
    assert checks[0]["status"] == "FAIL"
    assert "Broken" in checks[0]["detail"]
    assert "looks fine" in checks[0]["detail"]  # original judge text preserved
    assert checks[1]["status"] == "PASS"  # unrelated step untouched


def test_inject_skips_when_no_relevant_diagnostics():
    checks = [{"check_id": "c1", "status": "PASS", "detail": "ok"}]
    plan = [{"id": "c1", "target_step": "Step1"}]
    _inject_step_output_fails(checks, plan, [])
    assert checks[0]["status"] == "PASS"


def test_inject_preserves_skip_status():
    """SKIP means the check couldn't run at all — don't promote to FAIL,
    that would confuse 'we don't know' with 'we know it failed'."""
    checks = [{"check_id": "c1", "status": "SKIP", "detail": "binary output"}]
    plan = [{"id": "c1", "target_step": "Broken"}]
    diagnostics = [{"code": "empty_step_output", "target_step": "Broken"}]
    _inject_step_output_fails(checks, plan, diagnostics)
    assert checks[0]["status"] == "SKIP"


def test_inject_handles_invalid_json_diagnostic():
    """invalid_json_output is structural too — a step that claims JSON
    but doesn't produce JSON has silently broken the downstream consumer."""
    checks = [{"check_id": "c1", "status": "PASS", "detail": "looks fine"}]
    plan = [{"id": "c1", "target_step": "Export"}]
    diagnostics = [{"code": "invalid_json_output", "target_step": "Export"}]
    _inject_step_output_fails(checks, plan, diagnostics)
    assert checks[0]["status"] == "FAIL"
    assert "does not parse" in checks[0]["detail"]


def test_inject_handles_low_source_grounding_diagnostic():
    """low_source_grounding (>50% extracted values not in source) is a
    likely-hallucination signal that the judge typically rates as PASS."""
    checks = [{"check_id": "c1", "status": "PASS", "detail": "judge ok"}]
    plan = [{"id": "c1", "target_step": "Extract"}]
    diagnostics = [{"code": "low_source_grounding", "target_step": "Extract"}]
    _inject_step_output_fails(checks, plan, diagnostics)
    assert checks[0]["status"] == "FAIL"


def test_inject_ignores_warning_level_diagnostics():
    """Single ungrounded value is a warning, not a structural fail — it
    might be a legitimate paraphrase the source-grounding heuristic missed."""
    checks = [{"check_id": "c1", "status": "PASS", "detail": "ok"}]
    plan = [{"id": "c1", "target_step": "Extract"}]
    diagnostics = [{"code": "ungrounded_extracted_value", "target_step": "Extract"}]
    _inject_step_output_fails(checks, plan, diagnostics)
    assert checks[0]["status"] == "PASS"
