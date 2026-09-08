"""Tests for the SystemConfig branding fields (issue #819).

`app_name` names the tool in conversation; `org_name` stays the institution's
name, which other services stamp into creator credits. Adding `app_name` must
be purely additive: a deployment that only ever set `org_name` reads exactly
as it did before the upgrade.
"""

from app.models.system_config import SystemConfig


def test_app_name_defaults_to_empty():
    """Empty means 'fall back to org_name' — nothing is assumed about the tool."""
    config = SystemConfig.model_construct()
    assert config.app_name == ""


def test_existing_org_name_config_is_unchanged_by_the_new_field():
    """An install that set only org_name keeps every branding value it had."""
    config = SystemConfig.model_construct(org_name="Roger Williams University")

    assert config.org_name == "Roger Williams University"
    assert config.app_name == ""
    assert config.logo_data_url == ""
    assert config.icon_data_url == ""
    assert config.icon_hide_in_nav is False


def test_app_name_is_independent_of_org_name():
    """The two fields hold different values without either overwriting the other."""
    config = SystemConfig.model_construct(
        org_name="Roger Williams University",
        app_name="Vandalizer",
    )

    assert config.org_name == "Roger Williams University"
    assert config.app_name == "Vandalizer"
