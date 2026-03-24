"""Tier 2 integration tests — requires MongoDB.

These test real Beanie ODM operations, the Beanie-to-pymongo boundary,
and workflow execution with a real database.
Set INTEGRATION_MONGODB=1 to run.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# 1. Workflow model round-trip via Beanie
# ---------------------------------------------------------------------------

class TestWorkflowModelRoundTrip:
    """Create Workflow → WorkflowStep → WorkflowStepTask → WorkflowResult
    via Beanie and verify round-trip fidelity."""

    async def test_workflow_model_round_trip(self, mongo_client):
        from app.models.workflow import (
            Workflow,
            WorkflowStep,
            WorkflowStepTask,
            WorkflowResult,
        )

        task = WorkflowStepTask(name="Extraction", data={"keys": ["Name", "Age"]})
        await task.insert()
        assert task.id is not None

        step = WorkflowStep(name="Step1", tasks=[task.id], data={}, is_output=True)
        await step.insert()

        wf = Workflow(
            name="Test Workflow",
            description="Integration test",
            user_id="user_123",
            steps=[step.id],
            space="default",
        )
        await wf.insert()

        result = WorkflowResult(
            workflow=wf.id,
            session_id="session_abc",
            status="running",
            num_steps_total=1,
        )
        await result.insert()

        # Read back and verify
        wf_read = await Workflow.get(wf.id)
        assert wf_read is not None
        assert wf_read.name == "Test Workflow"
        assert wf_read.num_executions == 0
        assert len(wf_read.steps) == 1
        assert wf_read.steps[0] == step.id

        step_read = await WorkflowStep.get(step.id)
        assert step_read.name == "Step1"
        assert step_read.is_output is True
        assert step_read.tasks[0] == task.id

        result_read = await WorkflowResult.get(result.id)
        assert result_read.workflow == wf.id
        assert result_read.status == "running"
        assert result_read.start_time is not None


# ---------------------------------------------------------------------------
# 2. pymongo $set patterns matching workflow_tasks.py
# ---------------------------------------------------------------------------

class TestPymongoUpdatePatterns:
    """Create via Beanie, update via pymongo (sync), verify via Beanie.
    This catches field name mismatches between the two code paths."""

    async def test_pymongo_update_patterns(self, mongo_client, sync_mongo):
        from app.models.workflow import WorkflowResult

        result = WorkflowResult(
            session_id="session_xyz",
            status="pending",
            num_steps_total=3,
        )
        await result.insert()
        result_oid = ObjectId(str(result.id))

        # Replicate the $set operations from workflow_tasks.py
        sync_mongo.workflow_result.update_one(
            {"_id": result_oid},
            {"$set": {
                "status": "running",
                "num_steps_completed": 0,
                "num_steps_total": 3,
                "steps_output": {},
            }},
        )

        # Progress update: set nested steps_output
        sync_mongo.workflow_result.update_one(
            {"_id": result_oid},
            {"$set": {
                "steps_output.Extraction": {"output": [{"Name": "Alice"}]},
                "num_steps_completed": 1,
            }},
        )

        # Final update
        sync_mongo.workflow_result.update_one(
            {"_id": result_oid},
            {"$set": {
                "status": "completed",
                "final_output": {"output": "Done", "data": []},
            }},
        )

        # Read back via Beanie and verify
        updated = await WorkflowResult.get(result.id)
        assert updated.status == "completed"
        assert updated.num_steps_completed == 1
        assert updated.steps_output["Extraction"]["output"] == [{"Name": "Alice"}]
        assert updated.final_output["output"] == "Done"


# ---------------------------------------------------------------------------
# 3. workflow_service.get_workflow with real DB
# ---------------------------------------------------------------------------

class TestWorkflowServiceGetWorkflow:
    """Call get_workflow() against a real database with inserted documents."""

    async def test_workflow_service_get_workflow(self, mongo_client):
        from app.models.workflow import Workflow, WorkflowStep, WorkflowStepTask
        from app.services.workflow_service import get_workflow

        task1 = WorkflowStepTask(name="Extraction", data={"keys": ["Title"]})
        await task1.insert()
        task2 = WorkflowStepTask(name="Prompt", data={"prompt": "Summarize"})
        await task2.insert()

        step = WorkflowStep(name="ProcessStep", tasks=[task1.id, task2.id], is_output=True)
        await step.insert()

        wf = Workflow(
            name="Service Test WF",
            user_id="u1",
            steps=[step.id],
            space="default",
        )
        await wf.insert()

        result = await get_workflow(str(wf.id))

        assert result is not None
        assert result["name"] == "Service Test WF"
        assert result["num_executions"] == 0
        assert len(result["steps"]) == 1

        step_result = result["steps"][0]
        assert step_result["name"] == "ProcessStep"
        assert step_result["is_output"] is True
        assert len(step_result["tasks"]) == 2
        assert step_result["tasks"][0]["name"] == "Extraction"
        assert step_result["tasks"][1]["name"] == "Prompt"
        assert step_result["tasks"][0]["data"]["keys"] == ["Title"]


# ---------------------------------------------------------------------------
# 4. Full workflow execution: real DB + real engine (no engine mock)
# ---------------------------------------------------------------------------

class TestFullWorkflowWithRealEngine:
    """Insert real documents into MongoDB, run execute_workflow_task with
    a real build_workflow_engine (AddDocument nodes — no LLM needed).
    Verify the full path: DB reads → engine build → node execution → DB writes."""

    async def test_full_workflow_add_document(self, mongo_client, sync_mongo):
        from app.models.workflow import (
            Workflow,
            WorkflowStep,
            WorkflowStepTask,
            WorkflowResult,
        )
        from app.models.document import SmartDocument
        from app.tasks.workflow_tasks import execute_workflow_task

        # Insert a real SmartDocument with raw_text
        smart_doc = SmartDocument(
            path="/test/doc.pdf",
            downloadpath="/test/doc.pdf",
            title="Test Doc",
            uuid="full_test_uuid",
            space="default",
            user_id="u1",
            raw_text="The quick brown fox jumps over the lazy dog.",
        )
        await smart_doc.insert()

        # Create workflow: Document trigger → Step1(AddDocument)
        task_doc = WorkflowStepTask(name="AddDocument", data={})
        await task_doc.insert()

        step_doc = WorkflowStep(name="Step1", tasks=[task_doc.id])
        await step_doc.insert()

        wf = Workflow(name="Full Engine WF", user_id="u1", steps=[step_doc.id])
        await wf.insert()

        wr = WorkflowResult(
            workflow=wf.id,
            session_id="sess_full",
            status="pending",
        )
        await wr.insert()

        # Run with real engine — only mock _get_db and the fire-and-forget tasks
        with patch("app.tasks.workflow_tasks._get_db", return_value=sync_mongo), \
             patch("app.tasks.quality_tasks.auto_validate_workflow") as mock_val:
            mock_val.delay = MagicMock()

            execute_workflow_task(
                str(wr.id),
                str(wf.id),
                {"doc_uuids": ["full_test_uuid"]},
                "test-model",
            )

        # Verify WorkflowResult: status, steps_output, final_output
        updated_result = await WorkflowResult.get(wr.id)
        assert updated_result.status == "completed"
        assert updated_result.final_output is not None

        # The real engine wrote step output via the progress updater
        assert "Step1" in updated_result.steps_output
        step_output = updated_result.steps_output["Step1"]
        # AddDocument node joins doc_texts — our doc's raw_text should be in the output
        assert "quick brown fox" in str(step_output)

        # Verify workflow execution count incremented
        updated_wf = await Workflow.get(wf.id)
        assert updated_wf.num_executions == 1

    async def test_multi_doc_text_preloading(self, mongo_client, sync_mongo):
        """Verify that doc_texts are pre-loaded from multiple SmartDocuments
        and passed through to the engine."""
        from app.models.workflow import (
            Workflow,
            WorkflowStep,
            WorkflowStepTask,
            WorkflowResult,
        )
        from app.models.document import SmartDocument
        from app.tasks.workflow_tasks import execute_workflow_task

        doc1 = SmartDocument(
            path="/a.pdf", downloadpath="/a.pdf", title="Doc A",
            uuid="multi_uuid_1", space="s", user_id="u1",
            raw_text="Alpha content",
        )
        doc2 = SmartDocument(
            path="/b.pdf", downloadpath="/b.pdf", title="Doc B",
            uuid="multi_uuid_2", space="s", user_id="u1",
            raw_text="Beta content",
        )
        await doc1.insert()
        await doc2.insert()

        task_doc = WorkflowStepTask(name="AddDocument", data={})
        await task_doc.insert()
        step_doc = WorkflowStep(name="Combine", tasks=[task_doc.id])
        await step_doc.insert()
        wf = Workflow(name="MultiDoc WF", user_id="u1", steps=[step_doc.id])
        await wf.insert()
        wr = WorkflowResult(workflow=wf.id, session_id="sess_multi", status="pending")
        await wr.insert()

        with patch("app.tasks.workflow_tasks._get_db", return_value=sync_mongo), \
             patch("app.tasks.quality_tasks.auto_validate_workflow") as mock_val:
            mock_val.delay = MagicMock()
            execute_workflow_task(
                str(wr.id), str(wf.id),
                {"doc_uuids": ["multi_uuid_1", "multi_uuid_2"]},
                "test-model",
            )

        updated = await WorkflowResult.get(wr.id)
        assert updated.status == "completed"
        output_str = str(updated.steps_output)
        assert "Alpha content" in output_str
        assert "Beta content" in output_str


# ---------------------------------------------------------------------------
# 5. Error path: engine failure writes error status to real DB
# ---------------------------------------------------------------------------

class TestWorkflowErrorPath:
    """Verify that when the engine raises, execute_workflow_task writes
    {"status": "error"} to the real database before re-raising."""

    async def test_engine_error_writes_status(self, mongo_client, sync_mongo):
        from app.models.workflow import (
            Workflow,
            WorkflowStep,
            WorkflowStepTask,
            WorkflowResult,
        )
        from app.tasks.workflow_tasks import execute_workflow_task

        task_doc = WorkflowStepTask(name="AddDocument", data={})
        await task_doc.insert()
        step_doc = WorkflowStep(name="Step1", tasks=[task_doc.id])
        await step_doc.insert()
        wf = Workflow(name="Error WF", user_id="u1", steps=[step_doc.id])
        await wf.insert()
        wr = WorkflowResult(workflow=wf.id, session_id="sess_err", status="pending")
        await wr.insert()

        # Mock engine to raise
        mock_engine = MagicMock()
        mock_engine.execute.side_effect = RuntimeError("LLM provider timeout")
        mock_engine.usage = MagicMock(tokens_in=0, tokens_out=0)

        with patch("app.tasks.workflow_tasks._get_db", return_value=sync_mongo), \
             patch("app.services.workflow_engine.build_workflow_engine", return_value=mock_engine):
            with pytest.raises(RuntimeError, match="LLM provider timeout"):
                execute_workflow_task(
                    str(wr.id), str(wf.id),
                    {"doc_uuids": []}, "test-model",
                )

        # Verify error was written to real DB
        updated = await WorkflowResult.get(wr.id)
        assert updated.status == "error"

        # Verify execution count was NOT incremented (error path skips this)
        updated_wf = await Workflow.get(wf.id)
        assert updated_wf.num_executions == 0


# ---------------------------------------------------------------------------
# 6. SystemConfig singleton
# ---------------------------------------------------------------------------

class TestSystemConfigSingleton:
    """Verify get_config() creates exactly one document."""

    async def test_system_config_singleton(self, mongo_client):
        from app.models.system_config import SystemConfig

        config1 = await SystemConfig.get_config()
        config2 = await SystemConfig.get_config()

        assert config1.id == config2.id

        count = await SystemConfig.find_all().count()
        assert count == 1
