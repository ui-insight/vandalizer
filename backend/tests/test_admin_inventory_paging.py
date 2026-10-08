"""Paging does not hide teams or certification users after a cap."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.routers.admin import admin_list_all_teams, list_certification_progress

@pytest.mark.asyncio
async def test_team_page_uses_stable_database_paging_and_counts():
    team = SimpleNamespace(id='db-501', uuid='team-501', name='Research', owner_user_id='owner')
    chain = MagicMock()
    chain.count = AsyncMock(return_value=10001)
    chain.sort.return_value = chain
    chain.skip.return_value = chain
    chain.limit.return_value = chain
    chain.to_list = AsyncMock(return_value=[team])
    with patch('app.routers.admin._require_admin', new_callable=AsyncMock), patch('app.routers.admin.SystemConfig.get_config', new_callable=AsyncMock, return_value=SimpleNamespace(default_team_id='team-501')), patch('app.routers.admin.Team') as teams, patch('app.routers.admin.TeamMembership') as members:
        teams.find.return_value = chain
        members.aggregate.return_value.to_list = AsyncMock(return_value=[{'_id': 'db-501', 'count': 9}])
        result = await admin_list_all_teams(limit=500, offset=500, q='Research.*', user=object())
        chain.skip.assert_called_once_with(500)
        chain.sort.assert_called_once_with('name', '_id')
        assert teams.find.call_args.args[0]['name']['$regex'] == r'Research\.\*'
        assert result.items[0].uuid == 'team-501'
        assert result.items[0].member_count == 9
        assert result.items[0].is_default
        assert result.total == 10001 and result.capped

@pytest.mark.asyncio
async def test_certification_search_and_paging_reach_beyond_500():
    progresses = [SimpleNamespace(id=str(i), user_id=f'user-{i:04d}', modules={}, level='novice', total_xp=0, certified=False, certified_at=None, last_activity_date=None, unlocked=False, updated_at=None) for i in range(502)]
    with patch('app.routers.admin._require_admin', new_callable=AsyncMock), patch('app.models.certification.CertificationProgress') as model, patch('app.routers.admin.User') as users:
        model.find.return_value.to_list = AsyncMock(return_value=progresses)
        users.find.return_value.to_list = AsyncMock(return_value=[])
        page = await list_certification_progress(limit=500, offset=500, q='', user=object())
        assert [item.user_id for item in page.items] == ['user-0500', 'user-0501']
        assert page.total == 502 and not page.capped
        search = await list_certification_progress(limit=100, offset=0, q='user-0501', user=object())
        assert [item.user_id for item in search.items] == ['user-0501']
        assert search.total == 1
