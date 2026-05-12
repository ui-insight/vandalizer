"""Unit tests for Role Spine Layer 3.2 — role-tailored chat opener.

Covers:
- _role_first_session_addendum returns correct content per role
- select_seed_tasks pulls from the right role pool and respects count cap
"""

from app.services.briefing_primer_content import select_seed_tasks
from app.services.chat_service import (
    _role_first_session_addendum,
    _ROLE_FIRST_SESSION_ADDENDUM,
)


# ---------------------------------------------------------------------------
# Role addendum
# ---------------------------------------------------------------------------

def test_addendum_empty_for_null_role():
    assert _role_first_session_addendum(None) == ""


def test_addendum_empty_for_other_role():
    """'other' intentionally uses the unmodified generic prompt."""
    assert _role_first_session_addendum("other") == ""


def test_addendum_empty_for_unknown_role():
    assert _role_first_session_addendum("wizard") == ""


def test_addendum_present_for_known_roles():
    """Every canonical role (except 'other') must have an addendum."""
    from app.models.organization import VALID_ROLE_SEGMENTS

    for role in VALID_ROLE_SEGMENTS - {"other"}:
        addendum = _role_first_session_addendum(role)
        assert addendum, f"missing addendum for {role}"
        assert "## Role context" in addendum


def test_compliance_addendum_emphasizes_audit():
    """Compliance gets distinctive copy about audit trails."""
    addendum = _role_first_session_addendum("compliance")
    assert "audit" in addendum.lower()


def test_it_addendum_emphasizes_architecture():
    """IT gets architecture/private-endpoint framing, not researcher framing."""
    addendum = _role_first_session_addendum("it")
    assert "private" in addendum.lower() or "endpoint" in addendum.lower()


def test_pi_addendum_emphasizes_writing_flow():
    """PIs get framing around grant-writing, not document triage."""
    addendum = _role_first_session_addendum("pi")
    lower = addendum.lower()
    assert "proposal" in lower or "writing" in lower or "biosketch" in lower


def test_addendum_table_uses_canonical_keys():
    """Sanity: every key in the addendum table is a canonical role_segment."""
    from app.models.organization import VALID_ROLE_SEGMENTS

    for key in _ROLE_FIRST_SESSION_ADDENDUM:
        assert key in VALID_ROLE_SEGMENTS


# ---------------------------------------------------------------------------
# select_seed_tasks
# ---------------------------------------------------------------------------

def test_seed_tasks_returns_count():
    items = select_seed_tasks("research_admin", 3)
    assert len(items) == 3


def test_seed_tasks_respects_count_zero():
    assert select_seed_tasks("pi", 0) == []


def test_seed_tasks_returns_only_seeds_not_tips():
    """Distinct from select_primer_items which mixes seeds + tips."""
    items = select_seed_tasks("research_admin", 5)
    # Seed ids end in "-seed-..." per the content table convention
    for item in items:
        assert "-seed-" in item["id"], f"non-seed item leaked: {item['id']}"


def test_seed_tasks_falls_back_to_generic_for_unknown_role():
    items = select_seed_tasks(None, 2)
    assert len(items) == 2
    assert all(i["id"].startswith("gen-seed") for i in items)


def test_seed_tasks_distinct_from_primer_items():
    """select_seed_tasks must not include any tip items even when count > pool size."""
    items = select_seed_tasks("compliance", 99)
    for item in items:
        assert "-tip-" not in item["id"]
