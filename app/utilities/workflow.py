#!/usr/bin/env python3

import os
import openai
from pydantic import BaseModel
from dotenv import load_dotenv
import re

from pypdf import PdfReader

from typing import List, Dict, Any

from app import app
from app.utilities.extraction_manager2 import ExtractionManager2
from app.utilities.openai_interface import OpenAIInterface, extract_text_from_doc

from app.models import SmartDocument

from uuid import uuid4

import re
import graphlib

load_dotenv()

# TODO add the option to choose the llm model
# TODO add the option to choose the way we get the document content (luke's model, or pdfreader)


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


def llm_chat_model(prompt, docs):
    open_ai_interface = OpenAIInterface()
    output = open_ai_interface.ask_question_to_documents(
        root_path=app.root_path, documents=docs, question=prompt
    )
    return output


def data_extraction_model(keys, pdf_paths):
    extraction_manager = ExtractionManager2()
    output = extraction_manager.extract(keys, pdf_paths)
    return output


def format_model(formatting_prompt, text):
    prompt = f"{formatting_prompt}\n\n {text}"
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    response = completion.choices[0].message.content
    print("Response: ", response)
    if response is None:
        return None, None
    # formatted text is between ```json\n and \n```

    return prompt, response


class Node:
    def __init__(self, name):
        self.name = name
        self.inputs = {}
        self.outputs = {}

    def process(self, inputs):
        raise NotImplementedError


class FormatNode(Node):
    def __init__(self, data):
        super().__init__("Formatter")
        self.formatting_prompt = data.get("prompt", "")
        print("Format Node: ", data, self.formatting_prompt)

    def process(self, inputs):
        data = inputs.get("output", None)
        prev_step_name = inputs.get("step_name", None)
        text = None
        if prev_step_name == "Prompt":
            text = data.get("formatted_answer", "")

        print("Format Node data: ", text, prev_step_name)
        prompt, output = format_model(self.formatting_prompt, text)
        return {"output": output, "input": prompt}


class DocumentNode(Node):
    def __init__(self, data):
        super().__init__("Document")
        self.docs = data.get("docs", [])
        self.attachments = data.get("attachments", [])
        self.pdf_paths = []
        print("Document Node: ", data, self.docs, self.attachments)

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

    def process(self, inputs=None):

        # data = inputs.get("data", None)

        output = {"step_name": self.name, "output": self.pdf_paths, "input": None}

        return output


class ExtractionNode(Node):
    def __init__(self, data):
        super().__init__("Extraction")
        print("Extraction Node: ", data)
        self.keys = data.get("keys", [])
        print("Extraction keys: ", self.keys)

    def process(self, inputs):
        step_name = inputs.get("step_name", None)

        step_input = None
        pdf_paths = None
        if step_name == "Document":
            pdf_paths = inputs.get("output", None)
            if pdf_paths is None:
                return {"output": None}
            step_input = pdf_paths

        extraction_response = data_extraction_model(self.keys, pdf_paths)
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
        docs_paths = inputs.get("output", None)
        docs_uuids = []
        for doc_path in docs_paths:
            doc_uuid = doc_path.split("/")[-1].split(".")[0]
            docs_uuids.append(doc_uuid)
        docs = [SmartDocument.objects(uuid=doc_uuid).first() for doc_uuid in docs_uuids]

        chat_response = llm_chat_model(docs=docs, prompt=self.prompt)
        return {"output": chat_response, "input": self.prompt, "step_name": self.name}


# TODO track the execution of the workflow. The various steps, etc. Maybe return a list of steps executed
class WorkflowEngine:
    def __init__(self, workflow):
        self.workflow = workflow
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

    def execute(self):
        data = []
        nodes = self.get_topological_order()
        print("nodes", nodes)
        self.workflow.workflow_result.num_steps_completed = 0
        self.workflow.workflow_result.num_steps_total = len(nodes)
        latest_output = None
        for idx, node in enumerate(nodes):
            print("Executing node: ", node.name, idx, len(nodes))
            if idx == 0:
                output = node.process(dict())
            else:
                output = node.process(latest_output)

            self.workflow.workflow_result.steps_output[node.name] = output
            self.workflow.workflow_result.num_steps_completed += 1
            self.workflow.workflow_result.save()

            latest_output = output
            data.append(
                dict(
                    name=node.name,
                    output=output.get("output", None),
                    input=output.get("input", None),
                )
            )

        if latest_output is None:
            return None, data

        return latest_output.get("output"), data


def build_workflow_engine(steps, workflow):
    print("Building workflow engine: ", steps, workflow)
    engine = WorkflowEngine(workflow)
    nodes = []

    for idx, step in enumerate(steps):
        # node_id = uuid4().hex
        node = None
        if step.name == "Document":
            # node_objects[node_id] = DocumentNode(step.data)
            node = DocumentNode(step.data)
            nodes.append(node)
        elif step.name == "Extraction":
            extract_keys = step.extraction_items()
            node = ExtractionNode(dict(data=step.data, keys=extract_keys))
            nodes.append(node)
        elif step.name == "Prompt":
            node = PromptNode(step.data)
            nodes.append(node)
        elif step.name == "Formatter":
            node = FormatNode(step.data)
            nodes.append(node)

        print("Node: ", node, step.name)

        engine.add_node(node)

    # connect the steps
    for idx in range(len(nodes)):
        if idx == 0:
            continue
        engine.connect(nodes[idx - 1], nodes[idx])

    return engine
