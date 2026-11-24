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
         patch.object(router, "_require_test_case_rights", AsyncMock()), \
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


def _pending_session():
    return SimpleNamespace(
        status="pending",
        all_resolved=lambda: True,
        fields=[SimpleNamespace(key="award_number", status="approved", expected="UI-1", extracted="UI-1")],
        label=None,
        document_title="award.pdf",
        document_uuid="doc-1",
        search_set_uuid="ss-1",
        save=AsyncMock(),
    )


async def _finalize(session, *, verified, can_manage):
    """Finalize *session* as someone who may or may not manage its extraction."""
    from app.routers import verification_sessions as router

    search_set = SimpleNamespace(uuid="ss-1", verified=verified)
    model = MagicMock()
    model.uuid = "uuid"
    model.find_one = AsyncMock(return_value=search_set)
    authorized = AsyncMock(return_value=search_set if can_manage else None)
    create = AsyncMock(return_value=SimpleNamespace(uuid="tc-1", label="award.pdf", search_set_uuid="ss-1", expected_values={}))
    user = SimpleNamespace(user_id="u1", is_admin=False)
    with patch.object(router, "_get_owned", AsyncMock(return_value=session)), \
         patch.object(router, "_session_response", return_value={}), \
         patch.object(router, "SearchSet", model), \
         patch.object(router.access_control, "get_authorized_search_set", authorized), \
         patch.object(router.val_svc, "create_test_case", create):
        try:
            result = await router.finalize_session("sess-1", router.FinalizeRequest(), user=user)
        except router.HTTPException as exc:
            result = exc
    return result, create, authorized


@pytest.mark.asyncio
async def test_a_teammate_who_cannot_change_the_extraction_cannot_finalize_its_session():
    # #1164: a session is open to the whole team, and finalizing it adds a
    # test case to the extraction, which only its creator or a team admin may.
    session = _pending_session()
    result, create, authorized = await _finalize(session, verified=False, can_manage=False)

    assert result.status_code == 403
    create.assert_not_awaited()
    assert session.status == "pending"
    session.save.assert_not_awaited()
    assert authorized.await_args.kwargs["manage"] is True


@pytest.mark.asyncio
async def test_the_extractions_creator_finalizes_its_session():
    session = _pending_session()
    result, create, _ = await _finalize(session, verified=False, can_manage=True)

    assert result["test_case"]["uuid"] == "tc-1"
    create.assert_awaited_once()
    assert session.status == "completed"


@pytest.mark.asyncio
async def test_a_verified_extractions_session_stays_open_to_whoever_chat_let_start_it():
    session = _pending_session()
    result, create, authorized = await _finalize(session, verified=True, can_manage=False)

    assert result["test_case"]["uuid"] == "tc-1"
    authorized.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_teammate_who_cannot_change_the_extraction_cannot_answer_its_fields():
    from app.routers import verification_sessions as router

    session = _pending_session()
    model = MagicMock()
    model.uuid = "uuid"
    model.find_one = AsyncMock(return_value=SimpleNamespace(uuid="ss-1", verified=False))
    with patch.object(router, "_get_owned", AsyncMock(return_value=session)), \
         patch.object(router, "SearchSet", model), \
         patch.object(router.access_control, "get_authorized_search_set", AsyncMock(return_value=None)):
        with pytest.raises(router.HTTPException) as refused:
            await router.update_field(
                "sess-1", "award_number", router.FieldPatch(status="corrected", expected="WRONG"),
                user=SimpleNamespace(user_id="u1", is_admin=False),
            )

    assert refused.value.status_code == 403
    assert session.fields[0].expected == "UI-1"
    session.save.assert_not_awaited()
