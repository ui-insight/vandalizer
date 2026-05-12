"""Unit tests for Role Spine Layer 3.3 — list_role_matched_items.

Exercises the recommendation ranking against mocked LibraryItem +
VerifiedItemMetadata records. End-to-end with a real DB lives in tier-2.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _li(item_id: str, kind: str = "workflow"):
    """Build a LibraryItem-shaped mock. Uses the real LibraryItemKind enum so
    `li.kind == LibraryItemKind.WORKFLOW` comparisons in the service code work."""
    from app.models.library import LibraryItemKind

    m = MagicMock()
    m.item_id = item_id
    m.kind = LibraryItemKind(kind)
    return m


def _meta(kind: str, item_id: str, *, role_tags=None, quality=None, organization_ids=None, description=None, quality_tier=None):
    m = MagicMock()
    m.item_kind = kind
    m.item_id = str(item_id)
    m.role_tags = role_tags or []
    m.quality_score = quality
    m.quality_tier = quality_tier
    m.organization_ids = organization_ids or []
    m.description = description
    return m


def _user(role_segment: str | None):
    u = MagicMock()
    u.role_segment = role_segment
    return u


def _patch_db(items, metas, names):
    """Patch the three batch-fetches in list_role_matched_items.

    items: list of LibraryItem mocks
    metas: list of VerifiedItemMetadata mocks
    names: dict[str (item_id), str (resolved name)]
    """
    from app.services import verification_service as svc

    items_chain = MagicMock()
    items_chain.to_list = AsyncMock(return_value=items)
    items_find_chain = MagicMock()
    items_find_chain.sort = MagicMock(return_value=items_chain)

    meta_chain = MagicMock()
    meta_chain.to_list = AsyncMock(return_value=metas)

    def wf_find(_filter):
        wf_chain = MagicMock()
        wfs = []
        for wid in _filter.get("_id", {}).get("$in", []):
            if str(wid) in names:
                wf = MagicMock()
                wf.id = wid
                wf.name = names[str(wid)]
                wfs.append(wf)
        wf_chain.to_list = AsyncMock(return_value=wfs)
        return wf_chain

    def ss_find(_filter):
        ss_chain = MagicMock()
        sss = []
        for sid in _filter.get("_id", {}).get("$in", []):
            if str(sid) in names:
                ss = MagicMock()
                ss.id = sid
                ss.title = names[str(sid)]
                sss.append(ss)
        ss_chain.to_list = AsyncMock(return_value=sss)
        return ss_chain

    def kb_find(_filter):
        kb_chain = MagicMock()
        kbs = []
        for kid in _filter.get("_id", {}).get("$in", []):
            if str(kid) in names:
                kb = MagicMock()
                kb.id = kid
                kb.title = names[str(kid)]
                kbs.append(kb)
        kb_chain.to_list = AsyncMock(return_value=kbs)
        return kb_chain

    return [
        patch.object(svc.LibraryItem, "find", return_value=items_find_chain),
        patch.object(svc.VerifiedItemMetadata, "find_all", return_value=meta_chain),
        patch.object(svc.Workflow, "find", side_effect=wf_find),
        patch.object(svc.SearchSet, "find", side_effect=ss_find),
        patch.object(svc.KnowledgeBase, "find", side_effect=kb_find),
    ]


@pytest.fixture
def patch_db():
    """Helper: returns a context-manager-builder that applies _patch_db patches."""
    from contextlib import ExitStack

    def _apply(items, metas, names):
        stack = ExitStack()
        for p in _patch_db(items, metas, names):
            stack.enter_context(p)
        return stack

    return _apply


# ---------------------------------------------------------------------------
# Filter behavior
# ---------------------------------------------------------------------------

async def test_role_matched_only_returns_universal_and_overlapping(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [
        _li("a"),  # universal
        _li("b"),  # role-tagged for compliance
        _li("c"),  # role-tagged for PI
    ]
    metas = [
        _meta("workflow", "a", role_tags=[], quality=0.9),
        _meta("workflow", "b", role_tags=["compliance"], quality=0.95),
        _meta("workflow", "c", role_tags=["pi"], quality=0.99),
    ]
    names = {"a": "Alpha", "b": "Bravo", "c": "Charlie"}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=5)

    ids = [r["item_id"] for r in result]
    assert "b" in ids  # role match
    assert "a" in ids  # universal
    assert "c" not in ids  # other role


async def test_role_matched_prefers_role_match_over_universal(patch_db):
    """Even when universal has higher quality, a role-matched item ranks first."""
    from app.services.verification_service import list_role_matched_items

    items = [_li("u"), _li("r")]
    metas = [
        _meta("workflow", "u", role_tags=[], quality=0.99),
        _meta("workflow", "r", role_tags=["compliance"], quality=0.70),
    ]
    names = {"u": "Universal", "r": "RoleMatch"}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=2)

    assert result[0]["item_id"] == "r"  # role match wins despite lower quality
    assert result[1]["item_id"] == "u"


async def test_role_matched_secondary_sort_by_quality(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [_li("a"), _li("b"), _li("c")]
    metas = [
        _meta("workflow", "a", role_tags=["compliance"], quality=0.7),
        _meta("workflow", "b", role_tags=["compliance"], quality=0.95),
        _meta("workflow", "c", role_tags=["compliance"], quality=0.85),
    ]
    names = {"a": "A", "b": "B", "c": "C"}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=3)

    assert [r["item_id"] for r in result] == ["b", "c", "a"]


async def test_user_with_no_role_sees_only_universal(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [_li("u"), _li("r")]
    metas = [
        _meta("workflow", "u", role_tags=[], quality=0.8),
        _meta("workflow", "r", role_tags=["compliance"], quality=0.99),
    ]
    names = {"u": "Universal", "r": "RoleMatch"}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user(None), limit=5)

    ids = [r["item_id"] for r in result]
    assert "u" in ids
    assert "r" not in ids


async def test_org_visibility_filters_out_unauthorized(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [_li("a"), _li("b")]
    metas = [
        _meta("workflow", "a", role_tags=["compliance"], quality=0.9, organization_ids=["org-x"]),
        _meta("workflow", "b", role_tags=["compliance"], quality=0.8, organization_ids=[]),
    ]
    names = {"a": "A", "b": "B"}

    # User's ancestry doesn't include org-x
    with patch_db(items, metas, names):
        result = await list_role_matched_items(
            _user("compliance"), limit=5, user_org_ancestry=["org-y"]
        )

    ids = [r["item_id"] for r in result]
    assert "a" not in ids  # scoped out
    assert "b" in ids


async def test_limit_caps_results(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [_li(str(i)) for i in range(10)]
    metas = [_meta("workflow", str(i), role_tags=["compliance"], quality=0.5 + i * 0.01) for i in range(10)]
    names = {str(i): f"Item {i}" for i in range(10)}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=3)

    assert len(result) == 3


async def test_zero_limit_returns_empty(patch_db):
    from app.services.verification_service import list_role_matched_items

    with patch_db([], [], {}):
        result = await list_role_matched_items(_user("compliance"), limit=0)

    assert result == []


async def test_items_without_resolvable_name_are_skipped(patch_db):
    from app.services.verification_service import list_role_matched_items

    items = [_li("nameless"), _li("named")]
    metas = [
        _meta("workflow", "nameless", role_tags=["compliance"], quality=0.99),
        _meta("workflow", "named", role_tags=["compliance"], quality=0.5),
    ]
    names = {"named": "Named"}  # "nameless" intentionally missing

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=5)

    assert [r["item_id"] for r in result] == ["named"]


async def test_response_shape(patch_db):
    """The serialized result should carry the fields the frontend renders."""
    from app.services.verification_service import list_role_matched_items

    items = [_li("a")]
    metas = [_meta("workflow", "a", role_tags=["compliance"], quality=0.87, quality_tier="bronze", description="Does the thing")]
    names = {"a": "Alpha"}

    with patch_db(items, metas, names):
        result = await list_role_matched_items(_user("compliance"), limit=1)

    assert len(result) == 1
    r = result[0]
    assert r["item_id"] == "a"
    assert r["kind"] == "workflow"
    assert r["name"] == "Alpha"
    assert r["description"] == "Does the thing"
    assert r["quality_score"] == 0.87
    assert r["quality_tier"] == "bronze"
    assert r["role_tags"] == ["compliance"]
    assert r["deep_link"].startswith("/library?tab=catalog&item=")
