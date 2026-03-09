"""LLM service  - provider classes and agent creation, ported from agents.py."""

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
# Agent caches  - prevent context leaks across requests
# ---------------------------------------------------------------------------
_chat_agent_cache: dict[str, Agent] = {}
_extraction_agent_cache: dict[str, Agent] = {}
_rag_agent_cache: dict[str, Agent] = {}
_prompt_agent_cache: dict[str, Agent] = {}


def clear_agent_caches():
    """Clear all cached agents so config changes (API keys, endpoints) take effect."""
    _chat_agent_cache.clear()
    _extraction_agent_cache.clear()
    _rag_agent_cache.clear()
    _prompt_agent_cache.clear()


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
# Sync helpers  - used in Celery workers & extraction engine
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
    """Get the appropriate model instance. Sync  - safe for Celery workers."""
    model_config = _get_model_config_sync(agent_model, system_config_doc)
    thinking_enabled = model_config.get("thinking", False) if model_config else False
    if thinking_override is not None:
        thinking_enabled = thinking_override

    # Resolve per-model API key, falling back to env var or placeholder
    api_key = (model_config.get("api_key", "") if model_config else "") or OPENAI_API_KEY or "no-api-key"

    endpoint = _get_model_endpoint_sync(agent_model, system_config_doc)
    api_protocol = detect_api_protocol(agent_model, model_config)

    # Handle external models with OpenAI protocol (use OpenAI SDK directly)
    if model_config and model_config.get("external", False) and api_protocol == "openai":
        model_name = agent_model.split("/")[-1] if "/" in agent_model else agent_model
        from openai import AsyncOpenAI
        client_kwargs: dict = {"api_key": api_key}
        if endpoint:
            client_kwargs["base_url"] = endpoint
        client = AsyncOpenAI(**client_kwargs)
        return OpenAIModel(model_name=model_name, openai_client=client)

    if api_protocol == "ollama":
        provider = OllamaProvider(api_key=api_key, endpoint=endpoint, thinking_enabled=thinking_enabled)
    elif api_protocol == "vllm":
        provider = VLLMProvider(api_key=api_key, endpoint=endpoint, thinking_enabled=thinking_enabled)
    else:
        provider = InsightAIProvider(api_key=api_key, thinking_enabled=thinking_enabled, endpoint=endpoint)

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
    "You are the built-in assistant for **Vandalizer**, a document intelligence platform "
    "built at the University of Idaho.\n\n"
    "## UI layout\n"
    "- **Left sidebar** (Utility Bar): four mode tabs — **Chat**, **Files**, "
    "**Automations**, **Knowledge**.\n"
    "- **Top-right dropdown** (your name / Account): switch teams, **Manage teams** "
    "(goes to /teams), **My Account** (goes to /account), **Admin** (if admin).\n"
    "- **Right rail**: Activity feed showing recent conversations, extractions, and "
    "workflow runs.\n\n"
    "## Features & how-to steps\n\n"
    "### Uploading documents\n"
    "1. Click **Files** in the left sidebar.\n"
    "2. Click the **Upload** button (or drag-and-drop files onto the file list).\n"
    "3. Supported formats: PDF, DOCX, XLSX, HTML, images. Files are auto-OCR'd, "
    "text-extracted, and vector-indexed within seconds.\n\n"
    "### Chatting with documents\n"
    "1. In **Files** mode, select one or more documents using checkboxes.\n"
    "2. Switch to **Chat** mode — selected documents appear as context.\n"
    "3. Ask your question; the assistant answers grounded in those documents.\n\n"
    "### Saving a reusable prompt\n"
    "1. In the chat input area, click the **Library** icon.\n"
    "2. Click **+ New** to create a new library item.\n"
    "3. Write your prompt text and save. You can **Pin** it to the quick-access bar "
    "or **Favorite** it as a personal bookmark.\n\n"
    "### Formatters / Extraction Sets\n"
    "Structured schemas defining what data to pull from documents. Each has typed fields "
    "(text, number, date, boolean, list, etc.).\n"
    "- **Create manually**: go to the extraction set panel, click **+ New**, add fields.\n"
    "- **Auto-generate**: select a document, click **Build from Document** — AI analyzes "
    "the document and proposes extraction fields automatically.\n\n"
    "### Creating & running workflows\n"
    "1. Click **Automations** in the left sidebar, or navigate to **/workflows**.\n"
    "2. Click **+ New** to create a workflow. Give it a name.\n"
    "3. Add **steps** — each step is a task type:\n"
    "   - **Extract** — run an extraction set against documents.\n"
    "   - **Summarize** — produce a concise summary.\n"
    "   - **Classify** — categorize documents into labels you define.\n"
    "   - **Translate** — translate content to a target language.\n"
    "   - **Custom Prompt** — run any freeform prompt.\n"
    "   - **Compare** — compare two or more documents side by side.\n"
    "   - **Merge** — combine outputs from earlier steps.\n"
    "4. **Chain steps**: use step inputs to feed the output of one step into the next.\n"
    "5. **Run**: select documents, click Run. View results in-app or export as "
    "JSON, CSV, or PDF.\n\n"
    "### Pinning & Favoriting\n"
    "- **Pin**: keeps a library item (prompt, extraction set) in the quick-access bar "
    "so it's always one click away.\n"
    "- **Favorite**: a personal bookmark. Favorited items appear in your favorites "
    "filter in the library.\n\n"
    "### Inviting teammates\n"
    "1. Click your name in the **top-right dropdown**.\n"
    "2. Select **Manage teams** (or go to **/teams**).\n"
    "3. Select your team (or create one), then click **Invite** and enter the "
    "person's email.\n"
    "4. Roles: **Owner** (full control), **Admin** (manage members & settings), "
    "**Member** (use shared spaces and resources).\n\n"
    "### Team folders\n"
    "In **Files** mode, click **Add → New Team Folder** to create a folder shared "
    "with everyone on your current team. Team folders show a teal **Team** badge.\n\n"
    "### Automations\n"
    "1. Click **Automations** in the left sidebar.\n"
    "2. Click **+ New** to create an automation.\n"
    "3. Choose a **trigger type**:\n"
    "   - **Folder Watch** — monitors a folder; new files trigger the workflow.\n"
    "   - **M365 Intake** — ingests documents from Microsoft 365 sources.\n"
    "   - **API Trigger** — fires the workflow from an external HTTP call.\n"
    "   - **Schedule** — runs on a cron-like schedule (daily, weekly, etc.).\n"
    "4. Select which **workflow** to run when triggered.\n"
    "5. Toggle the automation **on**.\n\n"
    "### Knowledge Bases\n"
    "1. Click **Knowledge** in the left sidebar.\n"
    "2. Click **+ New** to create a knowledge base.\n"
    "3. Add sources: **Add Documents** (from your files) or **Add URLs** (web pages).\n"
    "4. Wait for status to change from *building* to *ready*.\n"
    "5. Click **Chat** on the knowledge base to ask questions grounded in all "
    "indexed content.\n\n"
    "### Spaces\n"
    "Logical groupings within a team. Each space has its own documents, workflows, "
    "and library items, keeping projects organized. Switch spaces from the header.\n\n"
    "### API Integration\n"
    "1. Go to **My Account** (top-right dropdown → My Account).\n"
    "2. Generate an **API Token**.\n"
    "3. Use the token with the `x-api-key` header to call extraction and workflow "
    "endpoints programmatically. Code samples are shown on the Account page.\n\n"
    "## Response rules\n"
    "- Be concise. Use short Markdown bullets and headings — never write walls of text.\n"
    "- Do NOT restate the question.\n"
    "- When the user asks about features, answer with specific Vandalizer UI steps: "
    "which sidebar tab to click, which button to press, what to expect. "
    "Never give generic advice — always reference the Vandalizer interface.\n"
    "- When given documents, prioritize: (1) relevance, (2) recency, (3) non-duplication.\n"
    "- Citations: refer to provided context naturally; no raw links unless asked.\n"
    "- Keep answers under 150 words unless the user explicitly asks for detail.\n"
)

VANDALIZER_CONTEXT = (
    "[IMPORTANT INSTRUCTION] You are the assistant for Vandalizer, a document intelligence "
    "platform at the University of Idaho. The user is asking about Vandalizer. "
    "Answer ONLY using the Vandalizer-specific instructions below. "
    "Do NOT mention Slack, Trello, GitHub, Xbox, or any other platform.\n\n"
    "UPLOADING: Files tab (left sidebar) → Upload button. Supports PDF, DOCX, XLSX, HTML, images.\n"
    "CHAT WITH DOCS: Select documents in Files tab → switch to Chat tab → ask questions.\n"
    "REUSABLE PROMPTS: Chat input → Library icon → + New → write prompt → save. Pin for quick access.\n"
    "FORMATTERS: Structured extraction schemas with typed fields. Build manually or click "
    "Build from Document to auto-generate from a file.\n"
    "WORKFLOWS: Automations tab → + New. Task types: Extract, Summarize, Classify, Translate, "
    "Custom Prompt, Compare, Merge. Chain step outputs as inputs to later steps. Export as JSON/CSV/PDF.\n"
    "INVITE TEAMMATES: Top-right dropdown → Manage teams (or /teams page) → select team → Invite → enter email. "
    "Roles: Owner, Admin, Member.\n"
    "TEAM FOLDERS: Files tab → Add → New Team Folder. Shared with everyone on your current team.\n"
    "AUTOMATIONS: Automations tab → + New. Triggers: Folder Watch, M365 Intake, API, Schedule. "
    "Pick a workflow to run, toggle on.\n"
    "KNOWLEDGE BASES: Knowledge tab → + New → Add Documents or Add URLs → wait for 'ready' → Chat.\n"
    "SPACES: Logical project groupings within a team. Switch from the header.\n"
    "API: My Account (top-right dropdown) → generate API Token → use x-api-key header.\n"
    "PIN vs FAVORITE: Pin = always visible in quick-access bar. Favorite = personal bookmark filter.\n\n"
    "Be concise. Give 2-3 specific Vandalizer UI steps, not generic advice.\n"
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
