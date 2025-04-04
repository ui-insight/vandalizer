#!/usr/bin/env python3

import graphlib
import json

# from app import socketio
import multiprocessing
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread
from typing import NoReturn

from devtools import debug
from dotenv import load_dotenv

from app import app
from app.celery import celery_app
from app.models import SearchSet, SmartDocument, Workflow, WorkflowResult
from app.utilities.config import model_type
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.llm import ChatLM
from app.utilities.openai_interface import (
    OpenAIInterface,
)
from app.utilities.config import model_type
from app.celery import celery_app

from threading import Thread

from app.models import SmartDocument, SearchSet, Workflow, WorkflowResult, WorkflowStep

import graphlib

load_dotenv()

# TODO add the option to choose the llm model
# TODO add the option to choose the way we get the document content (luke's model, or pdfreader)


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


def format_llm_output(text: str) -> str:
    r"""Format raw LLM text output to clean up escape characters and extra whitespace.
    Returns clean text that can be safely placed in HTML elements on the frontend.

    Args:
        text (str): Raw LLM output text containing \n literals and extra whitespace

    Returns:
        str: Cleaned text string

    """
    # Replace explicit \n escapes with actual newlines
    text = text.replace("\n", "")
    text = text.strip('"')

    # Remove any extra/duplicate newlines
    text = "\n".join(line for line in text.splitlines() if line.strip())

    # Remove any whitespace from start/end
    return text.strip()


def llm_chat_model(prompt, data=None, docs=None):
    if docs is None:
        docs = []
    open_ai_interface = OpenAIInterface()
    output = None
    if len(docs) == 0:
        # convert the data to string
        full_text = json.dumps(data)
        output_prompt = f"""Following the instruction and output your answer as a nicely formatted html to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not include newline break and quotes that break the formatting. Do not show ```html before the html.\n\nInstruction: {prompt}\n\n {full_text}"""

        chat_lm = ChatLM(model_type)

        output = chat_lm.completion(
            model="gpt-4o",
            messages=[{"role": "user", "content": output_prompt}],
            max_tokens=None,
        )
        output = format_llm_output(output).strip()
        # output = open_ai_interface.handle_short_context(
        #     prompt=prompt, full_text=full_text
        # )
        # if output is not None:
        #     output = output.get("answer", "")

    else:
        output = open_ai_interface.ask_question_to_documents(
            root_path=app.root_path,
            documents=docs,
            question=prompt,
        )
        output = output.get("answer", "")
        output = format_llm_output(output)
        debug(output)
    return output


def data_extraction_model(keys, pdf_paths, full_text=None):
    output = None
    extraction_manager = ExtractionManager3()
    if pdf_paths is None:
        output = extraction_manager.extract(keys, pdf_paths=[], full_text=full_text)
    else:
        output = extraction_manager.extract(keys, pdf_paths)

    debug(output)
    prompt = "Format the extracted data as a nicely formatted html with the extracted data as bullet points. Do not include newline break and quotes that break the formatting. Do not show ```html before the html."
    prompt += "\n\n"
    prompt += json.dumps(output, indent=4)
    chat_lm = ChatLM(model_type)
    response = chat_lm.completion(
        messages=[{"role": "user", "content": prompt}],
    )
    debug(response)
    return response


def format_model(formatting_prompt, text):
    system_prompt = """
Follow the instruction and output your answer as a nicely formatted html to display in a web interface chat bot. Always use html instead of markdown. Convert markdown to html. The html tags should fit nicely in a div on the page and not break formatting. Do not include newline break and quotes that break the formatting. Do not show ```html before the html.
CRITICAL:
- The formatted text should be a list of bullet points with the extracted data json data.
- The bullet points should be in a list format.
- Do not use markdown or json format by default, but use html format.
- If the user requests some formatting that looks like markdown, convert it as html.
    """

    # prompt = f"{formatting_prompt}\n\n {text}"
    prompt = f"{system_prompt}\n\n Instruction: {formatting_prompt}\n\n {text}"
    chat_lm = ChatLM(model_type)
    response = chat_lm.completion(
        messages=[{"role": "user", "content": prompt}],
    )

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

    def process(self, inputs) -> NoReturn:
        raise NotImplementedError

    def __repr__(self) -> str:
        node_class = self.__class__.__name__
        return f"""{node_class}(name={self.name}, inputs={self.inputs}, outputs={self.outputs})"""


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
            if isinstance(result.get("output"), str):
                output["output"].append(result.get("output", ""))
            else:
                output["output"].extend(result.get("output", {}))

        debug(output)
        return output


class DocumentNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Document")
        self.docs = data.get("docs", [])
        self.attachments = data.get("attachments", [])
        self.pdf_paths = []
        user_id = data.get("user_id", "0")

        # self.filename = data.get("filename", "")
        # self.content = ""
        self.docs_uuids = []
        self.content = ""
        for doc in self.attachments:
            if doc is None:
                continue
            doc_path = doc.absolute_path
            user_id = doc.user_id
            if not os.path.exists(str(doc_path)):
                doc_path = os.path.join(
                    app.root_path,
                    "static",
                    "uploads",
                    user_id,
                    str(doc.path),
                )
            self.pdf_paths.append(str(doc_path))

        for doc in self.docs:
            if doc is None:
                continue
            doc_path = doc.absolute_path
            user_id = doc.user_id
            if not os.path.exists(str(doc_path)):
                doc_path = os.path.join(
                    app.root_path,
                    "static",
                    "uploads",
                    user_id,
                    str(doc.path),
                )
            self.pdf_paths.append(str(doc_path))

        debug(self.docs[0])
        debug(self.pdf_paths)

    def process(self, inputs=None):
        # data = inputs.get("data", None)

        return {"step_name": self.name, "output": self.pdf_paths, "input": None}


class FormatNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Formatter")
        self.data = data

    def process(self, inputs):
        formatting_prompt = self.data.get("prompt", "")

        data = inputs.get("output", None)
        prev_step_name = inputs.get("step_name", None)
        text = None
        if prev_step_name == "Prompt":
            text = data.get("formatted_answer", "") if isinstance(data, dict) else data
        if prev_step_name == "Document":
            doc_paths = inputs.get("output", None)
            text = ""
            for doc_path in doc_paths:
                doc_text = extract_text_from_doc(doc_path)
                if doc_text is not None:
                    text += doc_text
        else:
            text = data

        prompt, output = format_model(formatting_prompt, text)
        return {"output": output, "input": prompt, "step_name": self.name}


class ExtractionNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Extraction")
        self.data = data

    def process(self, inputs):
        data = self.data
        debug(data)
        keys = self.data.get("searchphrases", [])
        if len(keys) == 0:
            keys = data.get("keys", [])

        prev_step_name = inputs.get("step_name", None)

        debug("Extraction", inputs, keys)

        step_input = None
        pdf_paths = None
        extraction_response = None
        if prev_step_name == "Document":
            pdf_paths = inputs.get("output", None)
            if pdf_paths is None:
                return {"output": None}
            step_input = pdf_paths

            extraction_response = data_extraction_model(keys, pdf_paths)
        elif prev_step_name == "Prompt":
            step_input = inputs.get("output", None)
            if isinstance(step_input, dict):
                step_input = step_input.get("answer")
            extraction_response = data_extraction_model(
                keys,
                pdf_paths,
                full_text=step_input,
            )
        elif prev_step_name in {"Extraction", "Formatter"}:
            step_input = inputs.get("output", None)
            extraction_response = data_extraction_model(
                keys,
                pdf_paths,
                full_text=step_input,
            )

        return {
            "output": extraction_response,
            "input": step_input,
            "step_name": self.name,
        }


class PromptNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Prompt")
        self.data = data

    def process(self, inputs):
        data = self.data
        prompt = data.get("prompt", "Enter prompt")

        prev_step_name = inputs.get("step_name", None)
        chat_response = None
        if prev_step_name == "Document":
            docs_paths = inputs.get("output", None)
            debug(docs_paths)
            docs_uuids = []
            for doc_path in docs_paths:
                doc_uuid = doc_path.split("/")[-1].split(".")[0]
                docs_uuids.append(doc_uuid)
            docs = [
                SmartDocument.objects(uuid=doc_uuid).first() for doc_uuid in docs_uuids
            ]

            chat_response = llm_chat_model(docs=docs, prompt=prompt)
        else:
            data = inputs.get("output", None)

            chat_response = llm_chat_model(docs=[], prompt=prompt, data=data)
        return {"output": chat_response, "input": prompt, "step_name": self.name}


# TODO track the execution of the workflow. The various steps, etc. Maybe return a list of steps executed
class WorkflowEngine:
    def __init__(self) -> None:
        self.nodes = []
        self.connections = []
        self.graph = graphlib.TopologicalSorter()
        self.graph_built = False
        self.max_workers = multiprocessing.cpu_count()

    def add_node(self, node) -> None:
        self.graph.add(node)

    def connect(self, from_node, to_node) -> None:
        self.graph.add(from_node, to_node)

    def get_topological_order(self):
        return list(reversed(tuple(self.graph.static_order())))

    def execute(self, workflow_result):
        data = []
        nodes = self.get_topological_order()
        debug(nodes)

        workflow_result.num_steps_completed = 0
        workflow_result.num_steps_total = len(nodes)
        latest_output = None
        for idx, node in enumerate(nodes):
            debug(node)

            node_outputs = []
            if idx == 0:
                output = node.process({})
                debug(output)
                latest_output = output
            else:
                debug(node)
                debug(latest_output)
                output = node.process(latest_output)
                for task in node.tasks:
                    process_node = None

                    if task.name == "Extraction":
                        process_node = ExtractionNode(
                            data=task.data,
                        )
                    elif task.name == "Prompt":
                        process_node = PromptNode(
                            data=task.data,
                        )
                    elif task.name == "Formatter":
                        process_node = FormatNode(
                            data=task.data,
                        )
                    else:
                        process_node = Node(task.name)

                    output = process_node.process(latest_output)
                    task_output = output.get("output", "")
                    if isinstance(task_output, list):
                        node_outputs.extend(output.get("output", ""))
                    else:
                        node_outputs.append(output.get("output", ""))

                # combine the outputs
                debug(node_outputs)
                latest_output = {
                    "output": node_outputs,
                    "input": output.get("input", ""),
                }
                # debug(latest_output)

            workflow_result.steps_output[node.name] = output
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

            # send the data to the frontend
            # socketio.emit(
            #     "workflow_status",
            #     {
            #         "steps_completed": workflow_result.num_steps_completed,
            #         "total_steps": workflow_result.num_steps_total,
            #         "steps_output": workflow_result.steps_output,
            #         "status": workflow_result.status,
            #     },
            # )

            workflow_result.save()

        if latest_output is None:
            return None, data

        workflow_result.status = "completed"

        # socketio.emit(
        #     "workflow_status",
        #     {
        #         "steps_completed": workflow_result.num_steps_completed,
        #         "total_steps": workflow_result.num_steps_total,
        #         "steps_output": workflow_result.steps_output,
        #         "status": workflow_result.status,
        #     },
        # )

        workflow_result.save()
        return latest_output.get("output"), data


def build_workflow_engine(steps, workflow):
    engine = WorkflowEngine()
    nodes = []

    for idx, step in enumerate(steps):
        # node_id = uuid4().hex
        node = None
        debug(step)
        if step.name == "Document":  # this the trigger step
            # node_objects[node_id] = DocumentNode(step.data)
            node = DocumentNode(step.data)
            nodes.append(node)
        else:  # this a task step
            tasks = []
            for task in step.tasks:
                if task.name == "Extraction":
                    if task.data.get("search_set_uuid"):
                        search_set = SearchSet.objects(
                            uuid=task.data.get("search_set_uuid"),
                        ).first()
                        search_items = search_set.items()
                        task.data["keys"] = [item.searchphrase for item in search_items]
                    debug(task.data)
                    node = ExtractionNode(
                        data=task.data,
                    )
                    tasks.append(node)
                    debug(tasks)
                elif task.name == "Prompt":
                    node = PromptNode(
                        data=task.data,
                    )
                    tasks.append(node)
                elif task.name == "Formatter":
                    node = FormatNode(
                        data=task.data,
                    )
                    tasks.append(node)

            node = MultiTaskNode(step.name)
            node.add_tasks(tasks)
            nodes.append(node)

        if node is not None:
            engine.add_node(node)

    debug(nodes)
    # connect the steps
    for idx in range(len(nodes)):
        if idx == 0:
            continue
        engine.connect(nodes[idx - 1], nodes[idx])

    return engine


@celery_app.task(bind=True, name="workflow.execute_workflow")
def execute_workflow_task(
    self, workflow_result_id, workflow_id, workflow_trigger_step_id
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
    workflow_result.num_steps_completed = 0
    workflow_result.num_steps_total = len(workflow.steps)
    workflow_result.steps_output = {}
    workflow_result.save()

    steps = [workflow_trigger_step]
    for step in workflow.steps:
        steps.append(step)

    debug(steps)

    engine = build_workflow_engine(steps, workflow)

    final_output, data = engine.execute(workflow_result)
    print(
        f"Workflow execution finished for Result ID: {workflow_result_id}. Status: {workflow_result.status}"
    )

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
        "output": final_output,
        "history": data,
    }
