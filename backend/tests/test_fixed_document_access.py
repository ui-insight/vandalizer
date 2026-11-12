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


def test_the_refusal_names_no_file():
    message = access.fixed_documents_denied_message(1)
    assert "neither you nor the workflow's owner can open" in message
    assert "secret" not in message.lower()
    assert "2 fixed documents" in access.fixed_documents_denied_message(2)


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
