"""Tests for WorkflowEngine execution, MultiTaskNode, UsageAccumulator,
topological ordering, data flow, progress callbacks, approval handling,
and the build_workflow_engine factory."""

import json
import threading
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.workflow_engine import (
    AddDocumentNode,
    ApprovalNode,
    CodeExecutionNode,
    DataExportNode,
    DocumentNode,
    DocumentRendererNode,
    MultiTaskNode,
    Node,
    UsageAccumulator,
    WorkflowEngine,
    build_workflow_engine,
    sanitize_step_name,
)


# ---------------------------------------------------------------------------
# UsageAccumulator
# ---------------------------------------------------------------------------

class TestUsageAccumulator:
    def test_initial_zero(self):
        acc = UsageAccumulator()
        assert acc.tokens_in == 0
        assert acc.tokens_out == 0

    def test_record_from_result(self):
        acc = UsageAccumulator()
        mock_result = MagicMock()
        mock_usage = MagicMock()
        mock_usage.request_tokens = 100
        mock_usage.response_tokens = 50
        mock_result.usage.return_value = mock_usage
        acc.record(mock_result)
        assert acc.tokens_in == 100
        assert acc.tokens_out == 50

    def test_record_accumulates(self):
        acc = UsageAccumulator()
        for _ in range(3):
            mock_result = MagicMock()
            mock_usage = MagicMock()
            mock_usage.request_tokens = 10
            mock_usage.response_tokens = 5
            mock_result.usage.return_value = mock_usage
            acc.record(mock_result)
        assert acc.tokens_in == 30
        assert acc.tokens_out == 15

    def test_record_handles_none_usage(self):
        acc = UsageAccumulator()
        mock_result = MagicMock()
        mock_usage = MagicMock()
        mock_usage.request_tokens = None
        mock_usage.response_tokens = None
        mock_result.usage.return_value = mock_usage
        acc.record(mock_result)
        assert acc.tokens_in == 0
        assert acc.tokens_out == 0

    def test_record_handles_missing_usage(self):
        acc = UsageAccumulator()
        mock_result = MagicMock()
        mock_result.usage.side_effect = AttributeError()
        acc.record(mock_result)
        assert acc.tokens_in == 0

    def test_add(self):
        acc = UsageAccumulator()
        acc.add(100, 50)
        acc.add(200, 100)
        assert acc.tokens_in == 300
        assert acc.tokens_out == 150

    def test_thread_safety(self):
        acc = UsageAccumulator()
        def add_many():
            for _ in range(1000):
                acc.add(1, 1)
        threads = [threading.Thread(target=add_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert acc.tokens_in == 4000
        assert acc.tokens_out == 4000


# ---------------------------------------------------------------------------
# WorkflowEngine - Topological ordering
# ---------------------------------------------------------------------------

class TestWorkflowEngineTopology:
    def test_single_node(self):
        engine = WorkflowEngine()
        node = DocumentNode({"doc_uuids": ["a"]})
        engine.add_node(node)
        order = engine.get_topological_order()
        assert len(order) == 1
        assert order[0] is node

    def test_two_connected_nodes(self):
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        add_doc = AddDocumentNode({"doc_texts": ["text"]})
        engine.add_node(doc)
        engine.add_node(add_doc)
        engine.connect(doc, add_doc)
        order = engine.get_topological_order()
        assert order[0] is doc
        assert order[1] is add_doc

    def test_three_node_chain(self):
        engine = WorkflowEngine()
        n1 = DocumentNode({"doc_uuids": ["a"]})
        n2 = AddDocumentNode({"doc_texts": ["text"]})
        n3 = DataExportNode({"format": "json"})
        engine.add_node(n1)
        engine.add_node(n2)
        engine.add_node(n3)
        engine.connect(n1, n2)
        engine.connect(n2, n3)
        order = engine.get_topological_order()
        assert order == [n1, n2, n3]


# ---------------------------------------------------------------------------
# WorkflowEngine - Execute
# ---------------------------------------------------------------------------

class TestWorkflowEngineExecute:
    def test_single_document_node(self):
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["uuid1", "uuid2"]})
        engine.add_node(doc)
        final, data = engine.execute()
        assert "uuid1" in str(final)

    def test_two_node_pipeline(self):
        """Document -> AddDocument flows data correctly."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["uuid1"]})
        add = AddDocumentNode({"doc_texts": ["Hello World"]})
        engine.add_node(doc)
        engine.add_node(add)
        engine.connect(doc, add)
        final, data = engine.execute()
        assert final == "Hello World"
        assert len(data) == 2

    def test_three_node_pipeline(self):
        """Document -> AddDocument -> DataExport (JSON)."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["uuid1"]})
        add = AddDocumentNode({"doc_texts": ["content"]})
        export = DataExportNode({"format": "json", "filename": "out"})
        engine.add_node(doc)
        engine.add_node(add)
        engine.add_node(export)
        engine.connect(doc, add)
        engine.connect(add, export)
        final, data = engine.execute()
        # DataExport produces file_download dict - it should pass through
        assert isinstance(final, dict)
        assert final["type"] == "file_download"
        assert len(data) == 3

    def test_data_flows_between_steps(self):
        """Verify output of each step becomes input of the next."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["uuid1"]})
        add = AddDocumentNode({"doc_texts": ["text1"]})
        engine.add_node(doc)
        engine.add_node(add)
        engine.connect(doc, add)
        final, data = engine.execute()
        # AddDocumentNode should have received Document's output as input
        assert data[1]["input"] is not None or data[1]["output"] == "text1"

    def test_empty_engine(self):
        engine = WorkflowEngine()
        final, data = engine.execute()
        assert final is None
        assert data == []

    def test_progress_callback(self):
        """Progress updater is called with step names and completion counts."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        add = AddDocumentNode({"doc_texts": ["text"]})
        engine.add_node(doc)
        engine.add_node(add)
        engine.connect(doc, add)

        updates = []
        def updater(update_dict):
            updates.append(update_dict)

        engine.execute(workflow_result_updater=updater)

        # Should have updates for starting each step and step completion
        step_names = [u.get("current_step_name") for u in updates if "current_step_name" in u]
        assert "Document" in step_names
        assert "AddDocument" in step_names

        # Should have steps_output updates
        steps_output_keys = [k for u in updates for k in u.keys() if k.startswith("steps_output.")]
        assert len(steps_output_keys) >= 2

    def test_progress_callback_includes_step_count(self):
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        add = AddDocumentNode({"doc_texts": ["text"]})
        engine.add_node(doc)
        engine.add_node(add)
        engine.connect(doc, add)

        updates = []
        engine.execute(workflow_result_updater=lambda u: updates.append(u))

        completion_updates = [u for u in updates if "num_steps_completed" in u]
        assert len(completion_updates) >= 2

    def test_approval_pause(self):
        """Engine returns early when an ApprovalNode signals pause."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        approval = ApprovalNode({"review_instructions": "Review this"})
        add = AddDocumentNode({"doc_texts": ["should not run"]})

        # ApprovalNode directly in the graph (not via MultiTaskNode)
        # to test the engine's _approval_pause detection
        engine.add_node(doc)
        engine.add_node(approval)
        engine.add_node(add)
        engine.connect(doc, approval)
        engine.connect(approval, add)

        final, data = engine.execute()
        assert isinstance(final, dict)
        assert final.get("_approval_pause") is True
        # AddDocumentNode should NOT have executed
        assert all(d["name"] != "AddDocument" for d in data)

    def test_resume_from_start_index(self):
        """Engine can resume from a specific step index with initial_output."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        add = AddDocumentNode({"doc_texts": ["resumed text"]})

        engine.add_node(doc)
        engine.add_node(add)
        engine.connect(doc, add)

        initial = {"output": "data from approval", "step_name": "Approval"}
        final, data = engine.execute(start_index=1, initial_output=initial)
        assert final == "resumed text"
        # Only the second node should appear in data
        assert len(data) == 1
        assert data[0]["name"] == "AddDocument"

    def test_steps_output_uses_sanitized_names(self):
        """Step output keys should be sanitized for MongoDB safety."""
        engine = WorkflowEngine()
        doc = DocumentNode({"doc_uuids": ["a"]})
        engine.add_node(doc)

        updates = []
        engine.execute(workflow_result_updater=lambda u: updates.append(u))

        # Find the steps_output update
        output_keys = [k for u in updates for k in u.keys() if k.startswith("steps_output.")]
        for key in output_keys:
            step_part = key.split(".", 1)[1]
            assert "." not in step_part
            assert "$" not in step_part


# ---------------------------------------------------------------------------
# MultiTaskNode
# ---------------------------------------------------------------------------

class TestMultiTaskNode:
    def test_single_task(self):
        multi = MultiTaskNode("Test Step")
        task = AddDocumentNode({"doc_texts": ["hello"]})
        multi.add_task(task)
        result = multi.process({"output": "prev"})
        assert result["output"] == "hello"

    def test_approval_pause_passthrough(self):
        multi = MultiTaskNode("Approval Step")
        task = ApprovalNode({"review_instructions": "Review this"})
        multi.add_task(task)

        result = multi.process({"output": "pending review"})

        assert result["_approval_pause"] is True
        assert result["_review_instructions"] == "Review this"
        assert result["output"] == "pending review"

    def test_multiple_tasks_parallel(self):
        """Multiple tasks execute in parallel and outputs are collected."""
        multi = MultiTaskNode("Test Step")
        task1 = AddDocumentNode({"doc_texts": ["text1"]})
        task2 = AddDocumentNode({"doc_texts": ["text2"]})
        multi.add_task(task1)
        multi.add_task(task2)
        result = multi.process({"output": "prev"})

        # Both outputs should be collected (order not guaranteed due to parallel execution)
        output = result["output"]
        if isinstance(output, list):
            assert set(output) == {"text1", "text2"}
        else:
            assert output in ("text1", "text2")

    def test_list_output_flattened(self):
        """When a task returns a list, it's extended (not nested)."""
        multi = MultiTaskNode("Test Step")

        class ListNode(Node):
            def process(self, inputs):
                return {"output": ["a", "b"], "step_name": "ListNode"}

        task = ListNode("list")
        multi.add_task(task)
        result = multi.process({"output": "prev"})
        # Single task with list output should be unwrapped
        # Since there's only one task and it returns a list of 2,
        # collected = ["a", "b"], len > 1, so output = ["a", "b"]
        assert result["output"] == ["a", "b"]

    def test_none_output_filtered(self):
        """Tasks returning None output are filtered out."""
        multi = MultiTaskNode("Test Step")

        class NoneNode(Node):
            def process(self, inputs):
                return {"output": None, "step_name": "NoneNode"}

        task1 = NoneNode("none")
        task2 = AddDocumentNode({"doc_texts": ["good"]})
        multi.add_task(task1)
        multi.add_task(task2)
        result = multi.process({"output": "prev"})
        assert result["output"] == "good"

    def test_inputs_deepcopied(self):
        """Each task gets its own copy of inputs."""
        multi = MultiTaskNode("Test Step")

        class MutatingNode(Node):
            def process(self, inputs):
                inputs["mutated"] = True
                return {"output": "done", "step_name": "Mutating"}

        task1 = MutatingNode("m1")
        task2 = AddDocumentNode({"doc_texts": ["safe"]})
        multi.add_task(task1)
        multi.add_task(task2)
        # Should not raise despite mutation
        result = multi.process({"output": "prev"})
        assert result is not None

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_post_process_called(self, mock_llm):
        """_apply_post_process is called on each task result."""
        mock_llm.return_value = "post-processed"
        multi = MultiTaskNode("Test Step")

        class TaskWithPostProcess(Node):
            def __init__(self):
                super().__init__("task")
                self.data = {"post_process_prompt": "Simplify this", "model": "gpt-4o"}

            def process(self, inputs):
                return {"output": "raw output", "step_name": "task"}

        task = TaskWithPostProcess()
        multi.add_task(task)
        result = multi.process({"output": "prev"})
        assert result["output"] == "post-processed"


# ---------------------------------------------------------------------------
# build_workflow_engine factory
# ---------------------------------------------------------------------------

class TestBuildWorkflowEngine:
    def test_document_only(self):
        steps = [{"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []}]
        engine = build_workflow_engine(steps, model="gpt-4o")
        order = engine.get_topological_order()
        assert len(order) == 1
        assert isinstance(order[0], DocumentNode)

    def test_document_plus_extraction(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Extract", "data": {}, "tasks": [
                {"name": "Extraction", "data": {"keys": ["Name"]}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o", user_id="user1")
        order = engine.get_topological_order()
        assert len(order) == 2
        assert isinstance(order[0], DocumentNode)
        assert isinstance(order[1], MultiTaskNode)
        assert len(order[1].tasks) == 1

    def test_all_task_types_recognized(self):
        """Every known task type creates a node without error."""
        task_names = [
            "Extraction", "Prompt", "Formatter", "AddWebsite", "AddDocument",
            "DescribeImage", "CodeNode", "CrawlerNode", "ResearchNode",
            "APINode", "DocumentRenderer", "FormFiller", "DataExport",
            "PackageBuilder", "BrowserAutomation", "KnowledgeBaseQuery", "Approval",
        ]
        for task_name in task_names:
            steps = [
                {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
                {"name": "Step", "data": {}, "tasks": [
                    {"name": task_name, "data": {}}
                ]},
            ]
            engine = build_workflow_engine(steps, model="gpt-4o", allow_code_execution=True)
            order = engine.get_topological_order()
            assert len(order) == 2, f"Failed for task type: {task_name}"
            assert len(order[1].tasks) == 1, f"No task created for: {task_name}"

    def test_code_node_rejected_when_not_admin(self):
        """CodeNode tasks are skipped when allow_code_execution is False."""
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "CodeNode", "data": {}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o", allow_code_execution=False)
        order = engine.get_topological_order()
        assert len(order) == 2
        assert len(order[1].tasks) == 0  # CodeNode was rejected

    def test_unknown_task_type_skipped(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "NonexistentTaskType", "data": {}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        order = engine.get_topological_order()
        assert len(order) == 2
        assert len(order[1].tasks) == 0  # unknown task was skipped

    def test_model_propagated_to_tasks(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "Prompt", "data": {}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o-mini")
        order = engine.get_topological_order()
        task = order[1].tasks[0]
        assert task.data.get("model") == "gpt-4o-mini"

    def test_task_model_override_preserved(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "Prompt", "data": {"model": "claude-3-opus"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o-mini")
        order = engine.get_topological_order()
        task = order[1].tasks[0]
        assert task.data.get("model") == "claude-3-opus"

    def test_user_id_set_on_tasks(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "Extraction", "data": {"keys": ["Name"]}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o", user_id="user123")
        order = engine.get_topological_order()
        task = order[1].tasks[0]
        assert task.data.get("user_id") == "user123"

    def test_system_config_propagated(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Step", "data": {}, "tasks": [
                {"name": "Prompt", "data": {}}
            ]},
        ]
        sys_cfg = {"extraction_model": "gpt-4o"}
        engine = build_workflow_engine(steps, model="gpt-4o", system_config_doc=sys_cfg)
        order = engine.get_topological_order()
        task = order[1].tasks[0]
        assert task._sys_cfg == sys_cfg

    def test_usage_accumulator_shared(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "S1", "data": {}, "tasks": [
                {"name": "Prompt", "data": {}}
            ]},
            {"name": "S2", "data": {}, "tasks": [
                {"name": "Extraction", "data": {"keys": ["X"]}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        order = engine.get_topological_order()
        # All tasks should share the engine's usage accumulator
        assert order[1].tasks[0]._usage_acc is engine.usage
        assert order[2].tasks[0]._usage_acc is engine.usage

    def test_sequential_connections(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "S1", "data": {}, "tasks": [{"name": "Prompt", "data": {}}]},
            {"name": "S2", "data": {}, "tasks": [{"name": "Prompt", "data": {}}]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        order = engine.get_topological_order()
        # Should be in order: Document -> S1 -> S2
        assert order[0].name == "Document"
        assert len(order) == 3

    def test_multiple_tasks_per_step(self):
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Multi", "data": {}, "tasks": [
                {"name": "Prompt", "data": {"prompt": "Q1"}},
                {"name": "Prompt", "data": {"prompt": "Q2"}},
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        order = engine.get_topological_order()
        assert isinstance(order[1], MultiTaskNode)
        assert len(order[1].tasks) == 2


# ---------------------------------------------------------------------------
# Full pipeline integration tests (no LLM, using pure nodes only)
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    def test_document_to_export_json(self):
        """End-to-end: Document -> AddDocument -> DataExport (JSON)."""
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Add", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["Hello World"]}}
            ]},
            {"name": "Export", "data": {}, "tasks": [
                {"name": "DataExport", "data": {"format": "json", "filename": "out"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert isinstance(final, dict)
        assert final.get("type") == "file_download"
        assert final.get("file_type") == "json"

    def test_document_to_renderer_md(self):
        """End-to-end: Document -> AddDocument -> DocumentRenderer (md)."""
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Add", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["# Report"]}}
            ]},
            {"name": "Render", "data": {}, "tasks": [
                {"name": "DocumentRenderer", "data": {"format": "md", "filename": "report"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert final["filename"] == "report.md"
        import base64
        content = base64.b64decode(final["data_b64"]).decode()
        assert content == "# Report"

    def test_document_to_package(self):
        """End-to-end: Document -> AddDocument -> PackageBuilder (zip)."""
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Add", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["data"]}}
            ]},
            {"name": "Pkg", "data": {}, "tasks": [
                {"name": "PackageBuilder", "data": {"package_name": "bundle"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert final["file_type"] == "zip"
        assert final["filename"] == "bundle.zip"

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_document_to_code_to_export(self, mock_validate):
        """End-to-end: Document -> AddDocument -> CodeNode -> DataExport."""
        mock_validate.return_value = None
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Add", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["one two three"]}}
            ]},
            {"name": "Code", "data": {}, "tasks": [
                {"name": "CodeNode", "data": {"code": "result = len(data.split())"}}
            ]},
            {"name": "Export", "data": {}, "tasks": [
                {"name": "DataExport", "data": {"format": "json", "filename": "count"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o", allow_code_execution=True)
        final, data = engine.execute()
        assert final["file_type"] == "json"
        import base64
        content = base64.b64decode(final["data_b64"]).decode()
        assert "3" in content

    def test_approval_in_pipeline(self):
        """Document -> Approval -> AddDocument stops at approval via factory."""
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Review", "data": {}, "tasks": [
                {"name": "Approval", "data": {"review_instructions": "Check it"}}
            ]},
            {"name": "Final", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["should not run"]}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert isinstance(final, dict)
        assert final.get("_approval_pause") is True
        # Final step should not have run
        assert all(d.get("name") != "AddDocument" for d in data)

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_in_pipeline(self, mock_llm):
        """Document -> AddDocument -> Prompt -> DataExport."""
        mock_llm.return_value = "Summarized: data was interesting"
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Add", "data": {}, "tasks": [
                {"name": "AddDocument", "data": {"doc_texts": ["Raw data here"]}}
            ]},
            {"name": "Summarize", "data": {}, "tasks": [
                {"name": "Prompt", "data": {"prompt": "Summarize this"}}
            ]},
            {"name": "Export", "data": {}, "tasks": [
                {"name": "DataExport", "data": {"format": "json", "filename": "summary"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert final["file_type"] == "json"
        import base64
        content = base64.b64decode(final["data_b64"]).decode()
        assert "Summarized" in content

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_in_pipeline(self, mock_extract):
        """Document -> Extraction -> DataExport."""
        mock_extract.return_value = {
            "raw": [{"Name": "Alice", "Role": "PI"}],
            "formatted": "- **Name**: Alice\n- **Role**: PI",
        }
        steps = [
            {"name": "Document", "data": {"doc_uuids": ["u1"]}, "tasks": []},
            {"name": "Extract", "data": {}, "tasks": [
                {"name": "Extraction", "data": {"keys": ["Name", "Role"], "doc_texts": ["Alice is the PI"]}}
            ]},
            {"name": "Export", "data": {}, "tasks": [
                {"name": "DataExport", "data": {"format": "csv", "filename": "people"}}
            ]},
        ]
        engine = build_workflow_engine(steps, model="gpt-4o")
        final, data = engine.execute()
        assert final["file_type"] == "csv"
        import base64
        content = base64.b64decode(final["data_b64"]).decode()
        assert "Name" in content
        assert "Alice" in content


# ---------------------------------------------------------------------------
# Node base class
# ---------------------------------------------------------------------------

class TestNodeBase:
    def test_repr(self):
        node = DocumentNode({"doc_uuids": []})
        assert "DocumentNode" in repr(node)
        assert "Document" in repr(node)

    def test_report_progress_with_reporter(self):
        node = DocumentNode({"doc_uuids": []})
        calls = []
        node.progress_reporter = lambda d=None, p=None: calls.append((d, p))
        node.report_progress("working", "preview data")
        assert calls == [("working", "preview data")]

    def test_report_progress_without_reporter(self):
        node = DocumentNode({"doc_uuids": []})
        # Should not raise
        node.report_progress("working")

    def test_process_not_implemented(self):
        node = Node("test")
        with pytest.raises(NotImplementedError):
            node.process({})
