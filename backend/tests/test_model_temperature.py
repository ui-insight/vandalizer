"""Per-model sampling temperature must survive the admin API and reach the model.

Temperature was the one sampling control the product never sent. `UserConfig`
carried a `temperature` field that nothing read, there was no UI for it, and
every request went out with no temperature at all — so the provider default
(~0.7 on vLLM) applied everywhere. Extraction and document chat therefore
returned a different answer to the same question on the same document, which
reads as a data bug rather than a sampling one.

These tests cover the two places it can silently go missing: the admin request
schema, and the persisted model entry the settings builder reads.
"""

from app.routers.admin import ModelAddRequest
from app.services.llm_service import build_thinking_model_settings


def _cfg(**model_fields):
    model_fields.setdefault("name", "the-model")
    return {"available_models": [model_fields]}


class TestAdminSchema:
    def test_temperature_is_accepted(self):
        body = ModelAddRequest(name="m", tag="m", temperature=0.2)
        assert body.temperature == 0.2

    def test_zero_is_preserved_by_the_schema(self):
        """The deterministic setting must not be coerced away as falsy."""
        body = ModelAddRequest(name="m", tag="m", temperature=0)
        assert body.temperature == 0.0

    def test_absent_temperature_stays_none(self):
        """None means 'use the provider default' — existing models are untouched."""
        assert ModelAddRequest(name="m", tag="m").temperature is None


class TestEndToEndThroughSettings:
    """A value saved by an admin has to come out the other end of the builder."""

    def test_a_saved_temperature_reaches_the_request(self):
        saved = {"name": "m", "temperature": 0.0}
        assert build_thinking_model_settings("m", system_config_doc=_cfg(**saved))[
            "temperature"
        ] == 0.0

    def test_a_model_without_one_sends_no_temperature(self):
        settings = build_thinking_model_settings("m", system_config_doc=_cfg(name="m"))
        assert "temperature" not in settings
