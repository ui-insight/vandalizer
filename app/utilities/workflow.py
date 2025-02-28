#!/usr/bin/env python3

import os
import json
import openai
from pydantic import BaseModel
from dotenv import load_dotenv
# from app import socketio

import re
import html

from pypdf import PdfReader

from typing import List, Dict, Any

from app import app
from app.utilities.document_readers import extract_text_from_doc
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.llm import ChatLM
from app.utilities.openai_interface import (
    OpenAIInterface,
)
from app.utilities.config import model_type

from threading import Thread

from app.models import SmartDocument, SearchSet

from uuid import uuid4

import re
import graphlib

load_dotenv()

# TODO add the option to choose the llm model
# TODO add the option to choose the way we get the document content (luke's model, or pdfreader)


class WorkflowThread(Thread):
    def __init__(
        self, group=None, target=None, name=None, args=(), kwargs={}, verbose=None
    ):
        super().__init__(group, target, name, args, kwargs)
        self._return = None
        self._target = target
        self._args = args
        self._kwargs = kwargs

    def run(self):
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


# TODO prompt and formatter
#
# def format_llm_output(text: str) -> str:
#     """
#     Format LLM output text for HTML display.

#     Args:
#         text (str): Raw LLM output text containing \n literals and markdown formatting

#     Returns:
#         str: Formatted HTML-safe string
#     """
#     # Replace explicit \n with actual newlines
#     text = text.replace("\\n", "\n")

#     # Escape HTML special characters
#     text = html.escape(text)

#     # Convert markdown-style bold to HTML
#     text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)

#     # Convert newlines to <br> tags
#     text = text.replace("\n", "<br>")

#     # Remove any extra whitespace at start/end
#     return text.strip()


def format_llm_output(text: str) -> str:
    """
    Format raw LLM text output to clean up escape characters and extra whitespace.
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


def llm_chat_model(prompt, data=None, docs=[]):
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
        print("llm chat response: ", output)
        output = format_llm_output(output).strip()
        # output = open_ai_interface.handle_short_context(
        #     prompt=prompt, full_text=full_text
        # )
        # if output is not None:
        #     output = output.get("answer", "")

    else:
        output = open_ai_interface.ask_question_to_documents(
            root_path=app.root_path, documents=docs, question=prompt
        )
    return output


def data_extraction_model(keys, pdf_paths, full_text=None):
    output = None
    extraction_manager = ExtractionManager3()
    if pdf_paths is None:
        output = extraction_manager.extract(keys, pdf_paths=[], full_text=full_text)
    else:
        output = extraction_manager.extract(keys, pdf_paths)
    return output


def format_model(formatting_prompt, text):
    prompt = f"{formatting_prompt}\n\n {text}"
    chat_lm = ChatLM(model_type)
    response = chat_lm.completion(
        messages=[{"role": "user", "content": prompt}],
    )

    if response is None:
        return None, None
    # formatted text is between ```json\n and \n```
    format_spec_regex = r"```(.*?)\n(.*?)\n```"
    match = re.search(format_spec_regex, response, re.DOTALL)
    if match is not None:
        formatted_text = match.group(2)
        return prompt, formatted_text
    else:
        return prompt, response


class Node:
    def __init__(self, name):
        self.name = name
        self.inputs = {}
        self.outputs = {}

    def process(self, inputs):
        raise NotImplementedError


class DocumentNode(Node):
    def __init__(self, data):
        super().__init__("Document")
        self.docs = data.get("docs", [])
        self.attachments = data.get("attachments", [])
        self.pdf_paths = []

        # self.filename = data.get("filename", "")
        # self.content = ""
        self.docs_uuids = []
        self.content = ""
        for doc in self.attachments:
            doc_path = os.path.join(app.root_path, "static", "uploads", doc.path)
            self.pdf_paths.append(doc_path)

        for doc in self.docs:
            doc_path = os.path.join(app.root_path, "static", "uploads", doc.path)
            self.pdf_paths.append(doc_path)

        print("PDF Paths: ", self.pdf_paths)

    def process(self, inputs=None):

        # data = inputs.get("data", None)

        output = {"step_name": self.name, "output": self.pdf_paths, "input": None}

        return output


class FormatNode(Node):
    def __init__(self, data):
        super().__init__("Formatter")
        self.formatting_prompt = data.get("prompt", "")

    def process(self, inputs):
        data = inputs.get("output", None)
        prev_step_name = inputs.get("step_name", None)
        text = None
        if prev_step_name == "Prompt":
            if isinstance(data, dict):
                text = data.get("formatted_answer", "")
            else:
                text = data
        if prev_step_name == "Document":
            doc_paths = inputs.get("output", None)
            text = ""
            for doc_path in doc_paths:
                doc_text = extract_text_from_doc(doc_path)
                if doc_text is not None:
                    text += doc_text
        else:
            text = data

        prompt, output = format_model(self.formatting_prompt, text)
        return {"output": output, "input": prompt, "step_name": self.name}


class ExtractionNode(Node):
    def __init__(self, data):
        super().__init__("Extraction")

        self.keys = data.get("searchphrases", [])
        if len(self.keys) == 0:
            self.keys = data.get("keys", [])
        print("keys: ", self.keys, data)

    def process(self, inputs):
        prev_step_name = inputs.get("step_name", None)

        step_input = None
        pdf_paths = None
        extraction_response = None
        if prev_step_name == "Document":
            pdf_paths = inputs.get("output", None)
            if pdf_paths is None:
                return {"output": None}
            step_input = pdf_paths

            extraction_response = data_extraction_model(self.keys, pdf_paths)
        elif prev_step_name == "Prompt":
            step_input = inputs.get("output", None)
            if isinstance(step_input, dict):
                step_input = step_input.get("answer")
            extraction_response = data_extraction_model(
                self.keys, pdf_paths, full_text=step_input
            )
        elif prev_step_name == "Extraction":
            step_input = inputs.get("output", None)
            extraction_response = data_extraction_model(
                self.keys, pdf_paths, full_text=step_input
            )
        elif prev_step_name == "Formatter":
            step_input = inputs.get("output", None)
            extraction_response = data_extraction_model(
                self.keys, pdf_paths, full_text=step_input
            )

        return {
            "output": extraction_response,
            "input": step_input,
            "step_name": self.name,
        }


class PromptNode(Node):
    def __init__(self, data):
        super().__init__("Prompt")
        self.prompt = data.get("prompt", "Enter prompt")

    def process(self, inputs):
        prev_step_name = inputs.get("step_name", None)
        chat_response = None
        if prev_step_name == "Document":
            docs_paths = inputs.get("output", None)
            docs_uuids = []
            for doc_path in docs_paths:
                doc_uuid = doc_path.split("/")[-1].split(".")[0]
                docs_uuids.append(doc_uuid)
            docs = [
                SmartDocument.objects(uuid=doc_uuid).first() for doc_uuid in docs_uuids
            ]

            chat_response = llm_chat_model(docs=docs, prompt=self.prompt)
        else:
            data = inputs.get("output", None)
            print("Prompt Data: ", data)

            chat_response = llm_chat_model(docs=[], prompt=self.prompt, data=data)
        return {"output": chat_response, "input": self.prompt, "step_name": self.name}


# TODO track the execution of the workflow. The various steps, etc. Maybe return a list of steps executed
class WorkflowEngine:
    def __init__(self):
        self.nodes = []
        self.connections = []
        self.graph = graphlib.TopologicalSorter()
        self.graph_built = False

    def add_node(self, node):
        self.graph.add(node)

    def connect(self, from_node, to_node):
        self.graph.add(from_node, to_node)

    def get_topological_order(self):
        return list(reversed(tuple(self.graph.static_order())))

    def execute(self, workflow_result):
        data = []
        nodes = self.get_topological_order()
        print("Nodes: ", nodes)

        workflow_result.num_steps_completed = 0
        workflow_result.num_steps_total = len(nodes)
        latest_output = None
        for idx, node in enumerate(nodes):
            print(f"Processing node {node}")

            if idx == 0:
                output = node.process(dict())
            else:
                output = node.process(latest_output)

            workflow_result.steps_output[node.name] = output
            workflow_result.num_steps_completed += 1

            latest_output = output
            data.append(
                dict(
                    name=node.name,
                    output=output.get("output", None),
                    input=output.get("input", None),
                )
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
        print("Step: ", step.name, step.data, step.tasks)
        if step.name == "Document":  # this the trigger step
            # node_objects[node_id] = DocumentNode(step.data)
            node = DocumentNode(step.data)
            nodes.append(node)
        else:  # this a task step
            for task in step.tasks:
                print("Task: ", task.name, task.data)
                if task.name == "Extraction":
                    if task.data.get("search_set_uuid"):
                        search_set = SearchSet.objects(
                            uuid=task.data.get("search_set_uuid")
                        ).first()
                        search_items = search_set.items()
                        print("Search Items: ", search_items, search_set.title)
                        task.data["keys"] = [item.searchphrase for item in search_items]
                    node = ExtractionNode(
                        data=task.data,
                    )
                    nodes.append(node)
                elif task.name == "Prompt":
                    node = PromptNode(
                        data=task.data,
                    )
                    nodes.append(node)
                elif task.name == "Formatter":
                    node = FormatNode(
                        data=task.data,
                    )
                    nodes.append(node)

        if node is not None:
            engine.add_node(node)

    # connect the steps
    for idx in range(len(nodes)):
        if idx == 0:
            continue
        engine.connect(nodes[idx - 1], nodes[idx])

    return engine
