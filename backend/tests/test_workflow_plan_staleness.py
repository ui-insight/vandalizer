"""Tests for stale validation-plan detection.

Covers the canonical definition hash (invariance + sensitivity), the
staleness computation behind GET /validation-plan, hash stamping on plan
writes, lazy blessing of pre-hash legacy plans, and the manual-check merge
on plan regeneration. Uses mocked Beanie models — no DB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from beanie import PydanticObjectId

from app.services.workflow_service import (
    _merge_manual_checks,
    _plan_staleness,
    compute_workflow_definition_hash,
    get_validation_plan,
    update_validation_plan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wf_data(steps=None, output_config=None, **extra):
    data = {
        "id": "abc",
        "name": "Test WF",
        "user_id": "user1",
        "steps": steps if steps is not None else [
            {
                "id": "s1",
                "name": "Extract Fields",
                "is_output": False,
                "tasks": [
                    {"id": "t1", "name": "Extraction", "data": {"extractions": [{"key": "award_number"}]}},
                ],
            },
            {
                "id": "s2",
                "name": "Summarize",
                "is_output": True,
                "tasks": [
                    {"id": "t2", "name": "Prompt", "data": {"prompt": "Summarize the award."}},
                ],
            },
        ],
        "output_config": output_config if output_config is not None else {"format": "markdown"},
        "validation_plan": [],
        "validation_inputs": [],
    }
    data.update(extra)
    return data


def _make_wf_doc(plan=None, stored_hash=None):
    wf = MagicMock()
    wf.id = PydanticObjectId()
    wf.validation_plan = plan or []
    wf.validation_plan_definition_hash = stored_hash
    wf.validation_plan_updated_at = None
    wf.save = AsyncMock()
    return wf


def _check(check_id="c1", name="Check", target_step="Summarize", source=None):
    c = {"id": check_id, "name": name, "description": "", "category": "content", "target_step": target_step}
    if source:
        c["source"] = source
    return c


# ---------------------------------------------------------------------------
# Definition hash: invariance + sensitivity
# ---------------------------------------------------------------------------

class TestDefinitionHash:
    def test_stable_across_identical_definitions(self):
        assert compute_workflow_definition_hash(_wf_data()) == compute_workflow_definition_hash(_wf_data())

    def test_ignores_plan_name_and_metadata(self):
        base = compute_workflow_definition_hash(_wf_data())
        changed = _wf_data(
            name="Renamed WF",
            validation_plan=[_check()],
            validation_inputs=[{"id": "i1"}],
            num_executions=42,
        )
        assert compute_workflow_definition_hash(changed) == base

    def test_ignores_step_and_task_ids(self):
        a = _wf_data()
        b = _wf_data()
        for s in b["steps"]:
            s["id"] = "different"
            for t in s["tasks"]:
                t["id"] = "different"
        assert compute_workflow_definition_hash(a) == compute_workflow_definition_hash(b)

    def test_changes_on_step_rename(self):
        base = compute_workflow_definition_hash(_wf_data())
        renamed = _wf_data()
        renamed["steps"][1]["name"] = "Summarize v2"
        assert compute_workflow_definition_hash(renamed) != base

    def test_changes_on_task_data_edit(self):
        base = compute_workflow_definition_hash(_wf_data())
        edited = _wf_data()
        edited["steps"][1]["tasks"][0]["data"]["prompt"] = "Summarize differently."
        assert compute_workflow_definition_hash(edited) != base

    def test_changes_on_is_output_toggle(self):
        base = compute_workflow_definition_hash(_wf_data())
        toggled = _wf_data()
        toggled["steps"][0]["is_output"] = True
        assert compute_workflow_definition_hash(toggled) != base

    def test_changes_on_output_config_edit(self):
        base = compute_workflow_definition_hash(_wf_data())
        assert compute_workflow_definition_hash(_wf_data(output_config={"format": "json"})) != base

    def test_handles_none_and_empty(self):
        assert compute_workflow_definition_hash(None) == compute_workflow_definition_hash({})


# ---------------------------------------------------------------------------
# _plan_staleness
# ---------------------------------------------------------------------------

class TestPlanStaleness:
    def test_empty_plan_is_fresh(self):
        stale, reasons, orphaned = _plan_staleness([], "anything", _wf_data())
        assert (stale, reasons, orphaned) == (False, [], [])

    def test_matching_hash_and_targets_is_fresh(self):
        data = _wf_data()
        stale, reasons, orphaned = _plan_staleness(
            [_check()], compute_workflow_definition_hash(data), data,
        )
        assert (stale, reasons, orphaned) == (False, [], [])

    def test_hash_mismatch_is_definition_changed(self):
        stale, reasons, orphaned = _plan_staleness([_check()], "stale-hash", _wf_data())
        assert stale is True
        assert reasons == ["definition_changed"]
        assert orphaned == []

    def test_orphaned_target_step_detected(self):
        data = _wf_data()
        plan = [_check("c1"), _check("c2", target_step="Deleted Step")]
        stale, reasons, orphaned = _plan_staleness(
            plan, compute_workflow_definition_hash(data), data,
        )
        assert stale is True
        assert reasons == ["orphaned_checks"]
        assert orphaned == ["c2"]

    def test_target_step_match_is_case_insensitive(self):
        data = _wf_data()
        plan = [_check(target_step="  summarize ")]
        stale, _, orphaned = _plan_staleness(
            plan, compute_workflow_definition_hash(data), data,
        )
        assert stale is False
        assert orphaned == []

    def test_check_without_target_step_is_not_orphaned(self):
        data = _wf_data()
        plan = [_check(target_step="")]
        stale, _, orphaned = _plan_staleness(
            plan, compute_workflow_definition_hash(data), data,
        )
        assert stale is False
        assert orphaned == []

    def test_missing_stored_hash_alone_is_fresh(self):
        # Legacy plan with no stamped hash and intact targets: drift is
        # undetectable, so it is not flagged (lazy bless happens at GET).
        stale, reasons, _ = _plan_staleness([_check()], None, _wf_data())
        assert stale is False
        assert reasons == []

    def test_both_signals_reported_together(self):
        plan = [_check("c1", target_step="Deleted Step")]
        stale, reasons, orphaned = _plan_staleness(plan, "stale-hash", _wf_data())
        assert stale is True
        assert set(reasons) == {"definition_changed", "orphaned_checks"}
        assert orphaned == ["c1"]


# ---------------------------------------------------------------------------
# get_validation_plan: staleness flags + lazy bless
# ---------------------------------------------------------------------------

class TestGetValidationPlan:
    @patch("app.services.workflow_service.get_workflow", new_callable=AsyncMock)
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_stale_plan_reported(self, mock_auth, mock_get_wf):
        wf = _make_wf_doc(plan=[_check()], stored_hash="stale-hash")
        mock_auth.return_value = wf
        mock_get_wf.return_value = _wf_data()

        result = await get_validation_plan(str(wf.id), MagicMock())
        assert result["plan_stale"] is True
        assert result["stale_reasons"] == ["definition_changed"]
        # An existing stored hash is never silently rewritten on read.
        assert wf.validation_plan_definition_hash == "stale-hash"
        wf.save.assert_not_awaited()

    @patch("app.services.workflow_service.get_workflow", new_callable=AsyncMock)
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_legacy_plan_lazily_blessed(self, mock_auth, mock_get_wf):
        data = _wf_data()
        wf = _make_wf_doc(plan=[_check()], stored_hash=None)
        mock_auth.return_value = wf
        mock_get_wf.return_value = data

        result = await get_validation_plan(str(wf.id), MagicMock())
        assert result["plan_stale"] is False
        assert wf.validation_plan_definition_hash == compute_workflow_definition_hash(data)
        wf.save.assert_awaited_once()

    @patch("app.services.workflow_service.get_workflow", new_callable=AsyncMock)
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_legacy_plan_with_orphans_not_blessed(self, mock_auth, mock_get_wf):
        wf = _make_wf_doc(plan=[_check(target_step="Deleted Step")], stored_hash=None)
        mock_auth.return_value = wf
        mock_get_wf.return_value = _wf_data()

        result = await get_validation_plan(str(wf.id), MagicMock())
        assert result["plan_stale"] is True
        assert result["stale_reasons"] == ["orphaned_checks"]
        assert result["orphaned_check_ids"] == ["c1"]
        assert wf.validation_plan_definition_hash is None
        wf.save.assert_not_awaited()

    @patch("app.services.workflow_service.get_workflow", new_callable=AsyncMock)
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_empty_plan_not_blessed(self, mock_auth, mock_get_wf):
        wf = _make_wf_doc(plan=[], stored_hash=None)
        mock_auth.return_value = wf
        mock_get_wf.return_value = _wf_data()

        result = await get_validation_plan(str(wf.id), MagicMock())
        assert result["plan_stale"] is False
        wf.save.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_validation_plan: blessing on save
# ---------------------------------------------------------------------------

class TestUpdateValidationPlanStamping:
    @patch("app.services.workflow_service.get_workflow", new_callable=AsyncMock)
    @patch("app.services.workflow_service.get_authorized_workflow")
    async def test_save_restamps_hash(self, mock_auth, mock_get_wf):
        data = _wf_data()
        wf = _make_wf_doc(plan=[_check()], stored_hash="stale-hash")
        mock_auth.return_value = wf
        mock_get_wf.return_value = data

        await update_validation_plan(str(wf.id), [_check()], MagicMock())
        assert wf.validation_plan_definition_hash == compute_workflow_definition_hash(data)
        assert wf.validation_plan_updated_at is not None
        wf.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# Regeneration: manual checks survive
# ---------------------------------------------------------------------------

class TestMergeManualChecks:
    def test_manual_checks_preserved_auto_replaced(self):
        existing = [
            _check("old-auto", source="auto"),
            _check("legacy"),  # no source: treated as auto
            _check("mine", name="My custom check", source="manual"),
        ]
        generated = [_check("new-auto", source="auto")]
        merged = _merge_manual_checks(existing, generated, {"summarize": "Summarize"})
        assert [c["id"] for c in merged] == ["new-auto", "mine"]

    def test_manual_target_step_remapped_case_insensitively(self):
        existing = [_check("mine", target_step="summarize  ", source="manual")]
        merged = _merge_manual_checks(existing, [], {"summarize": "Summarize"})
        assert merged[0]["target_step"] == "Summarize"

    def test_orphaned_manual_target_kept_as_is(self):
        # A manual check pointing at a deleted step is kept (the staleness
        # banner flags it) rather than silently dropped or re-bucketed.
        existing = [_check("mine", target_step="Deleted Step", source="manual")]
        merged = _merge_manual_checks(existing, [], {"summarize": "Summarize"})
        assert merged[0]["target_step"] == "Deleted Step"

    def test_empty_existing_plan(self):
        generated = [_check("new-auto", source="auto")]
        assert _merge_manual_checks([], generated, {}) == generated
