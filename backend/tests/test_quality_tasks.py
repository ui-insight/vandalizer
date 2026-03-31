"""Tests for app.tasks.quality_tasks — quality monitoring and auto-validation.

Mocks database init, models, and quality service functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _quality_monitor_async
# ---------------------------------------------------------------------------


class TestQualityMonitorAsync:
    @pytest.mark.asyncio
    async def test_creates_config_changed_alert_when_hash_differs(self):
        mock_sys_cfg = MagicMock()
        mock_sys_cfg.get_quality_config.return_value = {
            "monitoring": {"stale_threshold_days": 14, "degradation_alert_threshold": 10}
        }
        mock_sys_cfg.get_extraction_config.return_value = {"model": "gpt-4"}

        mock_latest_run = MagicMock()
        mock_latest_run.config_hash = "old-hash"

        mock_find_all = MagicMock()
        mock_find_all.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[mock_latest_run]
        )

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.models.quality_alert.QualityAlert") as MockAlert,
            patch("app.models.validation_run.ValidationRun") as MockValidationRun,
            patch("app.models.verification.VerifiedItemMetadata"),
            patch("app.services.quality_service.compute_config_hash", return_value="new-hash"),
            patch("app.services.quality_service.detect_stale_items", new_callable=AsyncMock, return_value=[]),
        ):
            MockConfig.get_config = AsyncMock(return_value=mock_sys_cfg)
            MockValidationRun.find_all = MagicMock(return_value=mock_find_all)
            MockAlert.find_one = AsyncMock(return_value=None)  # no existing alert

            mock_alert_instance = MagicMock()
            mock_alert_instance.insert = AsyncMock()
            MockAlert.return_value = mock_alert_instance

            from app.tasks.quality_tasks import _quality_monitor_async

            await _quality_monitor_async()

            MockAlert.assert_called_once()
            call_kwargs = MockAlert.call_args
            assert call_kwargs.kwargs.get("alert_type") == "config_changed" or \
                (len(call_kwargs.args) == 0 and call_kwargs[1].get("alert_type") == "config_changed")

    @pytest.mark.asyncio
    async def test_skips_config_alert_when_hashes_match(self):
        mock_sys_cfg = MagicMock()
        mock_sys_cfg.get_quality_config.return_value = {
            "monitoring": {"stale_threshold_days": 14, "degradation_alert_threshold": 10}
        }
        mock_sys_cfg.get_extraction_config.return_value = {"model": "gpt-4"}

        mock_latest_run = MagicMock()
        mock_latest_run.config_hash = "same-hash"

        mock_find_all = MagicMock()
        mock_find_all.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[mock_latest_run]
        )

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.models.quality_alert.QualityAlert") as MockAlert,
            patch("app.models.validation_run.ValidationRun") as MockValidationRun,
            patch("app.models.verification.VerifiedItemMetadata"),
            patch("app.services.quality_service.compute_config_hash", return_value="same-hash"),
            patch("app.services.quality_service.detect_stale_items", new_callable=AsyncMock, return_value=[]),
        ):
            MockConfig.get_config = AsyncMock(return_value=mock_sys_cfg)
            MockValidationRun.find_all = MagicMock(return_value=mock_find_all)

            from app.tasks.quality_tasks import _quality_monitor_async

            await _quality_monitor_async()

            # Should not have created any alert
            MockAlert.return_value.insert.assert_not_called() if hasattr(MockAlert.return_value, 'insert') else None

    @pytest.mark.asyncio
    async def test_creates_stale_alerts_for_stale_items(self):
        mock_sys_cfg = MagicMock()
        mock_sys_cfg.get_quality_config.return_value = {
            "monitoring": {"stale_threshold_days": 14, "degradation_alert_threshold": 10}
        }
        mock_sys_cfg.get_extraction_config.return_value = {}

        mock_find_all = MagicMock()
        mock_find_all.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        stale_items = [
            {
                "item_kind": "search_set",
                "item_id": "ss-1",
                "display_name": "Grant Fields",
                "last_validated_at": "2025-01-01",
                "quality_score": 85.0,
                "quality_tier": "good",
            }
        ]

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.models.quality_alert.QualityAlert") as MockAlert,
            patch("app.models.validation_run.ValidationRun") as MockValidationRun,
            patch("app.models.verification.VerifiedItemMetadata"),
            patch("app.services.quality_service.compute_config_hash", return_value="hash"),
            patch("app.services.quality_service.detect_stale_items", new_callable=AsyncMock, return_value=stale_items),
        ):
            MockConfig.get_config = AsyncMock(return_value=mock_sys_cfg)
            MockValidationRun.find_all = MagicMock(return_value=mock_find_all)
            MockAlert.find_one = AsyncMock(return_value=None)

            mock_alert_instance = MagicMock()
            mock_alert_instance.insert = AsyncMock()
            MockAlert.return_value = mock_alert_instance

            from app.tasks.quality_tasks import _quality_monitor_async

            await _quality_monitor_async()

            mock_alert_instance.insert.assert_called()

    @pytest.mark.asyncio
    async def test_skips_duplicate_stale_alerts(self):
        mock_sys_cfg = MagicMock()
        mock_sys_cfg.get_quality_config.return_value = {
            "monitoring": {"stale_threshold_days": 14, "degradation_alert_threshold": 10}
        }
        mock_sys_cfg.get_extraction_config.return_value = {}

        mock_find_all = MagicMock()
        mock_find_all.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])

        stale_items = [
            {"item_kind": "search_set", "item_id": "ss-1", "display_name": "X",
             "last_validated_at": None, "quality_score": 50, "quality_tier": "fair"},
        ]

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.system_config.SystemConfig") as MockConfig,
            patch("app.models.quality_alert.QualityAlert") as MockAlert,
            patch("app.models.validation_run.ValidationRun") as MockValidationRun,
            patch("app.models.verification.VerifiedItemMetadata"),
            patch("app.services.quality_service.compute_config_hash", return_value="hash"),
            patch("app.services.quality_service.detect_stale_items", new_callable=AsyncMock, return_value=stale_items),
        ):
            MockConfig.get_config = AsyncMock(return_value=mock_sys_cfg)
            MockValidationRun.find_all = MagicMock(return_value=mock_find_all)
            # Existing alert found — should not create duplicate
            MockAlert.find_one = AsyncMock(return_value=MagicMock())

            mock_alert_instance = MagicMock()
            mock_alert_instance.insert = AsyncMock()
            MockAlert.return_value = mock_alert_instance

            from app.tasks.quality_tasks import _quality_monitor_async

            await _quality_monitor_async()

            mock_alert_instance.insert.assert_not_called()


# ---------------------------------------------------------------------------
# _auto_validate_extraction_async
# ---------------------------------------------------------------------------


class TestAutoValidateExtractionAsync:
    @pytest.mark.asyncio
    async def test_runs_validation_when_test_cases_exist(self):
        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.extraction_test_case.ExtractionTestCase") as MockTestCase,
            patch("app.services.extraction_validation_service.run_validation", new_callable=AsyncMock) as mock_validate,
        ):
            mock_find = MagicMock()
            mock_find.count = AsyncMock(return_value=3)
            MockTestCase.find.return_value = mock_find

            from app.tasks.quality_tasks import _auto_validate_extraction_async

            await _auto_validate_extraction_async("ss-uuid", "user1", model="gpt-4")

            mock_validate.assert_awaited_once_with(
                search_set_uuid="ss-uuid",
                user_id="user1",
                model="gpt-4",
            )

    @pytest.mark.asyncio
    async def test_skips_validation_when_no_test_cases(self):
        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.extraction_test_case.ExtractionTestCase") as MockTestCase,
            patch("app.services.extraction_validation_service.run_validation", new_callable=AsyncMock) as mock_validate,
        ):
            mock_find = MagicMock()
            mock_find.count = AsyncMock(return_value=0)
            MockTestCase.find.return_value = mock_find

            from app.tasks.quality_tasks import _auto_validate_extraction_async

            await _auto_validate_extraction_async("ss-uuid", "user1")

            mock_validate.assert_not_called()


# ---------------------------------------------------------------------------
# _auto_validate_workflow_async
# ---------------------------------------------------------------------------


class TestAutoValidateWorkflowAsync:
    @pytest.mark.asyncio
    async def test_runs_validation_when_workflow_has_plan(self):
        mock_wf = MagicMock()
        mock_wf.id = "wf-id"
        mock_wf.validation_plan = [{"check": "output_exists"}]

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.workflow.Workflow") as MockWorkflow,
            patch("app.services.workflow_service.validate_workflow", new_callable=AsyncMock) as mock_validate,
        ):
            MockWorkflow.get = AsyncMock(return_value=mock_wf)

            from app.tasks.quality_tasks import _auto_validate_workflow_async

            await _auto_validate_workflow_async("wf-id")

            mock_validate.assert_awaited_once_with("wf-id")

    @pytest.mark.asyncio
    async def test_skips_when_workflow_not_found(self):
        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.workflow.Workflow") as MockWorkflow,
            patch("app.services.workflow_service.validate_workflow", new_callable=AsyncMock) as mock_validate,
        ):
            MockWorkflow.get = AsyncMock(return_value=None)

            from app.tasks.quality_tasks import _auto_validate_workflow_async

            await _auto_validate_workflow_async("missing-id")

            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_validation_plan(self):
        mock_wf = MagicMock()
        mock_wf.validation_plan = []

        with (
            patch("app.database.init_db", new_callable=AsyncMock),
            patch("app.config.Settings"),
            patch("app.models.workflow.Workflow") as MockWorkflow,
            patch("app.services.workflow_service.validate_workflow", new_callable=AsyncMock) as mock_validate,
        ):
            MockWorkflow.get = AsyncMock(return_value=mock_wf)

            from app.tasks.quality_tasks import _auto_validate_workflow_async

            await _auto_validate_workflow_async("wf-id")

            mock_validate.assert_not_called()
