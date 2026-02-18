#!/usr/bin/env python3

import graphlib
import json
import multiprocessing
import re
import uuid
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Thread
from typing import NoReturn

import chromadb
from chromadb.config import Settings
from devtools import debug
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from app import app
from app.celery_worker import celery_app
from app.models import (
    ActivityEvent,
    ActivityStatus,
    SearchSet,
    SmartDocument,
    Workflow,
    WorkflowResult,
    WorkflowStep,
)
from app.utilities.agents import create_chat_agent
from app.utilities.analytics_helper import activity_finish
from app.utilities.extraction_manager_nontyped import ExtractionManagerNonTyped
from app.utilities.chat_manager import ChatManager
from app.utilities.browser_automation import BrowserAutomationService

load_dotenv()


class WorkflowThread(Thread):
    def __init__(
        self,
        group=None,
        target=None,
        name=None,
        args=(),
        kwargs=None,
        verbose=None,
    ) -> None:
        if kwargs is None:
            kwargs = {}
        super().__init__(group, target, name, args, kwargs)
        self._return = None
        self._target = target
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        super().join(timeout)
        return self._return


def add_document_to_workflow_step(document, workflow_step):
    documents = workflow_step.data.get("documents", [])
    if document not in documents:
        documents.append(document)
        workflow_step.data["documents"] = documents
        workflow_step.save()
    return workflow_step


def remove_document_from_workflow_step(document, workflow_step):
    documents = workflow_step.data.get("documents", [])
    if document in documents:
        documents.remove(document)
        workflow_step.data["documents"] = documents
        workflow_step.save()
    return workflow_step


def resolve_fixed_documents(workflow):
    """Resolve fixed documents from workflow input_config to SmartDocument objects.

    Returns:
        List of SmartDocument objects (only those that still exist in the database)
    """
    fixed_entries = (workflow.input_config or {}).get('fixed_documents', [])
    docs = []
    for entry in fixed_entries:
        uuid = entry.get('uuid')
        if uuid:
            doc = SmartDocument.objects(uuid=uuid).first()
            if doc:
                docs.append(doc)
    return docs


def apply_input_config(data, inputs):
    """Apply task-level input_config to override the inputs for a task node.

    Args:
        data: The task's data dict (contains input_config)
        inputs: The default inputs from the previous step

    Returns:
        The (possibly overridden) inputs dict
    """
    input_config = data.get("input_config", {})
    source = input_config.get("source", "step_input")

    if source == "document":
        doc_uuid = input_config.get("document_uuid")
        if doc_uuid:
            return {"step_name": "Document", "output": [doc_uuid], "input": None}
    elif source == "workflow_documents":
        doc_uuids = data.get("_workflow_document_uuids", [])
        if doc_uuids:
            return {"step_name": "Document", "output": doc_uuids, "input": None}

    return inputs


def apply_output_postprocess(result, data, model):
    """Apply output post-processing if configured on a task node.

    Args:
        result: The task's output dict (contains 'output' key)
        data: The task's data dict (contains output_config)
        model: The LLM model to use for post-processing

    Returns:
        The (possibly post-processed) result dict
    """
    output_config = data.get("output_config", {})
    post_prompt = output_config.get("post_process_prompt", "")
    if post_prompt:
        result_text = result.get("output", "")
        if isinstance(result_text, dict):
            result_text = result_text.get("formatted_answer", "") or result_text.get("answer", "") or str(result_text)
        elif isinstance(result_text, list):
            result_text = "\n".join(str(x) for x in result_text)
        post_processed = llm_chat_model(
            model=model,
            docs=[],
            prompt=post_prompt,
            data=result_text,
            include_next_step=False,
        )
        result["output"] = post_processed
    return result


def format_llm_output(text: str) -> str:
    r"""Format raw LLM text output to clean up escape characters and extra whitespace.
    Returns clean text that can be safely placed in HTML elements on the frontend.

    Args:
        text (str): Raw LLM output text containing \n literals and extra whitespace

    Returns:
        str: Cleaned text string

    """

    debug(f"Formatting LLM output: {text}")
    # Replace explicit \n escapes with actual newlines
    text = text.replace("\n", "")
    text = text.strip('"')

    # Remove any extra/duplicate newlines
    text = "\n".join(line for line in text.splitlines() if line.strip())

    # Remove any whitespace from start/end
    return text.strip()


def llm_chat_model(
    model,
    prompt,
    data=None,
    docs=None,
    progress_callback=None,
    include_next_step=True,
):
    if docs is None:
        docs = []
    chat_manager = ChatManager()
    output = None
    debug(model)
    if len(docs) == 0:
        full_text = json.dumps(data)
        output_prompt = f"""Follow the instruction and output your answer as a nicely formatted markdown to display in a web interface chat bot. Only show the markdown output and add no text before it.\n\nInstruction: {prompt}\n\n {full_text}"""

        def _on_chunk(text):
            if progress_callback:
                progress_callback(text)

        output = chat_manager.stream_prompt(
            model=model,
            prompt=output_prompt,
            progress_callback=_on_chunk,
            include_next_step=include_next_step,
        )
        debug(f"Output from chat agent: {output}")

    else:
        output = chat_manager.ask_question_to_documents(
            model=model,
            root_path=app.root_path,
            documents=docs,
            question=prompt,
            include_next_step=include_next_step,
        )
        output = output.get("answer", "")
        debug(f"Output from chat agent: {output}")
        if progress_callback:
            progress_callback(output)
    return output


def data_extraction_model(
    model, keys, documents=None, full_text=None, progress_callback=None
):
    if documents is None:
        documents = []
    output = None
    extraction_manager = ExtractionManagerNonTyped()
    document_uuids = []
    for doc in documents:
        if doc is None:
            continue
        if isinstance(doc, str):
            document_uuids.append(doc)
        else:
            document_uuids.append(doc.uuid)
    output = extraction_manager.extract(
        keys, document_uuids, model, full_text=full_text
    )

    debug(output)
    formatted_output = format_extraction_results(output)
    extraction_payload = {
        "raw": output,
        "formatted": formatted_output,
    }
    if progress_callback:
        progress_callback(extraction_payload)
    return extraction_payload


def format_extraction_results(data):
    """
    Convert extraction JSON results into a markdown bullet list without invoking an LLM.
    """
    if data is None:
        return ""

    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return str(data)

    block_lines = []
    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            if len(items) > 1:
                block_lines.append(f"#### Result {idx}")
            for key, value in item.items():
                value_str = _stringify_extraction_value(value)
                block_lines.append(f"- **{key}**: {value_str}")
            block_lines.append("")  # spacing
        else:
            block_lines.append(f"- {item}")

    return "\n".join(line for line in block_lines if line is not None)


def _stringify_extraction_value(value):
    if value is None:
        return "N/A"
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify_extraction_value(v) for v in value if v is not None)
    if isinstance(value, dict):
        return json.dumps(value, indent=2)
    return str(value)


def format_model(model, formatting_prompt, text):
    system_prompt = """
Follow the instruction and output your answer as a nicely formatted markdown to display in a web interface chat bot.
CRITICAL:
- The formatted text should be a list of bullet points with the extracted data json data.
- The bullet points should be in a list format.
"""

    prompt = f"{system_prompt}\n\n Instruction: {formatting_prompt}\n\n {text}"
    chat_agent = create_chat_agent(model)
    response = chat_agent.run_sync(prompt)
    response = response.output

    debug(response)

    if response is None:
        return None, None
    # formatted text is between ```json\n and \n```
    format_spec_regex = r"```(.*?)\n(.*?)\n```"
    match = re.search(format_spec_regex, response, re.DOTALL)
    if match is not None:
        formatted_text = match.group(2)
        return prompt, formatted_text
    return prompt, response


class Node:
    def __init__(self, name) -> None:
        self.name = name
        self.inputs = {}
        self.outputs = {}
        self.tasks = []
        self.progress_reporter = None

    def process(self, inputs) -> NoReturn:
        raise NotImplementedError

    def __repr__(self) -> str:
        node_class = self.__class__.__name__
        return f"""{node_class}(name={self.name}, inputs={self.inputs}, outputs={self.outputs})"""

    def report_progress(self, detail=None, preview=None):
        if self.progress_reporter:
            self.progress_reporter(detail, preview)


class MultiTaskNode(Node):
    def __init__(self, name) -> None:
        super().__init__(name)
        self.tasks = []
        self.max_workers = multiprocessing.cpu_count()

    def add_task(self, task) -> None:
        self.tasks.append(task)

    def add_tasks(self, tasks) -> None:
        self.tasks.extend(tasks)

    def process_task(self, task):
        debug(task)
        return task.process(task.inputs)

    def process(self, inputs):
        for task in self.tasks:
            task.inputs = inputs
        debug(self.tasks)
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            task_futures = [
                executor.submit(self.process_task, task) for task in self.tasks
            ]

            results = []

            for future in as_completed(task_futures):
                results.append(future.result())

        # concatenate the results output
        output = {"input": inputs.get("input"), "output": [], "step_name": self.name}
        for result in results:
            debug(result)
            result_output = result.get("output", None)
            # add the step name to the output
            if result_output is None:
                continue
            elif isinstance(result_output, str):
                output["output"].append(result_output)
            elif isinstance(result_output, dict):
                # If output is a dict, append it as-is (don't extend with keys)
                output["output"].append(result_output)
            elif isinstance(result_output, list):
                # If output is a list, extend the output list
                output["output"].extend(result_output)
            else:
                # For other types, append them
                output["output"].append(result_output)

        debug(output)
        return output


class DocumentNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Document")
        self.docs = data.get("docs", [])
        self.attachments = []  # data.get("attachments", [])
        self.pdf_paths = []
        self.docs_uuids = []
        self.content = ""

        for doc in self.docs:
            if doc is None:
                continue
            self.docs_uuids.append(doc.uuid)

        debug(self.docs[0])
        debug(self.pdf_paths)
        debug(self.docs_uuids)

    def process(self, inputs=None):
        return {"step_name": self.name, "output": self.docs_uuids, "input": None}


class FormatNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Formatter")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        # Apply task-level input config override
        inputs = apply_input_config(self.data, inputs)

        formatting_prompt = self.data.get("prompt", "")

        data = inputs.get("output", None)
        prev_step_name = inputs.get("step_name", None)
        self.report_progress(f"Formatter: {formatting_prompt}")
        text = None
        if prev_step_name == "Prompt":
            text = data.get("formatted_answer", "") if isinstance(data, dict) else data
        if prev_step_name == "Document":
            docs_uuids = inputs.get("output", [])
            text = ""
            for doc in docs_uuids:
                doc = SmartDocument.objects(uuid=doc).first()
                text += doc.raw_text
        else:
            text = data

        prompt, output = format_model(self.model, formatting_prompt, text)
        result = {"output": output, "input": prompt, "step_name": self.name}
        return apply_output_postprocess(result, self.data, self.model)


class ExtractionNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Extraction")
        self.data = data
        self.user_id = data.get("user_id", "0")
        self.model = data.get("model")
        debug(self.data)
        debug(self.model)
        debug(self.user_id)

    def process(self, inputs):
        # Apply task-level input config override
        inputs = apply_input_config(self.data, inputs)

        data = self.data
        debug(data)
        keys = self.data.get("searchphrases", [])
        if len(keys) == 0:
            keys = data.get("keys", [])

        prev_step_name = inputs.get("step_name", None)

        debug("Extraction", inputs, keys, data)

        step_input = None
        docs_uuids = []
        extraction_response = None
        self.report_progress("Extraction running")

        def _on_progress(preview):
            if isinstance(preview, dict):
                preview_text = preview.get("formatted") or format_extraction_results(
                    preview.get("raw")
                )
            else:
                preview_text = preview
            self.report_progress("Extraction running", preview_text)

        if prev_step_name == "Document":
            docs_uuids = inputs.get("output", None)
            step_input = docs_uuids
            extraction_response = data_extraction_model(
                self.model,
                keys,
                docs_uuids,
                progress_callback=_on_progress,
            )
        elif prev_step_name == "Prompt":
            step_input = inputs.get("output", None)
            if isinstance(step_input, dict):
                step_input = step_input.get("answer")
            elif isinstance(step_input, list):
                step_input = "\n".join(step_input)
            extraction_response = data_extraction_model(
                self.model,
                keys,
                docs_uuids,
                full_text=step_input,
                progress_callback=_on_progress,
            )
        elif prev_step_name in {"Extraction", "Formatter"}:
            step_input = inputs.get("output", None)
            extraction_response = data_extraction_model(
                self.model,
                keys,
                docs_uuids,
                full_text=step_input,
                progress_callback=_on_progress,
            )

        # Return raw output for downstream steps to access structured data
        # But keep formatted output for display purposes
        raw_output = (
            extraction_response.get("raw")
            if isinstance(extraction_response, dict)
            else extraction_response
        )
        formatted_output = (
            extraction_response.get("formatted")
            if isinstance(extraction_response, dict)
            else extraction_response
        )

        result = {
            "output": raw_output,  # Raw structured data for variable interpolation
            "formatted_output": formatted_output,  # Formatted markdown for display
            "input": step_input,
            "step_name": self.name,
        }
        return apply_output_postprocess(result, self.data, self.model)



class BrowserAutomationNode(Node):
    """
    Node for browser automation within workflows.
    Executes web interactions via Chrome extension.
    """

    def __init__(self, data):
        super().__init__("BrowserAutomation")
        self.data = data
        self.model = data.get("model", "claude-sonnet-4-5")
        self.actions = data.get("actions", [])
        self.allowed_domains = data.get("allowed_domains", [])
        self.timeout_seconds = data.get("timeout_seconds", 300)
        self.user_id = data.get("user_id")
        self.workflow_result_id = data.get("workflow_result_id")

    def process(self, inputs):
        """
        Execute browser automation workflow.

        Flow:
        1. Create browser session
        2. Start session (open/attach to tab)
        3. Execute each action in sequence
        4. Handle user login pauses
        5. Extract and return data
        6. Clean up session
        """
        
        # If we are resuming from a user action (like login), inputs might contain state
        # But for now we assume linear execution or that the engine handles resume logic
        
        service = BrowserAutomationService.get_instance()

        # Create session
        session = service.create_session(
            user_id=self.user_id,
            workflow_result_id=self.workflow_result_id,
            allowed_domains=self.allowed_domains
        )

        try:
            # Start browser session
            self.report_progress("Connecting to browser extension...")
            service.start_session(session.session_id)

        # Execute actions sequentially
            extracted_data = {}
            for i, action in enumerate(self.actions):
                self.report_progress(
                    f"Step {i+1}/{len(self.actions)}: {action['type']}...",
                    preview=self._get_action_preview(action)
                )

                # Interpolate variables using both inputs and extracted_data
                # This allows referencing variables extracted by earlier actions in the same node

                # Handle different output formats from previous steps
                prev_output = inputs.get("output", {})

                if isinstance(prev_output, dict):
                    # Output is already a dict
                    output_dict = prev_output
                elif isinstance(prev_output, list) and len(prev_output) > 0:
                    # Output is a list - check if it contains dicts (common from extraction steps)
                    if isinstance(prev_output[0], dict):
                        # List of dicts - merge them all
                        output_dict = {}
                        for item in prev_output:
                            if isinstance(item, dict):
                                output_dict.update(item)
                    else:
                        # List of non-dict items - can't extract variables
                        output_dict = {}
                else:
                    output_dict = {}

                combined_inputs = {
                    "output": {**output_dict, **extracted_data},
                    "input": inputs.get("input"),
                    "step_name": inputs.get("step_name", self.name)
                }
                print(f"[BrowserAutomation] Before interpolation - action: {action}")
                print(f"[BrowserAutomation] Combined inputs: {combined_inputs}")
                interpolated_action = self._interpolate_variables(action, combined_inputs)
                print(f"[BrowserAutomation] After interpolation - action: {interpolated_action}")

                if interpolated_action.get('type') == 'assert':
                     result = service.execute_assertion(session.session_id, interpolated_action)
                     if not result['passed']:
                         # If assertion failed, we might want to stop or retry
                         # For now, following the plan: throw exception if configured to fail
                         if interpolated_action.get('on_failure', 'fail') == 'fail':
                              raise AssertionError(f"Step {i+1} failed: {result['message']}")
                else:
                    # Execute action using stack logic
                    result = self._execute_action(service, session, interpolated_action, inputs)

                # If the result contains extracted data, store it
                # This handles both explicit extract actions and smart actions that perform extraction
                if isinstance(result, dict) and "structured_data" in result:
                    print(f"[BrowserAutomationNode] Result contains structured_data: {result['structured_data']}")
                    extracted_data.update(result["structured_data"])
                elif action["type"] == "extract" and result:
                    # Legacy handling for extract actions that don't use structured_data wrapper
                    print(f"[BrowserAutomationNode] Extract action without wrapper, storing entire result: {result}")
                    extracted_data.update(result or {})
                
                # Store specific output if requested
                # Support both 'output_variable' (manual) and 'variable_name' (recorder)
                out_var = action.get('output_variable') or action.get('variable_name')
                
                if out_var and result:
                     val = result.get('structured_data', result)
                     # If the result is a dict containing the variable name (common in multi-field extract), unwrap it
                     if isinstance(val, dict) and out_var in val:
                         extracted_data[out_var] = val[out_var]
                     else:
                         extracted_data[out_var] = val

                # If login required, wait for user
                if action["type"] == "ensure_login":
                    self._wait_for_user_login(service, session, action)
                
                # If smart action
                if action["type"] == "smart_action":
                    # The service handles the LLM logic and execution
                    # We just pass the instruction
                    pass 

            # Clean up
            service.end_session(session.session_id, close_tab=False)

            # Return the raw extracted data without additional LLM summarization
            return {
                "output": extracted_data,
                "input": self._format_input(inputs),
                "step_name": self.name
            }

        except Exception as e:
            service.end_session(session.session_id, close_tab=False)
            # Re-raise or return error
            raise e

    def _execute_action(self, service, session, action, inputs):
        """Execute a single action and return results"""

        # Interpolate variables from previous steps
        action_with_values = self._interpolate_variables(action, inputs)

        if action_with_values["type"] == "smart_action":
            return service.execute_smart_action(
                session.session_id, 
                action_with_values["config"]["instruction"],
                model=self.model
            )

        return service.execute_action_with_stack(session.session_id, action_with_values)

    def _wait_for_user_login(self, service, session, action):
        """Pause execution and wait for user to complete login"""

        # Update workflow result with special status
        # Note: In a real async system, we would suspend execution here.
        # For this implementation, we are simulating the wait or assuming the service handles it.
        # Since we are in a thread/worker, blocking might be okay for short periods,
        # but for user interaction we need a better mechanism (suspend/resume).
        # For MVP, we will block and poll or rely on the service to block.
        
        self.report_progress(
            "Waiting for user login...",
            detail=action.get("instruction_to_user", "Please log in"),
            # In a real implementation, we'd pass a flag to the UI to show the button
            # requires_user_action=True 
        )

        # Block until login confirmed
        service.wait_for_user_login(
            session.session_id,
            action.get("detection_rules"),
            action.get("instruction_to_user")
        )
        
        # Wait for the session to become active again (user clicked "I'm logged in")
        import time
        while True:
            s = service.get_session(session.session_id)
            if s.state == SessionState.ACTIVE or s.state == SessionState.COMPLETED:
                break
            if s.state == SessionState.FAILED:
                raise Exception("Session failed during login wait")
            time.sleep(1)

    def _interpolate_variables(self, action, inputs):
        """Replace template variables like {{previous_step.field}} with actual values"""

        action_json = json.dumps(action)

        # Simple template replacement
        # Supports: {{previous_step.field_name}} or {{field_name}}
        pattern = r'\{\{([^}]+)\}\}'

        def replace_var(match):
            var_path = match.group(1).strip()
            # Log the variable being resolved
            print(f"[Variable Interpolation] Attempting to resolve: '{var_path}'")
            print(f"[Variable Interpolation] Full match: '{match.group(0)}'")

            # Split by first dot only to handle keys with dots/spaces in them
            if '.' in var_path:
                first_dot = var_path.index('.')
                parts = [var_path[:first_dot], var_path[first_dot+1:]]
            else:
                parts = [var_path]

            print(f"[Variable Interpolation] Parts after split: {parts}")

            # Try to find value in inputs
            # inputs usually has structure: {"output": ..., "input": ...} or is the output of prev step

            value = inputs

            # If inputs has "output" key (from previous node), use that as base
            if isinstance(inputs, dict) and "output" in inputs:
                # Check if we want the whole output or a field
                if len(parts) == 1 and parts[0] == "previous_step":
                    return str(inputs["output"])

                # Try to traverse
                current = inputs["output"]
                found = True
                for part in parts:
                    if part == "previous_step":
                        continue
                    if isinstance(current, dict):
                        # Try exact match first
                        if part in current:
                            current = current[part]
                        # Try case-insensitive match if exact fails
                        else:
                            # Create a mapping of lowercase keys to actual keys
                            key_map = {k.lower(): k for k in current.keys()}
                            lower_part = part.lower()
                            if lower_part in key_map:
                                actual_key = key_map[lower_part]
                                print(f"[Variable Interpolation] Case-insensitive match: '{part}' -> '{actual_key}'")
                                current = current[actual_key]
                            else:
                                # Log what keys ARE available for debugging
                                print(f"[Variable Interpolation] Key '{part}' not found. Available keys: {list(current.keys())}")
                                print(f"[Variable Interpolation] Available keys (repr): {[repr(k) for k in current.keys()]}")
                                found = False
                                break
                    else:
                        print(f"[Variable Interpolation] Expected dict but got {type(current)} when looking for '{part}'")
                        found = False
                        break

                if found:
                    return str(current)

            # Log when variable can't be resolved
            print(f"[Variable Interpolation] Could not resolve variable: {var_path}")
            print(f"[Variable Interpolation] Input structure: {inputs}")
            return match.group(0)

        interpolated = re.sub(pattern, replace_var, action_json)
        return json.loads(interpolated)
        
    def _get_action_preview(self, action):
        return f"Action: {action['type']}"

    def _format_input(self, inputs):
        return str(inputs)


class PromptNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Prompt")
        self.data = data
        self.user_id = data.get("user_id", "0")
        self.model = data.get("model")

    def process(self, inputs):
        # Apply task-level input config override
        inputs = apply_input_config(self.data, inputs)

        data = self.data
        prompt = data.get("prompt", "Enter prompt")
        print(f"INPUTS ARE {inputs}")

        prev_step_name = inputs.get("step_name", None)
        debug("Prompt", inputs, prompt)
        chat_response = None
        self.report_progress(f"Prompt: {prompt}")

        def _on_stream_update(preview):
            self.report_progress(f"Prompt: {prompt}", preview)

        if prev_step_name == "Document":
            docs_uuids = inputs.get("output", None)
            docs = []
            for doc_uuid in docs_uuids:
                doc = SmartDocument.objects(uuid=doc_uuid).first()
                if doc is not None:
                    docs.append(doc)

            chat_response = llm_chat_model(
                model=self.model,
                docs=docs,
                prompt=prompt,
                include_next_step=False,
                progress_callback=_on_stream_update,
            )
        else:
            data = inputs.get("output", None)

            chat_response = llm_chat_model(
                model=self.model,
                docs=[],
                prompt=prompt,
                data=data,
                progress_callback=_on_stream_update,
                include_next_step=False,
            )
        result = {"output": chat_response, "input": prompt, "step_name": self.name}
        return apply_output_postprocess(result, self.data, self.model)



class DocumentRendererNode(Node):
    def __init__(self, data):
        super().__init__("DocumentRenderer")
        self.data = data
        self.config = data.get("config", {})
        self.format = self.config.get("format", "pdf")
        self.folder_uuid = self.config.get("folder_uuid", None)
        self.auto_download = self.config.get("auto_download", False)

    def process(self, inputs):
        self.report_progress(f"Rendering document to {self.format.upper()}...")
        
        content = inputs.get("output", "")
        # Handle dict output (e.g. from template or extraction)
        if isinstance(content, dict):
            content = json.dumps(content, indent=2)
        elif isinstance(content, list):
            content = "\n".join([str(c) for c in content])
        
        output_data = {}
        
        if self.format == "pdf":
            try:
                # Import here to avoid potential circular import issues
                from app.blueprints.home.routes import markdown_or_html_to_pdf_bytes
                
                pdf_bytes_io = markdown_or_html_to_pdf_bytes(content, input_format="markdown")
                pdf_bytes = pdf_bytes_io.read()
                
                # Check for folder saving
                if self.folder_uuid:
                    user_id = self.data.get("user_id")
                    filename = f"rendered_docs/doc_{uuid.uuid4().hex[:8]}.pdf"
                    
                    # Ensure directory exists
                    abs_path = Path(app.root_path) / "static" / "uploads" / user_id / "rendered_docs"
                    abs_path.mkdir(parents=True, exist_ok=True)
                    
                    file_path = abs_path / f"doc_{uuid.uuid4().hex[:8]}.pdf"
                    
                    with open(file_path, "wb") as f:
                        f.write(pdf_bytes)
                        
                    # Create SmartDocument
                    doc = SmartDocument(
                        user_id=user_id,
                        title=f"Rendered Output {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        path=str(file_path.relative_to(Path(app.root_path) / "static" / "uploads")),
                        extension="pdf",
                        uuid=uuid.uuid4().hex,
                        space="default", # Ideally passed from context
                        folder=self.folder_uuid,
                        raw_text=content # Store source text
                    )
                    doc.save()
                    output_data["smart_document_uuid"] = doc.uuid
                    self.report_progress(f"Saved PDF to SmartFolder {self.folder_uuid}")

                # Encode for direct download/display if needed (optional, bytes might be too large)
                # For now, we return a "download" instruction
                import base64
                b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                
                output_data.update({
                    "type": "file_download",
                    "file_type": "pdf",
                    "filename": "output.pdf",
                    "data_b64": b64_pdf,
                    "preview": "PDF Generated. Click to download.",
                    "auto_download": self.auto_download
                })

                return {
                    "output": output_data,
                    "input": inputs,
                    "step_name": self.name
                }
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return {
                    "output": f"Error rendering PDF: {str(e)}",
                    "status": "error",
                    "step_name": self.name
                }
                
        return {
            "output": f"[Simulated {self.format.upper()} content...]",
            "input": inputs,
            "step_name": self.name
        }



class FormFillerNode(Node):
    def __init__(self, data):
        super().__init__("FormFiller")
        self.data = data
        self.config = data.get("config", {})
        self.flatten = self.config.get("flatten", False)
        self.auto_download = self.config.get("auto_download", False)

    def process(self, inputs):
        self.report_progress("Filling form data...")
        data_to_fill = inputs.get("output", {})
        # Mock implementation
        return {
            "output": f"[Filled PDF Form with data: {str(data_to_fill)[:50]}... Flattened={self.flatten}]",
            "input": inputs,
            "step_name": self.name
        }


class DataExportNode(Node):
    def __init__(self, data):
        super().__init__("DataExport")
        self.data = data
        self.config = data.get("config", {})
        self.format = self.config.get("format", "json")
        self.auto_download = self.config.get("auto_download", False)

    def process(self, inputs):
        self.report_progress(f"Exporting data to {self.format.upper()}...")
        data = inputs.get("output", [])
        
        try:
            import io
            import json
            import base64
            
            if self.format == "json":
                # JSON export is straightforward
                json_str = json.dumps(data, indent=2, default=str)
                json_bytes = json_str.encode('utf-8')
                b64_data = base64.b64encode(json_bytes).decode('utf-8')
                
                return {
                    "output": {
                        "type": "file_download",
                        "file_type": "json",
                        "filename": "export.json",
                        "data_b64": b64_data,
                        "preview": f"JSON export ready ({len(json_bytes)} bytes)",
                        "auto_download": self.auto_download
                    },
                    "input": inputs,
                    "step_name": self.name
                }
                
            elif self.format == "csv":
                import csv
                
                # Convert data to rows
                rows = []
                headers = []
                
                if isinstance(data, list) and len(data) > 0:
                    # List of dicts - extract headers from first item
                    if isinstance(data[0], dict):
                        headers = list(data[0].keys())
                        for item in data:
                            row = [str(item.get(h, "")) for h in headers]
                            rows.append(row)
                    else:
                        # List of primitives
                        headers = ["Value"]
                        rows = [[str(item)] for item in data]
                elif isinstance(data, dict):
                    # Single dict - convert to key-value pairs
                    headers = ["Key", "Value"]
                    rows = [[str(k), str(v)] for k, v in data.items()]
                else:
                    # Single value
                    headers = ["Value"]
                    rows = [[str(data)]]
                
                # Write CSV to memory
                csv_buffer = io.StringIO()
                writer = csv.writer(csv_buffer)
                writer.writerow(headers)
                writer.writerows(rows)
                
                csv_bytes = csv_buffer.getvalue().encode('utf-8')
                b64_data = base64.b64encode(csv_bytes).decode('utf-8')
                
                return {
                    "output": {
                        "type": "file_download",
                        "file_type": "csv",
                        "filename": "export.csv",
                        "data_b64": b64_data,
                        "preview": f"CSV export ready ({len(rows)} rows)",
                        "auto_download": self.auto_download
                    },
                    "input": inputs,
                    "step_name": self.name
                }
                
            elif self.format == "xlsx":
                try:
                    import openpyxl
                    from openpyxl import Workbook
                except ImportError:
                    return {
                        "output": "Error: openpyxl library not installed. Please install it to export Excel files.",
                        "status": "error",
                        "step_name": self.name
                    }
                
                # Create workbook
                wb = Workbook()
                ws = wb.active
                ws.title = "Export"
                
                # Convert data to rows
                rows = []
                headers = []
                
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict):
                        headers = list(data[0].keys())
                        for item in data:
                            row = [item.get(h, "") for h in headers]
                            rows.append(row)
                    else:
                        headers = ["Value"]
                        rows = [[item] for item in data]
                elif isinstance(data, dict):
                    headers = ["Key", "Value"]
                    rows = [[k, v] for k, v in data.items()]
                else:
                    headers = ["Value"]
                    rows = [[data]]
                
                # Write headers
                ws.append(headers)
                
                # Write data rows
                for row in rows:
                    ws.append(row)
                
                # Save to memory
                xlsx_buffer = io.BytesIO()
                wb.save(xlsx_buffer)
                xlsx_bytes = xlsx_buffer.getvalue()
                
                b64_data = base64.b64encode(xlsx_bytes).decode('utf-8')
                
                return {
                    "output": {
                        "type": "file_download",
                        "file_type": "xlsx",
                        "filename": "export.xlsx",
                        "data_b64": b64_data,
                        "preview": f"Excel export ready ({len(rows)} rows)",
                        "auto_download": self.auto_download
                    },
                    "input": inputs,
                    "step_name": self.name
                }
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "output": f"Error exporting data: {str(e)}",
                "status": "error",
                "step_name": self.name
            }


class PackageBuilderNode(Node):
    def __init__(self, data):
        super().__init__("PackageBuilder")
        self.data = data
        self.config = data.get("config", {})
        self.include_manifest = self.config.get("include_manifest", False)
        self.auto_download = self.config.get("auto_download", False)

    def process(self, inputs):
        self.report_progress("Building package...")
        content = inputs.get("output", "")
        
        try:
            import io
            import zipfile
            import json
            import base64
            
            # Create an in-memory zip file
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add the main content as a file
                if isinstance(content, dict):
                    content_str = json.dumps(content, indent=2)
                    zip_file.writestr("data.json", content_str)
                elif isinstance(content, list):
                    content_str = json.dumps(content, indent=2)
                    zip_file.writestr("data.json", content_str)
                else:
                    zip_file.writestr("output.txt", str(content))
                
                # Add manifest if requested
                if self.include_manifest:
                    manifest = {
                        "created_at": datetime.datetime.now().isoformat(),
                        "content_type": type(content).__name__,
                        "files": []
                    }
                    for info in zip_file.filelist:
                        manifest["files"].append({
                            "filename": info.filename,
                            "size": info.file_size
                        })
                    zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))
            
            # Get the zip bytes
            zip_bytes = zip_buffer.getvalue()
            
            # Encode as base64
            b64_zip = base64.b64encode(zip_bytes).decode('utf-8')
            
            output_data = {
                "type": "file_download",
                "file_type": "zip",
                "filename": "workflow_output.zip",
                "data_b64": b64_zip,
                "preview": f"ZIP package created ({len(zip_bytes)} bytes)",
                "auto_download": self.auto_download
            }
            
            return {
                "output": output_data,
                "input": inputs,
                "step_name": self.name
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "output": f"Error creating ZIP package: {str(e)}",
                "status": "error",
                "step_name": self.name
            }



def sanitize_step_name(name: str) -> str:
    name = name.replace(".", "_")
    name = name.replace("$", "_")
    name = name.strip()
    name = name.strip("_")
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"__+", "_", name)
    if not name:
        name = "step"
    return name


class WorkflowEngine:
    def __init__(self) -> None:
        self.nodes = []
        self.connections = []
        self.graph = graphlib.TopologicalSorter()
        self.graph_built = False
        self.max_workers = multiprocessing.cpu_count()
        self._last_progress_snapshot = None

    def add_node(self, node) -> None:
        self.graph.add(node)

    def connect(self, from_node, to_node) -> None:
        self.graph.add(from_node, to_node)

    def get_topological_order(self):
        return list(reversed(tuple(self.graph.static_order())))

    def execute(self, workflow_result=None):
        data = []
        nodes = self.get_topological_order()
        debug(nodes)

        if workflow_result:
            workflow_result.num_steps_completed = -1
            workflow_result.num_steps_total = len(nodes) - 1
        latest_output = None
        for idx, node in enumerate(nodes):
            debug(node)
            if workflow_result:
                self._report_progress(
                    workflow_result,
                    node.name,
                    detail=f"Starting {node.name}",
                )

            if idx == 0:
                output = node.process({})
                debug(output)
                latest_output = output
            else:
                debug(node)
                debug(latest_output)

                if workflow_result and isinstance(node, MultiTaskNode):
                    for task in node.tasks:
                        task.progress_reporter = (
                            lambda detail=None,
                            preview=None,
                            step=node.name,
                            task_name=task.name: self._report_progress(
                                workflow_result,
                                step,
                                detail=detail or task_name,
                                preview=preview,
                            )
                        )

                output = node.process(latest_output)
                latest_output = output

            if workflow_result:
                step_name = sanitize_step_name(node.name)
                debug(f"Step name: {step_name}")
                workflow_result.steps_output[step_name] = output
                workflow_result.num_steps_completed += 1
                workflow_result.save()

            debug(latest_output)
            data.append(
                {
                    "name": node.name,
                    "output": latest_output.get("output", None),
                    "input": latest_output.get("input", None),
                },
            )

        if latest_output is None:
            return None, data

        if workflow_result:
            workflow_result.status = "completed"
            workflow_result.save()
            self._report_progress(
                workflow_result,
                None,
                detail="Workflow completed",
                preview=None,
            )
            workflow_result.save()
            self._report_progress(
                workflow_result,
                None,
                detail="Workflow completed",
                preview=None,
            )
        # Prefer formatted_output for display, fall back to output
        display_value = latest_output.get("formatted_output") or latest_output.get("output")
        final_value = self._format_final_output(display_value)
        return final_value, data

    def _format_final_output(self, value):
        if value is None:
            return ""
        if isinstance(value, list):
            # If list contains a single dict, format it directly
            if len(value) == 1 and isinstance(value[0], dict):
                return self._format_final_output(value[0])

            formatted_items = [
                self._format_final_output(item)
                if isinstance(item, (list, dict))
                else self._normalize_text(str(item))
                for item in value
            ]
            formatted_items = [item for item in formatted_items if item]
            if not formatted_items:
                return ""
            if len(formatted_items) == 1:
                return formatted_items[0]
            blocks = []
            for idx, item in enumerate(formatted_items, start=1):
                if isinstance(item, str):
                    stripped = item.lstrip()
                    if stripped.startswith("#"):
                        blocks.append(item)
                    else:
                        blocks.append(f"### Result {idx}\n{item}")
                else:
                    try:
                        item_str = json.dumps(item, indent=2)
                    except:
                        item_str = str(item)
                    blocks.append(f"### Result {idx}\n{item_str}")
            return "\n\n".join(blocks)
        if isinstance(value, dict):
            # Pass through special output types (like file downloads) without stringifying
            if value.get("type") == "file_download":
                return value
            try:
                return json.dumps(value, indent=2)
            except Exception:
                return str(value)
        return self._normalize_text(str(value))

    @staticmethod
    def _normalize_text(text):
        if not isinstance(text, str):
            text = str(text)
        return text.replace("\\n", "\n").replace("\\t", "\t")

    def _report_progress(self, workflow_result, step_name, detail=None, preview=None):
        if not workflow_result:
            return

        update_ops = {}
        if step_name is not None:
            workflow_result.current_step_name = step_name
            update_ops["set__current_step_name"] = step_name
        if detail is not None:
            workflow_result.current_step_detail = detail
            update_ops["set__current_step_detail"] = detail
        if preview is not None:
            workflow_result.current_step_preview = preview
            update_ops["set__current_step_preview"] = preview
        elif (
            preview is None
            and "set__current_step_preview" not in update_ops
            and detail in {"Workflow completed", None}
        ):
            update_ops["unset__current_step_preview"] = 1

        if update_ops:
            WorkflowResult.objects(id=workflow_result.id).update_one(**update_ops)


def build_workflow_engine(steps, workflow, model, user_id=None, workflow_result=None):
    engine = WorkflowEngine()
    nodes = []

    # Extract workflow document UUIDs from the Document trigger step
    # so tasks with input_config.source == "workflow_documents" can use them
    workflow_doc_uuids = []
    if steps and steps[0].name == "Document":
        docs = steps[0].data.get("docs", [])
        workflow_doc_uuids = [doc.uuid for doc in docs if doc is not None]

    for idx, step in enumerate(steps):
        node = None
        debug(step.name, step.data)
        if step.name == "Document":  # this the trigger step
            node = DocumentNode(step.data)
            nodes.append(node)
        else:  # this a task step
            tasks = []
            for task in step.tasks:
                debug(task)

                # Inject workflow document UUIDs for tasks that need them
                if task.data.get("input_config", {}).get("source") == "workflow_documents":
                    task.data["_workflow_document_uuids"] = workflow_doc_uuids

                if task.name == "Extraction":
                    if task.data.get("search_set_uuid"):
                        search_set = SearchSet.objects(
                            uuid=task.data.get("search_set_uuid"),
                        ).first()
                        search_items = search_set.items()
                        task.data["keys"] = [item.searchphrase for item in search_items]

                    task.data["user_id"] = user_id
                    task.data["model"] = model
                    debug(task.data)
                    node = ExtractionNode(
                        data=task.data,
                    )
                    tasks.append(node)
                    debug(tasks)
                elif task.name == "Prompt":
                    task.data["user_id"] = user_id
                    task.data["model"] = model
                    node = PromptNode(
                        data=task.data,
                    )
                    tasks.append(node)
                elif task.name == "Formatter":
                    task.data["user_id"] = user_id
                    task.data["model"] = model
                    node = FormatNode(
                        data=task.data,
                    )
                    tasks.append(node)
                elif task.name == "BrowserAutomation":
                    task.data["user_id"] = user_id
                    task.data["model"] = model
                    if workflow_result:
                        task.data["workflow_result_id"] = str(workflow_result.id)
                    
                    node = BrowserAutomationNode(
                        data=task.data,
                    )
                    tasks.append(node)
                elif task.name == "DocumentRenderer":
                    tasks.append(DocumentRendererNode(task.data))
                elif task.name == "FormFiller":
                    tasks.append(FormFillerNode(task.data))
                elif task.name == "DataExport":
                    tasks.append(DataExportNode(task.data))
                elif task.name == "PackageBuilder":
                    tasks.append(PackageBuilderNode(task.data))

            node = MultiTaskNode(step.name)
            node.add_tasks(tasks)
            nodes.append(node)
            debug(step.tasks)

        engine.add_node(node)

    debug(nodes)
    # connect the steps
    for idx in range(len(nodes)):
        if idx == 0:
            continue
        engine.connect(nodes[idx - 1], nodes[idx])

    return engine


class WorkflowManager:
    def __init__(self, persist_directory=None) -> None:
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            length_function=len,
        )
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=self.persist_directory.as_posix(),
            settings=Settings(anonymized_telemetry=False, is_persistent=True),
        )

        # Create or get collection for workflows
        self.collection_name = "workflow_recommendations"
        try:
            self.collection = self.client.get_collection(self.collection_name)
        except:
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )


@celery_app.task(
    bind=True,
    name="tasks.workflow.execution",
    autoretry_for=(Exception,),
    rate_limit="1/s",
    max_retries=3,
    default_retry_delay=5,
)
def execute_workflow_task(
    self, workflow_result_id, workflow_id, workflow_trigger_step_id, model
):
    workflow_result = WorkflowResult.objects(id=workflow_result_id).first()
    workflow = Workflow.objects(id=workflow_id).first()
    workflow_trigger_step = WorkflowStep.objects(id=workflow_trigger_step_id).first()

    if not workflow_result:
        return {
            "status": "error",
            "error": "Workflow result not found",
        }
    if not workflow:
        return {
            "status": "error",
            "error": "Workflow not found",
        }
    if not workflow_trigger_step:
        return {
            "status": "error",
            "error": "Workflow trigger step not found",
        }

    workflow_result.status = "running"
    workflow_result.num_steps_completed = -1
    workflow_result.num_steps_total = len(workflow.steps) - 1
    workflow_result.steps_output = {}
    workflow_result.save()

    steps = [workflow_trigger_step]
    for step in workflow.steps:
        steps.append(step)
        debug(step.name, step.data)

    debug(steps)

    engine = build_workflow_engine(steps, workflow, model, user_id=workflow.user_id, workflow_result=workflow_result)

    final_output, data = engine.execute(workflow_result)
    debug(final_output)
    
    # Check if the last workflow step is an output step
    # If so, use its specific output as the final output
    if workflow.steps and workflow.steps[-1].is_output:
        last_step_name = sanitize_step_name(workflow.steps[-1].name)
        last_step_output = workflow_result.steps_output.get(last_step_name, {})
        
        # Use the last step's output as the final output
        if last_step_output:
            workflow_result.final_output = {"output": last_step_output.get("output", final_output), "data": data}
        else:
            workflow_result.final_output = {"output": final_output, "data": data}
    else:
        workflow_result.final_output = {"output": final_output, "data": data}
    
    workflow_result.status = "completed"
    workflow_result.save()
    print(
        f"Workflow execution finished for Result ID: {workflow_result_id}. Status: {workflow_result.status}"
    )

    # Ingest workflow into vector database for future recommendations (async)
    docs = workflow_trigger_step.data.get("docs", [])

    try:
        ingestion_text = "# Documents selected:"
        for doc in docs:
            if hasattr(doc, "raw_text"):
                ingestion_text += f"\n{doc.raw_text}"

        # Use singleton instance to avoid expensive re-initialization
        try:
            from app.blueprints.workflows.routes import get_recommendation_manager

            recommendation_manager = get_recommendation_manager()
            recommendation_manager.ingest_recommendation_item(
                identifier=workflow_id,
                ingestion_text=ingestion_text,
                recommendation_type="Workflow",
            )
            debug("Workflow recommendation ingested successfully")
            # Clear recommendations cache so new workflow appears immediately
            try:
                from app.blueprints.workflows.routes import clear_recommendations_cache

                clear_recommendations_cache()
            except Exception as cache_error:
                debug(f"Error clearing recommendations cache: {cache_error}")
        except ImportError:
            # Fallback if singleton not available (shouldn't happen in normal flow)
            persist_directory = "data/recommendations_vectordb"
            recommendation_manager = SemanticRecommender(
                persist_directory=persist_directory
            )
            recommendation_manager.ingest_recommendation_item(
                identifier=workflow_id,
                ingestion_text=ingestion_text,
                recommendation_type="Workflow",
            )
            debug("Workflow recommendation ingested successfully")
    except Exception as e:
        debug(f"Error ingesting workflow recommendation: {e}")

    # Update the activity status to completed
    activity = ActivityEvent.objects(workflow_result=workflow_result).first()
    if activity:
        snapshot = dict(activity.result_snapshot or {})

        snapshot_output = final_output
        try:
            json.dumps(snapshot_output)
        except TypeError:
            snapshot_output = str(snapshot_output)

        document_uuids: list[str] = []
        for doc in docs or []:
            if doc is None:
                continue
            if hasattr(doc, "uuid"):
                document_uuids.append(doc.uuid)
            elif isinstance(doc, str):
                document_uuids.append(doc)

        snapshot.update(
            {
                "output": snapshot_output,
                "history": data,
                "steps_total": workflow_result.num_steps_total,
                "steps_completed": workflow_result.num_steps_completed,
                "status": workflow_result.status,
                "workflow_result_id": workflow_result_id,
                "document_uuids": document_uuids,
                "session_id": workflow_result.session_id,
            },
        )

        if document_uuids:
            activity.documents_touched = len(set(document_uuids))

        activity.result_snapshot = snapshot
        activity_finish(activity, status=ActivityStatus.COMPLETED)

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
        "output": final_output,
        "history": data,
    }


@celery_app.task(bind=True, name="tasks.workflow.execution_step_test")
def execute_task_step_test(self, task_name, task_data, document_trigger_step_id):
    process_node = None
    workflow_trigger_step = WorkflowStep.objects(id=document_trigger_step_id).first()
    engine = WorkflowEngine()
    nodes = []
    node = DocumentNode(workflow_trigger_step.data)
    nodes.append(node)
    engine.add_node(node)

    debug(nodes)
    # connect the steps

    if task_name == "Extraction":
        process_node = ExtractionNode(
            data=task_data,
        )
        node = MultiTaskNode(task_name)
        node.add_tasks([process_node])
        nodes.append(node)
        engine.add_node(node)
    elif task_name == "Prompt":
        process_node = PromptNode(
            data=task_data,
        )
        node = MultiTaskNode(task_name)
        node.add_tasks([process_node])
        nodes.append(node)
        engine.add_node(node)
    elif task_name == "Formatter":
        process_node = FormatNode(
            data=task_data,
        )
        node = MultiTaskNode(task_name)
        node.add_tasks([process_node])
        nodes.append(node)
        engine.add_node(node)
    else:
        process_node = Node(task_name)
        node = MultiTaskNode(task_name)
        node.add_tasks([process_node])
        nodes.append(node)
        engine.add_node(node)

    for idx in range(len(nodes)):
        if idx == 0:
            continue
        engine.connect(nodes[idx - 1], nodes[idx])

    final_output, _ = engine.execute()
    print(final_output)

    return final_output
