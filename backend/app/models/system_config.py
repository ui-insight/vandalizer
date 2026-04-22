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
    "monitoring": {
        "auto_revalidate": True,
        "revalidate_interval_days": 7,
        "stale_threshold_days": 14,
        "degradation_alert_threshold": 10,
        "auto_review_on_degradation": True,
    },
    "kb_verification_gates": {
        "min_sources": 3,
        "min_chunks": 50,
        "min_source_health": 0.8,
        "min_retrieval_precision": 0.6,
    },
}


DEFAULT_CLASSIFICATION_CONFIG = {
    "enabled": True,
    "auto_classify_on_upload": True,
    "default_classification": "unrestricted",
    "levels": [
        {"name": "unrestricted", "label": "Unrestricted", "color": "#22c55e", "severity": 0},
        {"name": "internal", "label": "Internal", "color": "#3b82f6", "severity": 1},
        {"name": "ferpa", "label": "FERPA", "color": "#f59e0b", "severity": 2},
        {"name": "cui", "label": "CUI", "color": "#f97316", "severity": 3},
        {"name": "itar", "label": "ITAR", "color": "#ef4444", "severity": 4},
    ],
}

DEFAULT_RETENTION_CONFIG = {
    "enabled": False,
    "policies": {
        "unrestricted": {"retention_days": 365, "soft_delete_grace_days": 30, "warning_days_before": 14},
        "internal": {"retention_days": 730, "soft_delete_grace_days": 30},
        "ferpa": {"retention_days": 2555, "soft_delete_grace_days": 60},
        "cui": {"retention_days": 1825, "soft_delete_grace_days": 60},
        "itar": {"retention_days": 1825, "soft_delete_grace_days": 90},
    },
    "activity_retention_days": 180,
    "chat_retention_days": 365,
    "workflow_result_retention_days": 365,
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
    "use_images": False,
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

    ocr_endpoint: str = ""
    ocr_api_key: str = ""
    llm_endpoint: str = ""
    available_models: list[dict] = []
    # Name of the model to use when no explicit model is chosen. Empty = fall
    # back to the first entry in available_models.
    default_model: str = ""

    # Legacy fields kept for backwards compatibility
    extraction_model: str = ""
    extraction_strategy: str = ""

    # New extraction configuration
    extraction_config: dict = {}

    # Quality configuration
    quality_config: dict = {}

    # Classification configuration
    classification_config: dict = {}

    # Retention configuration
    retention_config: dict = {}

    # UI Configuration
    highlight_color: str = "#eab308"
    ui_radius: str = "12px"

    # Authentication
    auth_methods: list[str] = ["password"]
    oauth_providers: list[dict] = []

    # Support contacts — list of {"user_id": ..., "email": ..., "name": ...}
    support_contacts: list[dict] = []

    # M365 Integration
    m365_config: dict = {}

    # Default team for new user auto-assignment
    default_team_id: Optional[str] = None

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

    def get_classification_config(self) -> dict:
        """Return classification config with defaults merged in."""
        config = deepcopy(DEFAULT_CLASSIFICATION_CONFIG)
        if self.classification_config:
            _deep_merge(config, self.classification_config)
        return config

    def get_retention_config(self) -> dict:
        """Return retention config with defaults merged in."""
        config = deepcopy(DEFAULT_RETENTION_CONFIG)
        if self.retention_config:
            _deep_merge(config, self.retention_config)
        return config

    def get_m365_config(self) -> dict:
        """Return M365 config with defaults."""
        defaults = {
            "enabled": False,
            "client_id": "",
            "client_secret": "",
            "tenant_id": "",
        }
        if self.m365_config:
            _deep_merge(defaults, self.m365_config)
        return defaults

    def is_m365_enabled(self) -> bool:
        """Return whether M365 integration is enabled and configured."""
        cfg = self.get_m365_config()
        return bool(cfg.get("enabled") and cfg.get("client_id") and cfg.get("tenant_id"))
