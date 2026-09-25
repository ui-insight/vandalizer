"""One builder assembles ``steps_data`` for every path that runs a workflow (#862).

The scheduled / folder-watch path and the optimizer each kept a hand-copied
version of the interactive run's step-assembly loop, and each copy silently
missed fixes made to the original: the workflow default model (#842),
step-level input (#796), the selected-document preload, extraction
``field_metadata``, and saved Prompt/Formatter resolution. None of those
failures crash -- a scheduled run answers on the wrong model or over the
wrong document and reports success -- so the tests here are of two kinds:

* behavioural: a scheduled run and an optimizer trial receive steps_data
  carrying something only the shared builder produces;
* structural: there is exactly one step-assembly loop across the three
  modules, so the next fix cannot be made in one place and missed in another.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId


def _db_for(workflow, *, step_docs, task_docs, smart_docs=(), search_set_items=()):
    """A pymongo-shaped MagicMock holding one workflow and its steps."""
    db = MagicMock()
    steps = {s["_id"]: s for s in step_docs}
    tasks = {t["_id"]: t for t in task_docs}
    docs = {d["uuid"]: d for d in smart_docs}

    db.workflow.find_one.return_value = workflow
    db.workflow_step.find_one.side_effect = lambda q, *a, **k: steps.get(q.get("_id"))
    db.workflow_step_task.find_one.side_effect = lambda q, *a, **k: tasks.get(q.get("_id"))
    db.smart_document.find_one.side_effect = lambda q, *a, **k: docs.get(q.get("uuid"))
    db.smart_document.find.side_effect = lambda q, *a, **k: [
        d for d in docs.values() if d.get("_id") in ((q.get("_id") or {}).get("$in") or [])
    ]
    # Saved Prompt link: the set exists and its first item holds the body.
    db.search_set.find_one.side_effect = lambda q, *a, **k: {"uuid": q.get("uuid")}
    db.search_set_item.find_one.return_value = {"searchphrase": "Summarize the award terms."}
    db.search_set_item.find.return_value = list(search_set_items)
    db.user_model_config.find_one.return_value = None
    db.user.find_one.return_value = {"user_id": workflow["user_id"], "is_admin": False}
    return db


def _workflow_with_linked_prompt_and_extraction():
    """A workflow whose steps exercise what the copied loops did not do."""
    wf_id, prompt_step, prompt_task, ext_step, ext_task = (ObjectId() for _ in range(5))
    workflow = {
        "_id": wf_id,
        "user_id": "owner",
        "steps": [prompt_step, ext_step],
        "input_config": {"trigger_type": "folder_watch", "fixed_documents": [{"uuid": "fixed"}]},
    }
    step_docs = [
        {"_id": prompt_step, "name": "Summarize", "tasks": [prompt_task]},
        {"_id": ext_step, "name": "Extract", "tasks": [ext_task]},
    ]
    task_docs = [
        {"_id": prompt_task, "name": "Prompt",
         "data": {"saved_prompt_uuid": "sp1", "prompt": "STALE INLINE COPY"}},
        {"_id": ext_task, "name": "Extraction", "data": {"search_set_uuid": "ss1"}},
    ]
    smart_docs = [
        {"_id": ObjectId(), "uuid": "trigger-doc", "raw_text": "trigger text"},
        {"_id": ObjectId(), "uuid": "fixed", "raw_text": "fixed text"},
        # Written by this very workflow: must not feed back into it.
        {"_id": ObjectId(), "uuid": "own-output", "raw_text": "loop",
         "origin_workflow_id": str(wf_id)},
    ]
    search_set_items = [
        {"searchphrase": "amount", "is_optional": True, "enum_values": []},
    ]
    return workflow, step_docs, task_docs, smart_docs, search_set_items


def _assert_built_by_the_shared_builder(steps_data):
    by_name = {s["name"]: s for s in steps_data}
    prompt = by_name["Summarize"]["tasks"][0]["data"]
    extraction = by_name["Extract"]["tasks"][0]["data"]

    # Saved Prompt resolved to its library body -- the copies ran the stale inline text.
    assert prompt["prompt"] == "Summarize the award terms."
    # Extraction carries per-field constraints -- the copies produced keys only.
    assert extraction["keys"] == ["amount"]
    assert extraction["field_metadata"] == [
        {"key": "amount", "is_optional": True, "enum_values": []},
    ]
    # Trigger docs plus fixed documents, minus the workflow's own output.
    assert extraction["doc_texts"] == ["trigger text", "fixed text"]


class TestScheduledRunUsesTheSharedBuilder:
    @patch("app.services.metering.metered")
    @patch("app.services.workflow_engine.build_workflow_engine")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_folder_watch_run_gets_the_same_steps_data_as_a_manual_run(
        self, mock_get_db, mock_build, _metered,
    ):
        from app.tasks.passive_tasks import execute_workflow_passive

        workflow, step_docs, task_docs, smart_docs, ss_items = (
            _workflow_with_linked_prompt_and_extraction()
        )
        db = _db_for(workflow, step_docs=step_docs, task_docs=task_docs,
                     smart_docs=smart_docs, search_set_items=ss_items)
        mock_get_db.return_value = db
        trigger_doc = smart_docs[0]
        own_output = smart_docs[2]
        db.workflow_trigger_event.find_one.return_value = {
            "_id": ObjectId(), "workflow": workflow["_id"],
            "documents": [trigger_doc["_id"], own_output["_id"]],
            "trigger_type": "folder_watch",
        }
        db.system_config.find_one.return_value = {
            "available_models": [{"name": "sys-default"}], "default_model": "sys-default",
        }
        db.workflow_result.insert_one.return_value.inserted_id = ObjectId()
        mock_build.return_value.execute.return_value = ("final", [])

        out = execute_workflow_passive("0" * 24)

        assert "error" not in out, out
        _assert_built_by_the_shared_builder(mock_build.call_args.kwargs["steps_data"])

    @patch("app.services.metering.metered")
    @patch("app.services.workflow_engine.build_workflow_engine")
    @patch("app.tasks.passive_tasks.get_sync_db")
    def test_model_ladder_matches_the_interactive_run(self, mock_get_db, mock_build, _metered):
        """Workflow default first; below it the owner's chosen model (stored as
        a tag or a name), then the system default -- not whichever model
        happens to be first in System Config."""
        from app.tasks.passive_tasks import execute_workflow_passive

        workflow = {"_id": ObjectId(), "user_id": "owner", "steps": [], "input_config": {}}
        db = _db_for(workflow, step_docs=[], task_docs=[])
        mock_get_db.return_value = db
        db.workflow_trigger_event.find_one.return_value = {
            "_id": ObjectId(), "workflow": workflow["_id"], "documents": [], "trigger_type": "scheduled",
        }
        db.system_config.find_one.return_value = {
            "available_models": [
                {"name": "first-listed", "tag": "First"},
                {"name": "owners-pick", "tag": "Owner's"},
            ],
            "default_model": "first-listed",
        }
        db.user_model_config.find_one.return_value = {"user_id": "owner", "name": "Owner's"}
        db.workflow_result.insert_one.return_value.inserted_id = ObjectId()
        mock_build.return_value.execute.return_value = ("final", [])

        execute_workflow_passive("0" * 24)
        assert mock_build.call_args.kwargs["model"] == "owners-pick"

        workflow["input_config"] = {"default_model": "wf-default"}
        execute_workflow_passive("0" * 24)
        assert mock_build.call_args.kwargs["model"] == "wf-default"


class TestOptimizerTrialUsesTheSharedBuilder:
    @pytest.mark.asyncio
    async def test_trial_measures_the_configuration_that_actually_runs(self):
        from app.services import workflow_optimizer

        workflow, step_docs, task_docs, smart_docs, ss_items = (
            _workflow_with_linked_prompt_and_extraction()
        )
        db = _db_for(workflow, step_docs=step_docs, task_docs=task_docs,
                     smart_docs=smart_docs, search_set_items=ss_items)

        with (
            patch("app.tasks.get_sync_db", return_value=db),
            patch("app.models.system_config.SystemConfig.get_config", AsyncMock(return_value=None)),
            patch.object(workflow_optimizer, "get_user_model_name", AsyncMock(return_value="m")),
            patch("app.models.user.User") as MockUser,
            patch("app.services.workflow_engine.build_workflow_engine") as mock_build,
        ):
            MockUser.find_one = AsyncMock(return_value=None)
            mock_build.return_value.execute.return_value = ("final", [])
            mock_build.return_value.usage.tokens_in = 0
            mock_build.return_value.usage.tokens_out = 0

            await workflow_optimizer._execute_workflow_inproc(
                wf_id=str(workflow["_id"]),
                wf_data={"input_config": {}},
                user_id="owner",
                step_overrides={},
                doc_uuids=["trigger-doc", "own-output"],
            )

        _assert_built_by_the_shared_builder(mock_build.call_args.kwargs["steps_data"])


class TestThereIsOneStepAssemblyLoop:
    def test_only_the_shared_builder_walks_workflow_steps(self):
        """The general form of the ordering test in
        test_workflow_step_input_config: rather than pinning one setting's
        position in each copy, pin that there is no copy."""
        from app.services import workflow_optimizer
        from app.tasks import passive_tasks, workflow_tasks

        loops = [
            (mod.__name__, src.count("workflow_step.find_one("))
            for mod in (workflow_tasks, passive_tasks, workflow_optimizer)
            for src in [inspect.getsource(mod)]
        ]
        assert loops == [
            ("app.tasks.workflow_tasks", 1),
            ("app.tasks.passive_tasks", 0),
            ("app.services.workflow_optimizer", 0),
        ], loops

        assert "build_steps_data(" in inspect.getsource(passive_tasks.execute_workflow_passive)
        assert "build_steps_data(" in inspect.getsource(workflow_optimizer._execute_workflow_inproc)
        assert not hasattr(workflow_optimizer, "_build_steps_data_for_optimization")
