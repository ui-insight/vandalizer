"""Phase 9 of the agentic-chat harness uplift: bulk analysis subagents.

fan_out_analyses runs tool-less per-document sub-runs under a global
concurrency cap; per-document failures never abort the batch; results are
capped before entering the main context. analyze_documents validates and
authorizes up front and reports skipped documents instead of silently
dropping them."""

import asyncio
import types

from app.services import chat_subagents, chat_tools, llm_service
from app.services.chat_subagents import (
    fan_out_analyses,
    SUBAGENT_MAX_CONCURRENCY,
    SUBAGENT_RESULT_MAX_CHARS,
)
from app.services.chat_tools import analyze_documents


def _docs(n: int) -> list[dict]:
    return [
        {"uuid": f"d{i}", "title": f"Doc {i}", "raw_text": f"text {i} " * 50}
        for i in range(n)
    ]


class _FakeAgent:
    def __init__(self, run_fn):
        self._run_fn = run_fn

    async def run(self, prompt):
        return types.SimpleNamespace(output=await self._run_fn(prompt))


def _patch_agent(monkeypatch, run_fn):
    monkeypatch.setattr(
        llm_service, "create_chat_agent", lambda *a, **k: _FakeAgent(run_fn)
    )


class TestFanOut:
    async def test_returns_one_analysis_per_document(self, monkeypatch):
        async def run(prompt):
            return "digest: " + prompt.split("BEGIN DOCUMENT: ")[1][:5]

        _patch_agent(monkeypatch, run)
        results = await fan_out_analyses(
            documents=_docs(3), instruction="summarize",
            model_name="m", sys_config_doc={},
        )
        assert [r["uuid"] for r in results] == ["d0", "d1", "d2"]
        assert all(r["analysis"].startswith("digest:") for r in results)

    async def test_one_failure_never_aborts_the_batch(self, monkeypatch):
        async def run(prompt):
            if "Doc 1" in prompt:
                raise RuntimeError("provider exploded")
            return "ok"

        _patch_agent(monkeypatch, run)
        results = await fan_out_analyses(
            documents=_docs(3), instruction="summarize",
            model_name="m", sys_config_doc={},
        )
        assert "error" in results[1]
        assert results[0]["analysis"] == "ok" and results[2]["analysis"] == "ok"

    async def test_results_are_capped(self, monkeypatch):
        async def run(prompt):
            return "x" * (SUBAGENT_RESULT_MAX_CHARS + 500)

        _patch_agent(monkeypatch, run)
        [result] = await fan_out_analyses(
            documents=_docs(1), instruction="summarize",
            model_name="m", sys_config_doc={},
        )
        assert len(result["analysis"]) == SUBAGENT_RESULT_MAX_CHARS
        assert result["analysis_capped"] is True

    async def test_concurrency_is_globally_bounded(self, monkeypatch):
        live = {"now": 0, "peak": 0}

        async def run(prompt):
            live["now"] += 1
            live["peak"] = max(live["peak"], live["now"])
            await asyncio.sleep(0.01)
            live["now"] -= 1
            return "ok"

        _patch_agent(monkeypatch, run)
        await fan_out_analyses(
            documents=_docs(12), instruction="summarize",
            model_name="m", sys_config_doc={},
        )
        assert live["peak"] <= SUBAGENT_MAX_CONCURRENCY


def _ctx(chat_config=None, doc_uuids=None):
    return types.SimpleNamespace(deps=types.SimpleNamespace(
        system_config_doc={"chat_config": chat_config or {}},
        team_id="t1",
        user_id="u1",
        model_name="m",
        context_document_uuids=doc_uuids or [],
    ))


class TestAnalyzeDocumentsTool:
    async def test_flag_disabled_soft_errors_with_hint(self):
        result = await analyze_documents(
            _ctx({"subagents_enabled": False}), "summarize", ["d1", "d2", "d3"],
        )
        assert "disabled" in result["error"]
        assert "get_document_text" in result["hint"]

    async def test_missing_instruction_rejected(self):
        result = await analyze_documents(_ctx(), "   ", ["d1"])
        assert "instruction is required" in result["error"]
        assert "output" in result["hint"]

    async def test_too_many_documents_rejected(self):
        result = await analyze_documents(
            _ctx(), "summarize", [f"d{i}" for i in range(25)],
        )
        assert "Too many documents" in result["error"]

    async def test_authorizes_and_reports_skipped(self, monkeypatch):
        docs = {
            "mine": types.SimpleNamespace(
                uuid="mine", title="Mine", raw_text="content here",
                team_id="t1", user_id="u1",
            ),
            "theirs": types.SimpleNamespace(
                uuid="theirs", title="Theirs", raw_text="secret",
                team_id="t2", user_id="u2",
            ),
            "empty": types.SimpleNamespace(
                uuid="empty", title="Empty", raw_text="",
                team_id="t1", user_id="u1",
            ),
        }

        class _FakeSmartDocument:
            # Uninitialized Beanie models can't build `SmartDocument.uuid ==`
            # expressions; this stand-in makes the comparison yield the
            # queried uuid string, which find_one then looks up directly.
            class _UuidField:
                def __eq__(self, other):
                    return other

            uuid = _UuidField()

            @staticmethod
            async def find_one(query):
                return docs.get(query)

        monkeypatch.setattr(chat_tools, "SmartDocument", _FakeSmartDocument)

        async def fake_fan_out(*, documents, instruction, model_name, sys_config_doc):
            return [
                {"uuid": d["uuid"], "title": d["title"], "analysis": "ok"}
                for d in documents
            ]

        monkeypatch.setattr(chat_subagents, "fan_out_analyses", fake_fan_out)

        result = await analyze_documents(
            _ctx(), "summarize", ["mine", "theirs", "empty", "ghost"],
        )
        assert result["analyzed"] == 1
        assert result["results"][0]["uuid"] == "mine"
        reasons = {s["uuid"]: s["reason"] for s in result["skipped"]}
        assert reasons["theirs"] == "no access"
        assert "no text yet" in reasons["empty"]
        assert reasons["ghost"] == "not found"
