"""Who may have a workflow read its fixed documents.

A fixed document rides along on every run of a workflow, so it follows the
same access rules as a document someone selects for a run.

Two rules:

* **Saving**: a fixed document can only be added by someone who can read it
  (``workflow_service.ensure_fixed_documents_readable``).
* **Running**: a fixed document is read only if the person running the
  workflow, or the workflow's owner, can read it. The owner counts because
  bundling a reference file into a workflow they share is theirs to decide;
  a copy of that workflow belongs to someone else and gets no such pass.

This module is the run-time rule for the worker, which is synchronous pymongo
and cannot call ``access_control``. It mirrors ``get_authorized_document``
for reading: a file inside a project follows the project's access, any other
file is its owner's and their team's. Keep the two in step.
"""

from __future__ import annotations

from typing import Iterable

from pymongo.database import Database

FIXED_DOCUMENT_ACCESS_MESSAGE = (
    "You don't have access to a document set as a fixed document. Choose a "
    "file of your own or one that has been shared with you."
)

_PROJECT_READ_ROLES = ("owner", "editor", "viewer")


def fixed_document_uuids(input_config: dict | None) -> list[str]:
    """The fixed documents a run will load, in order, without duplicates.

    Empty in ``no_input`` mode, which never loads them.
    """
    config = input_config if isinstance(input_config, dict) else {}
    if config.get("trigger_type") == "no_input":
        return []
    uuids: list[str] = []
    for entry in config.get("fixed_documents") or []:
        uuid = (entry.get("uuid") if isinstance(entry, dict) else str(entry)) or ""
        if uuid and uuid not in uuids:
            uuids.append(uuid)
    return uuids


def fixed_documents_denied_message(count: int) -> str:
    """Deliberately names no file: the reader isn't entitled to its title."""
    one = count == 1
    return (
        f"This workflow has {'a fixed document' if one else f'{count} fixed documents'} that "
        f"neither you nor the workflow's owner can open, so the run was stopped before reading "
        f"{'it' if one else 'them'}. Remove {'it' if one else 'them'} on the workflow's Input tab, "
        f"or ask the file's owner to share {'it' if one else 'them'}."
    )


def _team_ids(db: Database[dict], user_id: str) -> set[str]:
    """Every team the user belongs to, as both uuid and ObjectId string."""
    team_oids = [m.get("team") for m in db.team_membership.find({"user_id": user_id}, {"team": 1})]
    team_oids = [oid for oid in team_oids if oid is not None]
    if not team_oids:
        return set()
    ids: set[str] = set()
    for team in db.team.find({"_id": {"$in": team_oids}}, {"uuid": 1}):
        ids.add(str(team["_id"]))
        if team.get("uuid"):
            ids.add(team["uuid"])
    return ids


def _folder_project(db: Database[dict], folder_uuid: object) -> dict | None:
    """The nearest project whose root folder contains *folder_uuid*."""
    ancestors: list[str] = []
    cursor = folder_uuid
    while isinstance(cursor, str) and cursor and cursor != "0" and cursor not in ancestors:
        folder = db.smart_folder.find_one({"uuid": cursor}, {"parent_id": 1})
        if not folder:
            break
        ancestors.append(cursor)
        cursor = folder.get("parent_id")
    if not ancestors:
        return None
    projects = list(db.project.find({"root_folder_uuid": {"$in": ancestors}}))
    if not projects:
        return None
    return min(projects, key=lambda p: ancestors.index(p["root_folder_uuid"]))


class _Reader:
    """One person's access, looked up once per run."""

    def __init__(self, db: Database[dict], user_id: str) -> None:
        self.db = db
        self.user_id = user_id
        user = db.user.find_one({"user_id": user_id}, {"is_admin": 1}) or {}
        self.is_admin = bool(user.get("is_admin"))
        self._teams: set[str] | None = None

    @property
    def teams(self) -> set[str]:
        if self._teams is None:
            self._teams = _team_ids(self.db, self.user_id)
        return self._teams

    def can_read(self, document: dict) -> bool:
        if self.is_admin:
            return True
        project = _folder_project(self.db, document.get("folder"))
        if project:
            if project.get("owner_user_id") == self.user_id:
                return True
            if project.get("team_id") and project["team_id"] in self.teams:
                return True
            membership = self.db.project_membership.find_one(
                {"project_uuid": project.get("uuid"), "user_id": self.user_id}, {"role": 1},
            )
            return bool(membership and membership.get("role") in _PROJECT_READ_ROLES)
        if document.get("user_id") == self.user_id:
            return True
        return bool(document.get("team_id") and document["team_id"] in self.teams)


def unreadable_fixed_documents(
    db: Database[dict], workflow_doc: dict, runner_user_ids: Iterable[str | None] = (),
) -> list[str]:
    """Uuids of fixed documents this run may not read.

    A document is readable when the workflow's owner or anyone in
    *runner_user_ids* (the person who started the run) can read it. Documents
    that no longer exist are not listed: a deleted fixed document is reported
    by ``_missing_fixed_documents`` with its own message.
    """
    uuids = fixed_document_uuids(workflow_doc.get("input_config"))
    if not uuids:
        return []
    people: list[str] = []
    for user_id in (workflow_doc.get("user_id"), *runner_user_ids):
        if user_id and user_id not in people:
            people.append(user_id)
    readers = [_Reader(db, user_id) for user_id in people]
    denied: list[str] = []
    for uuid in uuids:
        document = db.smart_document.find_one(
            {"uuid": uuid}, {"uuid": 1, "user_id": 1, "team_id": 1, "folder": 1, "soft_deleted": 1},
        )
        if not document or document.get("soft_deleted"):
            continue
        if not any(reader.can_read(document) for reader in readers):
            denied.append(uuid)
    return denied
