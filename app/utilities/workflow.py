#!/usr/bin/env python3

import asyncio
import graphlib
import json
import multiprocessing
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, NoReturn

import chromadb
from chromadb.config import Settings
from devtools import debug
from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from app import app
from app.celery_worker import celery_app
from app.models import (
    SearchSet,
    SmartDocument,
    Workflow,
    WorkflowResult,
    WorkflowStep,
)
from app.utilities.agents import create_chat_agent
from app.utilities.extraction_manager3 import ExtractionManager3
from app.utilities.openai_interface import (
    OpenAIInterface,
)

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


def llm_chat_model(model, prompt, data=None, docs=None):
    if docs is None:
        docs = []
    open_ai_interface = OpenAIInterface()
    output = None
    debug(model)
    if len(docs) == 0:
        full_text = json.dumps(data)
        output_prompt = f"""Following the instruction and output your answer as a nicely formatted html to display in a web interface chat bot. The html tags should fit nicely in a div on the page and not break formatting. Do not include newline break and quotes that break the formatting. Do not show ```html before the html.\n\nInstruction: {prompt}\n\n {full_text}"""
        chat_agent = create_chat_agent(model)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(chat_agent.run(output_prompt))
        output = result.output
        debug(f"Output from chat agent: {output}")
        output = format_llm_output(output).strip()

    else:
        output = open_ai_interface.ask_question_to_documents(
            model=model,
            root_path=app.root_path,
            documents=docs,
            question=prompt,
        )
        output = output.get("answer", "")
        debug(f"Output from chat agent: {output}")
        output = format_llm_output(output)
        debug(output)
    return output


def data_extraction_model(model, keys, documents=[], full_text=None):
    output = None
    extraction_manager = ExtractionManager3()
    document_uuids = []
    for doc in documents:
        if doc is None:
            continue
        if isinstance(doc, str):
            document_uuids.append(doc)
        else:
            document_uuids.append(doc.uuid)
    output = extraction_manager.extract(keys, document_uuids, full_text=full_text)

    debug(output)
    prompt = "Format the extracted data as a nicely formatted html with the extracted data as bullet points. Do not include newline break and quotes that break the formatting. Do not show ```html before the html."
    prompt += "\n\n"
    prompt += json.dumps(output, indent=4)
    loop = asyncio.new_event_loop()

    chat_agent = create_chat_agent(model)
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(chat_agent.run(prompt))
    return result.output


def format_model(model, formatting_prompt, text):
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
    chat_agent = create_chat_agent(model)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(chat_agent.run(prompt))
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
            result_output = result.get("output", None)
            # add the step name to the output
            if result_output is None:
                continue
            elif isinstance(result_output, str):
                output["output"].append(result_output)
            else:
                output["output"].extend(result_output)

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
            self.docs_uuids.append(doc.uuid)

        for doc in self.docs:
            if doc is None:
                continue
            self.docs_uuids.append(doc.uuid)

        debug(self.docs[0])
        debug(self.pdf_paths)
        debug(self.docs_uuids)

    def process(self, inputs=None):
        # data = inputs.get("data", None)

        return {"step_name": self.name, "output": self.docs_uuids, "input": None}


class FormatNode(Node):
    def __init__(self, data) -> None:
        super().__init__("Formatter")
        self.data = data
        self.model = data.get("model")

    def process(self, inputs):
        formatting_prompt = self.data.get("prompt", "")

        data = inputs.get("output", None)
        prev_step_name = inputs.get("step_name", None)
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
        return {"output": output, "input": prompt, "step_name": self.name}


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
        data = self.data
        debug(data)
        keys = self.data.get("searchphrases", [])
        if len(keys) == 0:
            keys = data.get("keys", [])

        prev_step_name = inputs.get("step_name", None)

        debug("Extraction", inputs, keys, data)

        step_input = None
        docs_uuids = []
        user_id = self.user_id
        extraction_response = None
        if prev_step_name == "Document":
            docs_uuids = inputs.get("output", None)
            step_input = docs_uuids
            extraction_response = data_extraction_model(self.model, keys, docs_uuids)
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
            )
        elif prev_step_name in {"Extraction", "Formatter"}:
            step_input = inputs.get("output", None)
            extraction_response = data_extraction_model(
                self.model,
                keys,
                docs_uuids,
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
        self.user_id = data.get("user_id", "0")
        self.model = data.get("model")

    def process(self, inputs):
        data = self.data
        prompt = data.get("prompt", "Enter prompt")
        print(f"INPUTS ARE {inputs}")

        prev_step_name = inputs.get("step_name", None)
        debug("Prompt", inputs, prompt)
        chat_response = None
        if prev_step_name == "Document":
            docs_uuids = inputs.get("output", None)
            docs = []
            for doc_uuid in docs_uuids:
                doc = SmartDocument.objects(uuid=doc_uuid).first()
                if doc is not None:
                    docs.append(doc)

            chat_response = llm_chat_model(model=self.model, docs=docs, prompt=prompt)
        else:
            data = inputs.get("output", None)

            chat_response = llm_chat_model(
                model=self.model,
                docs=[],
                prompt=prompt,
                data=data,
            )
        return {"output": chat_response, "input": prompt, "step_name": self.name}


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
                    debug(output)
                    task_output = output.get("output", "")
                    # add the input and the step_name to the output
                    node_output = output.get("output", "")
                    if isinstance(task_output, list):
                        node_outputs.extend(node_output)
                    else:
                        node_outputs.append(node_output)

                # combine the outputs
                debug(node_outputs)
                latest_output = {
                    "output": node_outputs,
                    "input": output.get("input", ""),
                    "step_name": output.get("step_name", ""),
                }
                # debug(latest_output)

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
        return latest_output.get("output"), data


def build_workflow_engine(steps, workflow, model, user_id=None):
    engine = WorkflowEngine()
    nodes = []

    for idx, step in enumerate(steps):
        # node_id = uuid4().hex
        node = None
        debug(step.name, step.data)
        if step.name == "Document":  # this the trigger step
            node = DocumentNode(step.data)
            nodes.append(node)
        else:  # this a task step
            tasks = []
            for task in step.tasks:
                debug(task)
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

            node = MultiTaskNode(step.name)
            node.add_tasks(tasks)
            nodes.append(node)
            debug(step.tasks)

        if node is not None:
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
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )

    def _extract_workflow_context(
        self, workflow: Workflow, workflow_trigger_step: WorkflowStep
    ) -> Dict[str, Any]:
        """Extract comprehensive context from workflow and trigger step for embedding."""

        # Extract document context from trigger step
        trigger_docs = workflow_trigger_step.data.get("docs", [])
        doc_context = []

        for doc in trigger_docs:
            if hasattr(doc, "title") and hasattr(doc, "content"):
                doc_info = {
                    "title": doc.title,
                    "content_preview": doc.content[:500] if doc.content else "",
                    "document_type": getattr(doc, "document_type", "unknown"),
                    "tags": getattr(doc, "tags", []),
                }
                doc_context.append(doc_info)

        return {
            "workflow_id": str(workflow.id),
            "workflow_name": workflow.name,
            "workflow_description": workflow.description or "",
            "trigger_documents": doc_context,
            "user_id": workflow.user_id,
            "space": workflow.space or "",
            "num_executions": workflow.num_executions,
            "created_at": workflow.created_at.isoformat()
            if workflow.created_at
            else None,
        }

    def _create_searchable_text(self, context: Dict[str, Any]) -> str:
        """Create searchable text representation of workflow context."""

        text_parts = []

        # Workflow metadata
        text_parts.append(f"Workflow: {context['workflow_name']}")
        if context["workflow_description"]:
            text_parts.append(f"Description: {context['workflow_description']}")

        # Document context
        if context["trigger_documents"]:
            text_parts.append("Document Types:")
            for doc in context["trigger_documents"]:
                text_parts.append(f"- {doc['title']} ({doc['document_type']})")
                if doc["content_preview"]:
                    text_parts.append(f"  Content: {doc['content_preview']}")
                if doc["tags"]:
                    text_parts.append(f"  Tags: {', '.join(doc['tags'])}")

        # Workflow steps
        if context["workflow_steps"]:
            text_parts.append("Workflow Steps:")
            for i, step in enumerate(context["workflow_steps"], 1):
                text_parts.append(f"{i}. {step['name']}")

                # Add step data context
                if step["data"]:
                    for key, value in step["data"].items():
                        if isinstance(value, (str, int, float, bool)):
                            text_parts.append(f"   {key}: {value}")

                # Add task context
                for task in step["tasks"]:
                    text_parts.append(f"   Task: {task['name']}")
                    if task["data"]:
                        for key, value in task["data"].items():
                            if isinstance(value, (str, int, float, bool)):
                                text_parts.append(f"     {key}: {value}")

        return "\n".join(text_parts)

    def ingest_workflow(self, workflow_id: str, ingestion_text: str) -> Dict[str, Any]:
        """Ingest (or upsert) a workflow into the vector store, averaging embeddings on each run."""
        try:
            workflow = Workflow.objects(id=workflow_id).first()
            if not workflow:
                return {"status": "error", "error": "Workflow not found"}

            new_embedding = self.embeddings.embed_query(ingestion_text)
            doc_id = f"{workflow_id}"

            # 1) Fetch any existing record
            existing = self.collection.get(
                ids=[doc_id], include=["embeddings", "metadatas"]
            )

            # 2) Decide: update vs. add
            if existing.get("ids"):
                # We have an old record → average embeddings
                old_embed = existing["embeddings"][0]
                meta = existing["metadatas"][0] or {}
                old_count = meta.get("num_executions", 1)

                new_count = old_count + 1
                avg_embed = [
                    (oe * old_count + ne) / new_count
                    for oe, ne in zip(old_embed, new_embedding)
                ]

                updated_meta = {
                    **meta,
                    "num_executions": new_count,
                }

                self.collection.update(
                    ids=[doc_id],
                    embeddings=[avg_embed],
                    documents=[ingestion_text],
                    metadatas=[updated_meta],
                )

            else:
                # No existing record → add fresh
                new_count = 1
                initial_meta = {
                    "workflow_id": workflow_id,
                    "workflow_name": workflow.name,
                    "user_id": workflow.user_id,
                    "space": workflow.space or "",
                    "num_executions": new_count,
                }
                self.collection.add(
                    embeddings=[new_embedding],
                    documents=[ingestion_text],
                    metadatas=[initial_meta],
                    ids=[doc_id],
                )

            return {
                "status": "success",
                "document_id": doc_id,
                "workflow_id": workflow_id,
                "message": f"Upserted workflow '{workflow.name}', run #{new_count}",
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def search_workflow_recommendations(
        self,
        selected_documents: List[SmartDocument],
        user_id: str = None,
        space: str = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for workflow recommendations based on selected documents."""

        min_similarity = 0.9

        try:
            # Create search context from selected documents
            search_text = ""
            search_text += "Documents selected:"

            print("Number of items in chroma database: ")
            print(self.collection.count())

            for doc in selected_documents:
                search_text += f"\n{doc.raw_text}"

            # Generate embedding for search
            search_embedding = self.embeddings.embed_query(search_text)

            # Build query filters
            where_filters = {}
            # if user_id:
            #     where_filters["user_id"] = user_id
            # if space:
            #     where_filters["space"] = space

            # Search vector database
            results = self.collection.query(
                query_embeddings=[search_embedding],
                n_results=limit,
                where=where_filters if where_filters else None,
                include=["metadatas", "documents", "distances"],
            )

            recommendations = []
            if results and results["ids"]:
                for i, doc_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i]
                    distance = results["distances"][0][i]
                    similarity_score = 1 - distance  # Convert distance to similarity
                    debug(f"Similarity score for document {doc_id}: {similarity_score}")
                    if similarity_score < min_similarity:
                        continue
                    # Parse context from metadata
                    context = json.loads(metadata.get("context", "{}"))

                    recommendation = {
                        "workflow_id": metadata["workflow_id"],
                        "similarity_score": similarity_score,
                        "user_id": metadata["user_id"],
                        "space": metadata.get("space", ""),
                        "num_executions": metadata.get("num_executions", 0),
                        "created_at": metadata.get("created_at"),
                        "context": context,
                    }
                    recommendations.append(recommendation)

            print(recommendations)
            return recommendations

        except Exception as e:
            print(f"Error searching workflow recommendations: {str(e)}")
            return []


@celery_app.task(name="workflow.ingestion")
def workflow_ingestion_task(workflow_id: str, ingestion_text: str) -> Dict[str, Any]:
    """Celery task to ingest workflow into vector database."""

    try:
        # Initialize workflow manager
        persist_directory = Path("data/workflows_vectordb")  # Configure as needed
        workflow_manager = WorkflowManager(persist_directory=persist_directory)

        # Ingest workflow
        result = workflow_manager.ingest_workflow(
            workflow_id=workflow_id,
            ingestion_text=ingestion_text,
        )

        print(f"Workflow ingestion task completed: {result}")
        return result

    except Exception as e:
        error_msg = f"Error in workflow ingestion task: {str(e)}"
        print(error_msg)
        return {"status": "error", "error": error_msg}


@celery_app.task(bind=True, name="workflow.execute_workflow")
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

    engine = build_workflow_engine(steps, workflow, model, user_id=workflow.user_id)

    final_output, data = engine.execute(workflow_result)
    debug(final_output)
    workflow_result.final_output = dict(output=final_output, data=data)
    workflow_result.status = "completed"
    workflow_result.save()
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


@celery_app.task(bind=True, name="workflow.execute_workflow_step_test")
def execute_task_step_test(self, task_name, task_data, document_trigger_step_id):
    process_node = None
    latest_output = None
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

    final_output, data = engine.execute()
    print(final_output)

    return final_output
