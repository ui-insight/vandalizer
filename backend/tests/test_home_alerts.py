"""Home notice access, evidence scope, and review status contracts."""
import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from app.services.home_alerts import owned_alert, alert_item, ReviewAlertRequest
from app.routers.config import home_alert_evidence, review_home_alert


def notice(**kw):
    return SimpleNamespace(**dict(uuid='a1', item_kind='search_set', item_id='set1',
        item_name='test', severity='warning', alert_type='regression',
        message='Score fell', previous_score=95, current_score=85,
        created_at=datetime.datetime(2026, 10, 9, tzinfo=datetime.timezone.utc),
        acknowledged=False, review_state='new', save=AsyncMock(), **kw))


@pytest.mark.asyncio
async def test_evidence_checks_ownership_before_reading_history():
    with patch('app.services.home_alerts.QualityAlert.find_one', AsyncMock(return_value=notice())), patch('app.services.home_alerts.SearchSet.find_one', AsyncMock(return_value=None)) as find, patch('app.services.quality_service.get_quality_history', AsyncMock()) as history:
        with pytest.raises(HTTPException) as err:
            await home_alert_evidence('a1', SimpleNamespace(user_id='other'))
        assert err.value.status_code == 404
        assert find.call_args.args[0] == {'uuid': 'set1', 'user_id': 'other'}
        history.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_is_bounded_to_the_owned_tool_and_does_not_invent_a_run_link():
    with patch('app.services.home_alerts.owned_alert', AsyncMock(return_value=notice())) as access, patch('app.services.quality_service.get_quality_history', AsyncMock(return_value=[{'uuid': 'run1'}])) as history:
        user = SimpleNamespace(user_id='owner')
        result = await home_alert_evidence('a1', user)
        access.assert_awaited_once_with('a1', user)
        history.assert_awaited_once_with('search_set', 'set1', limit=5)
        assert result == {'runs': [{'uuid': 'run1'}], 'linked_run': False}


@pytest.mark.asyncio
async def test_acknowledgement_and_review_are_durable_without_changing_scores():
    alert = notice()
    user = SimpleNamespace(user_id='owner')
    with patch('app.services.home_alerts.owned_alert', AsyncMock(return_value=alert)):
        result = await review_home_alert('a1', ReviewAlertRequest(state='in_review'), user)
        assert result.review_state == 'in_review'
        assert not alert.acknowledged
        result = await review_home_alert('a1', ReviewAlertRequest(state='acknowledged'), user)
        assert result.review_state == 'acknowledged'
        assert alert.acknowledged_by == 'owner'
        assert alert.acknowledged_at is not None
        assert result.current_score == 85
        assert alert.save.await_count == 2


@pytest.mark.asyncio
async def test_invalid_workflow_reference_returns_not_found():
    alert = notice()
    alert.item_kind = 'workflow'
    alert.item_id = 'not-an-object-id'
    with patch('app.services.home_alerts.QualityAlert.find_one', AsyncMock(return_value=alert)):
        with pytest.raises(HTTPException) as err:
            await owned_alert('a1', SimpleNamespace(user_id='owner'))
        assert err.value.status_code == 404


def test_notice_contract_includes_identity_measurement_and_timestamp():
    result = alert_item(notice()).model_dump(mode='json')
    assert result['item_kind'] == 'search_set'
    assert result['item_id'] == 'set1'
    assert result['previous_score'] == 95
    assert result['created_at'].startswith('2026-10-09')


@pytest.mark.asyncio
async def test_home_payload_supplies_notice_identity_and_ready_owned_documents():
    from contextlib import ExitStack
    from unittest.mock import MagicMock
    from app.routers import config

    now = datetime.datetime.now(datetime.timezone.utc)
    activity = SimpleNamespace(id='activity1', type='search_set_run', title='Budget review',
        last_updated_at=now, status='completed', search_set_uuid='set1', workflow=None, meta_summary={})
    rows = {
        'SmartDocument': [SimpleNamespace(uuid='doc1', title='Award notice.pdf')],
        'Workflow': [], 'SearchSet': [SimpleNamespace(uuid='set1', title='test')],
        'LibraryItem': [], 'TeamMembership': [], 'Automation': [],
        'KnowledgeBase': [], 'ChatConversation': [], 'ActivityEvent': [activity],
    }
    models = {}
    user = SimpleNamespace(user_id='owner', first_session_completed=True, last_login_at=None, save=AsyncMock())
    with ExitStack() as stack:
        for name, data in rows.items():
            model = stack.enter_context(patch.object(config, name))
            query = MagicMock()
            query.sort.return_value = query
            query.limit.return_value = query
            query.to_list = AsyncMock(return_value=data)
            query.count = AsyncMock(return_value=len(data))
            model.find.return_value = query
            models[name] = model
        stack.enter_context(patch.object(config, 'has_earned_certification', AsyncMock(return_value=False)))
        alerts = stack.enter_context(patch('app.models.quality_alert.QualityAlert.find'))
        alerts.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[notice()])
        validations = stack.enter_context(patch('app.models.validation_run.ValidationRun.find'))
        validations.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        result = await config.get_onboarding_status(user)
        assert result.active_alerts[0].uuid == 'a1'
        assert result.active_alerts[0].item_id == 'set1'
        assert result.recent_activity[0].item_kind == 'search_set'
        assert result.recent_activity[0].item_id == 'set1'
        assert result.recent_documents[0].title == 'Award notice.pdf'
        assert alerts.call_args.args[0]['$or'] == [{'item_kind': 'search_set', 'item_id': {'$in': ['set1']}}]
        doc_query = models['SmartDocument'].find.call_args.args[0]
        assert doc_query['user_id'] == 'owner'
        assert doc_query['task_status'] == 'complete'
        assert doc_query['soft_deleted'] == {'$ne': True}
        assert doc_query['raw_text'] == {'$type': 'string', '$ne': ''}
