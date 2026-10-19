"""Tier 2: the KB list total that the My KBs / Team tab counts show.

Org visibility used to be applied to the fetched page in Python, after the
count, so ``total`` included team KBs scoped to orgs the user is not in.
Now that the tabs display the total, it has to match what the user can see.
"""

import os

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]


async def _team_kb(title: str, **fields):
    from app.models.knowledge import KnowledgeBase

    kb = KnowledgeBase(title=title, user_id=fields.pop("user_id", "colleague"),
                       team_id="team-1", shared_with_team=True, **fields)
    await kb.insert()
    return kb


async def test_team_total_counts_only_kbs_the_user_can_see(mongo_client):
    from app.models.knowledge import KnowledgeBase
    from app.services.knowledge_service import list_knowledge_bases

    await _team_kb("Unscoped")
    await _team_kb("Our college", organization_ids=["org-engineering"])
    await _team_kb("Another college", organization_ids=["org-law"])
    await _team_kb("Mine, other college", user_id="me", organization_ids=["org-law"])
    # A row written before organization_ids existed.
    legacy = await _team_kb("Legacy")
    await KnowledgeBase.get_motor_collection().update_one(
        {"uuid": legacy.uuid}, {"$unset": {"organization_ids": ""}},
    )

    kbs, total = await list_knowledge_bases(
        "me", team_id="team-1", user_org_ancestry=["org-engineering", "org-university"], scope="team",
    )

    assert sorted(kb.title for kb in kbs) == [
        "Legacy", "Mine, other college", "Our college", "Unscoped",
    ]
    assert total == 4


async def test_pages_are_full_when_hidden_kbs_sort_first(mongo_client):
    from app.services.knowledge_service import list_knowledge_bases

    for i in range(3):
        await _team_kb(f"Visible {i}")
    # Newest, so they would have filled the first page and then been dropped.
    for i in range(3):
        await _team_kb(f"Hidden {i}", organization_ids=["org-law"])

    kbs, total = await list_knowledge_bases(
        "me", team_id="team-1", user_org_ancestry=["org-engineering"], scope="team", limit=3,
    )

    assert total == 3
    assert len(kbs) == 3
