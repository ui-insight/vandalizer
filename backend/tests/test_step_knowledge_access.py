"""A workflow step queries a knowledge base only for people allowed to open it.

Checked when the step is saved (or tested, imported, restored) and again
before a run queries it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import access_control, step_knowledge_access as kb_access, workflow_service

BOB = SimpleNamespace(user_id="bob")
ALICE = SimpleNamespace(user_id="alice")
KB_TASK = {"kb_uuid": "kb-a", "query": "{{ input }}"}


def _kbs(*existing: str):
    """KnowledgeBase stand-in: ``find_one`` finds only *existing* uuids."""
    model = MagicMock()
    model.uuid = "uuid"
    found: dict = {}

    async def find_one(*_):
        return found.get("next")

    model.find_one = AsyncMock(side_effect=find_one)
    return model, found


def _can_open(allowed: dict[str, set[str]]) -> AsyncMock:
    """get_authorized_knowledge_base: *allowed* maps user_id to the kbs they can open."""
    async def lookup(kb_uuid, user, **_):
        return SimpleNamespace(uuid=kb_uuid) if kb_uuid in allowed.get(user.user_id, set()) else None

    return AsyncMock(side_effect=lookup)


def test_only_a_knowledge_base_query_task_names_a_knowledge_base():
    assert kb_access.task_kb_uuid("KnowledgeBaseQuery", KB_TASK) == "kb-a"
    assert kb_access.task_kb_uuid("KnowledgeBaseQuery", {"kb_uuid": "  "}) is None
    # The same key on another kind of task is never queried.
    assert kb_access.task_kb_uuid("Prompt", KB_TASK) is None


def test_a_definition_lists_the_knowledge_bases_its_steps_query():
    definition = {"steps": [
        {"tasks": [{"name": "KnowledgeBaseQuery", "data": KB_TASK}, {"name": "Prompt", "data": {"prompt": "p"}}]},
        {"tasks": [{"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-b"}}]},
        # From an export file: importing clears this id, so it is never queried.
        {"tasks": [{"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-c", "_embedded_knowledge_base": {"title": "T"}}}]},
    ]}
    assert kb_access.definition_kb_uuids(definition) == ["kb-a", "kb-b"]
    assert kb_access.definition_kb_uuids(None) == []


def test_the_worker_finds_the_same_knowledge_bases():
    db = SimpleNamespace(
        workflow_step=MagicMock(), workflow_step_task=MagicMock(),
    )
    db.workflow_step.find_one.side_effect = lambda q, *_: {"tasks": ["t1", "t2"]}
    tasks = {"t1": {"name": "KnowledgeBaseQuery", "data": KB_TASK}, "t2": {"name": "Prompt", "data": KB_TASK}}
    db.workflow_step_task.find_one.side_effect = lambda q, *_: tasks[q["_id"]]
    assert kb_access.workflow_kb_uuids_sync(db, {"steps": ["s1"]}) == ["kb-a"]


async def test_saving_a_step_pointed_at_a_knowledge_base_you_cannot_open_is_refused():
    with patch.object(access_control, "get_authorized_knowledge_base", _can_open({"bob": {"kb-bob"}})):
        await kb_access.ensure_task_kb_readable("KnowledgeBaseQuery", {"kb_uuid": "kb-bob"}, BOB)
        with pytest.raises(workflow_service.FixedDocumentAccessError) as refused:
            await kb_access.ensure_task_kb_readable("KnowledgeBaseQuery", KB_TASK, BOB)
        # Unchanged from what the step already queried: its author's choice stands.
        await kb_access.ensure_task_kb_readable(
            "KnowledgeBaseQuery", {**KB_TASK, "k": 4}, BOB,
            already_name="KnowledgeBaseQuery", already_data=KB_TASK,
        )
        # A task that was something else before is treated as newly pointed.
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await kb_access.ensure_task_kb_readable(
                "KnowledgeBaseQuery", KB_TASK, BOB, already_name="Prompt", already_data=KB_TASK,
            )
    assert "kb-a" not in str(refused.value)
    assert "don't have access to the knowledge base" in str(refused.value)


async def test_a_definition_written_at_once_is_checked():
    definition = {"steps": [{"tasks": [{"name": "KnowledgeBaseQuery", "data": KB_TASK}]}]}
    with patch.object(access_control, "get_authorized_knowledge_base", _can_open({})):
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await kb_access.ensure_definition_kbs_readable(definition, BOB)
        # Already queried by the workflow: not re-checked.
        await kb_access.ensure_definition_kbs_readable(definition, BOB, already=["kb-a"])


async def test_a_run_may_query_a_knowledge_base_its_runner_or_owner_can_open():
    model, found = _kbs()
    found["next"] = SimpleNamespace(uuid="kb-a")
    with patch("app.models.knowledge.KnowledgeBase", model), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({"alice": {"kb-a"}})):
        # Bob's own workflow, Bob running it.
        assert await kb_access.unreadable_kbs(["kb-a"], [BOB]) == ["kb-a"]
        # Alice's workflow shared with Bob: the owner's access counts.
        assert await kb_access.unreadable_kbs(["kb-a"], [BOB, ALICE]) == []
        # A knowledge base that no longer exists is the step's own error.
        found["next"] = None
        assert await kb_access.unreadable_kbs(["gone"], [BOB]) == []


async def test_a_run_is_refused_before_dispatch_without_naming_the_knowledge_base():
    wf = SimpleNamespace(steps=["s1"], user_id="bob")
    with patch.object(kb_access, "workflow_kb_uuids", AsyncMock(return_value=["kb-a"])), \
         patch.object(kb_access, "unreadable_kbs", AsyncMock(return_value=["kb-a"])), \
         patch.object(kb_access, "_people", AsyncMock(return_value=[BOB])):
        with pytest.raises(workflow_service.FixedDocumentAccessError) as refused:
            await kb_access.ensure_kbs_runnable(wf, BOB, "bob")
    assert "neither you nor the workflow's owner can open" in str(refused.value)
    assert "kb-a" not in str(refused.value)


async def test_a_workflow_with_no_knowledge_base_step_costs_no_lookups():
    with patch.object(kb_access, "workflow_kb_uuids", AsyncMock(return_value=[])), \
         patch.object(kb_access, "unreadable_kbs", AsyncMock()) as check:
        await kb_access.ensure_kbs_runnable(SimpleNamespace(steps=["s1"], user_id="bob"), BOB, "bob")
    check.assert_not_awaited()
    # The worker opens no database connection either.
    with patch("app.tasks.run_task_async") as run:
        assert kb_access.unreadable_for_run_sync([], ["bob"]) == []
    run.assert_not_called()


def test_the_worker_refuses_the_run_before_any_step_executes():
    from app.tasks import workflow_tasks

    db = MagicMock()
    with patch.object(kb_access, "workflow_kb_uuids_sync", return_value=["kb-a"]), \
         patch.object(kb_access, "unreadable_for_run_sync", return_value=["kb-a"]) as check, \
         patch.object(workflow_tasks, "_activity_owner", return_value="amir"):
        denied = workflow_tasks._denied_knowledge_bases(db, {"user_id": "bob"}, {"user_id": "bob"}, "act-1")
    assert denied == ["kb-a"]
    # Checked against the owner, the starter on the trigger, and the activity's owner.
    assert check.call_args.args == (["kb-a"], ["bob", "bob", "amir"])
    assert "a step that queries a knowledge base" in workflow_tasks.knowledge_bases_denied_message(1)
    assert "steps that query 2 knowledge bases" in workflow_tasks.knowledge_bases_denied_message(2)


async def test_adding_or_changing_a_task_checks_its_knowledge_base_before_saving():
    step = SimpleNamespace(id="s1", tasks=[], save=AsyncMock())
    task = SimpleNamespace(id="t1", name="KnowledgeBaseQuery", data={"kb_uuid": "kb-bob"}, save=AsyncMock())
    with patch.object(workflow_service, "WorkflowStep") as steps, \
         patch.object(workflow_service, "WorkflowStepTask") as tasks, \
         patch.object(workflow_service, "PydanticObjectId", lambda value: value), \
         patch.object(workflow_service, "_get_workflow_for_step", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "_get_workflow_for_task", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch("app.services.access_control.can_manage_workflow", return_value=True), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({"bob": {"kb-bob"}})):
        steps.get = AsyncMock(return_value=step)
        tasks.get = AsyncMock(return_value=task)
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.add_task("s1", "KnowledgeBaseQuery", BOB, data=KB_TASK)
        tasks.assert_not_called()
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.update_task("t1", BOB, data=KB_TASK)

    assert task.data == {"kb_uuid": "kb-bob"}
    task.save.assert_not_awaited()
    step.save.assert_not_awaited()


async def test_changing_a_tasks_type_onto_existing_settings_is_checked_too():
    """Renaming a task to a Knowledge Base Query makes it read the kb_uuid
    already in its settings."""
    task = SimpleNamespace(id="t1", name="Prompt", data=dict(KB_TASK), save=AsyncMock())
    with patch.object(workflow_service, "WorkflowStepTask") as tasks, \
         patch.object(workflow_service, "PydanticObjectId", lambda value: value), \
         patch.object(workflow_service, "_get_workflow_for_task", AsyncMock(return_value=SimpleNamespace())), \
         patch.object(workflow_service, "get_team_access_context", AsyncMock()), \
         patch("app.services.access_control.can_manage_workflow", return_value=True), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({})):
        tasks.get = AsyncMock(return_value=task)
        with pytest.raises(workflow_service.FixedDocumentAccessError):
            await workflow_service.update_task("t1", BOB, name="KnowledgeBaseQuery")
    assert task.name == "Prompt"
    task.save.assert_not_awaited()


async def test_optimizer_trials_are_refused_like_any_run():
    wf = SimpleNamespace(steps=["s1"], user_id="bob")
    workflow_model = MagicMock()
    workflow_model.get = AsyncMock(return_value=wf)
    with patch("app.models.workflow.Workflow", workflow_model), \
         patch("beanie.PydanticObjectId", lambda value: value), \
         patch.object(kb_access, "ensure_kbs_runnable", AsyncMock()) as ensure:
        await kb_access.ensure_workflow_kbs_runnable("wf-1", BOB, "bob")
    ensure.assert_awaited_once_with(wf, BOB, "bob")


# ---------------------------------------------------------------------------
# Export and import files
# ---------------------------------------------------------------------------


async def test_an_export_names_a_knowledge_base_only_for_someone_who_can_open_it():
    from app.services import export_import_service as eis

    kb = SimpleNamespace(uuid="kb-a", title="Alice's private notes", description="Sensitive")
    model = MagicMock()
    model.find_one = AsyncMock(return_value=kb)
    with patch("app.models.knowledge.KnowledgeBase", model), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({"alice": {"kb-a"}})):
        own = await eis._resolve_task_references(KB_TASK, "KnowledgeBaseQuery", ALICE)
        other = await eis._resolve_task_references(KB_TASK, "KnowledgeBaseQuery", BOB)
        nobody = await eis._resolve_task_references(KB_TASK, "KnowledgeBaseQuery")

    assert own["_embedded_knowledge_base"] == {"title": "Alice's private notes", "description": "Sensitive"}
    # The block stays (importing relies on it), without the name.
    assert other["_embedded_knowledge_base"] == {"title": "Unknown", "description": None}
    assert nobody["_embedded_knowledge_base"] == {"title": "Unknown", "description": None}


async def test_an_export_names_a_steps_document_only_for_someone_who_can_open_it():
    from app.services import export_import_service as eis

    data = {"input_source": "select_document", "selected_document_uuid": "doc-a"}
    document = MagicMock()
    document.find_one = AsyncMock(return_value=SimpleNamespace(title="secret-A.md"))

    async def authorized(doc_uuid, user, **_):
        return SimpleNamespace(uuid=doc_uuid) if user.user_id == "alice" else None

    with patch("app.models.document.SmartDocument", document), \
         patch.object(access_control, "get_authorized_document", AsyncMock(side_effect=authorized)):
        own = await eis._resolve_task_references(data, "Prompt", ALICE)
        other = await eis._resolve_task_references(data, "Prompt", BOB)

    assert own["_embedded_document_ref"]["title"] == "secret-A.md"
    assert other["_embedded_document_ref"]["title"] == "Unknown"


async def test_an_import_clears_what_the_importer_cannot_open_and_goes_ahead():
    from app.services import export_import_service as eis

    item = {
        "input_config": {"fixed_documents": [{"uuid": "doc-bob", "title": "Mine"}, {"uuid": "doc-a", "title": "Theirs"}, "from-elsewhere"]},
        "steps": [
            {"data": {"input_sources": ["select_document"], "selected_document_uuid": "doc-a"},
             "tasks": [
                 {"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-a", "query": "q"}},
                 {"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-bob", "query": "q"}},
                 # From another deployment: the import clears this id itself.
                 {"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-x", "_embedded_knowledge_base": {"title": "T"}}},
                 {"name": "FormFiller", "data": {"template_source": "pdf", "template_document_uuid": "doc-a"}},
                 {"name": "Prompt", "data": {"input_source": "select_document", "selected_document_uuid": "doc-bob"}},
             ]},
        ],
    }

    async def document(doc_uuid, user, **_):
        return SimpleNamespace(uuid=doc_uuid, soft_deleted=False) if doc_uuid == "doc-bob" else None

    # "doc-a" exists here and is someone else's; "from-elsewhere" does not exist here.
    documents = MagicMock()
    documents.find_one = AsyncMock(side_effect=lambda query: SimpleNamespace() if query["uuid"] == "doc-a" else None)
    with patch("app.models.document.SmartDocument", documents), \
         patch.object(access_control, "get_authorized_document", AsyncMock(side_effect=document)), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({"bob": {"kb-bob"}})):
        await eis.drop_unreadable_import_references(item, BOB)

    # Someone else's file is left out; one from another deployment stays, to
    # be reported as missing rather than silently dropped.
    assert item["input_config"]["fixed_documents"] == [{"uuid": "doc-bob", "title": "Mine"}, "from-elsewhere"]
    step = item["steps"][0]
    assert step["data"]["selected_document_uuid"] == ""
    tasks = step["tasks"]
    assert tasks[0]["data"]["kb_uuid"] == "" and "knowledge base" in tasks[0]["data"]["_import_note"]
    assert tasks[1]["data"]["kb_uuid"] == "kb-bob"
    assert tasks[2]["data"]["kb_uuid"] == "kb-x"
    assert tasks[3]["data"]["template_document_uuid"] == ""
    assert tasks[4]["data"]["selected_document_uuid"] == "doc-bob"


async def test_importing_into_a_workflow_keeps_what_it_already_uses():
    from app.services import export_import_service as eis

    item = {
        "input_config": {"fixed_documents": [{"uuid": "owners-file"}]},
        "steps": [{"tasks": [
            {"name": "KnowledgeBaseQuery", "data": {"kb_uuid": "kb-a"}},
            {"name": "Prompt", "data": {"input_source": "select_document", "selected_document_uuid": "owners-doc"}},
        ]}],
    }
    with patch.object(access_control, "get_authorized_document", AsyncMock(return_value=None)), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({})):
        await eis.drop_unreadable_import_references(
            item, BOB, keep_fixed_documents={"fixed_documents": ["owners-file"]},
            keep_documents={"owners-doc"}, keep_knowledge_bases={"kb-a"},
        )

    assert item["input_config"]["fixed_documents"] == [{"uuid": "owners-file"}]
    assert item["steps"][0]["tasks"][0]["data"]["kb_uuid"] == "kb-a"
    assert item["steps"][0]["tasks"][1]["data"]["selected_document_uuid"] == "owners-doc"


@pytest.mark.parametrize("item", [
    # Shapes the editor never writes, which would still be read back as a
    # reference once saved: a mapping of fixed documents, task settings as a
    # list of pairs.
    {"input_config": {"fixed_documents": {"doc-a": 1}}},
    {"input_config": ["fixed_documents"]},
    {"input_config": {"fixed_documents": [["doc-a"]]}},
    {"steps": [{"tasks": [{"name": "KnowledgeBaseQuery", "data": [["kb_uuid", "kb-a"], ["query", "q"]]}]}]},
    {"steps": [{"data": [["selected_document_uuid", "doc-a"]], "tasks": []}]},
    {"steps": [{"tasks": {"0": {"name": "Prompt", "data": {}}}}]},
    {"steps": [["tasks"]]},
    {"steps": {"0": {}}},
])
async def test_an_import_file_in_an_unexpected_shape_is_rejected(item):
    from app.services import export_import_service as eis

    with patch.object(access_control, "get_authorized_document", AsyncMock(return_value=None)), \
         patch.object(access_control, "get_authorized_knowledge_base", _can_open({})):
        with pytest.raises(ValueError, match="isn't a valid workflow export"):
            await eis.drop_unreadable_import_references(item, BOB)


async def test_both_import_routes_clear_references_before_saving(monkeypatch):
    """The routes hand the file's first item to the check, with what the target
    already uses when importing into an existing workflow."""
    import io
    import json

    from fastapi import UploadFile

    from app.routers import workflows as routes
    from app.services import export_import_service as eis

    payload = {"export_type": "workflow", "items": [{"steps": []}]}
    calls: list[tuple] = []

    async def drop(item, user, **kept):
        calls.append((item, user, kept))
        return item

    target = SimpleNamespace(input_config={"fixed_documents": ["owners-file"]})
    monkeypatch.setattr(eis, "drop_unreadable_import_references", drop)
    monkeypatch.setattr(eis, "import_workflow", AsyncMock(return_value={"id": "new"}))
    monkeypatch.setattr(eis, "import_into_workflow", AsyncMock(return_value={"id": "w1"}))
    monkeypatch.setattr(routes, "get_authorized_workflow", AsyncMock(return_value=target))
    monkeypatch.setattr(routes, "_workflow_response_from_dict", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(routes.svc, "step_document_uuids", AsyncMock(return_value=["owners-doc"]))
    monkeypatch.setattr(kb_access, "workflow_kb_uuids", AsyncMock(return_value=["kb-a"]))
    user = SimpleNamespace(user_id="bob", current_team=None)

    def upload():
        return UploadFile(file=io.BytesIO(json.dumps(payload).encode()), filename="wf.json")

    await _call(routes.import_workflow, upload(), user)
    await _call(routes.import_into_workflow, "w1", upload(), user)

    assert [c[2] for c in calls] == [
        {},
        {"keep_fixed_documents": {"fixed_documents": ["owners-file"]},
         "keep_documents": {"owners-doc"}, "keep_knowledge_bases": {"kb-a"}},
    ]
    assert all(c[0] == {"steps": []} and c[1] is user for c in calls)


async def _call(route, *args):
    """Call a route function directly, whatever its parameter names are."""
    import inspect

    target = inspect.unwrap(route)
    names = [n for n in inspect.signature(target).parameters if n != "request"]
    kwargs = dict(zip(names, args))
    if "request" in inspect.signature(target).parameters:
        kwargs["request"] = MagicMock()
    return await target(**kwargs)
