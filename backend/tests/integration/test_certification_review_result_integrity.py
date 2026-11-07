"""Reject inconsistent but digest-valid saved feedback through its real reader."""

import json
import os
from unittest.mock import AsyncMock

import pytest

from tests.integration import test_certification_enrollments as existing
from app.models.certification import CertificationReviewAttempt
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.review_delivery import ReviewDelivery

repo = existing.repo
pytestmark = pytest.mark.skipif(
    not os.environ.get("CERTIFICATION_TEST_MONGO_URL"),
    reason="Requires disposable MongoDB",
)


@pytest.mark.parametrize(
    "change",
    ["missing_outcome", "wrong_summary", "missing_deterministic", "invented_quote"],
)
async def test_integrity_digest_does_not_turn_an_inconsistent_result_into_valid_feedback(
    repo, change
):
    source, package, _, _, run, _ = await existing.trusted_review_fixture(repo)
    prepared = await existing.prepare_trusted_review(
        repo, source, package, run["run_id"]
    )
    model = AsyncMock(side_effect=existing.supported_review)
    await existing.evaluate_review(repo, source, package, prepared["attempt_id"], model)
    delivery = ReviewDelivery(repo)
    assert (await delivery.get(source.user_id, source.uuid, prepared["attempt_id"]))[
        "status"
    ] == "requirements_supported"
    records = CertificationReviewAttempt.get_motor_collection()
    raw = await records.find_one({"uuid": prepared["attempt_id"]})
    result = json.loads(raw["result_json"])
    assessment = result["assessment"]
    if change == "missing_outcome":
        assessment["outcomes"].pop()
    elif change == "wrong_summary":
        assessment.update(passed=False, status="revision_required")
    elif change == "missing_deterministic":
        assessment["deterministic_outcomes"] = []
    else:
        assessment["outcomes"][0]["citations"][0]["quote"] = "PRIVATE INVENTED EVIDENCE"
    serialized, digest = encode(result)
    await records.update_one(
        {"uuid": prepared["attempt_id"]},
        {"$set": {"result_json": serialized, "result_sha256": digest}},
    )
    before = await records.find_one({"uuid": prepared["attempt_id"]})
    for read in (
        delivery.get(source.user_id, source.uuid, prepared["attempt_id"]),
        delivery.list(source.user_id, source.uuid, "foundations"),
    ):
        with pytest.raises(CourseCatalogError, match="needs reconciliation") as error:
            await read
        assert "PRIVATE" not in str(error.value)
    assert await records.find_one({"uuid": prepared["attempt_id"]}) == before
    model.assert_awaited_once()
    assert (await repo.read_progress(source.user_id, source.uuid)).total_xp == 0
