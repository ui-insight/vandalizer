"""Tests for app.services.organization_service.

Mocks Organization model's Beanie query methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_org(uuid="org-1", name="Test Org", org_type="department", parent_id=None):
    org = MagicMock()
    org.uuid = uuid
    org.name = name
    org.org_type = org_type
    org.parent_id = parent_id
    org.metadata = {}
    org.save = AsyncMock()
    org.insert = AsyncMock()
    org.delete = AsyncMock()
    return org


def _make_user(**overrides):
    defaults = {
        "id": "fake-id",
        "user_id": "testuser",
        "email": "test@example.com",
        "is_admin": False,
        "current_team": None,
        "organization_id": None,
    }
    user = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(user, k, v)
    user.save = AsyncMock()
    return user


class TestCreateOrganization:
    @pytest.mark.asyncio
    async def test_create_valid(self):
        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=None)

            mock_instance = MagicMock()
            mock_instance.insert = AsyncMock()
            MockOrg.return_value = mock_instance

            from app.services.organization_service import create_organization

            result = await create_organization(name="CS Dept", org_type="department")
            assert result is mock_instance
            mock_instance.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_invalid_type(self):
        from app.services.organization_service import create_organization

        with pytest.raises(ValueError, match="org_type must be one of"):
            await create_organization(name="Bad", org_type="invalid_type")

    @pytest.mark.asyncio
    async def test_create_missing_parent(self):
        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=None)

            from app.services.organization_service import create_organization

            with pytest.raises(ValueError, match="not found"):
                await create_organization(
                    name="Sub Dept", org_type="department", parent_id="nonexistent"
                )


class TestUpdateOrganization:
    @pytest.mark.asyncio
    async def test_update_found(self):
        org = _make_org(uuid="org-1", name="Old Name")
        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=org)

            from app.services.organization_service import update_organization

            result = await update_organization("org-1", name="New Name")
            assert result.name == "New Name"
            org.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=None)

            from app.services.organization_service import update_organization

            with pytest.raises(ValueError, match="not found"):
                await update_organization("missing-uuid", name="Name")


class TestDeleteOrganization:
    @pytest.mark.asyncio
    async def test_delete_reparents_children(self):
        parent_org = _make_org(uuid="parent-1", parent_id="grandparent-1")
        child1 = _make_org(uuid="child-1", parent_id="parent-1")
        child2 = _make_org(uuid="child-2", parent_id="parent-1")

        mock_find_result = MagicMock()
        mock_find_result.to_list = AsyncMock(return_value=[child1, child2])

        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=parent_org)
            MockOrg.find = MagicMock(return_value=mock_find_result)

            from app.services.organization_service import delete_organization

            await delete_organization("parent-1")

            # Children should be re-parented to grandparent
            assert child1.parent_id == "grandparent-1"
            assert child2.parent_id == "grandparent-1"
            child1.save.assert_awaited_once()
            child2.save.assert_awaited_once()
            parent_org.delete.assert_awaited_once()


class TestGetOrgTree:
    @pytest.mark.asyncio
    async def test_builds_nested_structure(self):
        root = _make_org(uuid="root", name="University", org_type="university", parent_id=None)
        dept = _make_org(uuid="dept-1", name="CS", org_type="department", parent_id="root")

        # First call to find (roots): returns [root]
        # Second call to find (children of root): returns [dept]
        # Third call to find (children of dept): returns []
        mock_roots = MagicMock()
        mock_roots.to_list = AsyncMock(return_value=[root])
        mock_children_of_root = MagicMock()
        mock_children_of_root.to_list = AsyncMock(return_value=[dept])
        mock_no_children = MagicMock()
        mock_no_children.to_list = AsyncMock(return_value=[])

        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find = MagicMock(
                side_effect=[mock_roots, mock_children_of_root, mock_no_children]
            )

            from app.services.organization_service import get_org_tree

            tree = await get_org_tree()

        assert len(tree) == 1
        assert tree[0]["uuid"] == "root"
        assert tree[0]["name"] == "University"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["uuid"] == "dept-1"


class TestGetVisibleOrgIds:
    @pytest.mark.asyncio
    async def test_admin_returns_none(self):
        user = _make_user(is_admin=True)

        from app.services.organization_service import get_visible_org_ids

        result = await get_visible_org_ids(user)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_org_returns_empty(self):
        user = _make_user(organization_id=None)

        from app.services.organization_service import get_visible_org_ids

        result = await get_visible_org_ids(user)
        assert result == []

    @pytest.mark.asyncio
    async def test_department_returns_self_and_descendants(self):
        user = _make_user(organization_id="dept-1")
        dept = _make_org(uuid="dept-1", org_type="department")
        child = _make_org(uuid="unit-1", org_type="unit", parent_id="dept-1")

        # Calls: find_one for user's org, find for descendants of dept-1,
        # find for descendants of unit-1
        mock_children_of_dept = MagicMock()
        mock_children_of_dept.to_list = AsyncMock(return_value=[child])
        mock_no_children = MagicMock()
        mock_no_children.to_list = AsyncMock(return_value=[])

        with patch("app.services.organization_service.Organization") as MockOrg:
            MockOrg.find_one = AsyncMock(return_value=dept)
            MockOrg.find = MagicMock(
                side_effect=[mock_children_of_dept, mock_no_children]
            )

            from app.services.organization_service import get_visible_org_ids

            result = await get_visible_org_ids(user)

        assert "dept-1" in result
        assert "unit-1" in result
