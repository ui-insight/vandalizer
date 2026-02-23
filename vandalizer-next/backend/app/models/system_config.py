"""SystemConfig model  - singleton for runtime-editable settings."""

import datetime
from copy import deepcopy
from typing import Optional

from beanie import Document


DEFAULT_QUALITY_CONFIG = {
    "verification_gates": {
        "require_validation": False,
        "min_extraction_accuracy": 0.7,
        "min_extraction_consistency": 0.8,
        "min_workflow_grade": "C",
    },
    "quality_tiers": {
        "excellent": {"min_score": 90},
        "good": {"min_score": 70},
        "fair": {"min_score": 50},
    },
}


DEFAULT_EXTRACTION_CONFIG = {
    "mode": "two_pass",
    "model": "",
    "one_pass": {
        "thinking": True,
        "structured": True,
        "model": "",
    },
    "two_pass": {
        "pass_1": {"thinking": True, "structured": False, "model": ""},
        "pass_2": {"thinking": False, "structured": True, "model": ""},
    },
    "chunking": {"enabled": False, "max_keys_per_chunk": 10},
    "repetition": {"enabled": False},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, modifying base in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _apply_legacy_strategy(config: dict, strategy: str):
    """Map old extraction_strategy string to new config structure."""
    if strategy == "two_pass":
        config["mode"] = "two_pass"
    elif strategy == "one_pass_thinking":
        config["mode"] = "one_pass"
        config["one_pass"]["thinking"] = True
        config["one_pass"]["structured"] = True
    elif strategy == "one_pass_no_thinking":
        config["mode"] = "one_pass"
        config["one_pass"]["thinking"] = False
        config["one_pass"]["structured"] = True


class SystemConfig(Document):
    """System-wide configuration singleton."""

    ocr_endpoint: str = "https://processpdf.insight.uidaho.edu"
    llm_endpoint: str = "https://mindrouter-api.nkn.uidaho.edu/v1"
    available_models: list[dict] = []

    # Legacy fields kept for backwards compatibility
    extraction_model: str = ""
    extraction_strategy: str = ""

    # New extraction configuration
    extraction_config: dict = {}

    # Quality configuration
    quality_config: dict = {}

    # UI Configuration
    highlight_color: str = "#eab308"
    ui_radius: str = "12px"

    # Authentication
    auth_methods: list[str] = ["password"]
    oauth_providers: list[dict] = []

    # Metadata
    updated_at: Optional[datetime.datetime] = None
    updated_by: Optional[str] = None

    class Settings:
        name = "system_config"

    @classmethod
    async def get_config(cls) -> "SystemConfig":
        """Get or create the singleton system configuration."""
        config = await cls.find_one()
        if not config:
            config = cls()
            await config.insert()
        return config

    def get_extraction_config(self) -> dict:
        """Return extraction config with defaults merged in."""
        config = deepcopy(DEFAULT_EXTRACTION_CONFIG)

        if self.extraction_config:
            _deep_merge(config, self.extraction_config)
        else:
            # Legacy migration
            if self.extraction_model:
                config["model"] = self.extraction_model
            if self.extraction_strategy:
                _apply_legacy_strategy(config, self.extraction_strategy)

        return config

    def get_quality_config(self) -> dict:
        """Return quality config with defaults merged in."""
        config = deepcopy(DEFAULT_QUALITY_CONFIG)
        if self.quality_config:
            _deep_merge(config, self.quality_config)
        return config
