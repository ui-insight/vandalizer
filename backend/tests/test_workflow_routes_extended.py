"""Extended route tests for workflow endpoints — status polling, download
(all formats), step test polling, batch status, and SSE streaming.

Follows the same mocking patterns as test_workflow_routes.py and
test_workflow_authz.py.
"""

import base64
import json
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="testuser"):
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


def _auth(user_id="testuser"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# GET /api/workflows/status
# ---------------------------------------------------------------------------

class TestGetWorkflowStatus:
    async def test_returns_status(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(return_value={
                "status": "completed",
                "num_steps_completed": 3,
                "num_steps_total": 3,
                "current_step_name": None,
                "current_step_detail": None,
                "current_step_preview": None,
                "final_output": {"output": "result"},
                "steps_output": {},
            })

            resp = await client.get(
                "/api/workflows/status?session_id=sess123",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["num_steps_completed"] == 3

    async def test_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/workflows/status?session_id=nonexistent",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workflows/batch-status
# ---------------------------------------------------------------------------

class TestGetBatchStatusRoute:
    async def test_returns_batch_status(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_batch_status = AsyncMock(return_value={
                "status": "running",
                "total": 3,
                "completed": 1,
                "failed": 0,
                "items": [
                    {"session_id": "s1", "status": "completed", "document_title": "doc1.pdf",
                     "num_steps_completed": 2, "num_steps_total": 2,
                     "current_step_name": None, "final_output": "done"},
                ],
            })

            resp = await client.get(
                "/api/workflows/batch-status?batch_id=batch1",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["total"] == 3

    async def test_batch_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_batch_status = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/workflows/batch-status?batch_id=missing",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workflows/steps/test/{task_id}
# ---------------------------------------------------------------------------

class TestPollStepTest:
    async def test_completed_test(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_test_status.return_value = {
                "status": "completed",
                "result": {"output": "test result"},
            }

            resp = await client.get(
                "/api/workflows/steps/test/task-abc",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["result"]["output"] == "test result"

    async def test_pending_test(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_test_status.return_value = {"status": "PENDING"}

            resp = await client.get(
                "/api/workflows/steps/test/task-abc",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "PENDING"


# ---------------------------------------------------------------------------
# GET /api/workflows/download — all formats
# ---------------------------------------------------------------------------

class TestDownloadResults:
    def _mock_status(self, output_data):
        return {
            "status": "completed",
            "num_steps_completed": 1,
            "num_steps_total": 1,
            "current_step_name": None,
            "current_step_detail": None,
            "current_step_preview": None,
            "final_output": {"output": output_data},
            "steps_output": {},
        }

    async def test_download_json(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status({"Name": "Alice", "Age": "30"})
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=json",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        data = json.loads(resp.content)
        assert data["Name"] == "Alice"

    async def test_download_csv_list_of_dicts(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status([
                    {"Name": "Alice", "Age": "30"},
                    {"Name": "Bob", "Age": "25"},
                ])
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=csv",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.content.decode()
        assert "Name" in content
        assert "Alice" in content
        assert "Bob" in content

    async def test_download_csv_dict(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status({"Key": "Value"})
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=csv",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Key" in content
        assert "Value" in content

    async def test_download_csv_scalar(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status("plain text result")
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=csv",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Output" in content
        assert "plain text result" in content

    async def test_download_csv_list_of_scalars(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status(["item1", "item2", "item3"])
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=csv",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Value" in content
        assert "item1" in content

    async def test_download_text_string(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status("Hello, World!")
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=text",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert resp.content.decode() == "Hello, World!"

    async def test_download_text_dict(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status({"name": "Alice", "role": "PI"})
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=text",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "name: Alice" in content
        assert "role: PI" in content

    async def test_download_text_list(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status(["line1", "line2"])
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=text",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        content = resp.content.decode()
        assert "line1" in content
        assert "line2" in content

    async def test_download_pdf(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status("PDF content here")
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1&format=pdf",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]
        # Should be valid PDF (starts with %PDF)
        assert resp.content[:5] == b"%PDF-"

    async def test_download_file_download_passthrough(self, client):
        """When output is already a file_download dict, serve it directly."""
        user = _make_user()
        cookies, headers = _auth()

        data_b64 = base64.b64encode(b"csv,content,here").decode()
        file_output = {
            "type": "file_download",
            "data_b64": data_b64,
            "file_type": "csv",
            "filename": "export.csv",
        }

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(
                return_value=self._mock_status(file_output)
            )

            resp = await client.get(
                "/api/workflows/download?session_id=sess1",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert resp.content == b"csv,content,here"
        assert "export.csv" in resp.headers["content-disposition"]

    async def test_download_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_workflow_status = AsyncMock(return_value=None)

            resp = await client.get(
                "/api/workflows/download?session_id=missing",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/workflows/steps/test
# ---------------------------------------------------------------------------

class TestTestStepRoute:
    _FAKE_OID = "6600000000000000000000aa"

    async def test_test_step(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows._authorize_documents", new_callable=AsyncMock, return_value=["doc1"]):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.test_step = AsyncMock(return_value="celery-task-id-123")

            resp = await client.post(
                "/api/workflows/steps/test",
                json={
                    "task_name": "Prompt",
                    "task_data": {"prompt": "Summarize"},
                    "document_uuids": ["doc1"],
                },
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["task_id"] == "celery-task-id-123"

    async def test_test_step_extraction_with_search_set(self, client):
        user = _make_user()
        cookies, headers = _auth()

        mock_ss = MagicMock()
        mock_ss.uuid = "ss-1"

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows._authorize_documents", new_callable=AsyncMock, return_value=["doc1"]), \
             patch("app.routers.workflows.get_authorized_search_set", new_callable=AsyncMock, return_value=mock_ss):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.test_step = AsyncMock(return_value="task-id")

            resp = await client.post(
                "/api/workflows/steps/test",
                json={
                    "task_name": "Extraction",
                    "task_data": {"search_set_uuid": "ss-1"},
                    "document_uuids": ["doc1"],
                },
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200

    async def test_test_step_unauthorized_search_set(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc, \
             patch("app.routers.workflows._authorize_documents", new_callable=AsyncMock, return_value=["doc1"]), \
             patch("app.routers.workflows.get_authorized_search_set", new_callable=AsyncMock, return_value=None):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/steps/test",
                json={
                    "task_name": "Extraction",
                    "task_data": {"search_set_uuid": "ss-unauthorized"},
                    "document_uuids": ["doc1"],
                },
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404
        assert "search set" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/workflows/{id}/reorder-steps (route level)
# ---------------------------------------------------------------------------

class TestReorderStepsRoute:
    async def test_reorder_success(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.reorder_steps = AsyncMock(return_value=True)

            resp = await client.post(
                "/api/workflows/wf-1/reorder-steps",
                json={"step_ids": ["s2", "s1"]},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_reorder_failure(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.reorder_steps = AsyncMock(return_value=False)

            resp = await client.post(
                "/api/workflows/wf-1/reorder-steps",
                json={"step_ids": ["invalid"]},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/workflows/{id}/save-expected-output
# ---------------------------------------------------------------------------

class TestSaveExpectedOutputRoute:
    _FAKE_OID = "6600000000000000000000aa"

    async def test_save_success(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.save_expected_output = AsyncMock(return_value={
                "id": "e1", "type": "expected_output", "session_id": "s1",
                "label": "Test expected", "output_text": "expected output",
            })

            resp = await client.post(
                f"/api/workflows/{self._FAKE_OID}/save-expected-output",
                json={"session_id": "s1", "label": "Test expected"},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["type"] == "expected_output"

    async def test_save_missing_session_id(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                f"/api/workflows/{self._FAKE_OID}/save-expected-output",
                json={"label": "no session"},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 400
        assert "session_id" in resp.json()["detail"]

    async def test_save_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.save_expected_output = AsyncMock(
                side_effect=ValueError("Completed workflow result not found")
            )

            resp = await client.post(
                f"/api/workflows/{self._FAKE_OID}/save-expected-output",
                json={"session_id": "nonexistent"},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET/DELETE expected outputs
# ---------------------------------------------------------------------------

class TestExpectedOutputRoutes:
    _FAKE_OID = "6600000000000000000000aa"

    async def test_get_expected_outputs(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.get_expected_outputs = AsyncMock(return_value=[
                {"id": "e1", "type": "expected_output", "label": "test"},
            ])

            resp = await client.get(
                f"/api/workflows/{self._FAKE_OID}/expected-outputs",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert len(resp.json()["expected_outputs"]) == 1

    async def test_delete_expected_output(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_expected_output = AsyncMock(return_value=True)

            resp = await client.delete(
                f"/api/workflows/{self._FAKE_OID}/expected-outputs/e1",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_delete_expected_output_not_found(self, client):
        user = _make_user()
        cookies, headers = _auth()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.svc") as mock_svc:
            MockUser.find_one = AsyncMock(return_value=user)
            mock_svc.delete_expected_output = AsyncMock(return_value=False)

            resp = await client.delete(
                f"/api/workflows/{self._FAKE_OID}/expected-outputs/missing",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404
