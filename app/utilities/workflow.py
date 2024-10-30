#!/usr/bin/env python3

import openai
from pydantic import BaseModel
from dotenv import load_dotenv

from pypdf import PdfReader

from typing import List, Dict, Any

import re
import graphlib

load_dotenv()

# TODO add the option to choose the llm model
# TODO add the option to choose the way we get the document content (luke's model, or pdfreader)


def add_document_to_workflow_step(document, workflow_step):
    documents = workflow_step.data.get("documents", [])
    documents.append(document)
    workflow_step.data["documents"] = documents
    workflow_step.save()
    return workflow_step


def llm_chat_model(prompt):
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


def data_extraction_model(prompt):
    model = "gpt-4o"

    completion = openai.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a data scientist working on a project to extract entities and their properties from a passage. You are tasked with extracting the entities and their properties from the following passage and provide the response in a JSON format.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    output = completion.choices[0].message.content
    if output is None:
        return None
    output = output.replace("\\n", "")
    output = output.replace("=json", "")
    output = output.replace("=", "")
    return output


def format_model(format, data):
    prompt = f"Format the following text in {format} format: \n{data}"
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    response = completion.choices[0].message.content
    if response is None:
        return None, None
    # formatted text is between ```json\n and \n```
    format_spec = f"```{format}\n"
    formatted_text = re.search(f"{format_spec}(.*?)\n```", response, re.DOTALL)
    if formatted_text is None:
        return prompt, None

    return prompt, formatted_text.group(1)


class Node:
    def __init__(self, name):
        self.name = name
        self.inputs = {}
        self.outputs = {}

    def process(self, inputs):
        raise NotImplementedError


class FormatNode(Node):
    def __init__(self, data):
        super().__init__("Format")
        self.format = data.get("format", "")

    def process(self, inputs):
        data = inputs.get("output", None)
        prompt, output = format_model(self.format, data)
        return {"output": output, "input": prompt}


class DocumentNode(Node):
    def __init__(self, data):
        super().__init__("Document")
        self.filename = data.get("filename", "")
        self.content = ""

    def process(self, inputs):

        data = inputs.get("output", None)
        # read the content of the file
        extension = self.filename.split(".")[-1]
        if extension == "pdf":
            pdf_path = f"uploads/{self.filename}"
            pdf = PdfReader(pdf_path)
            number_of_pages = len(pdf.pages)
            full_text = ""
            for i in range(number_of_pages):
                full_text = full_text + pdf.pages[i].extract_text() + " "
            self.content = full_text

        return {"output": self.content, "input": self.filename}


class ExtractionNode(Node):
    def __init__(self, data):
        super().__init__("Extraction")
        self.field = data.get("field", "")

    def process(self, inputs):
        text = inputs.get("output", None)
        if text is None:
            return {"output": None}
        extraction_response = data_extraction_model(text)
        return {"output": extraction_response, "input": text}


class PromptNode(Node):
    def __init__(self, data):
        super().__init__("Prompt")
        self.prompt = data.get("prompt", "Enter prompt")

    def process(self, inputs):
        data = inputs.get("output", None)
        self.prompt = f"{self.prompt} \n{data}"
        # print("Prompt Node: ", self.prompt)
        chat_response = llm_chat_model(self.prompt)
        return {"output": chat_response, "input": self.prompt}


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

    def execute(self):
        data = []
        nodes = self.get_topological_order()
        print("nodes", nodes)
        latest_output = None
        for idx, node in enumerate(nodes):
            if idx == 0:
                output = node.process(dict())
            else:
                output = node.process(latest_output)

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


def build_workflow(data):
    engine = WorkflowEngine()
    node_objects = {}

    for node_data in data["nodes"]:
        node_type = node_data["type"]
        node_id = node_data["id"]

        if node_type == "Document":
            node_objects[node_id] = DocumentNode(node_data["data"])
        elif node_type == "Extraction":
            node_objects[node_id] = ExtractionNode(node_data["data"])
        elif node_type == "Prompt":
            node_objects[node_id] = PromptNode(node_data["data"])
        elif node_type == "Format":
            node_objects[node_id] = FormatNode(node_data["data"])

        engine.add_node(node_objects[node_id])

    for conn_data in data["connections"]:
        from_node = node_objects[conn_data["from_"]["node"]]
        to_node = node_objects[conn_data["to"]["node"]]
        engine.connect(from_node, to_node)

    return engine


class NodeData(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]


class ConnectionData(BaseModel):
    from_: Dict[str, str]
    to: Dict[str, str]


class WorkflowData(BaseModel):
    nodes: List[NodeData]
    connections: List[ConnectionData]
