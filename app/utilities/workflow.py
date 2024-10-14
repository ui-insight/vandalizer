#!/usr/bin/env python3

import openai
from pydantic import BaseModel
from dotenv import load_dotenv

from pypdf import PdfReader

from typing import List, Dict, Any

load_dotenv()


def llm_chat_model(prompt):
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content


def data_extraction_model(prompt):
    print("Prompt", prompt)
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
    output = output.replace("\\n", "")
    output = output.replace("=json", "")
    output = output.replace("=", "")
    return output


class Node:
    def __init__(self, name):
        self.name = name
        self.inputs = {}
        self.outputs = {}

    def process(self, inputs):
        raise NotImplementedError


class ChooseFileNode(Node):
    def __init__(self, data):
        super().__init__("Choose File")
        self.output = data.get("filename", "selected_file.txt")

    def process(self, inputs=None):
        return {"output": self.output}


class DocumentNode(Node):
    def __init__(self, data):
        super().__init__("Document")
        self.filename = data.get("filename", "Document content")
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

        return {"output": self.content}


class DataExtractionNode(Node):
    def __init__(self, data):
        super().__init__("Data Extraction")
        self.field = data.get("field", "Extraction field")

    def process(self, inputs):
        text = inputs.get("output", None)
        if text is None:
            return {"output": None}
        extraction_response = data_extraction_model(text)
        return {"output": extraction_response}


class LLMChatNode(Node):
    def __init__(self, data):
        super().__init__("LLM Chat")
        self.prompt = data.get("prompt", "Enter prompt")

    def process(self, inputs):
        data = inputs.get("output", None)
        self.prompt = f"{self.prompt} \n{data}"
        print("Prompt", self.prompt)
        chat_response = llm_chat_model(self.prompt)
        return {"output": chat_response}


# TODO track the execution of the workflow. The various steps, etc. Maybe return a list of steps executed
class WorkflowEngine:
    def __init__(self):
        self.nodes = []
        self.connections = []

    def add_node(self, node):
        self.nodes.append(node)

    def connect(self, from_node, to_node):
        self.connections.append((from_node, to_node))

    def execute(self):
        data = {}
        print("nodes", [node.name for node in self.nodes])
        print("connections", self.connections)
        if len(self.connections) == 0:
            for node in self.nodes:
                output = node.process(data)
                data.update(output)
        for connection in self.connections:
            from_node, to_node = connection
            input_data = from_node.process(data)
            data.update(input_data)
            output = to_node.process(data)
            data.update(output)

        # for node in self.nodes:
        #     inputs = {}
        #     for from_node, to_node in self.connections:
        #         if to_node == node:
        #             input_data = from_node.process(inputs)
        #             inputs.update(input_data)
        #     output = node.process(inputs)
        #     if node.name:
        #         data[node.name] = output
        #     else:
        #         print("No name for node", node)
        return data


def build_workflow(data):
    engine = WorkflowEngine()
    node_objects = {}

    for node_data in data["nodes"]:
        node_type = node_data["type"]
        node_id = node_data["id"]

        if node_type == "Choose File":
            node_objects[node_id] = ChooseFileNode(node_data["data"])
        elif node_type == "Document":
            node_objects[node_id] = DocumentNode(node_data["data"])
        elif node_type == "Data Extraction":
            node_objects[node_id] = DataExtractionNode(node_data["data"])
        elif node_type == "LLM Chat":
            node_objects[node_id] = LLMChatNode(node_data["data"])

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
