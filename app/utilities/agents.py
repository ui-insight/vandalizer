"""Utilities for agents."""

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from devtools import debug
from dotenv import load_dotenv
from langchain_redis import RedisCache
from pydantic import BaseModel, create_model
from pydantic_ai import RunContext
from pydantic_ai.agent import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.openai import (
    OpenAIJsonSchemaTransformer,
    OpenAIModelProfile,
    openai_model_profile,
)
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.models import SmartDocument, SystemConfig
from app.utilities.config import get_default_model_name, settings
from app.utilities.document_manager import DocumentManager

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Standard cache
# cache ttl is 1 month
ttl = 60 * 60 * 24 * 30
cache = RedisCache(redis_url=f"redis://{REDIS_HOST}:6379/0", ttl=ttl)

langfuse_enabled = os.environ.get("LOG_ENABLED", "false").lower() == "true"
if langfuse_enabled:
    from langfuse import Langfuse

    langfuse = Langfuse()


# Cache dictionaries for agents to prevent context leaks
# These MUST be defined before any agent creation functions are called
_chat_agent_cache = {}
_rag_agent_cache = {}
_prompt_agent_cache = {}
_upload_agent_cache = {}
_extraction_agent_cache = {}

DEFAULT_CHAT_SYSTEM_PROMPT = """You are an engaging conversational assistant designed to provide helpful, informative, and friendly responses.

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

Next-Step Guidance
- Only ask clarifying questions when strictly necessary to proceed or prevent errors.
- End with one short, action-oriented “next step?” line only when appropriate.
- The next step must be tailored, concrete, valuable, and ≤ 16 words, phrased as a question.
- If confidence is low, prefer a quick validation step.
- If an action depends on missing input, ask for the single most critical item.
- You may offer at most one lightweight alternative in parentheses.

Allowed forms (pick exactly one):
1) "Want me to <do X>?"
2) "Next step: <single concrete action>?"
3) "Should we <validate/compare/prioritize> next?"
4) "Do you want <A> (or <B>)?"

Anti-patterns (never do):
- Don’t restate your whole answer in the next step.
- Don’t propose multi-step plans; keep it to one step.
- Don’t ask vague things like "Need anything else?"
"""

DEFAULT_CHAT_SYSTEM_PROMPT_NO_NEXT = """You are an engaging conversational assistant designed to provide helpful, informative, and friendly responses.

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

Keep responses focused on the user’s question with no forced next-step suggestion.
"""


def get_default_system_prompt(include_next_step: bool = True) -> str:
    return (
        DEFAULT_CHAT_SYSTEM_PROMPT
        if include_next_step
        else DEFAULT_CHAT_SYSTEM_PROMPT_NO_NEXT
    )


def _get_model_config(model_name: str) -> Optional[dict]:
    """Get model configuration from SystemConfig by model name."""
    try:
        config = SystemConfig.get_config()
        if config and config.available_models:
            for model in config.available_models:
                if model.get("name") == model_name:
                    return model
    except Exception:
        pass
    return None


def _get_model_endpoint(model_name: str) -> str:
    """Get the endpoint URL for a specific model, falling back to default if not set."""
    model_config = _get_model_config(model_name)
    if model_config and model_config.get("endpoint"):
        endpoint = model_config.get("endpoint", "").strip()
        if endpoint:
            return endpoint
    
    # Fallback to default LLM endpoint
    from app.utilities.config import get_llm_endpoint
    return get_llm_endpoint()


def _detect_api_protocol(model_name: str, model_config: Optional[dict] = None) -> str:
    """
    Detect API protocol based on model name and configuration.
    Returns: "openai", "ollama", or "vllm"
    """
    if model_config and model_config.get("api_protocol"):
        protocol = model_config.get("api_protocol", "").strip().lower()
        if protocol in ["openai", "ollama", "vllm"]:
            return protocol
    
    # Auto-detect based on model name patterns
    model_lower = model_name.lower()
    
    # OpenAI models typically have "gpt" or "openai/" prefix
    if "openai/" in model_name or model_name.startswith("gpt-") or "claude" in model_lower:
        return "openai"
    
    # Ollama models typically don't have "/" and are simple names
    if "/" not in model_name and not model_name.startswith("http"):
        return "ollama"
    
    # VLLM models might have specific patterns
    if "vllm" in model_lower or model_name.startswith("vllm/"):
        return "vllm"
    
    # Default to OpenAI-compatible for unknown models
    return "openai"


def get_model_api_protocol(model_name: str) -> str:
    """Public helper to determine API protocol for a model."""
    model_config = _get_model_config(model_name)
    return _detect_api_protocol(model_name, model_config)



class InsightAIProvider(OpenRouterProvider):
    """Custom OpenRouter provider for UIdaho Insight AI server."""

    def __init__(self, api_key: str, thinking_enabled: bool = False, endpoint: Optional[str] = None):
        # Set endpoint before calling super().__init__() because base_url property is accessed during initialization
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        if hasattr(self, '_endpoint') and self._endpoint:
            return self._endpoint
        return "https://mindrouter-api.nkn.uidaho.edu/v1"

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        # Special handling for Ollama models, those that do not contain "/" in the name
        if "/" not in model_name:
            profile = openai_model_profile(model_name)
            model_profile = OpenAIModelProfile(
                json_schema_transformer=OpenAIJsonSchemaTransformer
            ).update(profile)
            
            # Disable thinking if the model doesn't support it
            if not self.thinking_enabled:
                try:
                    if hasattr(model_profile, 'model_copy'):
                        model_profile = model_profile.model_copy(update={
                            "supports_thinking": False
                        })
                    elif hasattr(model_profile, 'supports_thinking'):
                        model_profile.supports_thinking = False
                except Exception:
                    debug(f"Could not disable thinking for model {model_name}")
            
            return model_profile

        # Fallback to parent logic
        return super().model_profile(model_name)


class OllamaProvider(OpenRouterProvider):
    """Provider for Ollama API-compatible servers."""

    def __init__(self, api_key: str, endpoint: str, thinking_enabled: bool = False):
        # Set endpoint before calling super().__init__() because base_url property is accessed during initialization
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        # Ollama typically uses /api/v1 or just /v1
        if hasattr(self, '_endpoint') and self._endpoint:
            if not self._endpoint.endswith("/v1") and not self._endpoint.endswith("/api/v1"):
                if self._endpoint.endswith("/"):
                    return self._endpoint + "v1"
                return self._endpoint + "/v1"
            return self._endpoint
        return "http://localhost:11434/v1"  # Default Ollama endpoint

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        # Ollama models use OpenAI-compatible profile
        profile = openai_model_profile(model_name)
        model_profile = OpenAIModelProfile(
            json_schema_transformer=OpenAIJsonSchemaTransformer
        ).update(profile)
        
        if not self.thinking_enabled:
            try:
                if hasattr(model_profile, 'model_copy'):
                    model_profile = model_profile.model_copy(update={
                        "supports_thinking": False
                    })
                elif hasattr(model_profile, 'supports_thinking'):
                    model_profile.supports_thinking = False
            except Exception:
                debug(f"Could not disable thinking for Ollama model {model_name}")
        
        return model_profile


class VLLMProvider(OpenRouterProvider):
    """Provider for VLLM API-compatible servers."""

    def __init__(self, api_key: str, endpoint: str, thinking_enabled: bool = False):
        # Set endpoint before calling super().__init__() because base_url property is accessed during initialization
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        # VLLM typically uses /v1
        if hasattr(self, '_endpoint') and self._endpoint:
            if not self._endpoint.endswith("/v1"):
                if self._endpoint.endswith("/"):
                    return self._endpoint + "v1"
                return self._endpoint + "/v1"
            return self._endpoint
        return "http://localhost:8000/v1"  # Default VLLM endpoint

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        # VLLM uses OpenAI-compatible profile
        # Special handling for models that do not contain "/" in the name
        if "/" not in model_name:
            profile = openai_model_profile(model_name)
            model_profile = OpenAIModelProfile(
                json_schema_transformer=OpenAIJsonSchemaTransformer
            ).update(profile)
            
            # Disable thinking if the model doesn't support it
            if not self.thinking_enabled:
                try:
                    if hasattr(model_profile, 'model_copy'):
                        model_profile = model_profile.model_copy(update={
                            "supports_thinking": False
                        })
                    elif hasattr(model_profile, 'supports_thinking'):
                        model_profile.supports_thinking = False
                except Exception:
                    debug(f"Could not disable thinking for VLLM model {model_name}")
            
            return model_profile

        # Fallback to parent logic
        return super().model_profile(model_name)


def get_agent_model(agent_model, thinking_override: Optional[bool] = None):
    """
    Get the appropriate model instance based on model configuration.
    Supports per-model endpoints and API protocols (OpenAI, Ollama, VLLM).
    """
    # Get model configuration
    model_config = _get_model_config(agent_model)
    thinking_enabled = model_config.get("thinking", False) if model_config else False
    if thinking_override is not None:
        thinking_enabled = thinking_override
    
    # Handle OpenAI models (external OpenAI API)
    if "openai" in agent_model and model_config and model_config.get("external", False):
        model_name = agent_model.split("/")[-1]
        return OpenAIModel(
            model_name=model_name,
        )
    
    # Get endpoint and protocol for this model
    endpoint = _get_model_endpoint(agent_model)
    api_protocol = _detect_api_protocol(agent_model, model_config)
    
    debug(f"Using model {agent_model} with endpoint {endpoint} and protocol {api_protocol}")
    
    # Create appropriate provider based on protocol
    if api_protocol == "ollama":
        provider = OllamaProvider(
            api_key="no-api-key",
            endpoint=endpoint,
            thinking_enabled=thinking_enabled
        )
    elif api_protocol == "vllm":
        provider = VLLMProvider(
            api_key="no-api-key",
            endpoint=endpoint,
            thinking_enabled=thinking_enabled
        )
    else:
        # Default to OpenAI-compatible (InsightAIProvider)
        provider = InsightAIProvider(
            api_key="no-api-key",
            thinking_enabled=thinking_enabled,
            endpoint=endpoint
        )
    
    return OpenAIModel(
        model_name=agent_model,
        provider=provider,
    )


# Cache dictionaries for agents to prevent context leaks
# These MUST be defined before any agent creation functions are called
_chat_agent_cache = {}
_rag_agent_cache = {}
_prompt_agent_cache = {}
_upload_agent_cache = {}
_extraction_agent_cache = {}
_secure_agent_cache = {}


@dataclass
class RagDeps:
    doc_manager: DocumentManager
    user_id: str
    documents: list[SmartDocument]


def create_rag_agent(agent_model):
    """Create or retrieve a cached RAG agent to prevent context leaks."""
    cache_key = f"rag_{agent_model}"

    if cache_key not in _rag_agent_cache:
        model = get_agent_model(agent_model)
        _rag_agent_cache[cache_key] = Agent(
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

    return _rag_agent_cache[cache_key]


def create_chat_agent(
    agent_model,
    system_prompt=None,
    include_next_step=True,
    thinking_override: Optional[bool] = None,
):
    """Create or retrieve a cached chat agent to prevent context leaks.

    Args:
        agent_model: The model name to use
        system_prompt: Optional custom system prompt
        include_next_step: Whether the default prompt should ask for next steps

    Returns:
        Cached Agent instance
    """
    prompt_to_use = (
        system_prompt
        if system_prompt is not None
        else get_default_system_prompt(include_next_step=include_next_step)
    )
    cache_key = f"{agent_model}_{hash(prompt_to_use)}_{thinking_override}"

    # Return cached agent if available
    if cache_key not in _chat_agent_cache:
        model = get_agent_model(agent_model, thinking_override=thinking_override)
        _chat_agent_cache[cache_key] = Agent(
            model,
            system_prompt=prompt_to_use,
        )

    return _chat_agent_cache[cache_key]


def create_prompt_agent(agent_model):
    """Create or retrieve a cached prompt agent to prevent context leaks."""
    cache_key = f"prompt_{agent_model}"

    if cache_key not in _prompt_agent_cache:
        model = get_agent_model(agent_model)
        _prompt_agent_cache[cache_key] = Agent(
            model,
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

    return _prompt_agent_cache[cache_key]


class UploadResult(BaseModel):
    feedback: str
    valid: bool


def create_upload_agent(agent_model):
    """Create or retrieve a cached upload agent to prevent context leaks."""
    cache_key = f"upload_{agent_model}"

    if cache_key not in _upload_agent_cache:
        model = get_agent_model(agent_model)
        _upload_agent_cache[cache_key] = Agent(
            model,
            system_prompt="""You are an expert in document management and processing. Your task is to assist users in uploading and ensuring their documents are valid and ready for processing. You will provide feedback on the document's validity, summarize its content, and ensure it meets the necessary criteria for further processing. If the document is invalid, you will provide specific feedback on what needs to be corrected or improved. Your responses should be clear, concise, and actionable.""",
            output_type=UploadResult,
        )

    return _upload_agent_cache[cache_key]


def create_secure_agent(agent_model):
    """Create or retrieve a cached upload agent to prevent context leaks."""
    cache_key = f"upload_{agent_model}"

    if cache_key not in _secure_agent_cache:
        model = get_agent_model(agent_model)
        _secure_agent_cache[cache_key] = Agent(
            model,
            system_prompt="""You are an expert in document management and processing. Your task is to assist users in uploading and ensuring their documents are valid and ready for processing. You will provide feedback on the document's validity, summarize its content, and ensure it meets the necessary criteria for further processing. If the document is invalid, you will provide specific feedback on what needs to be corrected or improved. Your responses should be clear, concise, and actionable.""",
            output_type=UploadResult,
        )

    return _secure_agent_cache[cache_key]


upload_agent = create_upload_agent(get_default_model_name())

rag_agent = create_rag_agent(get_default_model_name())

prompt_agent = create_prompt_agent(get_default_model_name())

secure_agent = create_secure_agent(settings.secure_model)


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


def create_field_inference_agent(agent_model, keys, context, prompt_context=None):
    model = get_agent_model(agent_model)
    system_prompt = create_field_inference_system_prompt(keys, context)
    return Agent(
        model,
        system_prompt=system_prompt,
        retries=3,
    )


model = get_agent_model(get_default_model_name())


def get_cache_key(key: str, context: str) -> str:
    """Generate consistent cache key for a field."""
    return f"field_type:{key}:{context}"


@dataclass
class ExtractionDeps:
    extraction_context: Optional[str]
    fields: dict[str, tuple]
    text: str


def create_extraction_agent(agent_model):
    model = get_agent_model(agent_model)
    return Agent(
        model,
        deps_type=ExtractionDeps,
        retries=3,
    )


extraction_agent = create_extraction_agent(get_default_model_name())


@extraction_agent.system_prompt
def extraction_system_prompt(
    context: RunContext[ExtractionDeps],
):
    text = context.deps.text
    fields = context.deps.fields
    field_descriptions = [f"- {field}" for field in fields.keys()]
    field_str = "\n".join(field_descriptions)

    system_prompt = (
        "You are a precise entity extraction assistant. Extract only the requested information in a single execution. "
        "Be as faithful as possible during extraction and do not modify the extracted items. "
        "\n\nTYPE SELECTION GUIDELINES:\n"
        "- Use strings for text, dates, monetary values, and formatted numbers\n"
        "- Use integers for whole numbers without decimals\n"
        "- Use floats for decimal numbers\n"
        "- Use booleans for true/false values\n"
        "- Use lists when multiple values are present for a field\n"
        "- Preserve ALL original formatting (commas, currency symbols, decimal places)\n"
        "- DO NOT convert between types or modify formatting\n"
        "\nCRITICAL: Your response MUST be valid JSON as a single object with the requested fields.\n"
        "IMPORTANT RULES:\n"
        "1. Set field values to null if the information is not found in the text\n"
        "2. Only include a field with a non-null value if you find that information in the text\n"
        "3. Do NOT make up or infer information that isn't explicitly stated\n"
        "4. Choose the most appropriate data type for each field based on the actual value found\n"
        "5. Return a flat JSON object with the field names as keys"
    )

    return (
        f"""
{system_prompt}

Extract the following information from the text below only if it is present:

{field_str}

Return the information as a JSON object with these exact field names as keys.
Set a field to null only if that information is not present in the text.

Text:
{text}""",
    )


# @observe()
def extract_entities_with_agent(
    text: str, keys: list[str], context: str = "", model_name: str | None = None
) -> dict:
    """Extract entities from text based on the provided extraction keys and return structured output.

    Args:
        text: Input text to extract information from
        keys: List of fields to extract
        context: Optional context for extraction
        model_name: Model to use for extraction

    Returns:
        A dictionary with extracted field values
    """
    # ensure keys are a list of strings, otherwise split on comma
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",")]
    else:
        keys = [k.strip() for k in keys]

    # Set all fields to Any type - let the model decide appropriate types
    inferred_fields = {key: (Any, None) for key in keys}

    debug(f"Fields for extraction: {inferred_fields}")

    # Create a cache key based on model name and field names only
    field_signature = frozenset(keys)
    cache_key = f"{model_name}_{hash(field_signature)}"

    # Reuse cached agent if available to prevent context leaks
    if cache_key not in _extraction_agent_cache:
        # Create dynamic model with UNIQUE name based on fields hash
        unique_model_name = f"ExtractionResult_{abs(hash(field_signature))}"

        # Create a single model directly (not wrapped in "entities" array)
        extraction_model = create_model(unique_model_name, **inferred_fields)

        model = get_agent_model(model_name or get_default_model_name())
        _extraction_agent_cache[cache_key] = Agent(
            model,
            deps_type=ExtractionDeps,
            output_type=extraction_model,
            output_retries=3,
            retries=3,
        )

    extractor_agent = _extraction_agent_cache[cache_key]

    extractor_deps = ExtractionDeps(
        extraction_context=context,
        fields=inferred_fields,
        text=text,
    )

    try:
        # Run the agent synchronously
        extraction = extractor_agent.run_sync(text, deps=extractor_deps)
        debug(extraction.output)

        result = extraction.output.model_dump_json(indent=2)

        result = json.loads(result)
        debug(result)

        # Filter out None/empty values
        # filtered_result = {k: v for k, v in result.items() if v not in (None, "", [], {})}

        # return filtered_result
        return result

    except AssertionError as e:
        # Extract the dictionary from the error message
        error_msg = str(e)
        debug(f"AssertionError during extraction: {e}")
        if error_msg.startswith("Expected code to be unreachable, but got: "):
            try:
                # Try to parse the dictionary from the error message
                entity_str = error_msg.replace(
                    "Expected code to be unreachable, but got: ",
                    "",
                )
                entity = json.loads(entity_str)
                debug(entity)
                # Filter out None values
                return {k: v for k, v in entity.items() if v not in (None, "", [], {})}
            except Exception as parse_error:
                debug(f"Failed to parse error message: {parse_error}")
                pass
        # If we can't recover, return empty dict
        return {}

    except Exception as e:
        debug(f"Unexpected error during extraction: {e}")
        return {}
