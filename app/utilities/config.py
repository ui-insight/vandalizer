#!/usr/bin/env python3


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
    {"name": "openai/gpt-5", "tag": "Cloud", "external": True},
    {
        "name": "gpt-oss-32k:120b",
        "tag": "Private",
        "external": False,
    },
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
        default="openai", description="Type of the model to use (openai or insight)."
    )

    base_model: str = Field(
        default="openai/gpt-4.1", description="The specific model to use for LLM tasks."
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


settings = Settings()
