"""Utilities for agents."""

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from devtools import debug
from dotenv import load_dotenv
from langchain_redis import RedisCache
from pydantic import create_model
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.agent import Agent

from app.models import SmartDocument
from app.utilities.async_utilities import function_event_loop_decorator
from app.utilities.document_manager import DocumentManager
from app.utilities.llm import remove_code_markers

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")

# Standard cache
# cache ttl is 1 month
ttl = 60 * 60 * 24 * 30
cache = RedisCache(redis_url=f"redis://{REDIS_HOST}:6379/0", ttl=ttl)

langfuse_enabled = os.environ.get("LOG_ENABLED", "false").lower() == "true"
if langfuse_enabled:
    from langfuse import Langfuse

    langfuse = Langfuse()


@dataclass
class RagDeps:
    doc_manager: DocumentManager
    user_id: str
    documents: list[SmartDocument]


chat_prompt = "You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know."

# @ model = OpenAIModel("gpt-4o")
model = "openai:gpt-4o"

rag_agent = Agent(
    model,
    deps_type=RagDeps,
    system_prompt="""You are a specialized knowledge assistant powered by retrieval-augmented generation.

When responding to queries:
1. Carefully analyze the retrieved context documents for relevance to the query
2. Synthesize information across multiple context fragments when appropriate
3. Quote or paraphrase the retrieved information with precise attribution (e.g., "According to Document 1...")
4. Maintain the original meaning and nuance from source documents
5. Identify and reconcile any contradictions between different sources
6. Distinguish between factual statements from the context and your own reasoning

Response guidelines:
- Begin with a direct answer to the question when possible
- Structure complex answers with clear headings or numbered points
- Highlight key information using formatting when helpful
- Include relevant examples or illustrations from the context
- Acknowledge information gaps explicitly rather than extrapolating
- If retrieved context is insufficient, clearly state "Based on the provided context, I cannot fully answer this question" and explain what information is missing

Never fabricate information beyond what is provided in the context. If the retrieved context doesn't contain the necessary information, acknowledge the limitations of your knowledge and suggest what additional information might be needed.""",
)

chat_agent = Agent(
    "openai:gpt-4o",
    system_prompt="""You are an engaging conversational assistant designed to provide helpful, informative, and friendly responses.

Your communication style:
- Warm and approachable while maintaining professionalism
- Concise but thorough - prioritize clarity over length
- Personalized to the user's tone and level of formality
- Balances helpfulness with respect for user autonomy

When responding:
1. Address the user's specific question or need first
2. Provide relevant context or background when helpful
3. If uncertain, acknowledge limitations rather than guessing
4. For complex topics, break information into digestible segments
5. Use natural, conversational language (contractions, varied sentence structure)
6. When appropriate, ask thoughtful follow-up questions to clarify or deepen the conversation

Content guidelines:
- Cite sources for factual claims when possible
- Present balanced perspectives on nuanced topics
- Avoid unnecessary jargon unless the conversation indicates technical expertise
- Respect privacy and security best practices

Remember that your goal is to be genuinely helpful while creating an engaging, natural conversation that adapts to the user's needs and communication style.""",
)

prompt_agent = Agent(
    "openai:gpt-4o",
    system_prompt="""You are a specialized prompt engineer focused on retrieval augmentation. Your task is to convert user questions into optimal search prompts for querying vector databases.

When generating search prompts:
1. Extract key entities, overview, main points, ideas, project details, concepts, and relationships from the user's question
2. Include relevant synonyms and alternative phrasings to increase recall
3. Remove conversational fillers and personal pronouns
4. Prioritize domain-specific terminology when present
5. Structure the prompt with the most important search terms first
6. Include any contextual constraints (time periods, locations, etc.)
7. Keep the prompt concise (under 100 words) but comprehensive
8. Format technical terms precisely as they would appear in documentation

Do not:
- Include explanations or reasoning in your response
- Ask clarifying questions
- Provide answers to the user's question
- Include special operators or syntax unless specified

Your output should be the search prompt only, with no additional text.""",
)


chat_agent = Agent(
    model,
    system_prompt=chat_prompt,
)


@rag_agent.tool
def retrieve(
    context: RunContext[RagDeps],
    question: str,
    docs_ids: Optional[list[str]] = None,
):
    """Retrieve documents for a given question
    Args:
        context: The call context
        question: The question of the user
        docs_ids: A list of document IDs to search in (optional).

    Returns:
        A list of documents that match the question

    """
    if docs_ids is None:
        docs_ids = []
    prompt_response = prompt_agent.run_sync(
        f"Generate a prompt for the following user question: {question}",
    )
    prompt = prompt_response.output
    debug(prompt)

    results = context.deps.doc_manager.query_documents(
        context.deps.user_id,
        prompt,
        docs_ids,
        k=10,
    )
    if len(results) == 0:
        # check if the document was added to the vectorstore
        non_existent_docs = []
        for doc in context.deps.documents:
            if not context.deps.doc_manager.document_exists(
                context.deps.user_id,
                doc.uuid,
            ):
                non_existent_docs.append(doc)
                absolute_path = doc.absolute_path
                debug(
                    "Recreating vectorstore",
                    context.deps.documents,
                    non_existent_docs,
                )
                context.deps.doc_manager.add_document(
                    user_id=context.deps.user_id,
                    doc_path=absolute_path,
                    document_name=doc.title,
                    document_id=doc.uuid,
                )
        debug(context.deps.documents[0].raw_text[:100])
        if len(non_existent_docs) > 0:
            results = context.deps.doc_manager.query_documents(
                context.deps.user_id,
                question,
                docs_ids,
            )

    debug(results)
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
    output_type=dict[str, str],
    system_prompt="You are a data modeling expert. Infer appropriate data types for fields based on their names and context. Return only valid json.",
)


@field_inference_agent.system_prompt
def field_inference_system_prompt(context: RunContext[FieldInferenceDeps]) -> str:
    keys = context.deps.keys
    prompt_context = context.deps.extraction_context
    return f"""Given these field names{" and prompt_context" if prompt_context else ""}:

Field names:
{json.dumps(keys, indent=2)}

{f"Context: {context}" if context else ""}

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


type_mapping = {
    "str": (str, ...),
    "int": (int, ...),
    "float": (float, ...),
    "bool": (bool, ...),
    "List[str]": (list[str], ...),
    "List[int]": (list[int], ...),
    "List[float]": (list[float], ...),
    "Dict[str, str]": (dict[str, str], ...),
    "Optional[str]": (str, None),
    "Optional[int]": (int, None),
    "Optional[float]": (float, None),
    "Optional[bool]": (bool, None),
    "Optional[List[str]]": (list[str], None),
    "Optional[List[int]]": (list[int], None),
    "Optional[List[float]]": (list[float], None),
}

reverse_type_mapping = {
    (str, ...): "str",
    (int, ...): "int",
    (float, ...): "float",
    (bool, ...): "bool",
    (list[str], ...): "List[str]",
    (list[int], ...): "List[int]",
    (list[float], ...): "List[float]",
    (Optional[str], None): "Optional[str]",
    (Optional[int], None): "Optional[int]",
    (Optional[float], None): "Optional[float]",
    (dict[str, str], ...): "Dict[str, str]",
    (str, None): "Optional[str]",
    (int, None): "Optional[int]",
    (float, None): "Optional[float]",
    (bool, None): "Optional[bool]",
}


def get_cache_key(key: str, context: str) -> str:
    """Generate consistent cache key for a field."""
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
        msg = f"Failed to parse type inference response: {e!s}"
        raise ModelRetry(msg)

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
            msg = f"Invalid type for field {key}: {e!s}"
            raise ModelRetry(msg)

    # Add fallback for missing keys (shouldn't happen but just in case)
    requested_keys = context.deps.keys
    for key in requested_keys:
        if key not in fields:
            fields[key] = (Optional[str], None)  # Default to optional string

    return fields


@dataclass
class ExtractionDeps:
    extraction_context: Optional[str]
    fields: dict[str, tuple]
    text: str


# model = OpenAIModel(
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


def filter_empty_entities(result: dict) -> list:
    """Filter out empty entities from the list.

    Args:
        result: The result dictionary containing entities

    Returns:
        Filtered list of entities

    """
    raw_entities = result.get("entities", [])

    def is_non_empty(e: dict) -> bool:
        if not isinstance(e, dict) or not e:
            return False
        return any(v not in (None, "", [], {}) for v in e.values())

    return [e for e in raw_entities if is_non_empty(e)]


# @observe()
@function_event_loop_decorator()
def extract_entities_with_agent(text: str, keys: list[str], context: str = ""):
    """Extract entities from text based on the provided extraction keys and return structured output.

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
        return result.get("entities", [])

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
    inferred_fields = {}
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
    if uncached_keys:
        field_inference_deps = FieldInferenceDeps(
            extraction_context=context,
            keys=uncached_keys,
        )
        new_fields = field_inference_agent.run_sync(
            "Infer the types of the keys",
            deps=field_inference_deps,
        ).output

        debug(new_fields)

        if isinstance(new_fields, str):
            try:
                new_fields = json.loads(new_fields)
            except json.JSONDecodeError:
                new_fields = {}
                # Handle the case where JSON parsing fails
                debug(
                    "Failed to parse field inference response as JSON.",
                    new_fields,
                    field_inference_deps,
                )

        elif isinstance(new_fields, dict):
            # Cache newly inferred fields individually
            for key, field_type in new_fields.items():
                key_cache_key = get_cache_key(key, context)
                type_str = reverse_type_mapping.get(field_type, "Any")
                cache.update(key_cache_key, "field_inference", [type_str])
        else:
            # Handle the case where the response is not a dict
            debug(
                "Unexpected field inference response format.",
                new_fields,
                field_inference_deps,
            )
            new_fields = {}

        if isinstance(new_fields, dict):
            for key_name, key_type in new_fields.items():
                if key_name not in inferred_fields:
                    inferred_fields[key_name] = type_mapping.get(key_type, (Any, ...))

    debug(inferred_fields)
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
        "ExtractionModel",
        entities=(list[DynamicModel], ...),
    )

    extractor_agent = Agent(
        model,
        deps_type=ExtractionDeps,
        result_type=ExtractionModel,
        result_retries=3,
        retries=3,
    )

    extractor_deps = ExtractionDeps(
        extraction_context=context,
        fields=inferred_fields,
        text=text,
    )
    try:
        debug(text)
        extraction = extractor_agent.run_sync(text, deps=extractor_deps)
        debug(extraction.output)

        result = extraction.output.model_dump_json(indent=2)
        debug(result)

        result = json.loads(result)
        filtered_entities = []
        # cache the result if it is not empty
        if result and "entities" in result and len(result["entities"]) > 0:
            filtered_entities = filter_empty_entities(
                result,
            )
            if filtered_entities and len(filtered_entities) > 0:
                cache.update(cache_key, llm_string, [json.dumps(result)])
        return filtered_entities
    except AssertionError as e:
        # Extract the dictionary from the error message
        error_msg = str(e)
        debug(e)
        if error_msg.startswith("Expected code to be unreachable, but got: "):
            try:
                # Try to parse the dictionary from the error message
                entity_str = error_msg.replace(
                    "Expected code to be unreachable, but got: ",
                    "",
                )
                # This may be incomplete JSON due to truncation in the error message
                # You might need a more robust approach to reconstruct it
                entity = json.loads(entity_str)
                debug(entity)
                return [entity]
            except:
                pass
        # If we can't recover, return empty results
        return []
