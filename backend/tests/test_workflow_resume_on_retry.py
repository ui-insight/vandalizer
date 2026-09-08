"""A retried workflow resumes; it does not re-execute what already succeeded.

`execute_workflow_task` carries `autoretry_for=TRANSIENT_EXCEPTIONS,
max_retries=3` and had no resume index, so a provider read timeout on step 4
restarted the whole workflow from step 0 — up to three more times. An
`APICallNode` POST on step 2 fired four times, a `save_to_folder` wrote four
copies, and the tokens for every earlier step were billed four times over.

The engine has supported resuming since the approval gate was built
(`start_index` / `initial_output`). These tests cover the decision of *where*
to pick up, which is the part that can be wrong in a way nobody notices until
a side effect has already fired twice.
"""

from unittest.mock import MagicMock

from app.tasks.workflow_tasks import _resume_point


def _engine(keys: list[str]) -> MagicMock:
    engine = MagicMock()
    engine.step_output_keys.return_value = keys
    return engine


KEYS = ["Document", "Extract", "Call API", "Format"]


class TestResumePoint:
    def test_resumes_after_the_last_completed_step(self):
        """num_steps_completed is the index of the step that finished, so the
        next pass starts one past it and is fed that step's output."""
        start, initial = _resume_point(
            _engine(KEYS),
            {
                "num_steps_completed": 1,
                "steps_output": {"Extract": {"output": "extracted", "step_name": "Extraction"}},
            },
        )
        assert start == 2
        assert initial == {"output": "extracted", "step_name": "Extraction"}

    def test_no_completed_steps_means_a_full_rerun(self):
        assert _resume_point(_engine(KEYS), {}) == (0, None)
        assert _resume_point(
            _engine(KEYS), {"num_steps_completed": 0, "steps_output": {}},
        ) == (0, None)

    def test_a_missing_output_for_the_last_step_means_a_full_rerun(self):
        """Resuming without the input the next step needs would feed it None
        and produce a confidently empty run."""
        assert _resume_point(
            _engine(KEYS),
            {"num_steps_completed": 2, "steps_output": {"Extract": {"output": "x"}}},
        ) == (0, None)

    def test_a_non_dict_output_means_a_full_rerun(self):
        assert _resume_point(
            _engine(KEYS),
            {"num_steps_completed": 1, "steps_output": {"Extract": "just a string"}},
        ) == (0, None)

    def test_a_workflow_edited_between_attempts_starts_over(self):
        """Replaying old outputs against a re-shaped graph would attribute them
        to different steps."""
        assert _resume_point(
            _engine(["Document", "Extract"]),
            {"num_steps_completed": 3, "steps_output": {"Format": {"output": "x"}}},
        ) == (0, None)

    def test_the_last_step_can_be_the_resume_point(self):
        start, initial = _resume_point(
            _engine(KEYS),
            {"num_steps_completed": 3, "steps_output": {"Format": {"output": "done"}}},
        )
        assert start == 4
        assert initial == {"output": "done"}

    def test_a_missing_count_is_treated_as_none_completed(self):
        assert _resume_point(
            _engine(KEYS), {"steps_output": {"Extract": {"output": "x"}}},
        ) == (0, None)


class TestApprovalResumeTakesTheFurtherPoint:
    """`resume_workflow_after_approval` carries the same
    `autoretry_for` + `max_retries=3` and had no resume index of its own, so a
    transient failure at step 8 re-ran steps 4-7 — the identical bug the
    initial-execution path just fixed. A first pass through the task must still
    start at the gate, so the two candidates are compared and the further one
    wins."""

    def test_a_retry_past_the_gate_beats_the_gate_index(self):
        start, initial = _resume_point(
            _engine(KEYS),
            {
                "num_steps_completed": 2,
                "steps_output": {"Call API": {"output": "called"}},
            },
        )
        gate_index = 1 + 1  # approval gate was step 1
        assert start == 3
        assert start > gate_index
        assert initial == {"output": "called"}

    def test_a_first_pass_falls_back_to_the_gate(self):
        """Nothing recorded past the gate — `_resume_point` declines, and the
        caller keeps `step_index + 1`."""
        start, _initial = _resume_point(_engine(KEYS), {"num_steps_completed": 0})
        assert start == 0


class TestFinalizeIsClaimedOnce:
    """The post-run tail (library write, execution counter) sits after
    execute() and outside the try, so a blip there retries the whole task; the
    resume then skips every step and lands right back on those side effects.
    The filename template carries {time}, so a second library write is a new
    document rather than an overwrite — up to four copies."""

    def test_the_claim_query_matches_a_row_that_never_had_the_field(self):
        """Runs written before `finalized_at` existed have no such key. In
        MongoDB `{"field": None}` matches missing as well as null, so they stay
        claimable exactly once rather than never."""
        from app.models.workflow import WorkflowResult

        assert "finalized_at" in WorkflowResult.model_fields
        assert WorkflowResult.model_fields["finalized_at"].default is None

    def test_every_task_that_counts_a_run_claims_it_first(self):
        """`execute_workflow_task` was given the claim; the approval-gated
        resume — same `autoretry_for`, same `max_retries=3`, same increment
        sitting after execute() — was not, so a blip in its tail counted one
        run up to four times. Asserted over every incrementing task, because
        the defect is a guard that reaches one path and not its sibling."""
        import ast
        import pathlib

        src = (
            pathlib.Path(__file__).resolve().parents[1]
            / "app" / "tasks" / "workflow_tasks.py"
        ).read_text()
        tree = ast.parse(src)

        incrementing = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = ast.get_source_segment(src, node) or ""
            if '"num_executions"' in body:
                incrementing.append((node.name, body))

        # Guards the guard: a rename or a moved counter must not pass vacuously.
        assert {n for n, _ in incrementing} == {
            "execute_workflow_task",
            "resume_workflow_after_approval",
        }, [n for n, _ in incrementing]

        unclaimed = [
            name for name, body in incrementing
            if "finalized_at" not in body or "modified_count" not in body
        ]
        assert not unclaimed, (
            "these tasks increment a workflow's execution count without "
            f"claiming finalization first, so a retry recounts the run: {unclaimed}"
        )
