"""Phase 8 of the agentic-chat harness uplift: the update_plan checklist tool.

Server-side enforcement of the TodoWrite contract: full-list updates, both
task forms required, exactly one in_progress until everything completes.
Violations are soft errors with corrective hints (Phase 5 convention)."""

import types

from app.services.chat_tools import update_plan
from app.services.llm_service import AGENTIC_CHAT_SYSTEM_PROMPT


def _ctx():
    return types.SimpleNamespace(deps=types.SimpleNamespace(plan_state=None))


def _task(content="Run extraction", active="Running extraction", status="pending"):
    return {"content": content, "active_form": active, "status": status}


class TestUpdatePlanValidation:
    async def test_happy_path_sets_plan_state(self):
        ctx = _ctx()
        result = await update_plan(ctx, [
            _task("Run extraction", "Running extraction", "in_progress"),
            _task("Check compliance", "Checking compliance", "pending"),
            _task("Save summary", "Saving summary", "pending"),
        ])
        assert result == {"ok": True, "task_count": 3, "completed": 0, "all_done": False}
        assert len(ctx.deps.plan_state) == 3
        assert ctx.deps.plan_state[0]["status"] == "in_progress"

    async def test_all_done_needs_no_in_progress(self):
        ctx = _ctx()
        result = await update_plan(ctx, [
            _task(status="completed"),
            _task("Check compliance", "Checking compliance", "completed"),
        ])
        assert result["all_done"] is True

    async def test_zero_in_progress_rejected_when_work_remains(self):
        ctx = _ctx()
        result = await update_plan(ctx, [_task(), _task("B", "Doing B")])
        assert "Exactly one task must be in_progress" in result["error"]
        assert "hint" in result
        assert ctx.deps.plan_state is None  # rejected update never lands

    async def test_two_in_progress_rejected(self):
        ctx = _ctx()
        result = await update_plan(ctx, [
            _task(status="in_progress"),
            _task("B", "Doing B", "in_progress"),
        ])
        assert "Exactly one task must be in_progress (got 2)" in result["error"]

    async def test_missing_active_form_rejected_with_hint(self):
        ctx = _ctx()
        result = await update_plan(ctx, [
            {"content": "Run extraction", "status": "in_progress"},
        ])
        assert "missing content or active_form" in result["error"]
        assert "present continuous" in result["hint"]

    async def test_invalid_status_rejected(self):
        ctx = _ctx()
        result = await update_plan(ctx, [_task(status="doing")])
        assert "invalid status" in result["error"]

    async def test_empty_and_oversized_lists_rejected(self):
        ctx = _ctx()
        assert "error" in await update_plan(ctx, [])
        too_many = [
            _task(f"T{i}", f"Doing T{i}", "in_progress" if i == 0 else "pending")
            for i in range(25)
        ]
        assert "Too many tasks" in (await update_plan(ctx, too_many))["error"]


class TestPromptSection:
    def test_agentic_base_teaches_planning(self):
        assert "## Planning multi-step work" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "exactly one" in AGENTIC_CHAT_SYSTEM_PROMPT
        assert "never batch completions" in AGENTIC_CHAT_SYSTEM_PROMPT
