"""LLM service — provider classes and agent creation, ported from agents.py."""

import os
from dataclasses import dataclass
from typing import Optional

from pydantic_ai.agent import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.openai import (
    OpenAIJsonSchemaTransformer,
    OpenAIModelProfile,
    openai_model_profile,
)
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.tools import RunContext

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Agent caches — prevent context leaks across requests
# ---------------------------------------------------------------------------
_chat_agent_cache: dict[str, Agent] = {}
_extraction_agent_cache: dict[str, Agent] = {}
_rag_agent_cache: dict[str, Agent] = {}
_prompt_agent_cache: dict[str, Agent] = {}


# ---------------------------------------------------------------------------
# RAG deps dataclass
# ---------------------------------------------------------------------------

@dataclass
class RagDeps:
    doc_manager: object  # DocumentManager instance
    user_id: str
    documents: list  # list of SmartDocument


# ---------------------------------------------------------------------------
# Provider classes
# ---------------------------------------------------------------------------

class InsightAIProvider(OpenRouterProvider):
    """Custom OpenRouter provider for UIdaho Insight AI server."""

    def __init__(self, api_key: str, thinking_enabled: bool = False, endpoint: Optional[str] = None):
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        if hasattr(self, "_endpoint") and self._endpoint:
            return self._endpoint
        return "https://mindrouter-api.nkn.uidaho.edu/v1"

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        if "/" not in model_name:
            profile = openai_model_profile(model_name)
            model_profile = OpenAIModelProfile(
                json_schema_transformer=OpenAIJsonSchemaTransformer
            ).update(profile)
            if not self.thinking_enabled:
                try:
                    if hasattr(model_profile, "model_copy"):
                        model_profile = model_profile.model_copy(update={"supports_thinking": False})
                    elif hasattr(model_profile, "supports_thinking"):
                        model_profile.supports_thinking = False
                except Exception:
                    pass
            return model_profile
        return super().model_profile(model_name)


class OllamaProvider(OpenRouterProvider):
    """Provider for Ollama API-compatible servers."""

    def __init__(self, api_key: str, endpoint: str, thinking_enabled: bool = False):
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        if hasattr(self, "_endpoint") and self._endpoint:
            if not self._endpoint.endswith("/v1") and not self._endpoint.endswith("/api/v1"):
                return self._endpoint.rstrip("/") + "/v1"
            return self._endpoint
        return "http://localhost:11434/v1"

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        profile = openai_model_profile(model_name)
        model_profile = OpenAIModelProfile(
            json_schema_transformer=OpenAIJsonSchemaTransformer
        ).update(profile)
        if not self.thinking_enabled:
            try:
                if hasattr(model_profile, "model_copy"):
                    model_profile = model_profile.model_copy(update={"supports_thinking": False})
                elif hasattr(model_profile, "supports_thinking"):
                    model_profile.supports_thinking = False
            except Exception:
                pass
        return model_profile


class VLLMProvider(OpenRouterProvider):
    """Provider for VLLM API-compatible servers."""

    def __init__(self, api_key: str, endpoint: str, thinking_enabled: bool = False):
        self._endpoint = endpoint
        self.thinking_enabled = thinking_enabled
        super().__init__(api_key=api_key)

    @property
    def base_url(self) -> str:
        if hasattr(self, "_endpoint") and self._endpoint:
            if not self._endpoint.endswith("/v1"):
                return self._endpoint.rstrip("/") + "/v1"
            return self._endpoint
        return "http://localhost:8000/v1"

    def model_profile(self, model_name: str) -> Optional[ModelProfile]:
        if "/" not in model_name:
            profile = openai_model_profile(model_name)
            model_profile = OpenAIModelProfile(
                json_schema_transformer=OpenAIJsonSchemaTransformer
            ).update(profile)
            if not self.thinking_enabled:
                try:
                    if hasattr(model_profile, "model_copy"):
                        model_profile = model_profile.model_copy(update={"supports_thinking": False})
                    elif hasattr(model_profile, "supports_thinking"):
                        model_profile.supports_thinking = False
                except Exception:
                    pass
            return model_profile
        return super().model_profile(model_name)


# ---------------------------------------------------------------------------
# Sync helpers — used in Celery workers & extraction engine
# ---------------------------------------------------------------------------

def _get_model_config_sync(model_name: str, system_config_doc: dict | None = None) -> Optional[dict]:
    """Get model config from a pre-fetched SystemConfig document (sync context)."""
    if system_config_doc and system_config_doc.get("available_models"):
        for model in system_config_doc["available_models"]:
            if model.get("name") == model_name:
                return model
    return None


def _get_model_endpoint_sync(model_name: str, system_config_doc: dict | None = None) -> str:
    """Get the endpoint URL for a model (sync context)."""
    model_config = _get_model_config_sync(model_name, system_config_doc)
    if model_config:
        endpoint = model_config.get("endpoint", "").strip()
        if endpoint:
            return endpoint
    if system_config_doc and system_config_doc.get("llm_endpoint"):
        return system_config_doc["llm_endpoint"]
    return "https://mindrouter-api.nkn.uidaho.edu/v1"


def detect_api_protocol(model_name: str, model_config: Optional[dict] = None) -> str:
    """Detect API protocol based on model name and configuration."""
    if model_config and model_config.get("api_protocol"):
        protocol = model_config.get("api_protocol", "").strip().lower()
        if protocol in ["openai", "ollama", "vllm"]:
            return protocol

    model_lower = model_name.lower()
    if "openai/" in model_name or model_name.startswith("gpt-") or "claude" in model_lower:
        return "openai"
    if "/" not in model_name and not model_name.startswith("http"):
        return "ollama"
    if "vllm" in model_lower or model_name.startswith("vllm/"):
        return "vllm"
    return "openai"


def get_model_api_protocol(model_name: str, system_config_doc: dict | None = None) -> str:
    """Public helper to determine API protocol for a model."""
    model_config = _get_model_config_sync(model_name, system_config_doc)
    return detect_api_protocol(model_name, model_config)


def get_agent_model(
    agent_model: str,
    thinking_override: Optional[bool] = None,
    system_config_doc: dict | None = None,
) -> OpenAIModel:
    """Get the appropriate model instance. Sync — safe for Celery workers."""
    model_config = _get_model_config_sync(agent_model, system_config_doc)
    thinking_enabled = model_config.get("thinking", False) if model_config else False
    if thinking_override is not None:
        thinking_enabled = thinking_override

    # Handle external OpenAI models
    if "openai" in agent_model and model_config and model_config.get("external", False):
        model_name = agent_model.split("/")[-1]
        return OpenAIModel(model_name=model_name)

    endpoint = _get_model_endpoint_sync(agent_model, system_config_doc)
    api_protocol = detect_api_protocol(agent_model, model_config)

    if api_protocol == "ollama":
        provider = OllamaProvider(api_key="no-api-key", endpoint=endpoint, thinking_enabled=thinking_enabled)
    elif api_protocol == "vllm":
        provider = VLLMProvider(api_key="no-api-key", endpoint=endpoint, thinking_enabled=thinking_enabled)
    else:
        provider = InsightAIProvider(api_key="no-api-key", thinking_enabled=thinking_enabled, endpoint=endpoint)

    return OpenAIModel(model_name=agent_model, provider=provider)


def create_chat_agent(
    agent_model: str,
    system_prompt: str | None = None,
    thinking_override: Optional[bool] = None,
    system_config_doc: dict | None = None,
) -> Agent:
    """Create or retrieve a cached chat agent."""
    prompt_to_use = system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT
    cache_key = f"{agent_model}_{hash(prompt_to_use)}_{thinking_override}"

    if cache_key not in _chat_agent_cache:
        model = get_agent_model(agent_model, thinking_override=thinking_override, system_config_doc=system_config_doc)
        _chat_agent_cache[cache_key] = Agent(model, system_prompt=prompt_to_use)

    return _chat_agent_cache[cache_key]


# ---------------------------------------------------------------------------
# Default system prompts
# ---------------------------------------------------------------------------

DEFAULT_CHAT_SYSTEM_PROMPT = (
    "You are a precise, concise assistant.\n"
    "Output: well-structured Markdown with clear headings and bullets.\n"
    "Do NOT restate the question. If info is missing, say so briefly and proceed best-effort.\n"
    "Citations: refer to provided context naturally; no raw links unless asked.\n"
    "When given documents, prioritize: (1) relevance, (2) recency, (3) non-duplication.\n"
)

RAG_SYSTEM_PROMPT = (
    "You are a specialized knowledge assistant powered by retrieval-augmented generation.\n\n"
    "When responding to queries:\n"
    "1. Carefully analyze the retrieved context documents for relevance to the query\n"
    "2. Synthesize information across multiple context fragments when appropriate\n"
    "3. Quote or paraphrase the retrieved information with precise attribution\n"
    "4. Maintain the original meaning and nuance from source documents\n"
    "5. Identify and reconcile any contradictions between different sources\n"
    "6. Distinguish between factual statements from the context and your own reasoning\n\n"
    "Response guidelines:\n"
    "- Begin with a direct answer to the question when possible\n"
    "- Structure complex answers with clear headings or numbered points\n"
    "- Acknowledge information gaps explicitly rather than extrapolating\n"
    "- Never fabricate information beyond what is provided in the context.\n"
)

PROMPT_AGENT_SYSTEM_PROMPT = (
    "You are a specialized prompt engineer focused on retrieval augmentation. "
    "Your task is to convert user questions into optimal search prompts for querying vector databases.\n\n"
    "When generating search prompts:\n"
    "1. Extract key entities, concepts, and relationships from the user's question\n"
    "2. Include relevant synonyms and alternative phrasings to increase recall\n"
    "3. Remove conversational fillers and personal pronouns\n"
    "4. Keep the prompt concise (under 100 words) but comprehensive\n\n"
    "Your output should be the search prompt only, with no additional text."
)


def create_rag_agent(
    agent_model: str,
    system_config_doc: dict | None = None,
) -> Agent:
    """Create or retrieve a cached RAG agent with retrieve tool."""
    cache_key = f"rag_{agent_model}"

    if cache_key not in _rag_agent_cache:
        model = get_agent_model(agent_model, system_config_doc=system_config_doc)
        _rag_agent_cache[cache_key] = Agent(
            model,
            deps_type=RagDeps,
            system_prompt=RAG_SYSTEM_PROMPT,
        )

        @_rag_agent_cache[cache_key].tool
        def retrieve(
            context: RunContext[RagDeps],
            question: str,
            docs_ids: Optional[list[str]] = None,
        ):
            """Retrieve relevant document chunks for a given question.

            Args:
                context: The call context
                question: The question of the user
                docs_ids: A list of document IDs to search in (optional).

            Returns:
                A list of document chunks that match the question
            """
            if docs_ids is None:
                docs_ids = []

            # Use prompt agent to optimize the query
            prompt_agent = create_prompt_agent(agent_model, system_config_doc=system_config_doc)
            prompt_response = prompt_agent.run_sync(
                f"Generate a prompt for the following user question: {question}",
            )
            prompt = prompt_response.output

            results = context.deps.doc_manager.query_documents(
                context.deps.user_id,
                prompt,
                docs_ids,
                k=10,
            )

            if len(results) == 0:
                # Try to re-ingest missing documents
                for doc in context.deps.documents:
                    if not context.deps.doc_manager.document_exists(
                        context.deps.user_id, doc.uuid
                    ):
                        context.deps.doc_manager.add_document(
                            user_id=context.deps.user_id,
                            doc_path="",
                            document_name=doc.title,
                            document_id=doc.uuid,
                            raw_text=doc.raw_text or "",
                        )

                results = context.deps.doc_manager.query_documents(
                    context.deps.user_id,
                    prompt,
                    docs_ids,
                    k=10,
                )

            return results

    return _rag_agent_cache[cache_key]


def create_prompt_agent(
    agent_model: str,
    system_config_doc: dict | None = None,
) -> Agent:
    """Create or retrieve a cached prompt optimization agent."""
    cache_key = f"prompt_{agent_model}"

    if cache_key not in _prompt_agent_cache:
        model = get_agent_model(agent_model, system_config_doc=system_config_doc)
        _prompt_agent_cache[cache_key] = Agent(
            model,
            system_prompt=PROMPT_AGENT_SYSTEM_PROMPT,
        )

    return _prompt_agent_cache[cache_key]
