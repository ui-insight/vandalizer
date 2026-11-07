"""A workflow can search the web, and its results arrive with their URLs.

Workflows could only fetch a URL fixed when the workflow was built, so a step
like "check the sponsor's current page limit" had no way to find the page.
"""

from unittest.mock import patch

from app.services.workflow_engine import WEB_SEARCH_HEADER, WebSearchNode, build_workflow_engine

CONFIGURED = {"web_search_provider": "tavily"}


def _node(data, sys_cfg=CONFIGURED):
    node = WebSearchNode(data)
    node._sys_cfg = sys_cfg
    return node


def _run(node, found, inputs=None):
    with patch("app.services.web_search_service.web_search_sync", return_value=found) as search:
        return node.process(inputs or {"output": "National Science Foundation"}), search


def test_results_go_downstream_framed_and_cited_by_url():
    found = {"results": [
        {"title": "PAPPG 24-1", "url": "https://nsf.gov/pappg", "snippet": "Page limit: 15 pages."},
        {"title": "", "url": "https://nsf.gov/faq", "snippet": ""},
    ]}
    out, search = _run(_node({"query": "{{ inputs.output }} project description page limit", "max_results": 3}), found)

    assert search.call_args.args[0] == "National Science Foundation project description page limit"
    assert search.call_args.kwargs["max_results"] == 3
    assert out["output"].startswith(WEB_SEARCH_HEADER)
    assert "[1] PAPPG 24-1\nhttps://nsf.gov/pappg\nPage limit: 15 pages." in out["output"]
    assert "[2] https://nsf.gov/faq\nhttps://nsf.gov/faq" in out["output"]
    assert [s["url"] for s in out["retrieved_sources"]] == ["https://nsf.gov/pappg", "https://nsf.gov/faq"]
    assert out["retrieved_sources"][0]["document_title"] == "PAPPG 24-1"
    assert "error" not in out and "warning" not in out


def test_screened_results_are_named_in_a_warning():
    found = {"screened": 1, "results": [
        {"title": "t", "url": "https://ex.org", "snippet": "[removed: text addressed to an AI]", "screened": True},
    ]}
    out, _ = _run(_node({"query": "q"}), found)
    assert "1 result had text addressed to an AI" in out["warning"]


def test_no_provider_halts_the_run_and_says_who_can_fix_it():
    out, search = _run(_node({"query": "q"}, sys_cfg={}), {"results": []})
    assert "no web search provider" in out["error"] and "System Config" in out["error"]
    search.assert_not_called()


def test_an_empty_query_is_a_configuration_error():
    out, search = _run(_node({"query": "  "}), {"results": []})
    assert "query is empty" in out["error"]
    search.assert_not_called()


def test_a_query_that_renders_empty_is_skipped_with_a_warning():
    out, search = _run(_node({"query": "{{ inputs.output }}"}), {"results": []}, inputs={"output": ""})
    assert "rendered to an empty string" in out["warning"] and "error" not in out
    search.assert_not_called()


def test_a_provider_failure_halts_the_run():
    out, _ = _run(_node({"query": "q"}), {"error": "Web search provider returned HTTP 401.", "results": []})
    assert out["error"] == "Web search failed: Web search provider returned HTTP 401."


def test_no_results_is_a_warning_not_a_failure():
    out, _ = _run(_node({"query": "q"}), {"results": []})
    assert "returned no results" in out["warning"] and "error" not in out


def test_the_engine_and_the_step_test_build_a_web_search_step():
    from app.services import workflow_engine

    built = []

    class Spy(WebSearchNode):
        def __init__(self, data):
            super().__init__(data)
            built.append(self)

    steps = [{"name": "Find the page", "data": {}, "tasks": [{"name": "WebSearch", "data": {"query": "q"}}]}]
    with patch.object(workflow_engine, "WebSearchNode", Spy):
        build_workflow_engine(steps, model="m", system_config_doc=CONFIGURED)
    assert len(built) == 1 and built[0].data["query"] == "q"


def test_chat_can_author_a_web_search_step():
    from app.services.chat_tools import _WORKFLOW_STEP_TYPES
    from app.services.chat_workflow_tools import _TASK_TYPES

    assert _WORKFLOW_STEP_TYPES["web_search"] == ("WebSearch", False)
    assert _TASK_TYPES["WebSearch"] == "web_search"
