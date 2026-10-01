"""Project roles govern the complete subtree, even for a former contributor."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services import access_control as ac

@pytest.mark.asyncio
@pytest.mark.parametrize('role,write,allowed', [('editor',False,True),('editor',True,True),('viewer',False,True),('viewer',True,False),('none',False,False),('none',True,False)])
async def test_project_document_role_overrides_original_uploader(role,write,allowed):
    user=SimpleNamespace(user_id='contributor',is_admin=False)
    project=SimpleNamespace(uuid='project',owner_user_id='owner',team_id=None)
    document=SimpleNamespace(uuid='document',folder='subfolder',user_id='contributor',team_id=None)
    with patch.object(ac,'SmartDocument') as docs, patch.object(ac,'find_folder_project',new=AsyncMock(return_value=project)), patch.object(ac,'ProjectMembership') as memberships:
        docs.find_one=AsyncMock(return_value=document)
        memberships.find_one=AsyncMock(return_value=None if role=='none' else SimpleNamespace(role=role))
        result=await ac.get_authorized_document('document',user,manage=write,team_access=ac.TeamAccessContext())
        assert (result is document)==allowed

@pytest.mark.asyncio
@pytest.mark.parametrize('role,contribute,allowed',[('viewer',False,True),('viewer',True,False),('editor',True,True),('none',False,False)])
async def test_creating_inside_project_requires_contributor_access(role,contribute,allowed):
    user=SimpleNamespace(user_id='member',is_admin=False)
    folder=SimpleNamespace(uuid='root',user_id='owner',team_id=None)
    project=SimpleNamespace(uuid='project',owner_user_id='owner',team_id=None)
    with patch.object(ac,'SmartFolder') as folders, patch.object(ac,'find_folder_project',new=AsyncMock(return_value=project)), patch.object(ac,'ProjectMembership') as memberships:
        folders.find_one=AsyncMock(return_value=folder)
        memberships.find_one=AsyncMock(return_value=None if role=='none' else SimpleNamespace(role=role))
        result=await ac.get_authorized_folder('root',user,contribute=contribute,team_access=ac.TeamAccessContext())
        assert (result is folder)==allowed

@pytest.mark.asyncio
async def test_nearest_root_wins_and_malformed_ancestry_terminates():
    inner=SimpleNamespace(root_folder_uuid='inner'); outer=SimpleNamespace(root_folder_uuid='outer')
    nodes={'child':SimpleNamespace(parent_id='inner'),'inner':SimpleNamespace(parent_id='outer'),'outer':SimpleNamespace(parent_id='child')}
    with patch.object(ac,'SmartFolder') as folders,patch.object(ac,'Project') as projects:
        folders.find_one=AsyncMock(side_effect=lambda q:nodes.get(q['uuid']))
        projects.find.return_value.to_list=AsyncMock(return_value=[outer,inner])
        assert await ac.find_folder_project('child') is inner
        assert folders.find_one.await_count==3
