#!/usr/bin/env python3


import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()

upload_compliance = """
Upload Compliance:
1. Document Format:
    - Ensure the document is in a supported format (PDF, DOCX, XLSX, TXT).
2. Content Guidelines:
    - The document should not contain FERPA violations.
    The Family Educational Rights and Privacy Act of 1974, as amended, also known as the Buckley Amendment  is a federal law that governs the confidentiality of student records. Generally, the law requires that educational institutions maintain the confidentiality of what are termed "education records," ensures that each student has access to his or her education records, and provides students with a limited opportunity to correct erroneous education records.
    FERPA applies to the education records of persons who are or have been in attendance at the University of Idaho. With certain exceptions, education records are those records maintained by the university which are directly related to a student. This is an extremely broad definition.
    FERPA may be more permissive or restrictive than the privacy and public information laws of some states. Therefore, the Idaho Public Records Law must be taken into account when the University of Idaho considers issues related to student records.
    - The document should not contain Personally Identifiable Information (PII) (for example student ID numbers, social security numbers, etc.).
    Personally identifiable information is information contained in any record which makes a student's identity easily traceable. A student's ID number, for example, is personally identifiable information. Personally identifiable information cannot be released to third parties without the student's written consent, except under very narrow circumstances.
"""


# try:
#     list_of_models = UILLM.list_models()
# except Exception as e:
#     print(f"Error listing models: {e}")
#     list_of_models = ""
# models = []
# if isinstance(list_of_models, str):
#     base_models = list_of_models.split("\n")
#     # filter out to show only those that start with "Model:" or "EMBED"
#     base_models = [model for model in base_models if model.startswith("Model:")]
#     external_providers = [
#         "openai",
#         "google",
#         "x-ai",
#         "microsoft",
#         "amazon",
#         "meta-llama",
#         "anthropic",
#         "mistralai",
#         "nousresearch",
#         "deepseek",
#         "qwen",
#     ]

#     for model in base_models:
#         name = model.split("Model: ")[-1].strip()
#         if name.startswith("EMBED"):
#             continue
#         # check if the model is an external provider
#         external = any(
#             provider in name.split("/")[0] for provider in external_providers
#         )
#         models.append({"name": name, "external": external})
#         # filter

models = [
    {
        "name": "gpt-oss-32k:120b",
        "tag": "University of Idaho - Private",
        "external": False,
    },
    {"name": "openai/gpt-5", "tag": "Cloud", "external": True},
]

max_length = 120000 * 4  # 120K tokens, assuming 4 characters per token on average


class ModelConfig(BaseModel):
    """Model configuration class for LLM tasks."""

    # Model name
    name: str = Field(description="The specific model to use for LLM tasks.")

    # Model type
    provider: str = Field(description="Type of the model to use (openai or insight).")

    # Model parameters
    temperature: float = Field(
        default=0.7,
        description="Temperature for the model's response generation.",
    )
    top_p: float = Field(
        default=0.9,
        description="Top-p sampling for the model's response generation.",
    )

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        """Create a ModelConfig instance from a dictionary."""
        try:
            return cls(**data)
        except ValidationError as e:
            raise ValueError(f"Invalid model configuration: {e}")


class ModelType(BaseModel):
    name: str
    external: bool
    tag: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="allow"
    )

    insight_endpoint: str = Field(
        default="https://mindrouter-api.nkn.uidaho.edu/v1",
        description="Endpoint for the insight server.",
    )

    # Model configuration
    # the model type to use, either openai or insight server (ollama)
    # model_type = "insight" or "openai"
    model_type: str = Field(
        default="gpt-oss-32k:120b",
        description="The specific model to use for LLM tasks.",
    )

    secure_model: str = Field(
        default="gpt-oss-32k:120b",
        description="Type of the model to use (openai or insight).",
    )

    base_model: str = Field(
        default="gpt-oss-32k:120b",
        description="Type of the model to use (openai or insight).",
    )
    models: list[ModelType] = Field(
        default=models,
        description="List of available models for LLM tasks.",
    )
    # 128K is the max context length for the GPT-4o model
    # we use less than this to be safe
    # TODO make this adaptable based on the model selected
    max_context_length: int = Field(
        default=max_length, description="Maximum context length for the model."
    )

    upload_compliance: str = Field(
        default=upload_compliance,
        description="Compliance guidelines for document uploads.",
    )

    openai_api_key: str
    redis_host: str

    # Environment configuration
    environment: str = Field(
        default="development",
        description="Application environment: development, staging, or production",
    )

    # ChromaDB configuration
    chroma_host: str = Field(
        default="localhost",
        description="ChromaDB server host for staging/production",
    )

    chroma_port: int = Field(
        default=8000,
        description="ChromaDB server port for staging/production",
    )

    use_chroma_server: bool = Field(
        default=False,
        description="Use ChromaDB server instead of persistent client (auto-enabled for staging/prod)",
    )

    # Extraction strategy configuration
    # two_pass: thinking draft -> structured final (no thinking)
    # one_pass_thinking: structured extraction with thinking enabled
    # one_pass_no_thinking: structured extraction with thinking disabled
    extraction_strategy: str = Field(
        default="two_pass",
        description="Extraction strategy: two_pass, one_pass_thinking, one_pass_no_thinking.",
    )
    extraction_model: str = Field(
        default="",
        description="Optional model name to use for extraction (overrides user selection).",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Override with database config if available
        self._load_from_db()

    def _load_from_db(self):
        """Load configuration from database SystemConfig if available."""
        try:
            from app.models import SystemConfig
            db_config = SystemConfig.get_config()
            if db_config:
                # Override LLM endpoint
                if db_config.llm_endpoint:
                    self.insight_endpoint = db_config.llm_endpoint

                # Override available models
                if db_config.available_models:
                    self.models = [
                        ModelType(**model) for model in db_config.available_models
                    ]
        except Exception as e:
            # Silently fail if database is not available or SystemConfig doesn't exist
            # This allows the app to start even if MongoDB is not yet initialized
            pass


settings = Settings()


def get_ocr_endpoint() -> str:
    """Get OCR endpoint from database config or default."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.ocr_endpoint:
            return db_config.ocr_endpoint
    except Exception:
        pass
    return "https://processpdf.insight.uidaho.edu"


def get_llm_endpoint() -> str:
    """Get LLM endpoint from database config or default."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.llm_endpoint:
            return db_config.llm_endpoint
    except Exception:
        pass
    return settings.insight_endpoint


def get_llm_models() -> list[dict]:
    """Return the current list of LLM models (SystemConfig or defaults)."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.available_models:
            return db_config.available_models
    except Exception:
        pass
    return [m.model_dump() for m in settings.models]


def get_default_model_name() -> str:
    """Return a sensible default model name based on configured models."""
    models = get_llm_models()
    if models:
        first = models[0]
        if isinstance(first, dict):
            return first.get("name") or settings.base_model
    return settings.base_model


def get_llm_model_names(models: list[dict] | None = None) -> set[str]:
    """Return the set of configured model names."""
    configured_models = models if models is not None else get_llm_models()
    return {
        model.get("name")
        for model in configured_models
        if isinstance(model, dict) and model.get("name")
    }


def get_llm_model_by_name(
    model_name: str | None,
    models: list[dict] | None = None,
) -> dict | None:
    """Return the configured model dict by name, if present."""
    if not model_name:
        return None
    configured_models = models if models is not None else get_llm_models()
    for model in configured_models:
        if isinstance(model, dict) and model.get("name") == model_name:
            return model
    return None


def resolve_model_name(
    model_name: str | None,
    models: list[dict] | None = None,
) -> str:
    """
    Resolve a model name to a currently configured model.

    If the provided model is missing/stale, falls back to the first configured model.
    """
    configured_models = models if models is not None else get_llm_models()
    if get_llm_model_by_name(model_name, configured_models):
        return model_name

    if configured_models:
        first = configured_models[0]
        if isinstance(first, dict) and first.get("name"):
            return first["name"]

    return settings.base_model


def is_external_model(
    model_name: str | None,
    models: list[dict] | None = None,
) -> bool:
    """Return whether a model is marked external in system configuration."""
    model = get_llm_model_by_name(model_name, models=models)
    return bool(model and model.get("external"))


def reconcile_user_model_config(
    user_id: str | None,
    create_if_missing: bool = False,
    persist: bool = True,
):
    """
    Reconcile a user's model config with current system model configuration.

    Returns:
        tuple(model_config_or_none, configured_models, resolved_model_name)
    """
    configured_models = get_llm_models()
    resolved_default = resolve_model_name(None, configured_models)

    if not user_id:
        return None, configured_models, resolved_default

    try:
        from app.models import UserModelConfig
    except Exception:
        return None, configured_models, resolved_default

    model_config = UserModelConfig.objects(user_id=user_id).first()
    if model_config is None:
        if create_if_missing:
            model_config = UserModelConfig(
                user_id=user_id,
                name=resolved_default,
                available_models=configured_models,
            )
            if persist:
                model_config.save()
        return model_config, configured_models, resolved_default

    resolved_model = resolve_model_name(model_config.name, configured_models)

    needs_save = False
    if model_config.name != resolved_model:
        model_config.name = resolved_model
        needs_save = True
    if model_config.available_models != configured_models:
        model_config.available_models = configured_models
        needs_save = True

    if needs_save and persist:
        model_config.save()

    return model_config, configured_models, resolved_model


def get_user_model_name(
    user_id: str | None,
    create_if_missing: bool = False,
    persist: bool = True,
) -> str:
    """Return a valid current model name for the user (auto-heals stale values)."""
    _, _, model_name = reconcile_user_model_config(
        user_id=user_id,
        create_if_missing=create_if_missing,
        persist=persist,
    )
    return model_name


def get_extraction_config() -> dict:
    """Get the full extraction configuration dict (DB > env > defaults)."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config:
            return db_config.get_extraction_config()
    except Exception:
        pass
    # Fallback: build from env-var settings
    from copy import deepcopy
    from app.models import DEFAULT_EXTRACTION_CONFIG, _apply_legacy_strategy
    config = deepcopy(DEFAULT_EXTRACTION_CONFIG)
    if hasattr(settings, "extraction_strategy") and settings.extraction_strategy:
        _apply_legacy_strategy(config, settings.extraction_strategy)
    if hasattr(settings, "extraction_model") and settings.extraction_model:
        config["model"] = settings.extraction_model
    return config


def get_extraction_strategy() -> str:
    """DEPRECATED: Use get_extraction_config() instead."""
    config = get_extraction_config()
    return config.get("mode", "two_pass")


def get_extraction_model_name() -> str | None:
    """DEPRECATED: Use get_extraction_config() instead."""
    config = get_extraction_config()
    model = config.get("model", "")
    return model or None


def get_highlight_color() -> str:
    """Get UI highlight color from database config or default."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.highlight_color:
            return db_config.highlight_color
    except Exception:
        pass
    return "#eab308"  # Vandal gold/yellow


def _normalize_radius(value: str) -> str:
    """Ensure a CSS-friendly radius string (append px if numeric)."""
    if not value:
        return "12px"
    value = value.strip()
    if value.isdigit():
        return f"{value}px"
    if value.replace(".", "", 1).isdigit() and not value.endswith("px"):
        return f"{value}px"
    return value


def get_ui_radius() -> str:
    """Get UI radius from database config or default."""
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and getattr(db_config, "ui_radius", None):
            return _normalize_radius(db_config.ui_radius)
    except Exception:
        pass
    return "12px"


def get_auth_methods() -> list[str]:
    """Get enabled authentication methods from database config."""
    env = os.getenv("FLASK_ENV", "development").lower()
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.auth_methods is not None:
            methods = list(db_config.auth_methods)
            # If nothing is configured at all, fall back to password in non-prod to avoid lockout
            if methods or env == "production":
                return methods
    except Exception:
        pass
    # Default/fallback: allow password in non-prod to avoid lockout when no config is present
    return [] if env == "production" else ["password"]


def get_oauth_providers(enabled_only: bool = True) -> list[dict]:
    """Get OAuth/SAML providers from database config.

    Args:
        enabled_only: If True, only return enabled providers

    Returns:
        List of provider configurations
    """
    try:
        from app.models import SystemConfig
        db_config = SystemConfig.get_config()
        if db_config and db_config.oauth_providers:
            if enabled_only:
                return [p for p in db_config.oauth_providers if p.get("enabled", True)]
            return db_config.oauth_providers
    except Exception:
        pass
    return []


def get_oauth_provider_by_type(provider_type: str) -> dict | None:
    """Get a specific OAuth provider configuration by type.

    Args:
        provider_type: The provider type (azure, saml, google, etc.)

    Returns:
        Provider configuration dict or None if not found
    """
    providers = get_oauth_providers(enabled_only=True)
    for provider in providers:
        if provider.get("provider") == provider_type:
            return provider
    return None
