"""Atomic review transitions, including races with reassignment/timeouts."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest
from app.services.approval_service import update_pending_approval

@pytest.mark.asyncio
@pytest.mark.parametrize('changed', [0, 1])
async def test_only_a_winning_compare_and_set_mutates_the_loaded_review(changed):
    approval = SimpleNamespace(id='id', status='pending', assigned_to_user_ids=['reviewer'], expires_at=None)
    with patch('app.services.approval_service.ApprovalRequest') as model:
        collection = model.get_motor_collection.return_value
        collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=changed))
        accepted = await update_pending_approval(approval, {'status':'approved'})
        assert accepted == bool(changed)
        assert approval.status == ('approved' if changed else 'pending')
        query, update = collection.update_one.await_args.args
        assert query == {'_id':'id','status':'pending','assigned_to_user_ids':['reviewer'],'expires_at':None}
        assert update == {'$set':{'status':'approved'}}

@pytest.mark.asyncio
@pytest.mark.parametrize('aware', [False, True])
async def test_overdue_human_decision_is_refused_but_timeout_can_claim(aware):
    past=dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)
    if not aware: past=past.replace(tzinfo=None)
    approval=SimpleNamespace(id='id',status='pending',assigned_to_user_ids=['reviewer'],expires_at=past)
    with patch('app.services.approval_service.ApprovalRequest') as model:
        collection=model.get_motor_collection.return_value
        collection.update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
        assert not await update_pending_approval(approval,{'status':'approved'})
        collection.update_one.assert_not_awaited()
        assert await update_pending_approval(approval,{'status':'expired'},allow_expired=True)
        assert approval.status=='expired'
