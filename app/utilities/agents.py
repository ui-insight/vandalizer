from dataclasses import dataclass
from pydantic import create_model
from typing import Dict, Optional, List, Any, Tuple, Union, List
import json
from app.utilities.llm_helpers import remove_code_markers

from pydantic_ai import RunContext, ModelRetry
from pydantic_ai.agent import Agent
from pydantic_ai.models.openai import OpenAIModel

from app.utilities.document_manager import DocumentManager

from langchain_redis import RedisCache
from devtools import debug
from app.utilities.async_utilities import function_event_loop_decorator

import os
from dotenv import load_dotenv

load_dotenv()

# Standard cache
# cache ttl is 1 month
ttl = 60 * 60 * 24 * 30
cache = RedisCache(redis_url="redis://localhost:6379", ttl=ttl)

langfuse_enabled = os.environ.get("LOG_ENABLED", "false").lower() == "true"
if langfuse_enabled:
    from langfuse import Langfuse

    langfuse = Langfuse()


@dataclass
class RagDeps:
    doc_manager: DocumentManager
    user_id: str


chat_prompt = "You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know."

# model = OpenAIModel("gpt-4o")
model = "openai:gpt-4o"

rag_agent = Agent(
    model,
    deps_type=RagDeps,
    system_prompt=chat_prompt,
)


chat_agent = Agent(
    model,
    system_prompt=chat_prompt,
)


@rag_agent.tool
def retrieve(context: RunContext[RagDeps], question: str, docs_ids: list[str] = []):
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
    model,
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
- Optional[str]
- Optional[int]
- Optional[float]
- Optional[bool]
- Optional[List[str]]
- Optional[List[int]]
- Optional[List[float]]

 CRITICAL:
1. Always make ALL fields Optional by default, as they might not appear in every document
2. Treat monetary values as strings, not floats.
3. Preserve ALL original formatting of numbers, including:
   - Keep ALL commas in numbers (e.g., "1,234,567")
   - Keep ALL currency symbols (e.g., "$1,234.56")
   - Keep ALL decimal places exactly as found
   - DO NOT convert formatted numbers into plain numbers
4. Extract values exactly as they appear in the text, without any modifications

Return a json object where keys are field names and values are the recommended type names and descriptions exactly as shown above. Do not convert floating numbers to integers and vice versa, or change the number of decimal places, or change numbers locale encoding. Preserve commas and other punctuation in the extracted text and numbers.
Consider making fields Optional if they might not always be present."""
    return prompt


type_mapping = {
    "str": (str, ...),
    "int": (int, ...),
    "float": (float, ...),
    "bool": (bool, ...),
    "List[str]": (List[str], ...),
    "List[int]": (List[int], ...),
    "List[float]": (List[float], ...),
    "Dict[str, str]": (Dict[str, str], ...),
    "Optional[str]": (str, None),
    "Optional[int]": (int, None),
    "Optional[float]": (float, None),
    "Optional[bool]": (bool, None),
    "Optional[List[str]]": (List[str], None),
    "Optional[List[int]]": (List[int], None),
    "Optional[List[float]]": (List[float], None),
}

reverse_type_mapping = {
    (str, ...): "str",
    (int, ...): "int",
    (float, ...): "float",
    (bool, ...): "bool",
    (List[str], ...): "List[str]",
    (List[int], ...): "List[int]",
    (List[float], ...): "List[float]",
    (Optional[str], None): "Optional[str]",
    (Optional[int], None): "Optional[int]",
    (Optional[float], None): "Optional[float]",
    (Dict[str, str], ...): "Dict[str, str]",
    (str, None): "Optional[str]",
    (int, None): "Optional[int]",
    (float, None): "Optional[float]",
    (bool, None): "Optional[bool]",
}


def get_cache_key(key: str, context: str) -> str:
    """Generate consistent cache key for a field"""
    return f"field_type:{key}:{context}"


@field_inference_agent.result_validator
def validate_fields_types(context: RunContext[FieldInferenceDeps], response: str):
    formatted_response = remove_code_markers(response)
    if langfuse_enabled:
        langfuse.trace(
            name="validate_fields_types",
            input=formatted_response,
        )

    try:
        inferred_fields = json.loads(formatted_response)
    except Exception as e:
        raise ModelRetry(f"Failed to parse type inference response: {str(e)}")

    # Modified validation logic
    fields = {}
    for key, type_str in inferred_fields.items():
        try:
            # Get type with fallback to Optional[str]
            field_type = type_mapping.get(type_str.strip(), (Optional[str], None))

            # Ensure Optional fields get None default
            if "Optional" in type_str:
                field_type = (field_type[0], None)

            fields[key] = field_type
        except Exception as e:
            if langfuse_enabled:
                langfuse.span(name="validation_error", input=e)
            raise ModelRetry(f"Invalid type for field {key}: {str(e)}")

    # Add fallback for missing keys (shouldn't happen but just in case)
    requested_keys = context.deps.keys
    for key in requested_keys:
        if key not in fields:
            fields[key] = (Optional[str], None)  # Default to optional string

    return fields


@dataclass
class ExtractionDeps:
    extraction_context: Optional[str]
    fields: Dict[str, tuple]
    text: str


# model = OllamaModel(
#     model_name="deepseek-r1:70b",
#     base_url="https://mindrouter-api.nkn.uidaho.edu",
# )

extraction_agent = Agent(
    model,
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
        "You are a precise entity extraction assistant. Extract only the requested information in a single execution. Be as faithful as possible during extraction and do not modify the extracted items. Do not integer to float and vice versa, or change the number of decimal places. Preserve commas and other punctuation in the extracted text and numbers. Extract all relevant entities from the text only if they are present. Return the extracted items in valid JSON format."
        'CRITICAL: Your response MUST be valid JSON with this exact format: {"entities": [...]}'
        "Each entity should be a complete object with all requested fields (use null for missing values)."
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


# @observe()
@function_event_loop_decorator()
def extract_entities_with_agent(text: str, keys: list[str], context: str = ""):
    """
    Extract entities from text based on the provided extraction keys and return structured output.

    Args:
        text: Input text to extract information from
        keys: List of fields to extract

    Returns:
        A JSON object with extracted entities
    """

    # check if previous extraction exists in cache
    cache_key = f"Keys:{keys}\n\nText:{text}"
    llm_string = "pydantic_model:openai:gpt-4o"

    cache_result = cache.lookup(cache_key, llm_string)
    if cache_result:
        result = json.loads(cache_result[0])
        print("Cache hit: ", cache_result, result)
        return result.get("entities", [])

    print("Cache miss")

    # field_inference_deps = FieldInferenceDeps(extraction_context=context, keys=keys)
    # fields = field_inference_agent.run_sync(
    #     "Infer the types of the keys", deps=field_inference_deps
    # ).data

    # ensure keys are a list of strings, otherwise split on comma
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",")]
    else:
        keys = [k.strip() for k in keys]

    # Individual field type caching
    inferred_fields = dict()
    uncached_keys = []

    # Check cache for each individual key
    for key in keys:
        key_cache_key = get_cache_key(key, context)
        cached = cache.lookup(key_cache_key, "field_inference")
        if cached:
            inferred_fields[key] = type_mapping.get(cached[0], (Any, ...))
        else:
            uncached_keys.append(key)

    # Process uncached keys in a single batch if any
    print("Uncached keys: ", len(uncached_keys), uncached_keys)
    print("Inferred fields: ", len(inferred_fields), inferred_fields)
    if uncached_keys:
        field_inference_deps = FieldInferenceDeps(
            extraction_context=context, keys=uncached_keys
        )
        new_fields = field_inference_agent.run_sync(
            "Infer the types of the keys", deps=field_inference_deps
        ).data

        # Cache newly inferred fields individually
        for key, field_type in new_fields.items():
            key_cache_key = get_cache_key(key, context)
            type_str = reverse_type_mapping.get(field_type, "Any")
            cache.update(key_cache_key, "field_inference", [type_str])

        inferred_fields.update(new_fields)

    # DynamicModel = create_model(
    #     "DynamicEntity",
    #     **{field_name: field_spec for field_name, field_spec in fields.items()},
    # )
    # ExtractionModel = create_model(
    #     "ExtractionModel", entities=(List[DynamicModel], ...)
    # )
    #
    # Proceed with entity extraction
    DynamicModel = create_model("DynamicEntity", **inferred_fields)
    ExtractionModel = create_model(
        "ExtractionModel", entities=(List[DynamicModel], ...)
    )

    extractor_agent = Agent(
        model,
        deps_type=ExtractionDeps,
        result_type=ExtractionModel,
        result_retries=3,
        retries=3,
    )

    extractor_deps = ExtractionDeps(
        extraction_context=context, fields=inferred_fields, text=text
    )
    try:
        debug(text)
        extraction = extractor_agent.run_sync(text, deps=extractor_deps)
        debug(extraction.data)

        result = extraction.data.model_dump_json(indent=2)
        debug(result)
        # cache the result
        cache.update(cache_key, llm_string, [result])
        result = json.loads(result)
        return result.get("entities", [])
    except AssertionError as e:
        # Extract the dictionary from the error message
        error_msg = str(e)
        debug(e)
        if error_msg.startswith("Expected code to be unreachable, but got: "):
            try:
                # Try to parse the dictionary from the error message
                entity_str = error_msg.replace(
                    "Expected code to be unreachable, but got: ", ""
                )
                # This may be incomplete JSON due to truncation in the error message
                # You might need a more robust approach to reconstruct it
                entity = json.loads(entity_str)
                debug(entity)
                return [entity]
            except:
                pass
        # If we can't recover, return empty results
        print(f"Error during extraction: {e}")
        return []
