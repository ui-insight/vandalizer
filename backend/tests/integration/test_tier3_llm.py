"""Tier 3 integration tests — requires a configured LLM.

These validate that prompts produce parseable output with a real LLM.
Assertions are generous (non-null, expected keys) not exact-match.

Configuration via environment variables:
    INTEGRATION_LLM=1           Gate flag (required to run these tests)
    INTEGRATION_LLM_MODEL       Model name as registered in system config
    INTEGRATION_LLM_API_KEY     API key for the model
    INTEGRATION_LLM_ENDPOINT    API endpoint URL (optional — omit for OpenAI-hosted models)
    INTEGRATION_LLM_PROTOCOL    API protocol: openai|ollama|vllm (default: openai)
"""

import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_LLM"),
        reason="Set INTEGRATION_LLM=1 (plus INTEGRATION_LLM_MODEL, INTEGRATION_LLM_API_KEY) to run LLM integration tests",
    ),
    pytest.mark.integration_tier3,
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm_model() -> str:
    return os.environ.get("INTEGRATION_LLM_MODEL", "gpt-4o-mini")


def _system_config_doc() -> dict:
    """Build a minimal system_config_doc that mirrors what SystemConfig
    stores in MongoDB, using env-var overrides for the test model."""
    model_name = _llm_model()
    api_key = os.environ.get("INTEGRATION_LLM_API_KEY", "")
    endpoint = os.environ.get("INTEGRATION_LLM_ENDPOINT", "")
    protocol = os.environ.get("INTEGRATION_LLM_PROTOCOL", "openai")

    model_entry: dict = {"name": model_name, "api_key": api_key, "api_protocol": protocol}
    if endpoint:
        model_entry["endpoint"] = endpoint

    return {
        "available_models": [model_entry],
        "llm_endpoint": endpoint,
    }


# ---------------------------------------------------------------------------
# 1. Full structured extraction pipeline
# ---------------------------------------------------------------------------

class TestExtractionStructuredReal:
    """Exercise _extract_structured with a real LLM call."""

    def test_extraction_structured_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        result = engine._extract_structured(
            content="Alice is 30 years old and works at Acme Corp.",
            keys=["Name", "Age", "Company"],
            model_name=_llm_model(),
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert isinstance(entity, dict)
        # All keys present with non-null values
        for key in ["Name", "Age", "Company"]:
            assert key in entity, f"Missing key: {key}"
            assert entity[key] is not None, f"Null value for: {key}"


# ---------------------------------------------------------------------------
# 2. Fallback JSON extraction pipeline
# ---------------------------------------------------------------------------

class TestExtractionFallbackJsonReal:
    """Exercise _extract_fallback_json with a real LLM call."""

    def test_extraction_fallback_json_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        result = engine._extract_fallback_json(
            content="Bob is 25 years old and works at Globex.",
            keys=["Name", "Age", "Company"],
            model_name=_llm_model(),
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert isinstance(entity, dict)
        for key in ["Name", "Age", "Company"]:
            assert key in entity, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 3. PromptNode with real LLM
# ---------------------------------------------------------------------------

class TestPromptNodeReal:
    """Exercise PromptNode.process() with a real LLM call."""

    def test_prompt_node_real(self):
        from app.services.workflow_engine import PromptNode

        sys_cfg = _system_config_doc()
        node = PromptNode(data={
            "prompt": "Respond with exactly one word: the color of grass.",
            "model": _llm_model(),
        })
        node._sys_cfg = sys_cfg

        output = node.process({"output": None, "step_name": "test"})

        assert output is not None
        assert isinstance(output["output"], (str, dict))
        # Should be a non-empty response
        if isinstance(output["output"], str):
            assert len(output["output"].strip()) > 0
        elif isinstance(output["output"], dict):
            answer = output["output"].get("answer", output["output"].get("formatted_answer", ""))
            assert len(str(answer).strip()) > 0


# ---------------------------------------------------------------------------
# 4. Extraction with enum constraint
# ---------------------------------------------------------------------------

class TestExtractionEnumConstraintReal:
    """Verify Literal enum constraints propagate to the LLM and
    the response respects them."""

    def test_extraction_enum_constraint_real(self):
        from app.services.extraction_engine import ExtractionEngine

        sys_cfg = _system_config_doc()
        engine = ExtractionEngine(system_config_doc=sys_cfg)
        meta_map = {"Status": {"enum_values": ["Active", "Inactive"]}}

        result = engine._extract_structured(
            content="The project is currently active and running smoothly.",
            keys=["Status"],
            model_name=_llm_model(),
            meta_map=meta_map,
        )

        assert isinstance(result, list)
        assert len(result) >= 1
        entity = result[0]
        assert "Status" in entity
        assert entity["Status"] in ("Active", "Inactive"), \
            f"Expected Active or Inactive, got: {entity['Status']}"


# ---------------------------------------------------------------------------
# 5. Extraction judge calibration vs human labels
#
# This is the load-bearing test for the LLM-as-judge claim. The fixture at
# tests/fixtures/judge_calibration.json carries human-labeled (expected,
# actual) triples covering field types, absence-equality, length-bias traps,
# multi-valued fields, and PARTIAL boundary cases. We run the judge against
# each case and measure:
#
#   * accuracy            — fraction of cases where the judge's score band
#                           matches the human gold verdict's band
#   * cohens_kappa        — agreement vs human verdicts, correcting for chance
#   * length_bias_penalty — fraction of "length_trap" cases the judge
#                           incorrectly PASSes (length-biased models would
#                           credit verbose actuals; this should stay low)
#
# Thresholds are intentionally lenient on the first pass — they catch
# regressions and let us measure improvement, not lock in an idealized
# number. Tighten over time as we collect more labels.
# ---------------------------------------------------------------------------


class TestExtractionJudgeCalibration:
    """Run the extraction judge against a human-labeled calibration set.

    Asserts Cohen's κ vs human ≥ 0.65 (substantial agreement on Landis-Koch),
    in-band accuracy ≥ 0.80, and length-bias incorrectness ≤ 20%. Tightened
    from the 0.55/0.75/0.30 launch floors after the calibration set grew
    from 53 → 120 cases (date/number/name/length-trap coverage). Detects
    both rubric-drift regressions and self-preference creep when the judge
    model changes."""

    def _load_calibration_cases(self) -> list[dict]:
        import json
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "fixtures" / "judge_calibration.json"
        return json.loads(fixture.read_text())["cases"]

    def _verdict_from_score(self, score: float) -> str:
        if score >= 0.7:
            return "PASS"
        if score >= 0.4:
            return "PARTIAL"
        return "FAIL"

    def _cohens_kappa(self, verdicts_a: list[str], verdicts_b: list[str]) -> float:
        """Cohen's κ for two categorical raters with 3 categories.

        Returns -1.0..1.0 where 0 = chance, 1 = perfect, <0 = worse than chance.
        """
        if len(verdicts_a) != len(verdicts_b) or not verdicts_a:
            return 0.0
        n = len(verdicts_a)
        cats = ("PASS", "PARTIAL", "FAIL")
        # Observed agreement
        p_obs = sum(1 for a, b in zip(verdicts_a, verdicts_b) if a == b) / n
        # Expected agreement (chance)
        p_exp = 0.0
        for c in cats:
            p_a = sum(1 for a in verdicts_a if a == c) / n
            p_b = sum(1 for b in verdicts_b if b == c) / n
            p_exp += p_a * p_b
        if p_exp >= 1.0:
            return 1.0
        return (p_obs - p_exp) / (1.0 - p_exp)

    def test_judge_calibration_vs_human(self):
        import asyncio
        import os

        from app.services.extraction_judge import judge_field_value

        # Patch the system config loader to use the env-var doc instead of
        # MongoDB — this test runs outside the full app lifecycle.
        from app.services import extraction_judge as ej

        sys_cfg = _system_config_doc()
        ej._system_config_doc_ctx.set(sys_cfg)

        cases = self._load_calibration_cases()

        async def _run_all() -> list[dict]:
            tasks = []
            for c in cases:
                tasks.append(judge_field_value(
                    field_name=c["field_name"],
                    expected=c["expected"],
                    actual=c["actual"],
                    model_name=_llm_model(),
                    field_metadata=c.get("field_metadata"),
                ))
            return await asyncio.gather(*tasks)

        results = asyncio.run(_run_all())

        gold_verdicts: list[str] = []
        judge_verdicts: list[str] = []
        in_band: list[bool] = []
        length_trap_passes_when_should_fail = 0
        length_trap_total = 0

        for case, result in zip(cases, results):
            score = float(result["score"])
            judge_verdict = self._verdict_from_score(score)
            gold_verdicts.append(case["gold_verdict"])
            judge_verdicts.append(judge_verdict)
            lo, hi = case["gold_score_band"]
            in_band.append(lo <= score <= hi)

            if case["field_type"] == "length_trap" and case["gold_verdict"] == "FAIL":
                length_trap_total += 1
                if judge_verdict == "PASS":
                    length_trap_passes_when_should_fail += 1

        accuracy = sum(1 for ok in in_band if ok) / len(in_band)
        kappa = self._cohens_kappa(gold_verdicts, judge_verdicts)
        length_bias_rate = (
            length_trap_passes_when_should_fail / length_trap_total
            if length_trap_total else 0.0
        )

        # Surface the numbers in the failure message so users debugging a
        # regression can see what shifted, not just that the gate flipped.
        report = (
            f"\nJudge calibration report ({_llm_model()}):\n"
            f"  accuracy (in band):      {accuracy:.3f}\n"
            f"  cohens kappa:            {kappa:.3f}\n"
            f"  length-bias FAIL→PASS:   {length_bias_rate:.3f} "
            f"({length_trap_passes_when_should_fail}/{length_trap_total})\n"
        )

        # Allow env-var override for further tightening (or temporary
        # loosening on a deliberate model swap) without code change.
        min_kappa = float(os.environ.get("JUDGE_CALIBRATION_MIN_KAPPA", "0.65"))
        min_accuracy = float(os.environ.get("JUDGE_CALIBRATION_MIN_ACCURACY", "0.80"))
        max_length_bias = float(os.environ.get("JUDGE_CALIBRATION_MAX_LENGTH_BIAS", "0.20"))

        assert kappa >= min_kappa, (
            f"Cohen's κ {kappa:.3f} < {min_kappa}. {report}"
        )
        assert accuracy >= min_accuracy, (
            f"In-band accuracy {accuracy:.3f} < {min_accuracy}. {report}"
        )
        assert length_bias_rate <= max_length_bias, (
            f"Length-bias rate {length_bias_rate:.3f} > {max_length_bias}. {report}"
        )

        # Drift ledger — record this run and fail if κ regressed > 0.05 vs
        # the trailing-30-run median for this surface. Catches silent rubric
        # / model drift that doesn't trip the absolute κ floor.
        from app.services import judge_drift
        judge_drift.assert_no_regression("extraction", kappa)
        judge_drift.record(
            "extraction",
            judge_model=_llm_model(),
            kappa=kappa,
            accuracy=accuracy,
            bias_metric_name="length_bias_fail_to_pass",
            bias_rate=length_bias_rate,
            n_cases=len(cases),
        )

        # Per-field-type κ — surface regressions in low-frequency types (dates,
        # numbers) that the aggregate κ would hide. Reported, not gated, until
        # the per-type sample sizes grow enough to make per-type thresholds
        # statistically meaningful.
        per_type: dict[str, list[tuple[str, str]]] = {}
        for case, verdict in zip(cases, judge_verdicts):
            per_type.setdefault(case["field_type"], []).append(
                (case["gold_verdict"], verdict)
            )
        type_report = ["  per-field-type κ:"]
        for ftype in sorted(per_type):
            pairs = per_type[ftype]
            if len(pairs) < 2:
                type_report.append(f"    {ftype:>14}: n={len(pairs)} (too few)")
                continue
            gold, got = zip(*pairs)
            k = self._cohens_kappa(list(gold), list(got))
            type_report.append(f"    {ftype:>14}: κ={k:+.3f}  n={len(pairs)}")
        print("\n".join(type_report))


# ---------------------------------------------------------------------------
# 6. Workflow judge calibration vs human labels
#
# Mirrors TestExtractionJudgeCalibration but for the unified workflow judge
# in workflow_service._evaluate_checks_against_output. Fixture at
# tests/fixtures/workflow_judge_calibration.json carries human-labeled
# (check, output, gold_verdict) triples across the six check_types.
#
# Gates start looser than extraction's (κ≥0.55) because the workflow rubric
# is younger and the calibration set is smaller. Tighten as data grows.
# ---------------------------------------------------------------------------


class TestWorkflowJudgeCalibration:
    """Run the unified workflow judge against a human-labeled calibration set.

    Asserts Cohen's κ vs human ≥ 0.55 (moderate agreement on Landis-Koch) and
    PASS-vs-FAIL accuracy ≥ 0.70. Per-check_type κ is reported (not gated)."""

    def _load_calibration_cases(self) -> list[dict]:
        import json
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "fixtures" / "workflow_judge_calibration.json"
        return json.loads(fixture.read_text())["cases"]

    @staticmethod
    def _normalize_verdict(status: str) -> str:
        """Collapse 4-status workflow output to 3-class for κ vs human gold.

        Gold labels use PASS/WARN/FAIL only. NEEDS_INVESTIGATION on judge side
        is treated as WARN — same direction as the human ambiguity bin."""
        s = (status or "").upper().strip()
        if s == "NEEDS_INVESTIGATION":
            return "WARN"
        if s in ("PASS", "WARN", "FAIL"):
            return s
        return "FAIL"  # unknown / parse failure

    def _cohens_kappa(self, verdicts_a: list[str], verdicts_b: list[str]) -> float:
        if len(verdicts_a) != len(verdicts_b) or not verdicts_a:
            return 0.0
        n = len(verdicts_a)
        cats = ("PASS", "WARN", "FAIL")
        p_obs = sum(1 for a, b in zip(verdicts_a, verdicts_b) if a == b) / n
        p_exp = 0.0
        for c in cats:
            p_a = sum(1 for a in verdicts_a if a == c) / n
            p_b = sum(1 for b in verdicts_b if b == c) / n
            p_exp += p_a * p_b
        if p_exp >= 1.0:
            return 1.0
        return (p_obs - p_exp) / (1.0 - p_exp)

    def test_workflow_judge_calibration_vs_human(self):
        import asyncio
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services.workflow_service import _evaluate_checks_against_output

        # Tier-3 tests run outside the full app lifecycle. The production judge
        # resolves its model name and system config from MongoDB; inject the
        # env-var config doc in their place so the real judge_fn runs unchanged.
        sys_cfg = _system_config_doc()
        cfg_stub = MagicMock()
        cfg_stub.model_dump.return_value = sys_cfg

        cases = self._load_calibration_cases()
        sem = asyncio.Semaphore(8)

        async def _judge_one(case: dict) -> str:
            # The unified judge scores a whole check set in one call, so wrap
            # each calibration case as a single-check plan and read its status.
            description = case["description"]
            if case.get("target_field"):
                description += f" (target field: {case['target_field']})"
            plan = [{
                "id": "c1",
                "name": case.get("check_type", "check"),
                "description": description,
            }]
            async with sem:
                try:
                    results = await _evaluate_checks_against_output(
                        plan, case["workflow_output"], {}, {"user_id": ""}
                    )
                except Exception:
                    return "FAIL"
            status = results[0]["status"] if results else "FAIL"
            return self._normalize_verdict(status)

        async def _run_all() -> list[str]:
            return await asyncio.gather(*[_judge_one(c) for c in cases])

        with patch(
            "app.services.workflow_service.get_user_model_name",
            AsyncMock(return_value=_llm_model()),
        ), patch(
            "app.models.system_config.SystemConfig.get_config",
            AsyncMock(return_value=cfg_stub),
        ):
            judge_verdicts = asyncio.run(_run_all())

        gold_verdicts = [c["gold_verdict"] for c in cases]
        agree = sum(1 for a, b in zip(gold_verdicts, judge_verdicts) if a == b)
        accuracy = agree / len(gold_verdicts)
        kappa = self._cohens_kappa(gold_verdicts, judge_verdicts)

        # Per-check_type κ — surfaces which type drags the aggregate
        per_type: dict[str, list[tuple[str, str]]] = {}
        for case, jv in zip(cases, judge_verdicts):
            per_type.setdefault(case["check_type"], []).append((case["gold_verdict"], jv))

        type_lines = ["  per-check_type κ:"]
        for ctype in sorted(per_type):
            pairs = per_type[ctype]
            if len(pairs) < 2:
                type_lines.append(f"    {ctype:>14}: n={len(pairs)} (too few)")
                continue
            gold, got = zip(*pairs)
            k = self._cohens_kappa(list(gold), list(got))
            type_lines.append(f"    {ctype:>14}: κ={k:+.3f}  n={len(pairs)}")

        report = (
            f"\nWorkflow judge calibration report ({_llm_model()}):\n"
            f"  accuracy (3-class):      {accuracy:.3f}\n"
            f"  cohens kappa:            {kappa:.3f}\n"
            + "\n".join(type_lines) + "\n"
        )

        min_kappa = float(os.environ.get("WORKFLOW_JUDGE_CALIBRATION_MIN_KAPPA", "0.55"))
        min_accuracy = float(os.environ.get("WORKFLOW_JUDGE_CALIBRATION_MIN_ACCURACY", "0.70"))

        assert kappa >= min_kappa, f"Cohen's κ {kappa:.3f} < {min_kappa}. {report}"
        assert accuracy >= min_accuracy, f"Accuracy {accuracy:.3f} < {min_accuracy}. {report}"

        from app.services import judge_drift
        judge_drift.assert_no_regression("workflow", kappa)
        judge_drift.record(
            "workflow",
            judge_model=_llm_model(),
            kappa=kappa,
            accuracy=accuracy,
            n_cases=len(cases),
        )


# ---------------------------------------------------------------------------
# 7. KB judge calibration vs human labels
#
# Mirrors the extraction and workflow calibration tests. Fixture at
# tests/fixtures/kb_judge_calibration.json carries (query, expected, actual,
# retrieved_context, gold_verdict) cases stratified across query categories.
#
# Per-category κ is reported so a regression on a single rubric (e.g. the
# hallucination_trap rubric drifts after a model upgrade) surfaces even when
# the aggregate κ stays above the gate.
# ---------------------------------------------------------------------------


class TestKBJudgeCalibration:
    """Run the per-category KB judge against a human-labeled calibration set.

    Asserts Cohen's κ vs human ≥ 0.60, in-band accuracy ≥ 0.75, and a
    hallucination-trap-specific FAIL→PASS bias ≤ 0.20 — the analogue of the
    extraction judge's length-bias rate. Per-category κ is reported."""

    def _load_calibration_cases(self) -> list[dict]:
        import json
        from pathlib import Path
        fixture = Path(__file__).parent.parent / "fixtures" / "kb_judge_calibration.json"
        return json.loads(fixture.read_text())["cases"]

    @staticmethod
    def _verdict_from_score(score: float) -> str:
        if score >= 0.7:
            return "PASS"
        if score >= 0.4:
            return "WARN"
        return "FAIL"

    def _cohens_kappa(self, verdicts_a: list[str], verdicts_b: list[str]) -> float:
        if len(verdicts_a) != len(verdicts_b) or not verdicts_a:
            return 0.0
        n = len(verdicts_a)
        cats = ("PASS", "WARN", "FAIL")
        p_obs = sum(1 for a, b in zip(verdicts_a, verdicts_b) if a == b) / n
        p_exp = 0.0
        for c in cats:
            p_a = sum(1 for a in verdicts_a if a == c) / n
            p_b = sum(1 for b in verdicts_b if b == c) / n
            p_exp += p_a * p_b
        if p_exp >= 1.0:
            return 1.0
        return (p_obs - p_exp) / (1.0 - p_exp)

    def test_kb_judge_calibration_vs_human(self):
        import asyncio
        import os

        from app.services import kb_validation_service as kbs

        sys_cfg = _system_config_doc()
        kbs._active_system_config_doc.set(sys_cfg)

        cases = self._load_calibration_cases()

        async def _run_all() -> list[dict]:
            sem = asyncio.Semaphore(8)

            async def _one(case: dict) -> dict:
                async with sem:
                    return await kbs._judge_answer(
                        query=case["query"],
                        expected_answer=case["expected_answer"],
                        actual_answer=case["actual_answer"],
                        model_name=_llm_model(),
                        retrieved_context=case.get("retrieved_context") or None,
                        category=case.get("category"),
                    )
            return await asyncio.gather(*(_one(c) for c in cases))

        results = asyncio.run(_run_all())

        gold_verdicts: list[str] = []
        judge_verdicts: list[str] = []
        in_band: list[bool] = []
        hallu_trap_total = 0
        hallu_trap_passes_when_should_fail = 0

        for case, result in zip(cases, results):
            score = float(result["score"])
            judge_verdict = self._verdict_from_score(score)
            gold_verdicts.append(case["gold_verdict"])
            judge_verdicts.append(judge_verdict)
            lo, hi = case["gold_score_band"]
            in_band.append(lo <= score <= hi)
            if case["category"] == "hallucination_trap" and case["gold_verdict"] == "FAIL":
                hallu_trap_total += 1
                if judge_verdict == "PASS":
                    hallu_trap_passes_when_should_fail += 1

        accuracy = sum(1 for ok in in_band if ok) / len(in_band)
        kappa = self._cohens_kappa(gold_verdicts, judge_verdicts)
        hallu_bias_rate = (
            hallu_trap_passes_when_should_fail / hallu_trap_total
            if hallu_trap_total else 0.0
        )

        per_cat: dict[str, list[tuple[str, str]]] = {}
        for case, jv in zip(cases, judge_verdicts):
            per_cat.setdefault(case["category"], []).append((case["gold_verdict"], jv))

        cat_lines = ["  per-category κ:"]
        for cat in sorted(per_cat):
            pairs = per_cat[cat]
            if len(pairs) < 2:
                cat_lines.append(f"    {cat:>20}: n={len(pairs)} (too few)")
                continue
            gold, got = zip(*pairs)
            k = self._cohens_kappa(list(gold), list(got))
            cat_lines.append(f"    {cat:>20}: κ={k:+.3f}  n={len(pairs)}")

        report = (
            f"\nKB judge calibration report ({_llm_model()}):\n"
            f"  accuracy (in band):      {accuracy:.3f}\n"
            f"  cohens kappa:            {kappa:.3f}\n"
            f"  hallu-trap FAIL→PASS:    {hallu_bias_rate:.3f} "
            f"({hallu_trap_passes_when_should_fail}/{hallu_trap_total})\n"
            + "\n".join(cat_lines) + "\n"
        )

        min_kappa = float(os.environ.get("KB_JUDGE_CALIBRATION_MIN_KAPPA", "0.60"))
        min_accuracy = float(os.environ.get("KB_JUDGE_CALIBRATION_MIN_ACCURACY", "0.75"))
        max_hallu_bias = float(os.environ.get("KB_JUDGE_CALIBRATION_MAX_HALLU_BIAS", "0.20"))

        assert kappa >= min_kappa, f"Cohen's κ {kappa:.3f} < {min_kappa}. {report}"
        assert accuracy >= min_accuracy, f"In-band accuracy {accuracy:.3f} < {min_accuracy}. {report}"
        assert hallu_bias_rate <= max_hallu_bias, (
            f"Hallucination-trap bias rate {hallu_bias_rate:.3f} > {max_hallu_bias}. {report}"
        )

        from app.services import judge_drift
        judge_drift.assert_no_regression("kb", kappa)
        judge_drift.record(
            "kb",
            judge_model=_llm_model(),
            kappa=kappa,
            accuracy=accuracy,
            bias_metric_name="hallucination_trap_fail_to_pass",
            bias_rate=hallu_bias_rate,
            n_cases=len(cases),
        )
