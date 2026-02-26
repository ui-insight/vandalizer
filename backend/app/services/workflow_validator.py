"""Workflow self-validation system.

Generates evaluation plans from workflow definitions, runs checks against
workflow outputs, and scores/grades the results.

Ported from Flask app/utilities/workflow_validator.py.
Uses pymongo (sync) for DB access — safe for Celery workers.
"""

import datetime
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
from uuid import uuid4

from pydantic_ai import Agent

from app.services.llm_service import get_agent_model

# ---------------------------------------------------------------------------
# Constants & JSON parsing helpers
# ---------------------------------------------------------------------------

VALID_CHECK_TYPES = {"presence", "format", "constraints", "completeness", "correctness", "hallucination"}
VALID_SEVERITIES = {"must", "should", "nice"}


def _get_db():
    from pymongo import MongoClient

    mongo_host = os.environ.get("MONGO_HOST", "mongodb://localhost:27017/")
    mongo_db = os.environ.get("MONGO_DB", "osp")
    return MongoClient(mongo_host)[mongo_db]


def _resolve_model_name(user_id: str | None = None) -> str:
    """Resolve model name using user config, falling back to system default."""
    db = _get_db()
    if user_id:
        user_config = db.user_model_config.find_one({"user_id": user_id})
        if user_config and user_config.get("name"):
            return user_config["name"]
    sys_cfg = db.system_config.find_one() or {}
    models = sys_cfg.get("available_models", [])
    if models and isinstance(models[0], dict):
        return models[0].get("name", "")
    return ""


def _extract_json(text: str) -> dict | list:
    """Extract JSON from LLM text output, handling markdown fences."""
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for i, ch in enumerate(text):
        if ch in ("{", "["):
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not extract JSON from LLM output: {text[:200]}")


def _parse_checks(raw: dict | list) -> list[dict]:
    """Normalise LLM output into a list of check dicts."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("checks", [raw] if "check_id" in raw or "description" in raw else [])
        if isinstance(items, dict):
            items = [items]
    else:
        return []

    checks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        check_type = str(item.get("check_type", "correctness")).lower().strip()
        if check_type not in VALID_CHECK_TYPES:
            check_type = "correctness"
        severity = str(item.get("severity", "should")).lower().strip()
        if severity not in VALID_SEVERITIES:
            severity = "should"
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        det = item.get("deterministic", False)
        deterministic = det if isinstance(det, bool) else str(det).lower().strip() in ("true", "1", "yes")

        checks.append({
            "check_id": str(item.get("check_id", "")),
            "check_type": check_type,
            "target_step": str(item.get("target_step", "")),
            "target_field": item.get("target_field"),
            "description": str(item.get("description", "")),
            "severity": severity,
            "weight": weight,
            "deterministic": deterministic,
            "validation_rule": item.get("validation_rule"),
            "llm_prompt": item.get("llm_prompt"),
        })
    return checks


def _parse_verdict(raw: dict | list) -> dict:
    """Normalise LLM output into a verdict dict."""
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raw = {}

    status = str(raw.get("status", "NEEDS_INVESTIGATION")).upper().strip()
    if status not in ("PASS", "FAIL", "WARN", "NEEDS_INVESTIGATION", "SKIPPED"):
        status = "NEEDS_INVESTIGATION"

    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        confidence = 0.5

    return {
        "status": status,
        "confidence": confidence,
        "evidence": str(raw.get("evidence", "")),
        "reasoning": str(raw.get("reasoning", "")),
        "fix_suggestion": str(raw.get("fix_suggestion", "") or ""),
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_GENERATION_SYSTEM_PROMPT = """\
You are an evaluation plan generator for automated document-processing workflows.
Given a workflow description (its steps, extraction fields, and prompts), generate
a set of concrete validation checks that define what "good output" means.

CHECK TYPES:
- presence: Verify a field or output section exists and is non-empty.
- format: Verify output matches an expected format (date, currency, email, etc.).
- constraints: Verify output meets constraints (length, numeric range, etc.).
- completeness: Verify all expected fields/sections are present in the output.
- correctness: Verify output content is reasonable and internally consistent.
- hallucination: Verify output does not contain fabricated or unsupported claims.

SEVERITY LEVELS:
- must: Critical. Failure means the output is invalid.
- should: Important. Failure significantly impacts quality.
- nice: Optional. Failure is noted but minor.

RULES:
- Prefer deterministic checks (set deterministic=true, provide validation_rule)
  whenever the check can be done without an LLM (e.g. field existence, regex).
- For semantic checks, set deterministic=false and provide a clear llm_prompt.
- Each check_id must be unique (e.g. chk_001, chk_002, ...).
- target_step must match one of the workflow step names provided.
- weight should be 1.0 by default; increase for more important checks.

You MUST respond with ONLY a JSON object (no markdown, no extra text). Example:
{"checks": [{"check_id": "chk_001", "check_type": "presence", "target_step": "Extraction", "target_field": "Name", "description": "Verify Name is present", "severity": "must", "weight": 1.0, "deterministic": true, "validation_rule": "not_empty", "llm_prompt": null}]}
"""

CHECK_EVALUATION_SYSTEM_PROMPT = """\
You are a quality evaluator for automated workflow outputs.
You will be given a validation check description and the workflow output to evaluate.

Evaluate the check and return your verdict.

You MUST respond with ONLY a JSON object (no markdown, no extra text). Example:
{"status": "PASS", "confidence": 0.95, "evidence": "The field contains a valid value", "reasoning": "The check is satisfied because...", "fix_suggestion": ""}

Rules for status:
- PASS: the check is fully satisfied
- FAIL: clearly not met
- WARN: partially met or minor issue
- NEEDS_INVESTIGATION: uncertain

Be strict but fair. Only mark PASS if the check is clearly satisfied.
"""


# ---------------------------------------------------------------------------
# PlanGenerator
# ---------------------------------------------------------------------------


class PlanGenerator:
    """Generates an EvaluationPlan from a Workflow definition using the system LLM."""

    COVERAGE_TARGETS = {
        "quick": (3, 5),
        "standard": (8, 15),
        "exhaustive": (15, 30),
    }

    def generate(
        self,
        workflow_id: str,
        coverage_level: str = "standard",
        user_id: str | None = None,
    ) -> dict:
        """Generate and persist an evaluation plan.

        Returns the plan document dict (with _id set by MongoDB).
        """
        from bson import ObjectId

        db = _get_db()
        workflow = db.workflow.find_one({"_id": ObjectId(workflow_id)})
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        workflow_description = self._build_workflow_description(workflow, db)
        min_checks, max_checks = self.COVERAGE_TARGETS.get(coverage_level, (8, 15))

        user_prompt = (
            f"Coverage level: {coverage_level}\n"
            f"Generate between {min_checks} and {max_checks} checks.\n\n"
            f"Workflow description:\n{workflow_description}"
        )

        model_name = _resolve_model_name(user_id)
        model = get_agent_model(model_name)

        agent = Agent(model, system_prompt=PLAN_GENERATION_SYSTEM_PROMPT)
        result = agent.run_sync(user_prompt)
        raw = _extract_json(result.output)
        checks = _parse_checks(raw)

        # Inject baseline deterministic checks
        existing_ids = {c["check_id"] for c in checks}
        baseline = self._build_baseline_checks(workflow, db, existing_ids)
        checks.extend(baseline)

        plan = {
            "uuid": uuid4().hex,
            "workflow": workflow["_id"],
            "coverage_level": coverage_level,
            "model_used": model_name,
            "checks": checks,
            "num_checks": len(checks),
            "created_by_user_id": user_id or "",
            "created_at": datetime.datetime.now(timezone.utc),
        }
        result = db.evaluation_plan.insert_one(plan)
        plan["_id"] = result.inserted_id
        return plan

    def _build_workflow_description(self, workflow: dict, db) -> str:
        lines = [
            f"Workflow: {workflow.get('name', '')}",
            f"Description: {workflow.get('description') or 'N/A'}",
            f"Number of steps: {len(workflow.get('steps', []))}",
            "",
        ]

        for idx, step_id in enumerate(workflow.get("steps", []), start=1):
            step = db.workflow_step.find_one({"_id": step_id})
            if not step:
                continue
            lines.append(f"Step {idx}: {step.get('name', '')}")

            tasks = []
            for task_id in step.get("tasks", []):
                task = db.workflow_step_task.find_one({"_id": task_id})
                if task:
                    tasks.append(task)

            if not tasks:
                lines.append("  (no tasks)")
                continue

            for task in tasks:
                lines.append(f"  Task: {task.get('name', '')}")
                if task.get("name") == "Extraction":
                    keys = self._get_extraction_keys(task, db)
                    if keys:
                        lines.append(f"    Extraction fields: {', '.join(keys)}")
                elif task.get("name") == "Prompt":
                    prompt_text = task.get("data", {}).get("prompt", "")
                    if prompt_text:
                        lines.append(f"    Prompt: {prompt_text[:200]}")
            lines.append("")

        return "\n".join(lines)

    def _get_extraction_keys(self, task: dict, db) -> list[str]:
        data = task.get("data", {})
        if data.get("search_set_uuid"):
            ss = db.search_set.find_one({"uuid": data["search_set_uuid"]})
            if ss:
                items = list(db.search_set_item.find({
                    "searchset": data["search_set_uuid"],
                    "searchtype": "extraction",
                }))
                return [item["searchphrase"] for item in items]
        if data.get("searchphrases"):
            return [p.strip() for p in data["searchphrases"].split(",")]
        return []

    def _build_baseline_checks(self, workflow: dict, db, existing_ids: set[str]) -> list[dict]:
        baseline = []
        counter = 900

        for step_id in workflow.get("steps", []):
            step = db.workflow_step.find_one({"_id": step_id})
            if not step:
                continue
            for task_id in step.get("tasks", []):
                task = db.workflow_step_task.find_one({"_id": task_id})
                if not task or task.get("name") != "Extraction":
                    continue
                keys = self._get_extraction_keys(task, db)
                for key in keys:
                    check_id = f"chk_{counter}"
                    counter += 1
                    if check_id in existing_ids:
                        continue
                    baseline.append({
                        "check_id": check_id,
                        "check_type": "presence",
                        "target_step": step.get("name", ""),
                        "target_field": key,
                        "description": f"Verify '{key}' is present and non-empty in {step.get('name', '')} output",
                        "severity": "must",
                        "weight": 1.0,
                        "deterministic": True,
                        "validation_rule": "not_empty",
                        "llm_prompt": None,
                    })
        return baseline


# ---------------------------------------------------------------------------
# CheckRunner
# ---------------------------------------------------------------------------


class CheckRunner:
    """Runs an EvaluationPlan against a WorkflowResult."""

    MAX_LLM_WORKERS = 4

    def run(
        self,
        plan: dict,
        workflow_result: dict,
        user_id: str | None = None,
    ) -> dict:
        """Execute evaluation plan and persist EvaluationRun.

        Returns the evaluation run document dict.
        """
        db = _get_db()
        now = datetime.datetime.now(timezone.utc)

        evaluation_run = {
            "uuid": uuid4().hex,
            "plan": plan["_id"],
            "workflow_result": workflow_result["_id"],
            "status": "running",
            "started_at": now,
            "created_by_user_id": user_id or "",
            "created_at": now,
        }
        result = db.evaluation_run.insert_one(evaluation_run)
        evaluation_run["_id"] = result.inserted_id

        model_name = _resolve_model_name(user_id)
        step_outputs = self._collect_step_outputs(workflow_result)
        final_output = self._get_final_output(workflow_result)

        check_results = []
        deterministic_checks = []
        llm_checks = []

        for check in plan.get("checks", []):
            if check.get("deterministic", False):
                deterministic_checks.append(check)
            else:
                llm_checks.append(check)

        for check in deterministic_checks:
            step_output = self._resolve_step_output(check, step_outputs, final_output)
            check_results.append(self._run_deterministic_check(check, step_output))

        if llm_checks:
            worker_count = min(len(llm_checks), self.MAX_LLM_WORKERS)
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {}
                for check in llm_checks:
                    step_output = self._resolve_step_output(check, step_outputs, final_output)
                    future = executor.submit(self._run_llm_check, check, step_output, model_name)
                    futures[future] = check

                for future in as_completed(futures):
                    check = futures[future]
                    try:
                        check_results.append(future.result())
                    except Exception as e:
                        check_results.append({
                            "check_id": check.get("check_id", "unknown"),
                            "status": "SKIPPED",
                            "confidence": 0.0,
                            "evidence": "",
                            "reasoning": f"Check execution error: {e}",
                            "fix_suggestion": "",
                        })

        scorer = Scorer()
        score, grade = scorer.score(check_results, plan.get("checks", []))

        num_passed = sum(1 for r in check_results if r["status"] == "PASS")
        num_failed = sum(1 for r in check_results if r["status"] == "FAIL")
        num_warned = sum(1 for r in check_results if r["status"] in ("WARN", "NEEDS_INVESTIGATION"))
        num_skipped = sum(1 for r in check_results if r["status"] == "SKIPPED")

        # Enrich results
        checks_by_id = {c.get("check_id"): c for c in plan.get("checks", [])}
        for result_item in check_results:
            plan_check = checks_by_id.get(result_item.get("check_id"), {})
            result_item.setdefault("description", plan_check.get("description", ""))
            result_item.setdefault("severity", plan_check.get("severity", ""))

        db.evaluation_run.update_one(
            {"_id": evaluation_run["_id"]},
            {
                "$set": {
                    "check_results": check_results,
                    "overall_score": score,
                    "grade": grade,
                    "num_passed": num_passed,
                    "num_failed": num_failed,
                    "num_warned": num_warned,
                    "num_skipped": num_skipped,
                    "model_used": model_name,
                    "status": "completed",
                    "finished_at": datetime.datetime.now(timezone.utc),
                }
            },
        )

        evaluation_run.update({
            "check_results": check_results,
            "overall_score": score,
            "grade": grade,
            "num_passed": num_passed,
            "num_failed": num_failed,
            "num_warned": num_warned,
            "num_skipped": num_skipped,
            "status": "completed",
        })
        return evaluation_run

    def _collect_step_outputs(self, workflow_result: dict) -> dict[str, str]:
        outputs = {}
        for step_name, step_data in (workflow_result.get("steps_output") or {}).items():
            if isinstance(step_data, dict):
                raw = step_data.get("output", "")
            else:
                raw = step_data
            outputs[step_name] = self._stringify(raw)
        return outputs

    def _get_final_output(self, workflow_result: dict) -> str:
        final = workflow_result.get("final_output") or {}
        return self._stringify(final.get("output", ""))

    def _resolve_step_output(self, check: dict, step_outputs: dict, final_output: str) -> str:
        target_step = check.get("target_step", "")
        if target_step in step_outputs:
            return step_outputs[target_step]
        for name, output in step_outputs.items():
            if name.lower() == target_step.lower():
                return output
        return final_output

    @staticmethod
    def _stringify(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return "\n".join(str(v) for v in value)
        if isinstance(value, dict):
            return json.dumps(value, indent=2, default=str)
        return str(value)

    def _run_deterministic_check(self, check: dict, step_output: str) -> dict:
        rule = check.get("validation_rule", "not_empty")
        target_field = check.get("target_field")
        check_id = check.get("check_id", "unknown")

        value = step_output
        if target_field:
            value = self._extract_field_value(step_output, target_field)

        passed = False
        reason = ""

        if rule == "not_empty":
            passed = value is not None and str(value).strip() != ""
            reason = "non-empty" if passed else "empty or missing"
        elif rule.startswith("regex:"):
            pattern = rule.split("regex:", 1)[1]
            try:
                passed = bool(re.search(pattern, str(value or "")))
                reason = f"regex '{pattern}' {'matched' if passed else 'did not match'}"
            except re.error as e:
                return {"check_id": check_id, "status": "SKIPPED", "confidence": 0.0, "evidence": "", "reasoning": f"Invalid regex: {e}", "fix_suggestion": ""}
        elif rule.startswith("type:"):
            type_name = rule.split("type:", 1)[1]
            passed = self._check_type(value, type_name)
            reason = f"type check '{type_name}' {'passed' if passed else 'failed'}"
        elif rule.startswith("min_length:"):
            min_len = int(rule.split("min_length:", 1)[1])
            actual = len(str(value or ""))
            passed = actual >= min_len
            reason = f"length {actual} {'>='}  {min_len}" if passed else f"length {actual} < {min_len}"
        elif rule.startswith("max_length:"):
            max_len = int(rule.split("max_length:", 1)[1])
            actual = len(str(value or ""))
            passed = actual <= max_len
            reason = f"length {actual} <= {max_len}" if passed else f"length {actual} > {max_len}"
        else:
            return {"check_id": check_id, "status": "SKIPPED", "confidence": 0.0, "evidence": "", "reasoning": f"Unknown rule: {rule}", "fix_suggestion": ""}

        snippet = str(value or "")[:200]
        return {
            "check_id": check_id,
            "status": "PASS" if passed else "FAIL",
            "confidence": 1.0,
            "evidence": f"Value: {snippet}" if value else "No value found",
            "reasoning": f"Deterministic check '{rule}': {reason}",
            "fix_suggestion": "" if passed else f"Ensure {target_field or 'output'} satisfies '{rule}'",
        }

    @staticmethod
    def _extract_field_value(output: str, field_name: str) -> str | None:
        if not output or not field_name:
            return None

        pattern = rf"-\s*\*\*{re.escape(field_name)}\*\*:\s*(.*)"
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        pattern = rf"{re.escape(field_name)}:\s*(.*)"
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        pattern = rf'"{re.escape(field_name)}"\s*:\s*"([^"]*)"'
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        if field_name.lower() in output.lower():
            return output

        return None

    @staticmethod
    def _check_type(value: str | None, type_name: str) -> bool:
        if value is None or str(value).strip() == "":
            return False
        val = str(value).strip()
        if type_name == "date":
            date_patterns = [r"\d{4}-\d{2}-\d{2}", r"\d{2}/\d{2}/\d{4}", r"\d{2}-\d{2}-\d{4}", r"[A-Z][a-z]+ \d{1,2},? \d{4}"]
            return any(re.search(p, val) for p in date_patterns)
        if type_name == "number":
            cleaned = val.replace(",", "").replace("$", "").replace("%", "").strip()
            try:
                float(cleaned)
                return True
            except ValueError:
                return False
        if type_name == "email":
            return bool(re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", val))
        return True

    def _run_llm_check(self, check: dict, step_output: str, model_name: str) -> dict:
        check_id = check.get("check_id", "unknown")
        description = check.get("description", "")
        llm_prompt = check.get("llm_prompt", "")
        check_type = check.get("check_type", "")

        prompt = f"Check to evaluate:\n  Type: {check_type}\n  Description: {description}\n"
        if llm_prompt:
            prompt += f"  Specific instruction: {llm_prompt}\n"
        prompt += f"\nWorkflow output to evaluate:\n---\n{step_output[:5000]}\n---"

        model = get_agent_model(model_name)
        agent = Agent(model, system_prompt=CHECK_EVALUATION_SYSTEM_PROMPT)
        result = agent.run_sync(prompt)
        raw = _extract_json(result.output)
        verdict = _parse_verdict(raw)
        verdict["check_id"] = check_id
        return verdict


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class Scorer:
    """Aggregates check results into an overall score and grade."""

    GRADE_BANDS = [("A", 90, 100), ("B", 80, 89), ("C", 70, 79), ("D", 60, 69), ("F", 0, 59)]

    def score(self, check_results: list[dict], checks: list[dict]) -> tuple[float, str]:
        checks_by_id = {c["check_id"]: c for c in checks}

        total_weight = 0.0
        earned_weight = 0.0
        must_failed = False

        for result in check_results:
            check = checks_by_id.get(result["check_id"], {})
            weight = float(check.get("weight", 1.0))
            severity = check.get("severity", "should")
            status = result["status"]

            if status == "SKIPPED":
                continue

            total_weight += weight

            if status == "PASS":
                earned_weight += weight
            elif status == "WARN":
                earned_weight += weight * 0.5
            elif status == "FAIL" and severity == "must":
                must_failed = True

        if total_weight == 0:
            final_score = 0.0
        else:
            final_score = (earned_weight / total_weight) * 100

        if must_failed:
            final_score = min(final_score, 59.0)

        grade = "F"
        for label, low, high in self.GRADE_BANDS:
            if low <= final_score <= high:
                grade = label
                break

        return round(final_score, 1), grade
