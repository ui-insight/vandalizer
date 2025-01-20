from dataclasses import dataclass
from langfuse.decorators import observe
from langfuse import Langfuse
from pydantic import create_model
from typing import Dict, Optional, List, Any, Tuple, Union, List
import json
from app.utilities.llm_helpers import remove_code_markers

from pydantic_ai import RunContext, ModelRetry
from pydantic_ai.agent import Agent

from app.utilities.document_manager import DocumentManager

langfuse = Langfuse()


@dataclass
class RagDeps:
    doc_manager: DocumentManager
    user_id: str


rag_agent = Agent(
    "openai:gpt-4o",
    deps_type=RagDeps,
    system_prompt="You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know.",
)


@rag_agent.tool
async def retrieve(
    context: RunContext[RagDeps], question: str, docs_ids: list[str] = []
):
    """
    Retrieve documents for a given question
    Args:
        context: The call context
        question: The question of the user
        docs_ids: A list of document IDs to search in (optional)

    Returns:
        A list of documents that match the question
    """
    results = context.deps.doc_manager.query_documents(
        context.deps.user_id, question, docs_ids
    )
    content = "Context: \n"
    for result in results:
        if result.get("metadata") is not None:
            content += f"Document title: {result['metadata'].get('document_name')}\n"
        content += f"Document content: {result['content']}\n\n"
    return content


@dataclass
class FieldInferenceDeps:
    extraction_context: Optional[str]
    keys: list[str]


field_inference_agent = Agent(
    "openai:gpt-4o",
    retries=3,
    deps_type=FieldInferenceDeps,
    system_prompt="You are a data modeling expert. Infer appropriate data types for fields based on their names and context. Return only valid json.",
)


@field_inference_agent.system_prompt
def field_inference_system_prompt(context: RunContext[FieldInferenceDeps]):
    keys = context.deps.keys
    prompt_context = context.deps.extraction_context
    prompt = f"""Given these field names{' and prompt_context' if prompt_context else ''}:

Field names:
{json.dumps(keys, indent=2)}

{f'Context: {context}' if context else ''}

For each field, determine the most appropriate data type and description from these options:
- str
- int
- float
- bool
- List[str]
- List[int]
- List[float]
- Optional[str]
- Optional[int]
- Optional[float]
- Optional[bool]

 CRITICAL:
1. Treat monetary values as strings, not floats.
2. Preserve ALL original formatting of numbers, including:
   - Keep ALL commas in numbers (e.g., "1,234,567")
   - Keep ALL currency symbols (e.g., "$1,234.56")
   - Keep ALL decimal places exactly as found
   - DO NOT convert formatted numbers into plain numbers
3. Extract values exactly as they appear in the text, without any modifications

Return a json object where keys are field names and values are the recommended type names and descriptions exactly as shown above. Do not convert floating numbers to integers and vice versa, or change the number of decimal places, or change numbers locale encoding. Preserve commas and other punctuation in the extracted text and numbers.
Consider making fields Optional if they might not always be present."""
    return prompt


@field_inference_agent.result_validator
def validate_fields_types(context: RunContext[FieldInferenceDeps], response: str):
    formatted_response = remove_code_markers(response)
    print("response: ", formatted_response)
    langfuse.trace(
        name="validate_fields_types",
        input=formatted_response,
    )
    inferred_fields = dict()
    try:
        inferred_fields = json.loads(formatted_response)
    except Exception as e:
        raise ModelRetry(f"Failed to parse type inference response: {str(e)}")
    type_mapping = {
        "str": (str, ...),
        "int": (int, ...),
        "float": (float, ...),
        "bool": (bool, ...),
        "List[str]": (List[str], ...),
        "List[int]": (List[int], ...),
        "List[float]": (List[float], ...),
        "Dict[str, str]": (Dict[str, str], ...),
        "Optional[str]": (Optional[str], ...),
        "Optional[int]": (Optional[int], ...),
        "Optional[float]": (Optional[float], ...),
        "Optional[bool]": (Optional[bool], ...),
    }

    print("inferred_fields: ", inferred_fields)

    fields = dict()
    try:
        fields = {
            key: type_mapping.get(type_str.strip(), (Any, ...))
            for key, type_str in inferred_fields.items()
        }
    except Exception as e:
        langfuse.span(name="validation_error", input=e)
        raise ModelRetry(f"Failed to parse type inference response: {str(e)}")

    return fields


@dataclass
class ExtractionDeps:
    extraction_context: Optional[str]
    fields: Dict[str, tuple]
    text: str


extraction_agent = Agent(
    "openai:gpt-4o",
    deps_type=ExtractionDeps,
    retries=3,
)


@extraction_agent.system_prompt
def extraction_system_prompt(
    context: RunContext[ExtractionDeps],
):
    text = context.deps.text
    fields = context.deps.fields
    field_descriptions = [
        f"- {field}: {field_type[0]}" for field, field_type in fields.items()
    ]
    field_str = "\n".join(field_descriptions)

    multiple_entity_instruction = (
        "\n\nImportant: Extract ALL relevant entities from the text only if it is present. "
        "Return a JSON array of objects, where each object represents a distinct entity. "
        "If no multiple entities are found, return a single-item array."
    )

    system_prompt = (
        "You are a precise entity extraction assistant. Extract only the requested information in a single execution. Be as faithful as possible during extraction and do not modify the extracted items. Do not integer to float and vice versa, or change the number of decimal places. Preserve commas and other punctuation in the extracted text and numbers. Extract all relevant entities from the text only if they are present. Return the extracted items in valid JSON format.",
    )

    return (
        f"""
{system_prompt}
Extract the following information from the text below only if it is present:

{field_str}

Return the information in JSON format and be as precise as possible{multiple_entity_instruction}

Text:
{text}""",
    )


@observe()
def extract_entities_with_agent(text: str, keys: list[str], context: str = ""):
    """
    Extract entities from text based on the provided extraction keys and return structured output.

    Args:
        text: Input text to extract information from
        keys: List of fields to extract

    Returns:
        A JSON object with extracted entities
    """
    field_inference_deps = FieldInferenceDeps(extraction_context=context, keys=keys)
    fields = field_inference_agent.run_sync(
        "Infer the types of the keys", deps=field_inference_deps
    ).data

    DynamicModel = create_model(
        "DynamicEntity",
        **{field_name: field_spec for field_name, field_spec in fields.items()},
    )
    ExtractionModel = create_model(
        "ExtractionModel", entities=(List[DynamicModel], ...)
    )

    extractor_agent = Agent(
        "openai:gpt-4o",
        deps_type=ExtractionDeps,
        result_type=ExtractionModel,
        result_retries=3,
        retries=3,
    )

    extractor_deps = ExtractionDeps(
        extraction_context=context, fields=fields, text=text
    )
    extraction = extractor_agent.run_sync(text, deps=extractor_deps)

    result = extraction.data.model_dump_json(indent=2)
    print("Result: ", result)
    result = json.loads(result)
    return result.get("entities", [])
