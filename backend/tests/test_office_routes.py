"""Authorization tests for office intake and work-item routes."""

import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id: str = "testuser"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.demo_status = None
    return user


def _auth(user_id: str = "testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


class _Field:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return (self.name, other)


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestOfficeRouteAuthz:
    @pytest.mark.asyncio
    async def test_create_intake_rejects_unauthorized_default_workflow(self, client):
        user = _make_user("owner")
        cookies, headers = _auth("owner")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "owner", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.office.access_control.get_authorized_workflow",
                new_callable=AsyncMock,
            ) as mock_get_workflow,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_workflow.return_value = None

            resp = await client.post(
                "/api/office/intakes",
                json={
                    "name": "Mail Intake",
                    "intake_type": "outlook_shared",
                    "default_workflow": "507f1f77bcf86cd799439011",
                },
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Workflow not found"

    @pytest.mark.asyncio
    async def test_manual_triage_requires_owned_item_on_owned_intake(self, client):
        user = _make_user("owner")
        cookies, headers = _auth("owner")
        intake = SimpleNamespace(id="intake-oid")

        class MockIntakeModel:
            uuid = _Field("uuid")
            owner_user_id = _Field("owner_user_id")

            @staticmethod
            async def find_one(*args):
                assert ("uuid", "intake-1") in args
                assert ("owner_user_id", "owner") in args
                return intake

        class MockWorkItemModel:
            uuid = _Field("uuid")
            owner_user_id = _Field("owner_user_id")
            intake_config = _Field("intake_config")

            @staticmethod
            async def find_one(*args):
                assert ("uuid", "item-1") in args
                assert ("owner_user_id", "owner") in args
                assert ("intake_config", "intake-oid") in args
                return None

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "owner", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.office.IntakeConfig", MockIntakeModel),
            patch("app.routers.office.WorkItem", MockWorkItemModel),
            patch("app.celery_app.celery_app.send_task") as mock_send_task,
        ):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/office/intakes/intake-1/triage/item-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        mock_send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_manual_process_requires_authorized_matched_workflow(self, client):
        user = _make_user("owner")
        cookies, headers = _auth("owner")
        intake = SimpleNamespace(id="intake-oid")

        item = SimpleNamespace(
            id="work-oid",
            matched_workflow="507f1f77bcf86cd799439011",
            status="awaiting_review",
            updated_at=None,
            save=AsyncMock(),
        )

        class MockIntakeModel:
            uuid = _Field("uuid")
            owner_user_id = _Field("owner_user_id")

            @staticmethod
            async def find_one(*args):
                return intake

        class MockWorkItemModel:
            uuid = _Field("uuid")
            owner_user_id = _Field("owner_user_id")
            intake_config = _Field("intake_config")

            @staticmethod
            async def find_one(*args):
                assert ("owner_user_id", "owner") in args
                assert ("intake_config", "intake-oid") in args
                return item

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "owner", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.office.IntakeConfig", MockIntakeModel),
            patch("app.routers.office.WorkItem", MockWorkItemModel),
            patch(
                "app.routers.office.access_control.get_authorized_workflow",
                new_callable=AsyncMock,
            ) as mock_get_workflow,
            patch("app.celery_app.celery_app.send_task") as mock_send_task,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_get_workflow.return_value = None

            resp = await client.post(
                "/api/office/intakes/intake-1/process/item-1",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Matched workflow not found"
        item.save.assert_not_awaited()
        mock_send_task.assert_not_called()
