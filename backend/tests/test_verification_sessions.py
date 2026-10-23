"""Finalizing a guided verification session (chat's "save as a test case")."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_finalize_saves_the_document_text_with_the_test_case():
    # Support ticket: test cases made through chat verification had no text
    # snapshot, so the Validate tab warned they'd only run for users who can
    # open the original document. The editor's path saves the text.
    from app.routers import verification_sessions as router

    session = SimpleNamespace(
        status="pending",
        all_resolved=lambda: True,
        fields=[
            SimpleNamespace(key="award_number", status="approved", expected="UI-BSU-2024-0847"),
            SimpleNamespace(key="pi_name", status="skipped", expected=None),
        ],
        label=None,
        document_title="subaward-agreement.pdf",
        document_uuid="doc-1",
        search_set_uuid="ss-1",
        save=AsyncMock(),
    )
    created = {}

    def make_test_case(**kwargs):
        created.update(kwargs)
        return SimpleNamespace(uuid="tc-1", insert=AsyncMock(), **kwargs)

    test_case_model = MagicMock(side_effect=make_test_case)
    document_model = MagicMock()
    document_model.find_one = AsyncMock(return_value=SimpleNamespace(raw_text="SUBAWARD AGREEMENT text"))
    with patch.object(router, "_get_owned", AsyncMock(return_value=session)), \
         patch.object(router, "_session_response", return_value={}), \
         patch("app.services.extraction_validation_service.ExtractionTestCase", test_case_model), \
         patch("app.services.extraction_validation_service.SmartDocument", document_model), \
         patch.object(router, "ExtractionTestCase", test_case_model, create=True):
        result = await router.finalize_session(
            "sess-1", router.FinalizeRequest(), user=SimpleNamespace(user_id="u1"),
        )

    assert created["source_text"] == "SUBAWARD AGREEMENT text"
    assert created["document_uuid"] == "doc-1"
    assert created["source_type"] == "document"
    assert created["expected_values"] == {"award_number": "UI-BSU-2024-0847"}
    assert result["test_case"]["uuid"] == "tc-1"
    assert session.status == "completed"
