"""Regression tests for the agentic-chat security hardening.

Covers three fixes:
  1. KB cross-tenant access — ``shared_with_team`` is not a global grant.
  2. SSRF — redirects are re-validated hop-by-hop (``safe_get``).
  3. Write-tool confirmation — the agent cannot self-confirm within one turn;
     a preview must be armed on an earlier turn before execution.

These live in a separate module (not test_chat_tools.py) on purpose, so they
don't collide with other in-flight edits to the main tool test file.
"""

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# 1. KB cross-tenant access
# ---------------------------------------------------------------------------

def _kb(**kw):
    base = {"user_id": "owner", "shared_with_team": False, "team_id": None, "verified": False}
    base.update(kw)
    return SimpleNamespace(**base)


def test_kb_access_owner_allowed():
    from app.services.chat_tools import _kb_access_ok
    kb = _kb(user_id="alice")
    assert _kb_access_ok(kb, "alice", None) is True


def test_kb_access_other_user_denied():
    from app.services.chat_tools import _kb_access_ok
    kb = _kb(user_id="alice")
    assert _kb_access_ok(kb, "mallory", "team-x") is False


def test_kb_shared_with_team_requires_matching_team():
    from app.services.chat_tools import _kb_access_ok
    kb = _kb(user_id="alice", shared_with_team=True, team_id="team-a")
    # Member of the owning team: allowed.
    assert _kb_access_ok(kb, "bob", "team-a") is True
    # Different team: DENIED (the old `... and not shared_with_team` bug let
    # this through).
    assert _kb_access_ok(kb, "mallory", "team-b") is False
    # No current team: DENIED (old read gate skipped the team check when the
    # caller's team_id was falsy).
    assert _kb_access_ok(kb, "mallory", None) is False


def test_kb_shared_with_team_but_no_team_id_denied_cross_user():
    from app.services.chat_tools import _kb_access_ok
    kb = _kb(user_id="alice", shared_with_team=True, team_id=None)
    assert _kb_access_ok(kb, "mallory", "team-b") is False


# ---------------------------------------------------------------------------
# 2. SSRF — redirect re-validation
# ---------------------------------------------------------------------------

class _FakeURL:
    def __init__(self, url):
        self._url = url

    def join(self, other):
        # The tests use absolute redirect targets, so join just adopts them.
        return _FakeURL(other)

    def __str__(self):
        return self._url


class _FakeResponse:
    def __init__(self, url, *, redirect_to=None):
        self.url = _FakeURL(url)
        self.is_redirect = redirect_to is not None
        self.headers = {"location": redirect_to} if redirect_to else {}


class _FakeClient:
    """Records every URL fetched and replays a scripted redirect chain."""

    def __init__(self, script):
        # script: {requested_url: _FakeResponse}
        self.script = script
        self.fetched = []

    async def get(self, url):
        self.fetched.append(url)
        return self.script[url]


@pytest.mark.asyncio
async def test_safe_get_blocks_redirect_to_internal(monkeypatch):
    from app.utils import url_validation

    # First hop is a public host; it 302s to the cloud metadata IP.
    def fake_validate(url):
        host = url.split("//", 1)[1].split("/", 1)[0]
        if host in ("169.254.169.254", "10.0.0.1", "localhost", "127.0.0.1"):
            raise ValueError(f"blocked {host}")
        return url

    monkeypatch.setattr(url_validation, "validate_outbound_url", fake_validate)

    client = _FakeClient({
        "https://evil.example.com/": _FakeResponse(
            "https://evil.example.com/", redirect_to="http://169.254.169.254/latest/meta-data/"
        ),
    })

    with pytest.raises(ValueError):
        await url_validation.safe_get(client, "https://evil.example.com/")

    # We must NOT have fetched the internal address.
    assert "http://169.254.169.254/latest/meta-data/" not in client.fetched


@pytest.mark.asyncio
async def test_safe_get_follows_safe_redirect(monkeypatch):
    from app.utils import url_validation

    monkeypatch.setattr(url_validation, "validate_outbound_url", lambda u: u)

    client = _FakeClient({
        "https://a.example.com/": _FakeResponse(
            "https://a.example.com/", redirect_to="https://b.example.com/final"
        ),
        "https://b.example.com/final": _FakeResponse("https://b.example.com/final"),
    })

    resp = await url_validation.safe_get(client, "https://a.example.com/")
    assert str(resp.url) == "https://b.example.com/final"
    assert client.fetched == ["https://a.example.com/", "https://b.example.com/final"]


@pytest.mark.asyncio
async def test_safe_get_redirect_limit(monkeypatch):
    from app.utils import url_validation

    monkeypatch.setattr(url_validation, "validate_outbound_url", lambda u: u)

    # Always redirects to itself → exceeds the cap.
    loop = {"https://loop.example.com/": _FakeResponse(
        "https://loop.example.com/", redirect_to="https://loop.example.com/"
    )}
    client = _FakeClient(loop)
    with pytest.raises(ValueError):
        await url_validation.safe_get(client, "https://loop.example.com/", max_redirects=2)


# ---------------------------------------------------------------------------
# 3. Write-tool confirmation gate
# ---------------------------------------------------------------------------

class _FakeConversation:
    def __init__(self, pending=None):
        self.pending_confirmations = list(pending or [])
        self.saves = 0

    async def save(self):
        self.saves += 1


def _ctx(conversation, turn_marker):
    deps = SimpleNamespace(conversation=conversation, turn_marker=turn_marker)
    return SimpleNamespace(deps=deps)


PREVIEW = {"action": "run_workflow", "preview": "Run X", "needs_confirmation": True}
KEY = {"workflow_id": "wf1", "docs": ["d1"]}


@pytest.mark.asyncio
async def test_confirm_gate_same_turn_self_confirm_is_downgraded():
    """confirmed=true on the first call (no prior-turn arming) → preview, no execute."""
    from app.services.chat_tools import _confirm_gate

    conv = _FakeConversation()
    ctx = _ctx(conv, turn_marker=5)
    out = await _confirm_gate(
        ctx, tool_name="run_workflow", key=KEY, confirmed=True, preview=PREVIEW
    )
    assert out is not None  # downgraded to a preview
    assert out["needs_confirmation"] is True
    # The action got armed for a future turn.
    assert len(conv.pending_confirmations) == 1
    assert conv.pending_confirmations[0]["turn"] == 5


@pytest.mark.asyncio
async def test_confirm_gate_preview_signals_action_not_performed():
    """A gated preview must be unmistakably 'not done' so the model can't
    narrate success (e.g. 'the PDFs are now indexed') on the preview turn."""
    from app.services.chat_tools import _confirm_gate

    conv = _FakeConversation()
    ctx = _ctx(conv, turn_marker=5)
    out = await _confirm_gate(
        ctx, tool_name="add_documents_to_kb", key=KEY, confirmed=True, preview=PREVIEW
    )
    assert out is not None
    assert out["status"] == "awaiting_user_confirmation"
    assert "NOT" in out["assistant_instruction"]
    assert "add_documents_to_kb" in out["assistant_instruction"]


@pytest.mark.asyncio
async def test_confirm_gate_preview_then_confirm_across_turns_executes():
    from app.services.chat_tools import _confirm_gate

    conv = _FakeConversation()

    # Turn 1: preview (confirmed=false). Arms at turn marker 5.
    ctx1 = _ctx(conv, turn_marker=5)
    out1 = await _confirm_gate(
        ctx1, tool_name="run_workflow", key=KEY, confirmed=False, preview=PREVIEW
    )
    assert out1 is not None
    assert len(conv.pending_confirmations) == 1

    # Turn 2 (a later user turn, larger marker): confirmed=true → executes.
    ctx2 = _ctx(conv, turn_marker=7)
    out2 = await _confirm_gate(
        ctx2, tool_name="run_workflow", key=KEY, confirmed=True, preview=PREVIEW
    )
    assert out2 is None  # caller proceeds to execute
    # Consumed: the pending entry is cleared so it can't be replayed.
    assert conv.pending_confirmations == []


@pytest.mark.asyncio
async def test_confirm_gate_confirm_same_turn_as_arming_does_not_execute():
    """Even with an armed entry, a confirm on the SAME turn must not execute."""
    from app.services.chat_tools import _confirm_gate

    conv = _FakeConversation([{"fp": "x", "turn": 5, "tool": "run_workflow"}])
    # Re-arm + confirm both at marker 5.
    ctx = _ctx(conv, turn_marker=5)
    out = await _confirm_gate(
        ctx, tool_name="run_workflow", key=KEY, confirmed=True, preview=PREVIEW
    )
    assert out is not None  # not executed; same-turn


@pytest.mark.asyncio
async def test_confirm_gate_fails_closed_without_conversation():
    from app.services.chat_tools import _confirm_gate

    ctx = _ctx(None, turn_marker=0)
    out = await _confirm_gate(
        ctx, tool_name="run_workflow", key=KEY, confirmed=True, preview=PREVIEW
    )
    assert out is not None  # no conversation → never executes


@pytest.mark.asyncio
async def test_confirm_gate_different_action_does_not_match():
    """A preview for action A must not authorize a different action B."""
    from app.services.chat_tools import _confirm_gate

    conv = _FakeConversation()
    # Arm action A on turn 5.
    await _confirm_gate(
        _ctx(conv, 5), tool_name="run_workflow", key=KEY, confirmed=False, preview=PREVIEW
    )
    # On a later turn, confirm a DIFFERENT action (different key) → downgraded.
    out = await _confirm_gate(
        _ctx(conv, 7),
        tool_name="run_workflow",
        key={"workflow_id": "wf2", "docs": ["d9"]},
        confirmed=True,
        preview=PREVIEW,
    )
    assert out is not None  # different fingerprint → not authorized
