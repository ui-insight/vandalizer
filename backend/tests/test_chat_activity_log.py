"""The chat's approval timeline (support ticket: NIFA subaward setup test).

The user couldn't tell what they had approved, how many times, or whether it
ran: "Move files" and "Add to inbox" had to be checked in Files and Projects
by hand.
"""

import datetime

from app.services.chat_activity_log import build_activity_log

T0 = datetime.datetime(2026, 11, 9, 14, 0, tzinfo=datetime.timezone.utc)


def _t(minutes: int) -> datetime.datetime:
    return T0 + datetime.timedelta(minutes=minutes)


def user(text="Yes, go ahead", *, at=0, approve=None, decline=None):
    m = {"role": "user", "content": text, "created_at": _t(at)}
    if approve:
        m["approval_for"] = approve
    if decline:
        m["decline_for"] = decline
    return m


def preview(call_id, tool="move_documents_to_project", label="Move files", key=None, args=None, **extra):
    call = {"tool_name": tool, "tool_call_id": call_id, "args": {**(args or {"project_uuid": "p1"}), "confirmed": False}}
    content = {"needs_confirmation": True, "approval_label": label, "preview": f"{label}: 3 files into NIFA Subaward",
               "approval_key": key or f"fp-{call_id}", **extra}
    return call, {"tool_name": tool, "tool_call_id": call_id, "content": content}


def confirmed(call_id, content, tool="move_documents_to_project", args=None):
    call = {"tool_name": tool, "tool_call_id": call_id, "args": {**(args or {"project_uuid": "p1"}), "confirmed": True}}
    return call, {"tool_name": tool, "tool_call_id": call_id, "content": content}


def assistant(*pairs, at=0, **extra):
    return {
        "role": "assistant", "content": "…", "created_at": _t(at),
        "tool_calls": [c for c, _ in pairs], "tool_results": [r for _, r in pairs], **extra,
    }


def test_approved_card_that_ran_is_done():
    log = build_activity_log([
        user("Set up the NIFA subaward", at=0),
        assistant(preview("c1"), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"status": "completed", "message": 'Moved 3 of 3 files into "NIFA".'}), at=3),
    ])
    [e] = log["entries"]
    assert (e["decision"], e["via"], e["action"], e["outcome"]) == ("approved", "button", "Move files", "done")
    assert e["detail"] == 'Moved 3 of 3 files into "NIFA".'
    assert e["time"] == _t(2).isoformat()
    assert not e["repeated"] and log["waiting"] == 0


def test_approved_twice_ran_once_is_flagged():
    # The second click found nothing armed; the gate showed the card again.
    log = build_activity_log([
        user("Add these to the inbox", at=0),
        assistant(preview("c1", tool="propose_obligations", label="Add to inbox", key="fp-ob"), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"ok": True, "added": [{}], "approval_key": "fp-ob"}, tool="propose_obligations"), at=3),
        user(at=4, approve="c1"),
        assistant(confirmed("c3", {"needs_confirmation": True, "approval_key": "fp-ob"}, tool="propose_obligations"), at=5),
    ])
    first, second = log["entries"]
    assert first["outcome"] == "done"
    assert second["outcome"] == "not_run"
    assert "no longer waiting" in second["detail"]
    assert (second["approvals"], second["runs"], second["repeated"]) == (2, 1, True)
    assert log["repeated"] == ["Add to inbox"]


def test_same_action_previewed_again_counts_as_a_repeat():
    log = build_activity_log([
        user(at=0),
        assistant(preview("c1", key="fp-move"), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"status": "completed"}), preview("c3", key="fp-move"), at=3),
        user(at=4, approve="c3"),
        assistant(confirmed("c4", {"status": "completed"}), at=5),
    ])
    assert [e["runs"] for e in log["entries"]] == [2, 2]
    assert all(e["repeated"] for e in log["entries"])


def test_waiting_card_is_listed_with_its_id():
    log = build_activity_log([
        user(at=0),
        assistant(preview("c1"), preview("c9", tool="save_to_folder", label="Save to folder"), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"status": "completed"}), at=3),
    ], pending_call_ids=["c9"])
    waiting = [e for e in log["entries"] if e["outcome"] == "waiting"]
    assert [(e["call_id"], e["action"]) for e in waiting] == [("c9", "Save to folder")]
    assert log["waiting"] == 1


def test_cancelled_card():
    log = build_activity_log([
        user(at=0), assistant(preview("c1"), at=1), user("No, cancel that", at=2, decline="c1"), assistant(at=3),
    ])
    [e] = log["entries"]
    assert (e["decision"], e["outcome"]) == ("cancelled", "cancelled")


def test_partial_and_failed_results():
    log = build_activity_log([
        user(at=0),
        assistant(preview("c1"), preview("c5", tool="run_workflow", label="Run workflow", args={"workflow_id": "w"}), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"status": "partial", "message": "Moved 2 of 3 files."}), at=3),
        user(at=4, approve="c5"),
        assistant(confirmed("c6", {"error": "Workflow not found."}, tool="run_workflow", args={"workflow_id": "w"}), at=5),
    ])
    moved, run = log["entries"]
    assert (moved["outcome"], moved["detail"]) == ("partial", "Moved 2 of 3 files.")
    assert (run["outcome"], run["detail"]) == ("not_run", "Workflow not found.")


def test_reply_that_skipped_the_action_is_not_run():
    log = build_activity_log([
        user(at=0), assistant(preview("c1"), at=1), user(at=2, approve="c1"), assistant(at=3),
    ])
    assert log["entries"][0]["outcome"] == "not_run"


def test_approval_still_streaming_has_no_result_yet():
    log = build_activity_log([user(at=0), assistant(preview("c1"), at=1), user(at=2, approve="c1")])
    assert log["entries"][0]["outcome"] == "no_result"


def test_typed_yes_that_ran_is_recorded():
    log = build_activity_log([
        user(at=0), assistant(preview("c1"), at=1), user("yes please", at=2),
        assistant(confirmed("c2", {"status": "completed"}), at=3),
    ])
    [e] = log["entries"]
    assert (e["via"], e["said"], e["outcome"]) == ("typed", "yes please", "done")


def test_typed_message_that_ran_nothing_is_not_an_approval():
    log = build_activity_log([user(at=0), assistant(preview("c1"), at=1), user("what's in file 2?", at=2), assistant(at=3)])
    assert log["entries"] == []


def test_replaced_card_nobody_decided_is_left_out():
    log = build_activity_log([user(at=0), assistant(preview("c1"), at=1), user("never mind", at=2), assistant(at=3)],
                             pending_call_ids=[])
    assert log["entries"] == []


def test_duplicate_preview_in_one_reply_shows_once():
    _, dup = preview("c2")
    dup["content"]["already_waiting"] = True
    log = build_activity_log([user(at=0), assistant(preview("c1"), (preview("c2")[0], dup), at=1)],
                             pending_call_ids=["c1"])
    assert [e["call_id"] for e in log["entries"]] == ["c1"]


async def test_audit_records_only_the_latest_turns_decisions(monkeypatch):
    """Admin → Audit gets who approved what, when, and what happened."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services import audit_service, chat_activity_log

    log = build_activity_log([
        user(at=0),
        assistant(preview("c1"), preview("c5", tool="propose_obligations", label="Add to inbox"), at=1),
        user(at=2, approve="c1"),
        assistant(confirmed("c2", {"status": "completed", "message": "Moved 3 files."}), at=3),
        user(at=4, approve="c5"),
        assistant(confirmed("c6", {"error": "You need edit access."}, tool="propose_obligations"), at=5),
    ])
    monkeypatch.setattr(chat_activity_log, "load_activity_log", AsyncMock(return_value=log))
    log_event = AsyncMock()
    monkeypatch.setattr(audit_service, "log_event", log_event)

    conv = SimpleNamespace(uuid="conv-1", title="NIFA subaward", team_id="team-1")
    who = SimpleNamespace(user_id="u-1", organization_id="org-1")
    assert await chat_activity_log.audit_turn(conv, who) == 1

    kwargs = log_event.await_args.kwargs
    assert kwargs["action"] == "chat.action_approved"
    assert (kwargs["actor_user_id"], kwargs["resource_type"], kwargs["resource_id"]) == ("u-1", "chat", "conv-1")
    assert kwargs["detail"]["action"] == "Add to inbox"
    assert kwargs["detail"]["outcome"] == "not_run"
    assert kwargs["detail"]["result"] == "You need edit access."
