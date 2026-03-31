"""Tests for app.services.workflow_validator — evaluation plan generation, check execution, and scoring.

Covers: _extract_json, _parse_checks, _parse_verdict, _resolve_model_name,
        PlanGenerator, CheckRunner (deterministic checks, step output resolution,
        field extraction, type checking, stringify), and Scorer.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.workflow_validator import (
    CheckRunner,
    PlanGenerator,
    Scorer,
    _extract_json,
    _parse_checks,
    _parse_verdict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_check(
    check_id="chk_001",
    check_type="presence",
    target_step="Extraction",
    target_field="Name",
    description="Verify Name is present",
    severity="must",
    weight=1.0,
    deterministic=True,
    validation_rule="not_empty",
    llm_prompt=None,
):
    return {
        "check_id": check_id,
        "check_type": check_type,
        "target_step": target_step,
        "target_field": target_field,
        "description": description,
        "severity": severity,
        "weight": weight,
        "deterministic": deterministic,
        "validation_rule": validation_rule,
        "llm_prompt": llm_prompt,
    }


def _make_plan(checks=None, plan_id="plan-oid"):
    plan = {
        "_id": plan_id,
        "checks": checks or [],
    }
    return plan


def _make_workflow_result(steps_output=None, final_output=None, result_id="wr-oid"):
    return {
        "_id": result_id,
        "steps_output": steps_output or {},
        "final_output": final_output or {},
    }


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json_object(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_plain_json_array(self):
        result = _extract_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_json_in_markdown_fences(self):
        text = '```json\n{"checks": []}\n```'
        result = _extract_json(text)
        assert result == {"checks": []}

    def test_json_with_leading_text(self):
        text = 'Here is the result: {"status": "PASS"}'
        result = _extract_json(text)
        assert result == {"status": "PASS"}

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json("no json here at all")

    def test_json_with_whitespace(self):
        text = '   \n  {"a": 1}  \n  '
        result = _extract_json(text)
        assert result == {"a": 1}

    def test_markdown_fences_without_language(self):
        text = '```\n[1, 2]\n```'
        result = _extract_json(text)
        assert result == [1, 2]


# ---------------------------------------------------------------------------
# _parse_checks
# ---------------------------------------------------------------------------


class TestParseChecks:
    def test_list_input(self):
        raw = [{"check_id": "chk_001", "description": "Test check"}]
        checks = _parse_checks(raw)
        assert len(checks) == 1
        assert checks[0]["check_id"] == "chk_001"

    def test_dict_with_checks_key(self):
        raw = {"checks": [{"check_id": "chk_001", "description": "Test"}]}
        checks = _parse_checks(raw)
        assert len(checks) == 1

    def test_single_dict_with_check_id(self):
        raw = {"check_id": "chk_001", "check_type": "presence", "description": "Test"}
        checks = _parse_checks(raw)
        assert len(checks) == 1
        assert checks[0]["check_type"] == "presence"

    def test_invalid_check_type_defaults_to_correctness(self):
        raw = [{"check_id": "chk_001", "check_type": "INVALID"}]
        checks = _parse_checks(raw)
        assert checks[0]["check_type"] == "correctness"

    def test_invalid_severity_defaults_to_should(self):
        raw = [{"check_id": "chk_001", "severity": "INVALID"}]
        checks = _parse_checks(raw)
        assert checks[0]["severity"] == "should"

    def test_invalid_weight_defaults_to_1(self):
        raw = [{"check_id": "chk_001", "weight": "not-a-number"}]
        checks = _parse_checks(raw)
        assert checks[0]["weight"] == 1.0

    def test_deterministic_string_true(self):
        raw = [{"check_id": "chk_001", "deterministic": "yes"}]
        checks = _parse_checks(raw)
        assert checks[0]["deterministic"] is True

    def test_deterministic_string_false(self):
        raw = [{"check_id": "chk_001", "deterministic": "no"}]
        checks = _parse_checks(raw)
        assert checks[0]["deterministic"] is False

    def test_non_dict_items_skipped(self):
        raw = [{"check_id": "chk_001"}, "not a dict", 42]
        checks = _parse_checks(raw)
        assert len(checks) == 1

    def test_empty_list_returns_empty(self):
        assert _parse_checks([]) == []

    def test_non_list_non_dict_returns_empty(self):
        assert _parse_checks("garbage") == []


# ---------------------------------------------------------------------------
# _parse_verdict
# ---------------------------------------------------------------------------


class TestParseVerdict:
    def test_valid_pass_verdict(self):
        raw = {"status": "PASS", "confidence": 0.95, "evidence": "OK", "reasoning": "Good"}
        verdict = _parse_verdict(raw)
        assert verdict["status"] == "PASS"
        assert verdict["confidence"] == 0.95

    def test_invalid_status_defaults(self):
        raw = {"status": "INVALID_STATUS"}
        verdict = _parse_verdict(raw)
        assert verdict["status"] == "NEEDS_INVESTIGATION"

    def test_confidence_clamped_high(self):
        raw = {"confidence": 5.0}
        verdict = _parse_verdict(raw)
        assert verdict["confidence"] == 1.0

    def test_confidence_clamped_low(self):
        raw = {"confidence": -1.0}
        verdict = _parse_verdict(raw)
        assert verdict["confidence"] == 0.0

    def test_invalid_confidence_defaults(self):
        raw = {"confidence": "not-a-number"}
        verdict = _parse_verdict(raw)
        assert verdict["confidence"] == 0.5

    def test_list_input_takes_first(self):
        raw = [{"status": "FAIL", "confidence": 0.8}]
        verdict = _parse_verdict(raw)
        assert verdict["status"] == "FAIL"

    def test_non_dict_returns_defaults(self):
        verdict = _parse_verdict("garbage")
        assert verdict["status"] == "NEEDS_INVESTIGATION"
        assert verdict["confidence"] == 0.5

    def test_empty_list_returns_defaults(self):
        verdict = _parse_verdict([])
        assert verdict["status"] == "NEEDS_INVESTIGATION"


# ---------------------------------------------------------------------------
# CheckRunner._stringify
# ---------------------------------------------------------------------------


class TestStringify:
    def test_none_returns_empty(self):
        assert CheckRunner._stringify(None) == ""

    def test_string_passthrough(self):
        assert CheckRunner._stringify("hello") == "hello"

    def test_list_joined(self):
        assert CheckRunner._stringify(["a", "b"]) == "a\nb"

    def test_dict_to_json(self):
        result = CheckRunner._stringify({"key": "val"})
        assert '"key"' in result
        assert '"val"' in result

    def test_number_to_string(self):
        assert CheckRunner._stringify(42) == "42"


# ---------------------------------------------------------------------------
# CheckRunner._extract_field_value
# ---------------------------------------------------------------------------


class TestExtractFieldValue:
    def test_markdown_bold_field(self):
        output = "- **Name**: John Doe\n- **Age**: 30"
        assert CheckRunner._extract_field_value(output, "Name") == "John Doe"

    def test_plain_colon_field(self):
        output = "Name: Jane Doe"
        assert CheckRunner._extract_field_value(output, "Name") == "Jane Doe"

    def test_json_quoted_field(self):
        output = '{"Name": "Bob Smith"}'
        assert CheckRunner._extract_field_value(output, "Name") == "Bob Smith"

    def test_field_name_present_in_text(self):
        output = "The Name field was found in the document."
        result = CheckRunner._extract_field_value(output, "Name")
        assert result == output

    def test_field_not_found(self):
        output = "Some unrelated text"
        assert CheckRunner._extract_field_value(output, "MissingField") is None

    def test_empty_output(self):
        assert CheckRunner._extract_field_value("", "Name") is None

    def test_empty_field_name(self):
        assert CheckRunner._extract_field_value("Name: John", "") is None


# ---------------------------------------------------------------------------
# CheckRunner._check_type
# ---------------------------------------------------------------------------


class TestCheckType:
    def test_date_yyyy_mm_dd(self):
        assert CheckRunner._check_type("2024-01-15", "date") is True

    def test_date_mm_dd_yyyy(self):
        assert CheckRunner._check_type("01/15/2024", "date") is True

    def test_date_written(self):
        assert CheckRunner._check_type("January 15, 2024", "date") is True

    def test_date_invalid(self):
        assert CheckRunner._check_type("not a date", "date") is False

    def test_number_integer(self):
        assert CheckRunner._check_type("42", "number") is True

    def test_number_with_dollar(self):
        assert CheckRunner._check_type("$1,234.56", "number") is True

    def test_number_invalid(self):
        assert CheckRunner._check_type("abc", "number") is False

    def test_email_valid(self):
        assert CheckRunner._check_type("user@example.com", "email") is True

    def test_email_invalid(self):
        assert CheckRunner._check_type("not-an-email", "email") is False

    def test_none_value(self):
        assert CheckRunner._check_type(None, "date") is False

    def test_empty_value(self):
        assert CheckRunner._check_type("", "number") is False

    def test_unknown_type_returns_true(self):
        assert CheckRunner._check_type("anything", "unknown_type") is True


# ---------------------------------------------------------------------------
# CheckRunner._run_deterministic_check
# ---------------------------------------------------------------------------


class TestRunDeterministicCheck:
    def setup_method(self):
        self.runner = CheckRunner()

    def test_not_empty_pass(self):
        check = _make_check(validation_rule="not_empty", target_field="Name")
        result = self.runner._run_deterministic_check(check, "- **Name**: John")
        assert result["status"] == "PASS"
        assert result["check_id"] == "chk_001"
        assert result["confidence"] == 1.0

    def test_not_empty_fail(self):
        check = _make_check(validation_rule="not_empty", target_field="Missing")
        result = self.runner._run_deterministic_check(check, "no match here")
        assert result["status"] == "FAIL"

    def test_regex_pass(self):
        check = _make_check(validation_rule=r"regex:\d{3}-\d{4}", target_field=None)
        result = self.runner._run_deterministic_check(check, "Call 555-1234")
        assert result["status"] == "PASS"

    def test_regex_fail(self):
        check = _make_check(validation_rule=r"regex:\d{3}-\d{4}", target_field=None)
        result = self.runner._run_deterministic_check(check, "no phone number")
        assert result["status"] == "FAIL"

    def test_regex_invalid_pattern_skipped(self):
        check = _make_check(validation_rule="regex:[invalid", target_field=None)
        result = self.runner._run_deterministic_check(check, "anything")
        assert result["status"] == "SKIPPED"

    def test_type_date_pass(self):
        check = _make_check(validation_rule="type:date", target_field=None)
        result = self.runner._run_deterministic_check(check, "2024-01-15")
        assert result["status"] == "PASS"

    def test_type_date_fail(self):
        check = _make_check(validation_rule="type:date", target_field=None)
        result = self.runner._run_deterministic_check(check, "not a date")
        assert result["status"] == "FAIL"

    def test_min_length_pass(self):
        check = _make_check(validation_rule="min_length:3", target_field=None)
        result = self.runner._run_deterministic_check(check, "hello")
        assert result["status"] == "PASS"

    def test_min_length_fail(self):
        check = _make_check(validation_rule="min_length:100", target_field=None)
        result = self.runner._run_deterministic_check(check, "short")
        assert result["status"] == "FAIL"

    def test_max_length_pass(self):
        check = _make_check(validation_rule="max_length:10", target_field=None)
        result = self.runner._run_deterministic_check(check, "short")
        assert result["status"] == "PASS"

    def test_max_length_fail(self):
        check = _make_check(validation_rule="max_length:3", target_field=None)
        result = self.runner._run_deterministic_check(check, "this is too long")
        assert result["status"] == "FAIL"

    def test_unknown_rule_skipped(self):
        check = _make_check(validation_rule="unknown_rule")
        result = self.runner._run_deterministic_check(check, "anything")
        assert result["status"] == "SKIPPED"
        assert "Unknown rule" in result["reasoning"]


# ---------------------------------------------------------------------------
# CheckRunner._resolve_step_output & _collect_step_outputs
# ---------------------------------------------------------------------------


class TestStepOutputResolution:
    def setup_method(self):
        self.runner = CheckRunner()

    def test_collect_step_outputs_dict(self):
        wr = _make_workflow_result(steps_output={"Step1": {"output": "result1"}})
        outputs = self.runner._collect_step_outputs(wr)
        assert outputs["Step1"] == "result1"

    def test_collect_step_outputs_string(self):
        wr = _make_workflow_result(steps_output={"Step1": "plain string"})
        outputs = self.runner._collect_step_outputs(wr)
        assert outputs["Step1"] == "plain string"

    def test_collect_step_outputs_none(self):
        wr = _make_workflow_result(steps_output=None)
        outputs = self.runner._collect_step_outputs(wr)
        assert outputs == {}

    def test_resolve_exact_match(self):
        step_outputs = {"Extraction": "data"}
        check = _make_check(target_step="Extraction")
        result = self.runner._resolve_step_output(check, step_outputs, "fallback")
        assert result == "data"

    def test_resolve_case_insensitive_match(self):
        step_outputs = {"Extraction": "data"}
        check = _make_check(target_step="extraction")
        result = self.runner._resolve_step_output(check, step_outputs, "fallback")
        assert result == "data"

    def test_resolve_falls_back_to_final_output(self):
        step_outputs = {"Extraction": "data"}
        check = _make_check(target_step="NonExistent")
        result = self.runner._resolve_step_output(check, step_outputs, "fallback")
        assert result == "fallback"

    def test_get_final_output(self):
        wr = _make_workflow_result(final_output={"output": "final text"})
        result = self.runner._get_final_output(wr)
        assert result == "final text"

    def test_get_final_output_empty(self):
        wr = _make_workflow_result(final_output=None)
        result = self.runner._get_final_output(wr)
        assert result == ""


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class TestScorer:
    def setup_method(self):
        self.scorer = Scorer()

    def test_all_pass_grade_a(self):
        checks = [_make_check(check_id="c1", weight=1.0, severity="must")]
        results = [{"check_id": "c1", "status": "PASS"}]
        score, grade = self.scorer.score(results, checks)
        assert score == 100.0
        assert grade == "A"

    def test_all_fail_grade_f(self):
        checks = [_make_check(check_id="c1", weight=1.0, severity="should")]
        results = [{"check_id": "c1", "status": "FAIL"}]
        score, grade = self.scorer.score(results, checks)
        assert score == 0.0
        assert grade == "F"

    def test_must_fail_caps_at_59(self):
        checks = [
            _make_check(check_id="c1", weight=1.0, severity="must"),
            _make_check(check_id="c2", weight=1.0, severity="should"),
        ]
        # c1 fails (must), c2 passes
        results = [
            {"check_id": "c1", "status": "FAIL"},
            {"check_id": "c2", "status": "PASS"},
        ]
        score, grade = self.scorer.score(results, checks)
        # Without cap would be 50.0, but must-fail caps at 59 (50 < 59 so stays 50)
        assert score == 50.0
        assert grade == "F"

    def test_must_fail_caps_high_score(self):
        checks = [
            _make_check(check_id="c1", weight=1.0, severity="must"),
            _make_check(check_id="c2", weight=5.0, severity="should"),
            _make_check(check_id="c3", weight=5.0, severity="should"),
        ]
        results = [
            {"check_id": "c1", "status": "FAIL"},
            {"check_id": "c2", "status": "PASS"},
            {"check_id": "c3", "status": "PASS"},
        ]
        # Without cap: 10/11 * 100 = ~90.9, but must-fail caps at 59
        score, grade = self.scorer.score(results, checks)
        assert score <= 59.0
        assert grade == "F"

    def test_warn_gets_half_credit(self):
        checks = [_make_check(check_id="c1", weight=2.0, severity="should")]
        results = [{"check_id": "c1", "status": "WARN"}]
        score, grade = self.scorer.score(results, checks)
        assert score == 50.0

    def test_skipped_excluded_from_total(self):
        checks = [
            _make_check(check_id="c1", weight=1.0, severity="should"),
            _make_check(check_id="c2", weight=1.0, severity="should"),
        ]
        results = [
            {"check_id": "c1", "status": "PASS"},
            {"check_id": "c2", "status": "SKIPPED"},
        ]
        score, grade = self.scorer.score(results, checks)
        assert score == 100.0
        assert grade == "A"

    def test_no_checks_score_zero(self):
        score, grade = self.scorer.score([], [])
        assert score == 0.0
        assert grade == "F"

    def test_grade_b(self):
        checks = [
            _make_check(check_id=f"c{i}", weight=1.0, severity="should")
            for i in range(10)
        ]
        # 8 pass, 2 fail => 80%
        results = [
            {"check_id": f"c{i}", "status": "PASS" if i < 8 else "FAIL"}
            for i in range(10)
        ]
        score, grade = self.scorer.score(results, checks)
        assert grade == "B"

    def test_grade_c(self):
        checks = [
            _make_check(check_id=f"c{i}", weight=1.0, severity="should")
            for i in range(10)
        ]
        # 7 pass, 3 fail => 70%
        results = [
            {"check_id": f"c{i}", "status": "PASS" if i < 7 else "FAIL"}
            for i in range(10)
        ]
        score, grade = self.scorer.score(results, checks)
        assert grade == "C"

    def test_grade_d(self):
        checks = [
            _make_check(check_id=f"c{i}", weight=1.0, severity="should")
            for i in range(10)
        ]
        # 6 pass, 4 fail => 60%
        results = [
            {"check_id": f"c{i}", "status": "PASS" if i < 6 else "FAIL"}
            for i in range(10)
        ]
        score, grade = self.scorer.score(results, checks)
        assert grade == "D"

    def test_weighted_scoring(self):
        checks = [
            _make_check(check_id="c1", weight=3.0, severity="should"),
            _make_check(check_id="c2", weight=1.0, severity="should"),
        ]
        results = [
            {"check_id": "c1", "status": "PASS"},
            {"check_id": "c2", "status": "FAIL"},
        ]
        score, grade = self.scorer.score(results, checks)
        # 3/4 * 100 = 75
        assert score == 75.0
        assert grade == "C"


# ---------------------------------------------------------------------------
# _resolve_model_name
# ---------------------------------------------------------------------------


class TestResolveModelName:
    @patch("app.services.workflow_validator._get_db")
    def test_returns_user_model_if_configured(self, mock_get_db):
        db = MagicMock()
        db.user_model_config.find_one.return_value = {"user_id": "u1", "name": "gpt-4"}
        db.system_config.find_one.return_value = {}
        mock_get_db.return_value = db

        from app.services.workflow_validator import _resolve_model_name
        result = _resolve_model_name("u1")
        assert result == "gpt-4"

    @patch("app.services.workflow_validator._get_db")
    def test_falls_back_to_system_default(self, mock_get_db):
        db = MagicMock()
        db.user_model_config.find_one.return_value = None
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "claude-3"}]
        }
        mock_get_db.return_value = db

        from app.services.workflow_validator import _resolve_model_name
        result = _resolve_model_name("u1")
        assert result == "claude-3"

    @patch("app.services.workflow_validator._get_db")
    def test_returns_empty_when_no_models(self, mock_get_db):
        db = MagicMock()
        db.user_model_config.find_one.return_value = None
        db.system_config.find_one.return_value = {}
        mock_get_db.return_value = db

        from app.services.workflow_validator import _resolve_model_name
        result = _resolve_model_name(None)
        assert result == ""


# ---------------------------------------------------------------------------
# CheckRunner.run — integration of deterministic checks
# ---------------------------------------------------------------------------


class TestCheckRunnerRun:
    @patch("app.services.workflow_validator._resolve_model_name", return_value="test-model")
    @patch("app.services.workflow_validator._get_db")
    def test_run_deterministic_only(self, mock_get_db, mock_resolve):
        db = MagicMock()
        insert_result = MagicMock()
        insert_result.inserted_id = "run-oid"
        db.evaluation_run.insert_one.return_value = insert_result
        mock_get_db.return_value = db

        checks = [
            _make_check(check_id="c1", validation_rule="not_empty", target_field=None, deterministic=True),
        ]
        plan = _make_plan(checks=checks)
        wr = _make_workflow_result(
            steps_output={"Extraction": {"output": "Some content"}},
            final_output={"output": "final"},
        )

        runner = CheckRunner()
        result = runner.run(plan, wr, user_id="u1")

        assert result["status"] == "completed"
        assert result["num_passed"] == 1
        assert result["num_failed"] == 0
        assert result["grade"] == "A"
        db.evaluation_run.update_one.assert_called_once()

    @patch("app.services.workflow_validator.get_agent_model")
    @patch("app.services.workflow_validator.Agent")
    @patch("app.services.workflow_validator._resolve_model_name", return_value="test-model")
    @patch("app.services.workflow_validator._get_db")
    def test_run_llm_check_failure_skipped(self, mock_get_db, mock_resolve, mock_agent_cls, mock_get_model):
        """When an LLM check raises an exception, the result should be SKIPPED."""
        db = MagicMock()
        insert_result = MagicMock()
        insert_result.inserted_id = "run-oid"
        db.evaluation_run.insert_one.return_value = insert_result
        mock_get_db.return_value = db

        # Make the agent raise an error
        mock_agent_instance = MagicMock()
        mock_agent_instance.run_sync.side_effect = RuntimeError("LLM unavailable")
        mock_agent_cls.return_value = mock_agent_instance

        checks = [
            _make_check(check_id="llm1", deterministic=False, llm_prompt="Check this"),
        ]
        plan = _make_plan(checks=checks)
        wr = _make_workflow_result(
            steps_output={"Extraction": {"output": "data"}},
            final_output={"output": "final"},
        )

        runner = CheckRunner()
        result = runner.run(plan, wr, user_id="u1")

        assert result["status"] == "completed"
        assert result["num_skipped"] == 1
        assert result["num_passed"] == 0


# ---------------------------------------------------------------------------
# PlanGenerator._build_workflow_description
# ---------------------------------------------------------------------------


class TestBuildWorkflowDescription:
    def test_builds_description_with_steps(self):
        db = MagicMock()
        step_doc = {
            "_id": "step1",
            "name": "Extract Info",
            "tasks": ["task1"],
        }
        task_doc = {
            "_id": "task1",
            "name": "Extraction",
            "data": {"searchphrases": "Name, Age, Email"},
        }
        db.workflow_step.find_one.return_value = step_doc
        db.workflow_step_task.find_one.return_value = task_doc

        workflow = {
            "name": "Test Workflow",
            "description": "A test workflow",
            "steps": ["step1"],
        }

        gen = PlanGenerator()
        desc = gen._build_workflow_description(workflow, db)

        assert "Test Workflow" in desc
        assert "Extract Info" in desc
        assert "Name, Age, Email" in desc

    def test_handles_missing_steps(self):
        db = MagicMock()
        db.workflow_step.find_one.return_value = None

        workflow = {
            "name": "Empty Workflow",
            "description": None,
            "steps": ["nonexistent"],
        }

        gen = PlanGenerator()
        desc = gen._build_workflow_description(workflow, db)
        assert "Empty Workflow" in desc
        assert "N/A" in desc


# ---------------------------------------------------------------------------
# PlanGenerator._get_extraction_keys
# ---------------------------------------------------------------------------


class TestGetExtractionKeys:
    def test_from_searchphrases(self):
        gen = PlanGenerator()
        task = {"data": {"searchphrases": "Name, Age, Email"}}
        keys = gen._get_extraction_keys(task, MagicMock())
        assert keys == ["Name", "Age", "Email"]

    def test_from_search_set(self):
        gen = PlanGenerator()
        db = MagicMock()
        db.search_set.find_one.return_value = {"uuid": "ss1"}
        db.search_set_item.find.return_value = [
            {"searchphrase": "Title", "searchset": "ss1", "searchtype": "extraction"},
            {"searchphrase": "Author", "searchset": "ss1", "searchtype": "extraction"},
        ]
        task = {"data": {"search_set_uuid": "ss1"}}
        keys = gen._get_extraction_keys(task, db)
        assert keys == ["Title", "Author"]

    def test_empty_data(self):
        gen = PlanGenerator()
        task = {"data": {}}
        keys = gen._get_extraction_keys(task, MagicMock())
        assert keys == []


# ---------------------------------------------------------------------------
# PlanGenerator._build_baseline_checks
# ---------------------------------------------------------------------------


class TestBuildBaselineChecks:
    def test_creates_presence_checks_for_extraction_fields(self):
        db = MagicMock()
        db.workflow_step.find_one.return_value = {
            "_id": "s1",
            "name": "Extraction Step",
            "tasks": ["t1"],
        }
        db.workflow_step_task.find_one.return_value = {
            "_id": "t1",
            "name": "Extraction",
            "data": {"searchphrases": "Name, Age"},
        }

        workflow = {"steps": ["s1"]}
        gen = PlanGenerator()
        baseline = gen._build_baseline_checks(workflow, db, existing_ids=set())

        assert len(baseline) == 2
        assert baseline[0]["check_type"] == "presence"
        assert baseline[0]["target_field"] == "Name"
        assert baseline[0]["severity"] == "must"
        assert baseline[0]["deterministic"] is True
        assert baseline[1]["target_field"] == "Age"

    def test_skips_existing_ids(self):
        db = MagicMock()
        db.workflow_step.find_one.return_value = {
            "_id": "s1",
            "name": "Step",
            "tasks": ["t1"],
        }
        db.workflow_step_task.find_one.return_value = {
            "_id": "t1",
            "name": "Extraction",
            "data": {"searchphrases": "Name"},
        }

        workflow = {"steps": ["s1"]}
        gen = PlanGenerator()
        baseline = gen._build_baseline_checks(workflow, db, existing_ids={"chk_900"})
        assert len(baseline) == 0

    def test_skips_non_extraction_tasks(self):
        db = MagicMock()
        db.workflow_step.find_one.return_value = {
            "_id": "s1",
            "name": "Step",
            "tasks": ["t1"],
        }
        db.workflow_step_task.find_one.return_value = {
            "_id": "t1",
            "name": "Prompt",
            "data": {"prompt": "Do something"},
        }

        workflow = {"steps": ["s1"]}
        gen = PlanGenerator()
        baseline = gen._build_baseline_checks(workflow, db, existing_ids=set())
        assert len(baseline) == 0
