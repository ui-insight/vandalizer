"""A workflow reads a fixed document only for people allowed to open it.

Fixed documents are checked when they are saved and again before a run reads
them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import fixed_document_access as access
from app.services import workflow_service


# ---------------------------------------------------------------------------
# A small in-memory stand-in for the worker's pymongo database
# ---------------------------------------------------------------------------


class _Collection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    @staticmethod
    def _matches(row: dict, query: dict) -> bool:
        for key, want in query.items():
            have = row.get(key)
            if isinstance(want, dict) and "$in" in want:
                if have not in want["$in"]:
                    return False
            elif have != want:
                return False
        return True

    def find(self, query: dict | None = None, projection: dict | None = None) -> list[dict]:
        return [r for r in self.rows if self._matches(r, query or {})]

    def find_one(self, query: dict | None = None, projection: dict | None = None) -> dict | None:
        found = self.find(query)
        return found[0] if found else None


def _db(**collections: list[dict]) -> SimpleNamespace:
    names = ("user", "team", "team_membership", "smart_document", "smart_folder",
             "project", "project_membership", "activity_event")
    return SimpleNamespace(**{name: _Collection(collections.get(name, [])) for name in names})


SECRET = {"uuid": "secret-a", "user_id": "alice", "team_id": "team-a", "folder": "0"}
TEAMS = [{"_id": "oid-a", "uuid": "team-a"}, {"_id": "oid-b", "uuid": "team-b"}]
MEMBERS = [
    {"user_id": "alice", "team": "oid-a"},
    {"user_id": "amir", "team": "oid-a"},
    {"user_id": "bob", "team": "oid-b"},
]


def _workflow(owner: str, *fixed: str, **config) -> dict:
    return {"user_id": owner, "input_config": {"fixed_documents": [{"uuid": u, "title": "x"} for u in fixed], **config}}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def test_another_teams_private_file_is_not_readable_as_a_fixed_document():
    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    # Bob's own workflow, Bob running it.
    assert access.unreadable_fixed_documents(db, _workflow("bob", "secret-a"), ["bob"]) == ["secret-a"]


def test_the_owner_and_their_team_can_use_the_file():
    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    assert access.unreadable_fixed_documents(db, _workflow("alice", "secret-a"), ["alice"]) == []
    # A teammate's workflow: the file is their team's.
    assert access.unreadable_fixed_documents(db, _workflow("amir", "secret-a"), ["amir"]) == []


def test_a_private_file_with_no_team_is_only_its_owners():
    private = {"uuid": "mine", "user_id": "alice", "team_id": None, "folder": "0"}
    db = _db(smart_document=[private], team=TEAMS, team_membership=MEMBERS)
    assert access.unreadable_fixed_documents(db, _workflow("amir", "mine"), ["amir"]) == ["mine"]


def test_a_shared_workflow_carries_the_file_its_owner_bundled():
    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    # Alice owns the workflow and the file; Bob runs it through a share.
    assert access.unreadable_fixed_documents(db, _workflow("alice", "secret-a"), ["bob"]) == []


def test_a_copy_of_that_workflow_does_not():
    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    # The copy is Bob's. Neither its owner nor its runner can open the file.
    assert access.unreadable_fixed_documents(db, _workflow("bob", "secret-a"), ["bob", None]) == ["secret-a"]


def test_a_project_file_follows_the_project_not_the_uploader():
    in_project = {"uuid": "proj-doc", "user_id": "alice", "team_id": "team-a", "folder": "sub"}
    db = _db(
        smart_document=[in_project], team=TEAMS, team_membership=MEMBERS,
        smart_folder=[{"uuid": "sub", "parent_id": "root"}, {"uuid": "root", "parent_id": "0"}],
        project=[{"uuid": "p1", "root_folder_uuid": "root", "owner_user_id": "carol", "team_id": None}],
        project_membership=[{"project_uuid": "p1", "user_id": "bob", "role": "viewer"}],
    )
    # Bob is a project viewer; Amir shares Alice's team but is not on the project.
    assert access.unreadable_fixed_documents(db, _workflow("bob", "proj-doc"), ["bob"]) == []
    assert access.unreadable_fixed_documents(db, _workflow("amir", "proj-doc"), ["amir"]) == ["proj-doc"]


def test_admins_can_read_any_file():
    db = _db(smart_document=[SECRET], user=[{"user_id": "root", "is_admin": True}])
    assert access.unreadable_fixed_documents(db, _workflow("root", "secret-a"), ["root"]) == []


def test_no_input_mode_and_deleted_files_are_not_access_failures():
    db = _db(smart_document=[SECRET, {"uuid": "trashed", "user_id": "alice", "soft_deleted": True}])
    assert access.unreadable_fixed_documents(db, _workflow("bob", "secret-a", trigger_type="no_input"), ["bob"]) == []
    # Missing and deleted fixed documents have their own message.
    assert access.unreadable_fixed_documents(db, _workflow("bob", "gone", "trashed"), ["bob"]) == []


def _with_steps(db, workflow: dict, *task_datas: dict, step_data: dict | None = None) -> dict:
    db.workflow_step = _Collection([{
        "_id": "s1", "name": "Step", "data": step_data or {},
        "tasks": [f"t{i}" for i in range(len(task_datas))],
    }])
    db.workflow_step_task = _Collection([{"_id": f"t{i}", "name": "Prompt", "data": d} for i, d in enumerate(task_datas)])
    return {**workflow, "steps": ["s1"]}


def test_a_deleted_documents_text_is_never_loaded():
    """A soft-deleted file keeps its text; the builder must not read it, on any
    run path (not every path has the missing-document pre-flight)."""
    from app.tasks import workflow_tasks

    trashed = {"uuid": "trashed", "user_id": "bob", "soft_deleted": True, "raw_text": "old text"}
    db = _db(smart_document=[trashed])
    workflow = _with_steps(
        db, _workflow("bob", "trashed"),
        {"prompt": "p", "input_sources": ["select_document"], "selected_document_uuid": "trashed"},
    )
    steps, _ = workflow_tasks.build_steps_data(db, workflow, "wf-1", {"doc_uuids": [], "user_id": "bob"})
    assert "old text" not in repr(steps)


def test_a_missing_fixed_document_is_named_by_its_saved_title_only():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[{"uuid": "trashed", "title": "Real title", "soft_deleted": True}])
    workflow = {"input_config": {"fixed_documents": ["trashed", {"uuid": "gone", "title": "Policy.pdf"}]}}
    # The id as entered, not "Real title".
    assert workflow_tasks._missing_fixed_documents(db, workflow) == ["trashed", "Policy.pdf"]


# ---------------------------------------------------------------------------
# A step's selected document follows the same rule
# ---------------------------------------------------------------------------

SELECTED = {"prompt": "p", "input_sources": ["select_document"], "selected_document_uuid": "secret-a"}


def test_only_a_step_that_reads_its_selected_document_counts():
    assert access.selected_document_uuid(SELECTED) == "secret-a"
    assert access.selected_document_uuid({"input_source": "select_document", "selected_document_uuid": "x"}) == "x"
    # Left over from an earlier setting, but not read.
    assert access.selected_document_uuid({"input_sources": ["step_input"], "selected_document_uuid": "x"}) is None
    assert access.selected_document_uuid({"input_sources": ["select_document"]}) is None


def test_a_run_may_not_read_a_step_document_its_runner_and_owner_cannot_open():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    workflow = _with_steps(db, _workflow("bob"), SELECTED)
    assert workflow_tasks._denied_fixed_documents(db, workflow, {"user_id": "bob"}) == ["secret-a"]
    with pytest.raises(workflow_tasks.FixedDocumentsDenied):
        workflow_tasks.build_steps_data(db, workflow, "wf-1", {"doc_uuids": [], "user_id": "bob"})
    # Alice's own workflow reads it as before.
    assert workflow_tasks._denied_fixed_documents(db, _with_steps(db, _workflow("alice"), SELECTED), {"user_id": "alice"}) == []


def test_the_refusal_names_no_file():
    message = access.fixed_documents_denied_message(1)
    assert "neither you nor the workflow's owner can open" in message
    assert "secret" not in message.lower()
    assert "2 documents" in access.fixed_documents_denied_message(2)


def test_the_builder_never_loads_a_denied_fixed_document():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    db.workflow_step = _Collection([{"_id": "s1", "name": "Step", "tasks": ["t1"]}])
    db.workflow_step_task = _Collection([{"_id": "t1", "name": "Prompt", "data": {"prompt": "Quote it"}}])
    workflow = {**_workflow("bob", "secret-a"), "steps": ["s1"]}

    with pytest.raises(workflow_tasks.FixedDocumentsDenied) as denied:
        workflow_tasks.build_steps_data(db, workflow, "wf-1", {"doc_uuids": ["bobs-own"], "user_id": "bob"})
    assert denied.value.count == 1


def test_the_run_is_checked_against_the_person_who_started_it():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    workflow = _workflow("bob", "secret-a")
    # Amir (Alice's team) starts Bob's workflow: Amir may read the file.
    assert workflow_tasks._denied_fixed_documents(db, workflow, {"user_id": "amir"}) == []
    # An older queued run carries no runner: only the owner counts.
    assert workflow_tasks._denied_fixed_documents(db, workflow, {}) == ["secret-a"]


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def fake_model_list(rows: list):
    """A Beanie model stand-in whose ``find(...).to_list()`` returns *rows*."""
    model = MagicMock()
    model.find.return_value.to_list = AsyncMock(return_value=rows)
    return model


def _authorized(readable: set[str]) -> AsyncMock:
    async def lookup(doc_uuid, user, **_):
        return SimpleNamespace(uuid=doc_uuid, title="t", soft_deleted=False) if doc_uuid in readable else None

    return AsyncMock(side_effect=lookup)


async def test_saving_refuses_a_fixed_document_the_user_cannot_read():
    bob = SimpleNamespace(user_id="bob")
    with patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized({"bobs"})):
        await workflow_service.ensure_fixed_documents_readable(
            {"fixed_documents": [{"uuid": "bobs", "title": "ok"}]}, bob,
        )
        with pytest.raises(workflow_service.FixedDocumentAccessError) as refused:
            await workflow_service.ensure_fixed_documents_readable(
                {"fixed_documents": [{"uuid": "bobs"}, {"uuid": "secret-a"}]}, bob,
            )
    assert "don't have access" in str(refused.value)
    assert "secret-a" not in str(refused.value)


async def test_saving_checks_even_when_the_mode_would_not_load_them():
    bob = SimpleNamespace(user_id="bob")
    with patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_fixed_documents_readable(
                {"trigger_type": "no_input", "fixed_documents": ["secret-a"]}, bob,
            )


async def test_saving_other_settings_leaves_the_owners_fixed_documents_alone():
    editor = SimpleNamespace(user_id="amir")
    lookup = _authorized(set())
    existing = {"fixed_documents": [{"uuid": "owners-file", "title": "Policy"}]}
    with patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", lookup):
        await workflow_service.ensure_fixed_documents_readable(
            {"default_model": "m", "fixed_documents": [{"uuid": "owners-file", "title": "Policy"}]},
            editor, already=existing,
        )
    lookup.assert_not_awaited()


async def test_update_workflow_does_not_save_a_refused_fixed_document():
    wf = SimpleNamespace(
        id="w", name="n", user_id="bob", team_id=None, input_config={}, save=AsyncMock(),
        description=None, output_config=None, updated_at=None,
    )
    with patch.object(workflow_service, "get_authorized_workflow", AsyncMock(return_value=wf)), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.update_workflow(
                "w", SimpleNamespace(user_id="bob"), input_config={"fixed_documents": [{"uuid": "secret-a"}]},
            )
    assert wf.input_config == {}
    wf.save.assert_not_awaited()


async def test_chat_refuses_to_create_the_workflow_at_all():
    from app.services import chat_tools

    context = MagicMock()
    context.deps.user = SimpleNamespace(user_id="bob")
    context.deps.model_name = None
    with patch.object(chat_tools, "_resolve_requested_model", AsyncMock(return_value=(None, None))), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())), \
         patch.object(workflow_service, "create_workflow", AsyncMock()) as create, \
         patch.object(chat_tools, "_confirm_gate", AsyncMock()) as gate:
        result = await chat_tools.create_workflow(
            context, name="Access test",
            steps=[{"type": "prompt", "name": "Quote", "prompt": "Summarize the document."}],
            fixed_document_uuids=["secret-a"],
        )
    assert "don't have access" in result["error"]
    assert "Nothing was created" in result["error"]
    gate.assert_not_awaited()
    create.assert_not_awaited()


async def test_a_step_cannot_be_set_to_read_a_document_the_user_cannot_read():
    bob = SimpleNamespace(user_id="bob")
    lookup = _authorized({"bobs"})
    with patch.object(workflow_service, "get_authorized_document", lookup):
        await workflow_service.ensure_step_document_readable({**SELECTED, "selected_document_uuid": "bobs"}, bob)
        with pytest.raises(workflow_service.FixedDocumentAccessError) as refused:
            await workflow_service.ensure_step_document_readable(SELECTED, bob)
        # Unchanged from what the step already read: its author's choice stands.
        await workflow_service.ensure_step_document_readable(SELECTED, bob, already=dict(SELECTED))
        # Not read by the step, so not checked.
        await workflow_service.ensure_step_document_readable(
            {"input_sources": ["step_input"], "selected_document_uuid": "secret-a"}, bob,
        )
    assert "secret-a" not in str(refused.value)


async def test_a_whole_definition_written_at_once_is_checked():
    """Importing a file into a workflow, or restoring a version, replaces the
    input settings and steps in one go."""
    manager = SimpleNamespace(user_id="amir")
    with patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized({"amirs"})):
        ok = {"input_config": {"fixed_documents": [{"uuid": "amirs"}]},
              "steps": [{"tasks": [{"name": "Prompt", "data": {**SELECTED, "selected_document_uuid": "amirs"}}]}]}
        await workflow_service.ensure_definition_documents_readable(ok, manager)

        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_definition_documents_readable(
                {"input_config": {"fixed_documents": [{"uuid": "owners-file"}]}}, manager,
            )
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_definition_documents_readable(
                {"steps": [{"tasks": [{"name": "Prompt", "data": SELECTED}]}]}, manager,
            )
        # What the workflow already reads is not re-checked.
        await workflow_service.ensure_definition_documents_readable(
            {"input_config": {"fixed_documents": [{"uuid": "owners-file"}]},
             "steps": [{"tasks": [{"name": "Prompt", "data": SELECTED}]}]},
            manager, already_input_config={"fixed_documents": ["owners-file"]},
            already_step_documents={"secret-a"},
        )


async def test_adding_or_changing_a_step_checks_its_document_before_saving():
    bob = SimpleNamespace(user_id="bob")
    step = SimpleNamespace(id="s1", tasks=[], save=AsyncMock())
    task = SimpleNamespace(id="t1", name="Prompt", data={"prompt": "p"}, save=AsyncMock())
    with patch.object(workflow_service, "WorkflowStep") as steps, \
         patch.object(workflow_service, "WorkflowStepTask") as tasks, \
         patch.object(workflow_service, "PydanticObjectId", lambda value: value), \
         patch.object(workflow_service, "_get_workflow_for_step", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "_get_workflow_for_task", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch("app.services.access_control.can_manage_workflow", return_value=True), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        steps.get = AsyncMock(return_value=step)
        tasks.get = AsyncMock(return_value=task)
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.add_task("s1", "Prompt", bob, data=SELECTED)
        tasks.assert_not_called()  # nothing was created
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.update_task("t1", bob, data=SELECTED)

    assert task.data == {"prompt": "p"}
    task.save.assert_not_awaited()
    step.save.assert_not_awaited()


async def test_a_run_is_refused_before_dispatch_for_a_step_document_too():
    bob = SimpleNamespace(user_id="bob")
    wf = SimpleNamespace(input_config={}, user_id="bob", steps=["s1"])
    document = MagicMock()
    document.find_one = AsyncMock(return_value=SimpleNamespace(soft_deleted=False))
    with patch.object(workflow_service, "step_document_uuids", AsyncMock(return_value=["secret-a"])), \
         patch.object(workflow_service, "SmartDocument", document), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        with pytest.raises(workflow_service.FixedDocumentAccessError) as refused:
            await workflow_service.ensure_fixed_documents_runnable(wf, bob, "bob")
    assert "neither you nor the workflow's owner can open" in str(refused.value)


# ---------------------------------------------------------------------------
# Input set on the step itself (what the editor saves)
# ---------------------------------------------------------------------------

STEP_INPUT = {"input_sources": ["select_document"], "selected_document_uuid": "secret-a"}


def test_a_document_set_on_the_step_is_the_one_checked_and_never_loaded_when_denied():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[{**SECRET, "raw_text": "the secret text"}], team=TEAMS, team_membership=MEMBERS)
    # The task itself names no document: the step's setting is pushed down.
    workflow = _with_steps(db, _workflow("bob"), {"prompt": "p"}, step_data=STEP_INPUT)

    assert access.step_document_uuids(db, workflow) == ["secret-a"]
    assert workflow_tasks._denied_fixed_documents(db, workflow, {"user_id": "bob"}) == ["secret-a"]
    with pytest.raises(workflow_tasks.FixedDocumentsDenied):
        workflow_tasks.build_steps_data(db, workflow, "wf-1", {"doc_uuids": [], "user_id": "bob"})

    # The same workflow owned by someone who can read the file loads it.
    own = _with_steps(db, _workflow("alice"), {"prompt": "p"}, step_data=STEP_INPUT)
    steps, _ = workflow_tasks.build_steps_data(db, own, "wf-1", {"doc_uuids": [], "user_id": "alice"})
    assert "the secret text" in repr(steps)


def test_a_leftover_task_setting_the_step_replaces_is_not_checked():
    """The step's input wins and the task's stale keys are dropped, so a run
    is not refused over a document it would never load."""
    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    workflow = _with_steps(db, _workflow("bob"), SELECTED, step_data={"input_sources": ["step_input"]})
    assert access.step_document_uuids(db, workflow) == []
    # Unless the task overrides the step's input.
    overriding = _with_steps(
        db, _workflow("bob"), {**SELECTED, "override_step_input": True}, step_data={"input_sources": ["step_input"]},
    )
    assert access.step_document_uuids(db, overriding) == ["secret-a"]


async def test_the_service_resolves_step_documents_the_same_way():
    step = SimpleNamespace(id="s1", data=STEP_INPUT, tasks=["t1", "t2"])
    tasks = [SimpleNamespace(id="t1", data={"prompt": "p"}),
             SimpleNamespace(id="t2", data={**SELECTED, "selected_document_uuid": "other", "override_step_input": True})]
    with patch.object(workflow_service, "WorkflowStep", fake_model_list([step])), \
         patch.object(workflow_service, "WorkflowStepTask", fake_model_list(tasks)):
        found = await workflow_service.step_document_uuids(SimpleNamespace(steps=["s1"]))
    assert found == ["secret-a", "other"]


async def test_setting_a_document_on_a_step_is_checked_before_saving():
    bob = SimpleNamespace(user_id="bob")
    step = SimpleNamespace(id="s1", name="Step", data={"input_sources": ["step_input"]}, is_output=False, tasks=[], save=AsyncMock())
    workflow = SimpleNamespace(id="w1", steps=[], save=AsyncMock(), updated_at=None)
    with patch.object(workflow_service, "WorkflowStep") as steps, \
         patch.object(workflow_service, "PydanticObjectId", lambda value: value), \
         patch.object(workflow_service, "get_authorized_workflow", AsyncMock(return_value=workflow)), \
         patch.object(workflow_service, "_get_workflow_for_step", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch("app.services.access_control.can_manage_workflow", return_value=True), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        steps.get = AsyncMock(return_value=step)
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.add_step("w1", "Step", bob, data=STEP_INPUT)
        steps.assert_not_called()  # nothing was created
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.update_step("s1", bob, data=STEP_INPUT)

    assert step.data == {"input_sources": ["step_input"]}
    step.save.assert_not_awaited()
    workflow.save.assert_not_awaited()


async def test_a_definition_with_a_document_set_on_a_step_is_checked():
    manager = SimpleNamespace(user_id="amir")
    with patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        # On the step, with a task that takes the step's input.
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_definition_documents_readable(
                {"steps": [{"data": STEP_INPUT, "tasks": [{"name": "Prompt", "data": {"prompt": "p"}}]}]}, manager,
            )
        # On a step that has no task yet.
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_definition_documents_readable({"steps": [{"data": STEP_INPUT, "tasks": []}]}, manager)
        # Already read by the workflow: not re-checked.
        await workflow_service.ensure_definition_documents_readable(
            {"steps": [{"data": STEP_INPUT, "tasks": []}]}, manager, already_step_documents={"secret-a"},
        )


# ---------------------------------------------------------------------------
# A Form Filler's template PDF is a document the run loads too
# ---------------------------------------------------------------------------

TEMPLATE = {"template_source": "pdf", "template_document_uuid": "secret-a"}


def test_only_a_pdf_template_counts_as_a_document_the_task_loads():
    assert access.task_document_uuids(TEMPLATE) == ["secret-a"]
    assert access.task_document_uuids({"template_source": "text", "template_document_uuid": "secret-a"}) == []
    assert access.task_document_uuids({**SELECTED, **TEMPLATE, "template_document_uuid": "form"}) == ["secret-a", "form"]


def test_a_run_may_not_fill_a_template_its_runner_and_owner_cannot_open():
    from app.tasks import workflow_tasks

    db = _db(smart_document=[SECRET], team=TEAMS, team_membership=MEMBERS)
    workflow = _with_steps(db, _workflow("bob"), TEMPLATE)
    db.workflow_step_task.rows[0]["name"] = "FormFiller"
    assert workflow_tasks._denied_fixed_documents(db, workflow, {"user_id": "bob"}) == ["secret-a"]
    with patch.object(workflow_tasks, "_preload_form_filler_template") as load:
        with pytest.raises(workflow_tasks.FixedDocumentsDenied):
            workflow_tasks.build_steps_data(db, workflow, "wf-1", {"doc_uuids": [], "user_id": "bob"})
    load.assert_not_called()


async def test_a_template_the_user_cannot_read_is_refused_when_saving_or_testing_a_step():
    bob = SimpleNamespace(user_id="bob")
    with patch.object(workflow_service, "get_authorized_document", _authorized(set())):
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.ensure_step_document_readable(TEMPLATE, bob)
        await workflow_service.ensure_step_document_readable(TEMPLATE, bob, already=dict(TEMPLATE))


def test_a_deleted_template_is_reported_gone_not_loaded():
    from app.services import form_fill

    db = _db(smart_document=[{"uuid": "form", "title": "Real title", "extension": "pdf", "soft_deleted": True}])
    data = {"template_source": "pdf", "template_document_uuid": "form"}
    form_fill.load_form_filler_assets(db, data, upload_dir="/nonexistent")
    assert "no longer exists" in data["template_load_error"]
    assert "Real title" not in data["template_load_error"]
    assert "template_pdf_b64" not in data
