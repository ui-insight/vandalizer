"""Tests for the Phase 11 certification chat tools in app.services.chat_tools.

The tools are thin wrappers over certification_service (the same service the
Certification panel calls), so these tests mock the service layer and verify
argument plumbing, result shape, and error handling.
"""

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.chat_tools import (
    check_certification_module,
    complete_certification_module,
    get_certification_module,
    get_certification_progress,
    provision_certification_lab,
    submit_certification_assessment,
)


def _make_context(**overrides):
    @dataclass
    class FakeDeps:
        user: MagicMock = field(default_factory=lambda: MagicMock(user_id="user1"))
        user_id: str = "user1"
        team_id: str | None = "team1"

    ctx = MagicMock()
    ctx.deps = FakeDeps(**{k: v for k, v in overrides.items() if k in FakeDeps.__dataclass_fields__})
    return ctx


def _progress(modules=None, **overrides):
    base = {
        "id": "p1",
        "user_id": "user1",
        "modules": modules or {},
        "total_xp": 150,
        "level": "apprentice",
        "certified": False,
        "certified_at": None,
        "streak_days": 2,
        "last_activity_date": "2026-07-09",
        "unlocked": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# get_certification_progress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_reports_next_module_and_counts():
    modules = {
        "ai_literacy": {"completed": True, "stars": 3},
        "foundations": {"completed": True, "stars": 2},
    }
    with patch(
        "app.services.certification_service.get_progress_dict",
        new=AsyncMock(return_value=_progress(modules)),
    ):
        result = await get_certification_progress(_make_context())

    assert result["modules_completed"] == 2
    assert result["modules_total"] == 11
    # Next incomplete module in MODULE_ORDER after ai_literacy + foundations
    assert result["next_module_id"] == "process_mapping"
    assert result["total_xp"] == 150
    assert result["level"] == "apprentice"
    by_id = {m["module_id"]: m for m in result["modules"]}
    assert by_id["foundations"]["stars"] == 2
    assert by_id["foundations"]["title"] == "Foundations"
    assert by_id["governance"]["completed"] is False


@pytest.mark.asyncio
async def test_progress_fully_certified_has_no_next_module():
    modules = {}
    from app.services.certification_service import MODULE_ORDER

    for mid in MODULE_ORDER:
        modules[mid] = {"completed": True, "stars": 3}
    with patch(
        "app.services.certification_service.get_progress_dict",
        new=AsyncMock(return_value=_progress(modules, certified=True)),
    ):
        result = await get_certification_progress(_make_context())

    assert result["next_module_id"] is None
    assert result["certified"] is True
    assert result["modules_completed"] == 11


# ---------------------------------------------------------------------------
# get_certification_module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_module_unknown_id_errors():
    result = await get_certification_module(_make_context(), "not_a_module")
    assert "error" in result
    assert "foundations" in result["hint"]


@pytest.mark.asyncio
async def test_get_module_merges_exercise_and_progress():
    exercise = {
        "overview": "Build your first extraction.",
        "instructions": ["Open the Challenge tab."],
        "expected_fields": ["pi_name", "award_amount"],
        "star_criteria": {"1": "pass"},
        "documents": ["sample.pdf"],
    }
    modules = {"foundations": {"completed": True, "stars": 2, "provisioned_docs": ["D1"]}}
    with (
        patch("app.services.certification_service.get_exercise", return_value=exercise),
        patch(
            "app.services.certification_service.get_progress_dict",
            new=AsyncMock(return_value=_progress(modules)),
        ),
    ):
        result = await get_certification_module(_make_context(), "foundations")

    assert result["title"] == "Foundations"
    assert result["xp"] == 100
    assert result["completed"] is True
    assert result["stars"] == 2
    assert result["expected_fields"] == ["pi_name", "award_amount"]
    assert result["provisioned_docs"] == ["D1"]
    assert result["assessment_keys"] == []  # hands-on module


@pytest.mark.asyncio
async def test_get_module_reflective_exposes_assessment_keys():
    with (
        patch("app.services.certification_service.get_exercise", return_value={}),
        patch(
            "app.services.certification_service.get_progress_dict",
            new=AsyncMock(return_value=_progress()),
        ),
    ):
        result = await get_certification_module(_make_context(), "ai_literacy")

    assert result["assessment_keys"] == ["experience", "comfort", "concern"]


# ---------------------------------------------------------------------------
# provision_certification_lab
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_unknown_module_errors():
    result = await provision_certification_lab(_make_context(), "bogus")
    assert "error" in result


@pytest.mark.asyncio
async def test_provision_passes_user_and_reports_docs():
    provision = AsyncMock(return_value={"provisioned_docs": ["D1", "D2"]})
    ctx = _make_context()
    with (
        patch("app.services.certification_service.provision_module_documents", new=provision),
        patch("app.config.Settings", return_value=MagicMock()),
        patch(
            "app.services.certification_service.get_exercise",
            return_value={"documents": ["a.pdf", "b.pdf"]},
        ),
    ):
        result = await provision_certification_lab(ctx, "foundations")

    assert provision.await_args.args[0] is ctx.deps.user
    assert provision.await_args.args[1] == "foundations"
    assert result["provisioned_docs"] == ["D1", "D2"]
    assert result["document_names"] == ["a.pdf", "b.pdf"]
    assert result["folder"] == "Certification Lab"


@pytest.mark.asyncio
async def test_provision_service_error_is_relayed():
    provision = AsyncMock(return_value={"error": "No exercise defined for module x"})
    with (
        patch("app.services.certification_service.provision_module_documents", new=provision),
        patch("app.config.Settings", return_value=MagicMock()),
    ):
        result = await provision_certification_lab(_make_context(), "foundations")

    assert result["error"] == "No exercise defined for module x"


# ---------------------------------------------------------------------------
# check_certification_module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_module_relays_validator_result():
    validation = {
        "passed": False,
        "stars": 0,
        "checks": [{"name": "Extraction template exists", "passed": False, "detail": "Create one"}],
    }
    with patch(
        "app.services.certification_service.validate_module",
        new=AsyncMock(return_value=validation),
    ) as validate:
        result = await check_certification_module(_make_context(), "foundations")

    validate.assert_awaited_once_with("user1", "foundations")
    assert result["module_id"] == "foundations"
    assert result["title"] == "Foundations"
    assert result["passed"] is False
    assert result["checks"][0]["name"] == "Extraction template exists"


@pytest.mark.asyncio
async def test_check_module_unknown_id_errors():
    result = await check_certification_module(_make_context(), "bogus")
    assert "error" in result


# ---------------------------------------------------------------------------
# complete_certification_module
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_success_adds_title():
    completion = {
        "module_id": "foundations",
        "stars": 2,
        "xp_earned": 100,
        "total_xp": 250,
        "level": "builder",
        "level_up": True,
        "certified": False,
        "validation": {"passed": True, "stars": 2, "checks": []},
    }
    with patch(
        "app.services.certification_service.complete_module",
        new=AsyncMock(return_value=completion),
    ):
        result = await complete_certification_module(_make_context(), "foundations")

    assert result["title"] == "Foundations"
    assert result["xp_earned"] == 100
    assert result["level"] == "builder"


@pytest.mark.asyncio
async def test_complete_failure_returns_validation():
    failure = {
        "error": "Validation did not pass",
        "validation": {"passed": False, "stars": 0, "checks": [{"name": "x", "passed": False, "detail": ""}]},
    }
    with patch(
        "app.services.certification_service.complete_module",
        new=AsyncMock(return_value=failure),
    ):
        result = await complete_certification_module(_make_context(), "foundations")

    assert result["error"] == "Validation did not pass"
    assert result["validation"]["passed"] is False


# ---------------------------------------------------------------------------
# submit_certification_assessment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assessment_rejects_hands_on_module():
    result = await submit_certification_assessment(
        _make_context(), "foundations", {"experience": "lots"},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_assessment_rejects_missing_keys():
    result = await submit_certification_assessment(
        _make_context(), "ai_literacy", {"experience": "some", "comfort": "  "},
    )
    assert "error" in result
    assert "comfort" in result["error"]
    assert "concern" in result["error"]


@pytest.mark.asyncio
async def test_assessment_stores_only_required_keys_stripped():
    store = AsyncMock(return_value={"stored": True})
    answers = {
        "experience": "  I use AI weekly  ",
        "comfort": "pretty comfortable",
        "concern": "hallucinations",
        "extra_key": "should be dropped",
    }
    with patch("app.services.certification_service.store_assessment", new=store):
        result = await submit_certification_assessment(
            _make_context(), "ai_literacy", answers,
        )

    assert result["stored"] is True
    stored_answers = store.await_args.args[2]
    assert stored_answers == {
        "experience": "I use AI weekly",
        "comfort": "pretty comfortable",
        "concern": "hallucinations",
    }
