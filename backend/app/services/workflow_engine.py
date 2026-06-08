"""Workflow engine  - ported from app/utilities/workflow.py.

All node processing is synchronous (runs in Celery workers).
Progress reporting uses pymongo directly for sync context.
"""

import base64
import csv
import graphlib
import io
import json
import logging
import multiprocessing
import re
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NoReturn
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.extraction_engine import ExtractionEngine
from app.services.llm_service import create_chat_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token usage accumulator
# ---------------------------------------------------------------------------

class UsageAccumulator:
    """Thread-safe token usage accumulator for workflow/extraction LLM calls."""
    __slots__ = ("tokens_in", "tokens_out", "_lock")

    def __init__(self):
        self.tokens_in = 0
        self.tokens_out = 0
        self._lock = threading.Lock()

    def record(self, result) -> None:
        """Record usage from a pydantic-ai RunResult."""
        try:
            usage = result.usage()
            with self._lock:
                self.tokens_in += usage.request_tokens or 0
                self.tokens_out += usage.response_tokens or 0
        except (AttributeError, TypeError):
            pass  # usage() not available on all result types

    def add(self, tokens_in: int, tokens_out: int) -> None:
        with self._lock:
            self.tokens_in += tokens_in
            self.tokens_out += tokens_out


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def sanitize_step_name(name: str) -> str:
    name = name.replace(".", "_").replace("$", "_").strip().strip("_")
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"__+", "_", name)
    return name or "step"


def _extract_text_from_html(html: str) -> str:
    """Extract clean text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_extraction_results(data) -> str:
    """Convert extraction JSON results into a markdown bullet list."""
    if data is None:
        return ""
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return str(data)

    lines = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            if len(items) > 1:
                lines.append(f"#### Result {idx}")
            for key, value in item.items():
                value_str = _stringify_value(value)
                lines.append(f"- **{key}**: {value_str}")
            lines.append("")
        else:
            lines.append(f"- {item}")
    return "\n".join(line for line in lines if line is not None)


def _stringify_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify_value(v) for v in value if v is not None)
    if isinstance(value, dict):
        return json.dumps(value, indent=2)
    return str(value)


# ---------------------------------------------------------------------------
# Input source resolution (shared by Prompt / Extraction / Format / etc.)
# ---------------------------------------------------------------------------

INPUT_SOURCE_LABELS = {
    "step_input": "Previous Step Output",
    "select_document": "Selected Document",
    "workflow_documents": "Workflow Documents",
}


def _resolve_input_sources(data: dict, prev_step_name: str | None = None) -> list[str]:
    """Return the ordered, deduped list of input sources for a node.

    Prefers the new `input_sources` list if present; otherwise falls back to
    the legacy single `input_source` (default `step_input`). When the previous
    step is the Document trigger, `step_input` is swapped for
    `workflow_documents` because the trigger emits doc UUIDs, not text.
    """
    raw = data.get("input_sources")
    if isinstance(raw, list) and raw:
        sources = [s for s in raw if s in INPUT_SOURCE_LABELS]
    else:
        legacy = data.get("input_source", "step_input")
        sources = [legacy] if legacy in INPUT_SOURCE_LABELS else ["step_input"]

    if prev_step_name == "Document":
        sources = ["workflow_documents" if s == "step_input" else s for s in sources]

    seen: set[str] = set()
    deduped: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped or ["step_input"]


def _stringify_context(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)


def _join_doc_texts(doc_texts: list[str]) -> str:
    if not doc_texts:
        return ""
    if len(doc_texts) == 1:
        return doc_texts[0]
    return "\n\n".join(f"=== Document {i} ===\n{dt}" for i, dt in enumerate(doc_texts, 1))


def _build_combined_context(data: dict, inputs: dict, sources: list[str]):
    """Build the data payload to feed an LLM node.

    For a single source, returns the raw payload (str / dict / list) so the
    downstream prompt template formats it the same as before. For multiple
    sources, returns a labeled multi-section string. Empty sources are
    skipped; if all are empty, returns "".
    """
    sections: list[tuple[str, str]] = []
    raw_single = None
    for src in sources:
        if src == "step_input":
            payload = inputs.get("output")
            text = _stringify_context(payload)
            if text:
                sections.append((INPUT_SOURCE_LABELS[src], text))
                raw_single = payload
        elif src == "select_document":
            doc = data.get("selected_doc_text") or ""
            if doc:
                sections.append((INPUT_SOURCE_LABELS[src], doc))
                raw_single = doc
        elif src == "workflow_documents":
            joined = _join_doc_texts(data.get("doc_texts") or [])
            if joined:
                sections.append((INPUT_SOURCE_LABELS[src], joined))
                raw_single = joined

    if not sections:
        return ""
    if len(sections) == 1:
        return raw_single
    return "\n\n".join(f"=== {label} ===\n{content}" for label, content in sections)


def _build_extraction_texts(data: dict, inputs: dict, sources: list[str]) -> list[str]:
    """Build a list of texts for ExtractionEngine, one entry per source/document.

    Each non-empty source contributes one entry, except `workflow_documents`
    which expands to one entry per loaded document (preserving existing
    multi-doc extraction behavior).
    """
    texts: list[str] = []
    for src in sources:
        if src == "step_input":
            payload = inputs.get("output")
            if isinstance(payload, dict):
                # Defensive: if a Prompt-style dict ever lands here, prefer
                # its "answer" field; otherwise fall back to JSON.
                text = payload.get("answer") or _stringify_context(payload)
            elif isinstance(payload, list):
                text = "\n".join(str(x) for x in payload if x is not None)
            else:
                text = _stringify_context(payload)
            if text:
                texts.append(text)
        elif src == "select_document":
            doc = data.get("selected_doc_text") or ""
            if doc:
                texts.append(doc)
        elif src == "workflow_documents":
            for dt in data.get("doc_texts") or []:
                if dt:
                    texts.append(dt)
    return texts


# ---------------------------------------------------------------------------
# LLM helper functions (sync, for nodes)
# ---------------------------------------------------------------------------

def llm_chat_model(model: str, prompt: str, data=None, progress_callback=None,
                   include_next_step: bool = True, system_config_doc: dict | None = None,
                   usage_acc: UsageAccumulator | None = None):
    """Run a chat prompt via LLM. Sync context."""
    if data is None or data == "":
        data_block = "(No data provided.)"
    elif isinstance(data, str):
        data_block = data
    else:
        try:
            data_block = json.dumps(data, indent=2, default=str)
        except (TypeError, ValueError):
            data_block = str(data)

    output_prompt = (
        "You are completing one step of a multi-step workflow. Answer the "
        "INSTRUCTION below using ONLY the CONTEXT block, which is the output "
        "of the previous step. Do not draw on outside knowledge or invent "
        "details that are not present in the CONTEXT. If the CONTEXT does not "
        "contain what the instruction needs, say so explicitly rather than "
        "guessing.\n\n"
        "Format your answer as clean markdown for a web chat UI. Output only "
        "the markdown — no preamble, no code fences around the whole reply.\n\n"
        f"INSTRUCTION:\n{prompt}\n\n"
        f"CONTEXT:\n{data_block}"
    )
    chat_agent = create_chat_agent(model, system_config_doc=system_config_doc)
    result = chat_agent.run_sync(output_prompt)
    if usage_acc:
        usage_acc.record(result)
    output = result.output
    if progress_callback:
        progress_callback(output)
    return output


def data_extraction_model(model: str, keys: list[str], doc_texts: list[str] | None = None,
                          full_text: str | None = None, system_config_doc: dict | None = None,
                          usage_acc: UsageAccumulator | None = None,
                          field_metadata: list[dict] | None = None):
    """Run extraction and return {raw, formatted}. Sync context."""
    engine = ExtractionEngine(system_config_doc=system_config_doc)
    output = engine.extract(
        extract_keys=keys,
        model=model,
        full_text=full_text,
        doc_texts=doc_texts,
        field_metadata=field_metadata,
    )
    if usage_acc:
        usage_acc.add(engine.tokens_in, engine.tokens_out)
    formatted_output = format_extraction_results(output)
    return {"raw": output, "formatted": formatted_output}


def format_model(model: str, formatting_prompt: str, text, system_config_doc: dict | None = None,
                 usage_acc: UsageAccumulator | None = None):
    """Format text via LLM. Returns (prompt, formatted_text)."""
    system_prompt = (
        "You are a document formatter. You will receive a formatting instruction and "
        "source text. Your ONLY job is to reformat the source text exactly as the "
        "instruction says. Follow the instruction literally.\n"
        "RULES:\n"
        "- The formatting instruction is ABSOLUTE. If it says poem, output a poem. "
        "If it says bullet list, output a bullet list. Do not second-guess it.\n"
        "- Output clean markdown. Do NOT wrap your response in code fences.\n"
        "- Never output raw JSON."
    )
    prompt = (
        f"FORMATTING INSTRUCTION:\n{formatting_prompt}\n\n"
        f"---\n\n"
        f"SOURCE TEXT:\n{text}"
    )
    chat_agent = create_chat_agent(model, system_prompt=system_prompt, system_config_doc=system_config_doc)
    response = chat_agent.run_sync(prompt)
    if usage_acc:
        usage_acc.record(response)
    output = response.output
    if output is None:
        return None, None
    return prompt, output


# ---------------------------------------------------------------------------
# Node base classes
# ---------------------------------------------------------------------------

class Node:
    def __init__(self, name: str) -> None:
        self.name = name
        self.inputs = {}
        self.outputs = {}
        self.tasks = []
        self.progress_reporter = None
        self._sys_cfg: dict | None = None
        self._usage_acc: UsageAccumulator | None = None

    def process(self, inputs) -> NoReturn:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"

    def report_progress(self, detail=None, preview=None):
        if self.progress_reporter:
            self.progress_reporter(detail, preview)

    def _apply_post_process(self, result: dict) -> dict:
        """Apply post_process_prompt if configured in task data."""
        post_prompt = getattr(self, "data", {}).get("post_process_prompt") if hasattr(self, "data") else None
        if not post_prompt or not result.get("output"):
            return result
        self.report_progress("Post-processing output")
        processed = llm_chat_model(
            model=getattr(self, "data", {}).get("model"),
            prompt=post_prompt,
            data=result["output"],
            include_next_step=False,
            system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )
        result["output"] = processed
        return result


class MultiTaskNode(Node):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.tasks = []
        self.max_workers = multiprocessing.cpu_count()

    def add_task(self, task) -> None:
        self.tasks.append(task)

    def add_tasks(self, tasks) -> None:
        self.tasks.extend(tasks)

    def process_task(self, task):
        result = task.process(task.inputs)
        return task._apply_post_process(result)

    def process(self, inputs):
        import contextvars
        from copy import deepcopy

        for task in self.tasks:
            task.inputs = deepcopy(inputs)
        # Run each node within a copy of the current context so contextvars set
        # by the caller (notably the LLM metering scope) propagate into the
        # worker threads — ThreadPoolExecutor does not copy contextvars itself.
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            task_futures = [
                executor.submit(contextvars.copy_context().run, self.process_task, task)
                for task in self.tasks
            ]
            results = [future.result() for future in as_completed(task_futures)]

        collected = []
        task_step_name = self.name
        for result in results:
            if result.get("_approval_pause"):
                return result
            result_output = result.get("output")
            if result_output is None:
                continue
            elif isinstance(result_output, list):
                collected.extend(result_output)
            else:
                collected.append(result_output)
            # Preserve the underlying task step_name for downstream routing
            if result.get("step_name"):
                task_step_name = result["step_name"]

        # Unwrap single-element lists for cleaner downstream data flow
        final_output = collected[0] if len(collected) == 1 else collected

        return {"input": inputs.get("input"), "output": final_output, "step_name": task_step_name}


# ---------------------------------------------------------------------------
# Concrete nodes
# ---------------------------------------------------------------------------

class DocumentNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("Document")
        self.doc_uuids = data.get("doc_uuids", [])

    def process(self, inputs=None):
        return {"step_name": self.name, "output": self.doc_uuids, "input": None}


class ExtractionNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("Extraction")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        keys = self.data.get("searchphrases", [])
        if not keys:
            keys = self.data.get("keys", [])
        if not keys:
            raw = self.data.get("extractions", [])
            if isinstance(raw, list):
                keys = [str(k).strip() for k in raw if str(k).strip()]
            elif isinstance(raw, str) and raw.strip():
                keys = [s.strip() for s in raw.split(",") if s.strip()]

        prev_step_name = inputs.get("step_name")

        task_label = self.data.get("name")
        self.report_progress(f"Running {task_label}" if task_label else "Extraction running")

        sources = _resolve_input_sources(self.data, prev_step_name)
        texts = _build_extraction_texts(self.data, inputs, sources)

        # Use `doc_texts` whenever the user picked a doc-list source or has
        # more than one text; otherwise pass a single string via `full_text`.
        # Functionally equivalent in the engine, but preserves call-shape
        # expectations from older callers.
        kwargs: dict = {"system_config_doc": self._sys_cfg, "usage_acc": self._usage_acc}
        if "workflow_documents" in sources or len(texts) > 1:
            kwargs["doc_texts"] = texts
        elif texts:
            kwargs["full_text"] = texts[0]

        # Carry per-field validation / optional designations resolved from the
        # saved set (see workflow_tasks resolution) so enum and optional rules
        # are honored at extraction time.
        field_metadata = self.data.get("field_metadata")
        if field_metadata:
            kwargs["field_metadata"] = field_metadata

        extraction_response = data_extraction_model(self.model, keys, **kwargs)

        raw_output = extraction_response.get("raw") if isinstance(extraction_response, dict) else extraction_response
        formatted_output = extraction_response.get("formatted") if isinstance(extraction_response, dict) else extraction_response

        # Label output with the custom task name when set
        if task_label:
            if isinstance(raw_output, list):
                for entity in raw_output:
                    if isinstance(entity, dict):
                        entity["task_name"] = task_label
            if isinstance(formatted_output, str):
                formatted_output = f"### {task_label}\n{formatted_output}"

        return {
            "output": raw_output,
            "formatted_output": formatted_output,
            "input": inputs.get("output"),
            "step_name": self.name,
        }


class PromptNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("Prompt")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        prompt = self.data.get("prompt", "Enter prompt")
        prev_step_name = inputs.get("step_name")
        self.report_progress(f"Prompt: {prompt}")

        sources = _resolve_input_sources(self.data, prev_step_name)
        context = _build_combined_context(self.data, inputs, sources)

        chat_response = llm_chat_model(
            model=self.model, prompt=prompt, data=context,
            include_next_step=False, system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )

        return {"output": chat_response, "input": prompt, "step_name": self.name}


class FormatNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("Formatter")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        formatting_prompt = self.data.get("format_template") or self.data.get("prompt", "")
        prev_step_name = inputs.get("step_name")
        self.report_progress(f"Formatter: {formatting_prompt}")

        sources = _resolve_input_sources(self.data, prev_step_name)
        text = _build_combined_context(self.data, inputs, sources)

        _, output = format_model(self.model, formatting_prompt, text, system_config_doc=self._sys_cfg,
                                 usage_acc=self._usage_acc)
        return {"output": output, "input": formatting_prompt, "step_name": self.name}


class WebsiteNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("AddWebsite")
        self.data = data

    def process(self, inputs):
        url = self.data.get("url", "")
        if not url:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        from app.services.web_fetcher import fetch_url_sync

        self.report_progress(f"Fetching {url}")
        try:
            result = fetch_url_sync(url)
            text = result.text
        except ValueError as e:
            text = f"Blocked URL: {e}"
        except httpx.HTTPStatusError as e:
            text = f"HTTP error fetching {url}: {e.response.status_code}"
        except httpx.RequestError as e:
            text = f"Request error fetching {url}: {e}"
        return {"output": text, "input": inputs.get("output"), "step_name": self.name}


class AddDocumentNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("AddDocument")
        self.data = data

    def process(self, inputs):
        doc_texts = self.data.get("doc_texts", [])
        text = "\n".join(doc_texts) if doc_texts else ""
        self.report_progress("Adding document text")
        return {"output": text, "input": inputs.get("output"), "step_name": self.name}


class DescribeImageNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("DescribeImage")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        image_url = self.data.get("image_url", "")
        prompt = self.data.get("prompt", "Describe this image in detail.")
        self.report_progress(f"Describing image: {image_url}")
        full_prompt = f"Describe this image: {image_url}\n\nAdditional instructions: {prompt}"
        response = llm_chat_model(
            model=self.model, prompt=full_prompt, data=inputs.get("output"),
            include_next_step=False, system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )
        return {"output": response, "input": inputs.get("output"), "step_name": self.name}


class CodeExecutionNode(Node):
    """Execute user-provided Python code in a restricted sandbox.

    WARNING: The sandbox restricts builtins but does NOT provide full isolation.
    Code runs in a daemon thread with a timeout. Do not rely on this for
    untrusted input in high-security contexts.
    """

    CODE_TIMEOUT_SECONDS = 10

    def __init__(self, data: dict) -> None:
        super().__init__("CodeNode")
        self.data = data

    def process(self, inputs):
        code = self.data.get("code", "")
        if not code:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}
        self.report_progress("Running code")

        from app.utils.code_sandbox import validate_sandbox_code

        try:
            validate_sandbox_code(code)
        except (ValueError, SyntaxError) as e:
            return {
                "output": f"Code rejected: {e}",
                "input": inputs.get("output"),
                "step_name": self.name,
            }

        from app.utils.code_sandbox_runner import execute_sandboxed_code

        result = execute_sandboxed_code(
            code, inputs.get("output"), timeout=self.CODE_TIMEOUT_SECONDS
        )

        if result.get("timed_out"):
            return {
                "output": f"Code execution timed out after {self.CODE_TIMEOUT_SECONDS} seconds",
                "input": inputs.get("output"),
                "step_name": self.name,
            }

        if "error" in result:
            return {
                "output": f"Code execution error: {result['error']}",
                "input": inputs.get("output"),
                "step_name": self.name,
            }

        return {
            "output": result.get("result"),
            "input": inputs.get("output"),
            "step_name": self.name,
        }


class CrawlerNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("CrawlerNode")
        self.data = data

    def process(self, inputs):
        start_url = self.data.get("start_url", "")
        max_pages = int(self.data.get("max_pages", 5))
        allowed_domains = self.data.get("allowed_domains", "")
        if not start_url:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        from app.utils.url_validation import validate_outbound_url

        try:
            validate_outbound_url(start_url)
        except ValueError as e:
            return {"output": f"Blocked URL: {e}", "input": inputs.get("output"), "step_name": self.name}

        self.report_progress(f"Crawling from {start_url}")
        parsed_start = urlparse(start_url)
        allowed = {d.strip() for d in allowed_domains.split(",") if d.strip()} if allowed_domains else {parsed_start.netloc}

        visited = set()
        to_visit = [start_url]
        all_text = []

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            while to_visit and len(visited) < max_pages:
                url = to_visit.pop(0)
                if url in visited:
                    continue
                visited.add(url)
                self.report_progress(f"Crawling page {len(visited)}/{max_pages}: {url}")
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except Exception:
                    continue
                text = _extract_text_from_html(resp.text)
                all_text.append(f"--- {url} ---\n{text}")
                soup = BeautifulSoup(resp.text, "html.parser")
                for link in soup.find_all("a", href=True):
                    abs_url = urljoin(url, link["href"])
                    parsed = urlparse(abs_url)
                    if parsed.netloc in allowed and abs_url not in visited:
                        try:
                            validate_outbound_url(abs_url)
                            to_visit.append(abs_url)
                        except ValueError:
                            continue

        return {"output": "\n\n".join(all_text), "input": inputs.get("output"), "step_name": self.name}


class ResearchNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("ResearchNode")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        question = self.data.get("question", "")
        prev_step_name = inputs.get("step_name")

        sources = _resolve_input_sources(self.data, prev_step_name)
        input_data = _build_combined_context(self.data, inputs, sources)

        self.report_progress("Pass 1: Analyzing data")

        analysis_prompt = (
            f"Analyze the following data and generate structured findings related to this question: {question}\n\n"
            "Provide your analysis as a structured list of key findings, evidence, and observations."
        )
        findings = llm_chat_model(
            model=self.model, prompt=analysis_prompt, data=input_data,
            include_next_step=False, system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )

        self.report_progress("Pass 2: Synthesizing report")
        synthesis_prompt = (
            f"Based on the following analysis findings, create a comprehensive research report about: {question}\n\n"
            "Structure the report with clear sections: Executive Summary, Key Findings, "
            "Detailed Analysis, and Conclusions.\n\n"
            f"Findings:\n{findings}"
        )
        report = llm_chat_model(
            model=self.model, prompt=synthesis_prompt, data=input_data,
            include_next_step=False, system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )
        return {"output": report, "input": inputs.get("output"), "step_name": self.name}


def _open_sync_db():
    """Open a pymongo handle for in-node credential lookups (sync context)."""
    from app.tasks import get_sync_db

    return get_sync_db()


# Header names whose values are secrets and must never appear in a debug
# preview, a log line, or the step output. Matched as case-insensitive
# substrings so e.g. "X-Api-Key" and "Proxy-Authorization" are both caught.
_SENSITIVE_HEADER_HINTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "api-key",
    "apikey",
    "password",
    "auth",
)

_REQUEST_BODY_PREVIEW_LIMIT = 4000


def _redact_headers(headers: dict) -> dict:
    """Copy *headers*, masking the values of any secret-bearing header."""
    redacted: dict[str, str] = {}
    for k, v in headers.items():
        if any(hint in str(k).lower() for hint in _SENSITIVE_HEADER_HINTS):
            redacted[str(k)] = "<redacted>"
        else:
            redacted[str(k)] = str(v)
    return redacted


def _build_request_preview(method: str, url: str, headers: dict, body) -> dict:
    """A safe, structured snapshot of the request the API node is about to send.

    Used for debugging — surfaced in the step output and logged — so authors can
    see exactly what went on the wire (the recurring pain behind API-node
    tickets). Secret header values are redacted; the body is the literal text
    that will be transmitted, truncated if very large.
    """
    if isinstance(body, (dict, list)):
        body_text = json.dumps(body)
    elif isinstance(body, str):
        body_text = body
    else:
        body_text = ""
    byte_len = len(body_text.encode("utf-8"))
    if len(body_text) > _REQUEST_BODY_PREVIEW_LIMIT:
        body_text = body_text[:_REQUEST_BODY_PREVIEW_LIMIT] + "…(truncated)"
    return {
        "method": method,
        "url": url,
        "headers": _redact_headers(headers),
        "body": body_text,
        "body_bytes": byte_len,
    }


def _format_request_preview(preview: dict) -> str:
    """Render a request preview as a readable block for inclusion in output."""
    lines = [f"{preview.get('method', '')} {preview.get('url', '')}".strip()]
    headers = preview.get("headers") or {}
    if headers:
        lines.append("Headers:")
        lines.extend(f"  {k}: {v}" for k, v in headers.items())
    else:
        lines.append("Headers: (none)")
    body = preview.get("body") or ""
    lines.append(f"Body ({preview.get('body_bytes', 0)} bytes):")
    lines.append(body if body else "(empty)")
    return "\n".join(lines)


class APICallNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("APINode")
        self.data = data

    def process(self, inputs):
        from app.utils import templating

        method = self.data.get("method", "GET").upper()
        auth_strategy = (self.data.get("auth_strategy") or "none").lower()
        credential_id = self.data.get("credential_id") or ""

        # Resolve {{ inputs.output }}-style placeholders against the previous
        # step's output so authors can reference upstream data instead of
        # pasting it in literally. URL and headers use raw-string substitution
        # (they sit inside already-quoted positions); the body is rendered
        # below with JSON-encoding semantics.
        try:
            url = templating.render(self.data.get("url", ""), inputs, json_encode=False)
            headers_raw = templating.render(
                self.data.get("headers", ""), inputs, json_encode=False
            )
        except templating.TemplateError as e:
            return {"output": str(e), "input": inputs.get("output"), "step_name": self.name}
        body_raw = self.data.get("body", "")
        if not url:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        from app.utils.url_validation import validate_outbound_url

        try:
            validate_outbound_url(url)
        except ValueError as e:
            return {"output": f"Blocked URL: {e}", "input": inputs.get("output"), "step_name": self.name}

        self.report_progress(f"{method} {url}")
        headers: dict[str, str] = {}
        if headers_raw:
            try:
                parsed = json.loads(headers_raw)
            except json.JSONDecodeError as e:
                return {
                    "output": (
                        f"Invalid Headers JSON: {e}. "
                        "Check for smart quotes or other invisible characters."
                    ),
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            if not isinstance(parsed, dict):
                return {
                    "output": (
                        "Invalid Headers JSON: expected an object like "
                        '{"x-api-key": "..."}'
                    ),
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            headers = {str(k): str(v) for k, v in parsed.items()}

        # Apply credential-based auth (overrides any conflicting header).
        if auth_strategy != "none":
            if not credential_id:
                return {
                    "output": f"API Node auth_strategy {auth_strategy!r} requires credential_id",
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            from app.services import credentials_service

            try:
                db = _open_sync_db()
                cred_doc = credentials_service.fetch_credential_sync(db, credential_id)
            except Exception as e:
                logger.exception("Credential lookup failed")
                return {
                    "output": f"Credential lookup failed: {e}",
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            if not cred_doc:
                return {
                    "output": f"Credential {credential_id!r} not found",
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            if cred_doc.get("type") != auth_strategy:
                return {
                    "output": (
                        f"Credential type {cred_doc.get('type')!r} does not match "
                        f"auth_strategy {auth_strategy!r}"
                    ),
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }
            try:
                credentials_service.apply_auth(credential_doc=cred_doc, headers=headers)
            except credentials_service.CredentialError as e:
                return {
                    "output": f"Auth setup failed: {e}",
                    "input": inputs.get("output"),
                    "step_name": self.name,
                }

        body = None
        body_is_json = False
        if method in ("POST", "PUT", "PATCH"):
            if body_raw and body_raw.strip():
                # Render {{ inputs.output }} placeholders with JSON-encoding so
                # an envelope like {"records": {{ inputs.output }}} stays valid
                # JSON whatever the upstream output's type is.
                try:
                    rendered_body = templating.render(body_raw, inputs, json_encode=True)
                except templating.TemplateError as e:
                    return {
                        "output": str(e),
                        "input": inputs.get("output"),
                        "step_name": self.name,
                    }
                try:
                    parsed = json.loads(rendered_body)
                except json.JSONDecodeError:
                    # Not JSON — send the literal text as-is.
                    body = rendered_body
                else:
                    # Objects/arrays go out via httpx's json= (which also sets
                    # Content-Type). Any other JSON type — a scalar or null —
                    # is still a body the author configured, so send its raw
                    # JSON text rather than silently transmitting zero bytes.
                    body = parsed if isinstance(parsed, (dict, list)) else rendered_body
                    body_is_json = True
            else:
                # Implicit passthrough: an empty body on a write request sends
                # the previous step's output as-is. This is what lets a
                # [generate] -> [POST] workflow store its result without the
                # author wiring up a template at all.
                upstream = inputs.get("output")
                if isinstance(upstream, (dict, list)):
                    body = upstream
                    body_is_json = True
                elif isinstance(upstream, str):
                    # Raw text — its type is unknown, so don't claim it's JSON.
                    body = upstream
                elif upstream is not None:
                    # Scalars (number/bool) — send a JSON literal as the body.
                    body = json.dumps(upstream)
                    body_is_json = True

        # When we're sending a JSON body, tag it as such so servers that route
        # on Content-Type (e.g. Flask's request.json, which 415s without it)
        # parse it. httpx only sets this automatically on the json= path, not
        # for JSON we send as a string (scalars/null) — and the author may not
        # have added the header themselves. Never override an explicit choice.
        if body_is_json and not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"

        # Snapshot exactly what we're about to send (secrets redacted). This is
        # attached to the step result so authors can inspect the request when
        # debugging — and embedded into the error output when it fails, since
        # that's when they most need to see it.
        request_preview = _build_request_preview(method, url, headers, body)
        logger.info(
            "APINode sending %s %s (%d body bytes)",
            method, url, request_preview["body_bytes"],
        )

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.request(method, url, headers=headers, json=body if isinstance(body, (dict, list)) else None, content=body if isinstance(body, str) else None)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return {
                "output": (
                    f"HTTP error: {e.response.status_code} {e.response.text[:500]}\n\n"
                    f"--- Request sent ---\n{_format_request_preview(request_preview)}"
                ),
                "input": inputs.get("output"),
                "step_name": self.name,
                "request": request_preview,
            }
        except httpx.RequestError as e:
            return {
                "output": (
                    f"Request error: {e}\n\n"
                    f"--- Request sent ---\n{_format_request_preview(request_preview)}"
                ),
                "input": inputs.get("output"),
                "step_name": self.name,
                "request": request_preview,
            }

        try:
            output = resp.json()
        except Exception:
            output = resp.text

        return {
            "output": output,
            "input": inputs.get("output"),
            "step_name": self.name,
            "request": request_preview,
        }


class DocumentRendererNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("DocumentRenderer")
        self.data = data

    def process(self, inputs):
        fmt = self.data.get("format", "md")
        filename = self.data.get("filename", "output")
        input_data = inputs.get("output", "")
        self.report_progress(f"Rendering as {fmt}")

        text = input_data if isinstance(input_data, str) else json.dumps(input_data, indent=2)
        ext = "md" if fmt == "md" else "txt"
        full_filename = f"{filename}.{ext}"
        data_b64 = base64.b64encode(text.encode("utf-8")).decode("utf-8")

        return {
            "output": {"type": "file_download", "data_b64": data_b64, "file_type": ext, "filename": full_filename},
            "input": inputs.get("output"),
            "step_name": self.name,
        }


class FormFillerNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("FormFiller")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        template = self.data.get("template", "")
        prev_step_name = inputs.get("step_name")

        sources = _resolve_input_sources(self.data, prev_step_name)
        input_data = _build_combined_context(self.data, inputs, sources)

        self.report_progress("Filling template")

        prompt = (
            f"Fill all {{{{placeholders}}}} in the following template using the provided data. "
            f"Return only the filled template with no extra commentary.\n\n"
            f"Template:\n{template}"
        )
        filled = llm_chat_model(
            model=self.model, prompt=prompt, data=input_data,
            include_next_step=False, system_config_doc=self._sys_cfg,
            usage_acc=self._usage_acc,
        )
        return {"output": filled, "input": inputs.get("output"), "step_name": self.name}


class DataExportNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("DataExport")
        self.data = data

    def process(self, inputs):
        fmt = self.data.get("format", "json")
        filename = self.data.get("filename", "export")
        input_data = inputs.get("output", "")
        self.report_progress(f"Exporting as {fmt}")

        if fmt == "csv":
            buf = io.StringIO()
            if isinstance(input_data, list) and input_data and isinstance(input_data[0], dict):
                headers = list(input_data[0].keys())
                writer = csv.DictWriter(buf, fieldnames=headers)
                writer.writeheader()
                for row in input_data:
                    writer.writerow({k: str(v) for k, v in row.items()})
            elif isinstance(input_data, dict):
                headers = list(input_data.keys())
                writer = csv.DictWriter(buf, fieldnames=headers)
                writer.writeheader()
                writer.writerow({k: str(v) for k, v in input_data.items()})
            else:
                buf.write(str(input_data))
            content = buf.getvalue()
            ext = "csv"
        else:
            content = json.dumps(input_data, indent=2) if not isinstance(input_data, str) else input_data
            ext = "json"

        full_filename = f"{filename}.{ext}"
        data_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        return {
            "output": {"type": "file_download", "data_b64": data_b64, "file_type": ext, "filename": full_filename},
            "input": inputs.get("output"),
            "step_name": self.name,
        }


class PackageBuilderNode(Node):
    def __init__(self, data: dict) -> None:
        super().__init__("PackageBuilder")
        self.data = data

    def process(self, inputs):
        package_name = self.data.get("package_name", "package")
        input_data = inputs.get("output", "")
        self.report_progress("Building package")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            json_content = json.dumps(input_data, indent=2) if not isinstance(input_data, str) else input_data
            zf.writestr("output.json", json_content)
            text_content = input_data if isinstance(input_data, str) else json.dumps(input_data, indent=2)
            zf.writestr("output.txt", text_content)
        buf.seek(0)

        full_filename = f"{package_name}.zip"
        data_b64 = base64.b64encode(buf.read()).decode("utf-8")
        return {
            "output": {"type": "file_download", "data_b64": data_b64, "file_type": "zip", "filename": full_filename},
            "input": inputs.get("output"),
            "step_name": self.name,
        }


class ApprovalNode(Node):
    """Workflow step that pauses execution for human review.

    Configuration (`data`):
      review_instructions: str — text shown to the reviewer.
      assignee_role: "specific_users" | "workflow_owner" | "team_admins"
      assigned_to_user_ids: list[str] — used when assignee_role == specific_users.
      sla_days: int | None — days from pause until the timeout_action fires.
      timeout_action: "none" | "approve" | "reject" | "escalate"
      escalation_user_ids: list[str] — used when timeout_action == escalate.

    The node emits a sentinel dict with `_approval_pause: True`. The engine's
    execute() loop returns early when it sees that, and the workflow Celery
    task persists an ApprovalRequest from the sentinel payload.
    """

    def __init__(self, data: dict) -> None:
        super().__init__("Approval")
        self.data = data

    def process(self, inputs):
        review_instructions = self.data.get("review_instructions", "Please review the workflow output.")
        return {
            "output": inputs.get("output"),
            "input": inputs.get("output"),
            "step_name": self.name,
            "_approval_pause": True,
            "_review_instructions": review_instructions,
            "_assignee_role": self.data.get("assignee_role", "specific_users"),
            "_assigned_to_user_ids": self.data.get("assigned_to_user_ids", []),
            "_sla_days": self.data.get("sla_days"),
            "_timeout_action": self.data.get("timeout_action", "none"),
            "_escalation_user_ids": self.data.get("escalation_user_ids", []),
            "_data_for_review": inputs.get("output"),
        }


class BrowserAutomationNode(Node):
    """Workflow step that drives a Chrome extension browser session."""

    def __init__(self, data: dict) -> None:
        super().__init__("BrowserAutomation")
        self.data = data

    def process(self, inputs):
        from app.services.browser_automation import BrowserAutomationService

        service = BrowserAutomationService.get_instance()
        user_id = self.data.get("user_id", "")
        allowed_domains = self.data.get("allowed_domains", [])
        initial_url = self.data.get("initial_url")
        actions = self.data.get("actions", [])
        smart_instruction = self.data.get("smart_instruction")
        model = self.data.get("model", "gpt-4")

        self.report_progress("Starting browser session")

        session = service.create_session(user_id, "", allowed_domains)
        session_id = session.session_id

        try:
            service.start_session(session_id, initial_url=initial_url)

            results = []

            if smart_instruction:
                result = service.execute_smart_action(session_id, smart_instruction, model=model)
                results.append(result)
            else:
                for action in actions:
                    self.report_progress(f"Executing: {action.get('type', 'action')}")
                    result = service.execute_action_with_stack(session_id, action)
                    results.append(result)

            return {
                "output": results[-1] if results else None,
                "all_results": results,
                "session_id": session_id,
                "step_name": self.name,
            }

        except Exception as e:
            return {
                "output": f"Browser automation error: {e}",
                "error": str(e),
                "session_id": session_id,
                "step_name": self.name,
            }
        finally:
            service.end_session(session_id)


class KnowledgeBaseQueryNode(Node):
    """Workflow step that queries a knowledge base and returns matching chunks as context."""

    def __init__(self, data: dict) -> None:
        super().__init__("KnowledgeBaseQuery")
        self.data = data

    def process(self, inputs):
        from app.services.document_manager import DocumentManager

        kb_uuid = self.data.get("kb_uuid", "").strip()
        query = self.data.get("query", "").strip()
        k = int(self.data.get("k", 8))

        if not kb_uuid:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        if not query:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        self.report_progress("Querying knowledge base…")

        dm = DocumentManager()
        results = dm.query_kb(kb_uuid, query, k=k)

        if not results:
            return {"output": "", "input": inputs.get("output"), "step_name": self.name}

        # Format as plain text context block so downstream LLM steps can use it naturally
        parts = []
        sources: list[dict] = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata") or {}
            source_name = meta.get("source_name", "Unknown source")
            page = meta.get("page")
            sheet = meta.get("sheet")
            label = source_name
            if isinstance(page, int):
                label = f"{source_name} · p. {page}"
            elif isinstance(sheet, str) and sheet:
                label = f"{source_name} · {sheet}"
            parts.append(f"[{i}] {label}\n{r['content']}")
            sources.append({
                "document_id": meta.get("source_id"),
                "document_title": source_name,
                "page": page if isinstance(page, int) else None,
                "sheet": sheet if isinstance(sheet, str) else None,
                "chunk_id": r.get("chunk_id"),
                "score": r.get("score"),
                "content_preview": (r.get("content") or "")[:240],
            })

        output = "\n\n---\n\n".join(parts)
        return {
            "output": output,
            "input": inputs.get("output"),
            "step_name": self.name,
            "retrieved_sources": sources,
        }


# ---------------------------------------------------------------------------
# Workflow Engine
# ---------------------------------------------------------------------------

class WorkflowCancelled(Exception):
    """Raised inside execute() when a user-requested cancel is detected between
    steps. Callers should treat this as a clean terminal stop (status
    ``canceled``), not an error, and must not retry the task."""


class WorkflowEngine:
    def __init__(self) -> None:
        self.nodes: list[Node] = []
        self.connections = []
        self.graph = graphlib.TopologicalSorter()
        self.usage = UsageAccumulator()

    def add_node(self, node: Node) -> None:
        self.graph.add(node)

    def connect(self, from_node: Node, to_node: Node) -> None:
        self.graph.add(from_node, to_node)

    def get_topological_order(self) -> list[Node]:
        return list(reversed(tuple(self.graph.static_order())))

    def execute(self, workflow_result_updater=None, start_index=0, initial_output=None,
                should_cancel=None):
        """Execute workflow. Returns (final_output, step_data_list).

        Args:
            workflow_result_updater: Optional callable(update_dict) for progress.
            start_index: Index to start execution from (for resumption after approval).
            initial_output: Output to feed into the first node when resuming.
            should_cancel: Optional callable() -> bool, polled before each step.
                When it returns True the run is aborted with WorkflowCancelled.
                This is the cooperative backstop for the between-steps case; an
                in-flight step is interrupted out-of-band via Celery revocation.
        """
        data = []
        nodes = self.get_topological_order()

        latest_output = initial_output
        for idx, node in enumerate(nodes):
            # Skip already-executed nodes when resuming
            if idx < start_index:
                continue

            # Cooperative cancellation: bail before starting the next step if the
            # user requested a stop while we were between steps.
            if should_cancel is not None and should_cancel():
                raise WorkflowCancelled()

            if workflow_result_updater:
                workflow_result_updater({
                    "current_step_name": node.name,
                    "current_step_detail": f"Starting {node.name}",
                })

            if idx == 0 and latest_output is None:
                output = node.process({})
            else:
                if isinstance(node, MultiTaskNode):
                    for task in node.tasks:
                        task.progress_reporter = (
                            lambda detail=None, preview=None, step=node.name:
                                workflow_result_updater({
                                    "current_step_name": step,
                                    "current_step_detail": detail,
                                    "current_step_preview": preview,
                                }) if workflow_result_updater else None
                        )
                output = node.process(latest_output or {})

            latest_output = output

            # Check for approval pause signal
            if latest_output and latest_output.get("_approval_pause"):
                return latest_output, data

            if workflow_result_updater:
                step_name = sanitize_step_name(node.name)
                workflow_result_updater({
                    f"steps_output.{step_name}": output,
                    "num_steps_completed": idx,
                })

            entry = {
                "name": node.name,
                "output": latest_output.get("output"),
                "input": latest_output.get("input"),
            }
            sources = latest_output.get("retrieved_sources")
            if isinstance(sources, list) and sources:
                entry["retrieved_sources"] = sources
            data.append(entry)

        if latest_output is None:
            return None, data

        display_value = latest_output.get("formatted_output") or latest_output.get("output")
        final_value = self._format_final_output(display_value)
        return final_value, data

    def _format_final_output(self, value):
        if value is None:
            return ""
        if isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], dict):
                return self._format_final_output(value[0])
            formatted = [
                self._format_final_output(item) if isinstance(item, (list, dict))
                else str(item)
                for item in value
            ]
            formatted = [f for f in formatted if f]
            if len(formatted) <= 1:
                return formatted[0] if formatted else ""
            blocks = []
            for i, item in enumerate(formatted, start=1):
                if isinstance(item, str) and item.lstrip().startswith("#"):
                    blocks.append(item)
                else:
                    blocks.append(f"### Result {i}\n{item}")
            return "\n\n".join(blocks)
        if isinstance(value, dict):
            if value.get("type") == "file_download":
                return value
            try:
                return json.dumps(value, indent=2)
            except Exception:
                return str(value)
        return str(value)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_workflow_engine(
    steps_data: list[dict],
    model: str,
    user_id: str | None = None,
    system_config_doc: dict | None = None,
    allow_code_execution: bool = False,
) -> WorkflowEngine:
    """Build a WorkflowEngine from step data dicts.

    Args:
        steps_data: List of step dicts, each with 'name', 'tasks' (list of task dicts), 'data'.
                    First step should be 'Document' trigger with 'doc_uuids'.
        model: LLM model name.
        user_id: User ID for extraction nodes.
        system_config_doc: Pre-fetched SystemConfig as dict.
        allow_code_execution: If False, CodeNode tasks are rejected. Only admins should set True.
    """
    engine = WorkflowEngine()
    nodes = []

    for idx, step in enumerate(steps_data):
        step_name = step.get("name", "")
        step_data = step.get("data", {})

        if step_name == "Document":
            node = DocumentNode(step_data)
            nodes.append(node)
        else:
            tasks = []
            for task in step.get("tasks", []):
                task_name = task.get("name", "")
                task_data = task.get("data", {})
                task_data["user_id"] = user_id
                task_data["model"] = task_data.get("model") or model

                if task_name == "Extraction":
                    n = ExtractionNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "Prompt":
                    n = PromptNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "Formatter":
                    n = FormatNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "AddWebsite":
                    n = WebsiteNode(data=task_data)
                    tasks.append(n)
                elif task_name == "AddDocument":
                    n = AddDocumentNode(data=task_data)
                    tasks.append(n)
                elif task_name == "DescribeImage":
                    n = DescribeImageNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "CodeNode":
                    if not allow_code_execution:
                        logger.warning("Code execution task rejected — user is not an admin")
                        continue
                    n = CodeExecutionNode(data=task_data)
                    tasks.append(n)
                elif task_name == "CrawlerNode":
                    n = CrawlerNode(data=task_data)
                    tasks.append(n)
                elif task_name == "ResearchNode":
                    n = ResearchNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "APINode":
                    n = APICallNode(data=task_data)
                    tasks.append(n)
                elif task_name == "DocumentRenderer":
                    n = DocumentRendererNode(data=task_data)
                    tasks.append(n)
                elif task_name == "FormFiller":
                    n = FormFillerNode(data=task_data)
                    n._sys_cfg = system_config_doc
                    tasks.append(n)
                elif task_name == "DataExport":
                    n = DataExportNode(data=task_data)
                    tasks.append(n)
                elif task_name == "PackageBuilder":
                    n = PackageBuilderNode(data=task_data)
                    tasks.append(n)
                elif task_name == "BrowserAutomation":
                    n = BrowserAutomationNode(data=task_data)
                    tasks.append(n)
                elif task_name == "KnowledgeBaseQuery":
                    n = KnowledgeBaseQueryNode(data=task_data)
                    tasks.append(n)
                elif task_name == "Approval":
                    n = ApprovalNode(data=task_data)
                    tasks.append(n)
                else:
                    logger.warning("Unknown task type '%s' in step '%s' — skipping", task_name, step_name)

            # Propagate usage accumulator to all task nodes
            for t in tasks:
                t._usage_acc = engine.usage

            node = MultiTaskNode(step_name)
            node.add_tasks(tasks)
            nodes.append(node)

        engine.add_node(node)

    # Connect sequentially
    for i in range(1, len(nodes)):
        engine.connect(nodes[i - 1], nodes[i])

    return engine
