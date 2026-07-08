"""Phase 7 of the agentic-chat harness uplift: parallel tool execution.

pydantic-ai runs a response's tool calls concurrently by default; the safety
model is fail-closed registration — everything outside PARALLEL_SAFE_TOOLS is
sequential, so writes never race each other, their targets, or the
confirm-gate bookkeeping."""

from app.services import llm_service
from app.services.chat_tools import (
    COMPACTABLE_TOOLS,
    PARALLEL_SAFE_TOOLS,
    TOOLS,
)

# Every gated write / mutating tool in the registry. If a new write tool is
# added to TOOLS without updating this list, the fail-closed default still
# protects it — this list exists so the assertion below catches someone
# adding a write tool to PARALLEL_SAFE_TOOLS.
WRITE_TOOLS = {
    "create_knowledge_base", "add_documents_to_kb", "add_url_to_kb",
    "run_workflow", "approve_workflow_step", "reject_workflow_step",
    "propose_test_case", "run_validation", "create_extraction_from_document",
    "start_optimization", "apply_optimization", "regenerate_validation_plan",
    "save_to_folder", "create_project", "run_pin_on_project",
    "pin_to_project", "unpin_from_project", "set_project_status",
    "create_automation", "create_workflow",
}


class TestParallelSafeClassification:
    def test_no_write_tool_is_parallel_safe(self):
        assert not (PARALLEL_SAFE_TOOLS & WRITE_TOOLS)

    def test_safe_set_is_reads_plus_status(self):
        assert PARALLEL_SAFE_TOOLS == COMPACTABLE_TOOLS | {
            "get_workflow_status", "get_optimization_run",
        }

    def test_every_registered_tool_is_classified(self):
        names = {fn.__name__ for fn in TOOLS}
        # Sanity: the union of safe + write covers the registry, so a new
        # tool forces a conscious classification decision here.
        unclassified = names - PARALLEL_SAFE_TOOLS - WRITE_TOOLS
        assert not unclassified, f"classify these tools: {unclassified}"


class TestAgentRegistration:
    def _agent(self, monkeypatch, config=None):
        from pydantic_ai.models.test import TestModel

        monkeypatch.setattr(
            llm_service, "get_agent_model", lambda *a, **k: TestModel()
        )
        llm_service._agentic_chat_agent_cache.clear()
        try:
            return llm_service.create_agentic_chat_agent(
                "unit-test-model", system_config_doc=config,
            )
        finally:
            llm_service._agentic_chat_agent_cache.clear()

    def test_write_tools_sequential_read_tools_parallel(self, monkeypatch):
        agent = self._agent(monkeypatch)
        flags = {name: t.sequential for name, t in agent._function_toolset.tools.items()}
        for name in WRITE_TOOLS:
            assert flags[name] is True, f"{name} must be sequential"
        for name in PARALLEL_SAFE_TOOLS:
            assert flags[name] is False, f"{name} should run concurrently"

    def test_kill_switch_forces_everything_sequential(self, monkeypatch):
        agent = self._agent(
            monkeypatch,
            config={"chat_config": {"parallel_tools_enabled": False}},
        )
        flags = {name: t.sequential for name, t in agent._function_toolset.tools.items()}
        assert all(flags.values())


class TestPromptInvitation:
    def test_agentic_base_invites_parallel_reads(self):
        assert "## Parallel lookups" in llm_service.AGENTIC_CHAT_SYSTEM_PROMPT
        assert "multiple tool calls in a single response" in llm_service.AGENTIC_CHAT_SYSTEM_PROMPT
