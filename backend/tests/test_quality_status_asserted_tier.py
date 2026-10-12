"""A catalog author's tier is not a validation result (#1013 §5).

Seeded workflows and extractions carry a hand-typed quality tier
("excellent") with no score and no validation run. The editors' Quality
card read that as validated and showed a green "excellent" shield.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers import extractions as extractions_router
from app.routers import workflows as workflows_router


def _meta(score=None, tier="excellent"):
    return SimpleNamespace(
        quality_score=score, quality_tier=tier, last_validated_at=None,
        regression_pending_review=False, validation_run_count=0,
    )


def _patches(meta, latest):
    verified = MagicMock()
    verified.find_one = AsyncMock(return_value=meta)
    return (
        patch("app.models.verification.VerifiedItemMetadata", verified),
        patch("app.services.quality_service.get_latest_validation", AsyncMock(return_value=latest)),
    )


async def _workflow_status(meta, latest=None):
    p1, p2 = _patches(meta, latest)
    wf = SimpleNamespace(validation_plan=[], steps=[])
    with p1, p2, patch.object(workflows_router, "get_authorized_workflow", AsyncMock(return_value=wf)):
        return await workflows_router.get_workflow_quality_status("wf-1", user=MagicMock())


async def _extraction_status(meta, latest=None):
    p1, p2 = _patches(meta, latest)
    ss = SimpleNamespace(extraction_config={})
    with p1, p2, patch.object(extractions_router, "_get_search_set_or_404", AsyncMock(return_value=ss)):
        return await extractions_router.get_extraction_quality_status("ss-1", user=MagicMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("status_of", [_workflow_status, _extraction_status])
async def test_an_author_tier_alone_is_unvalidated(status_of):
    result = await status_of(_meta())
    assert result["status"] == "unvalidated"
    assert result["tier"] is None
    assert result["tier_asserted"] == "excellent"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_of", [_workflow_status, _extraction_status])
async def test_a_measured_score_is_still_validated(status_of):
    result = await status_of(_meta(score=91.0))
    assert result["status"] == "validated"
    assert result["tier"] == "excellent"
    assert "tier_asserted" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("status_of", [_workflow_status, _extraction_status])
async def test_a_validation_run_is_still_validated(status_of):
    latest = {"score": 72.0, "created_at": "2026-10-01T00:00:00+00:00", "extraction_config": {}}
    result = await status_of(_meta(), latest)
    assert result["status"] == "validated"
