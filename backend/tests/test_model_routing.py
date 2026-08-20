"""Choosing a bigger model when a document doesn't fit the current one.

A complete grant proposal is one document, and people want to read it as one.
Measured on a real 79-page grant proposal: 41,213 tokens against a 32,768-token
model. It cannot fit — not with better settings, not with the context-budget
share fixed. The model silently answered from 33 of 79 pages.

The same deployment had a 262,144-token model configured, which holds that
document four times over. Routing to it is the difference between reading a
proposal and reading part of one.

Two things make this dangerous if built naively, and both are tested here:

* **Privacy.** Model choice has always been a human decision. The moment the
  system chooses, "whichever window is big enough" can mean shipping a
  confidential proposal to an external API. `privacy` is stored on every model
  and displayed in the UI, but nothing in the backend has ever enforced it —
  this is the first feature that must.
* **Silence.** Switching models without saying so is the same failure shape as
  trimming a document without saying so.
"""

from app.services.model_routing import (
    PRIVACY_RANK,
    choose_document_model,
    suggest_document_model,
)


def _model(name, window, privacy="internal"):
    return {"name": name, "context_window": window, "privacy": privacy}


SMALL = _model("small", 32768)
LARGE = _model("large", 262144)


class TestWhenToSwitch:
    def test_a_request_that_fits_stays_put(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=1000,
        )
        assert d.switched is False
        assert d.model_name == "small"

    def test_a_request_that_does_not_fit_moves_to_the_larger_model(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=41213,          # the real 79-page grant proposal
        )
        assert d.switched is True
        assert d.model_name == "large"
        assert "41,213" in d.reason and "large" in d.reason

    def test_no_switch_when_the_candidate_would_also_compact(self):
        """Switching buys nothing if the document is trimmed either way —
        and it would cost the user the model they chose."""
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=999_999,
        )
        assert d.switched is False
        assert d.model_name == "small"

    def test_no_candidate_configured_is_not_an_error(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="", candidate_config=None,
            input_tokens=41213,
        )
        assert d.switched is False
        assert d.model_name == "small"

    def test_candidate_that_is_the_current_model_is_a_no_op(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="small", candidate_config=SMALL,
            input_tokens=41213,
        )
        assert d.switched is False

    def test_a_missing_candidate_config_does_not_switch(self):
        """Nominated model was deleted or renamed — fall back, don't guess."""
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="ghost", candidate_config=None,
            input_tokens=41213,
        )
        assert d.switched is False


class TestPrivacyGate:
    def test_never_escalates_from_internal_to_external(self):
        external = _model("cloud", 1_000_000, privacy="external")
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="cloud", candidate_config=external,
            input_tokens=41213,
        )
        assert d.switched is False
        assert "privacy" in d.reason.lower()

    def test_unspecified_privacy_counts_as_weaker_than_internal(self):
        """A blank privacy field is unknown, not safe. Refuse rather than
        assume a model nobody labelled is as protected as one labelled
        internal."""
        unknown = _model("mystery", 1_000_000, privacy="")
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="mystery", candidate_config=unknown,
            input_tokens=41213,
        )
        assert d.switched is False

    def test_equal_privacy_is_allowed(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=41213,
        )
        assert d.switched is True

    def test_external_current_may_route_to_internal_candidate(self):
        """Tightening privacy is always safe."""
        current = _model("cloud", 32768, privacy="external")
        d = choose_document_model(
            current_name="cloud", current_config=current,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=41213,
        )
        assert d.switched is True

    def test_internal_is_ranked_stricter_than_external(self):
        assert PRIVACY_RANK["internal"] < PRIVACY_RANK["external"]


class TestTheReasonIsUsable:
    def test_a_switch_explains_itself_in_the_users_terms(self):
        d = choose_document_model(
            current_name="small", current_config=SMALL,
            candidate_name="large", candidate_config=LARGE,
            input_tokens=41213,
        )
        # The notice goes to a person, so it names both models and the size.
        assert "small" in d.reason and "large" in d.reason
        assert d.reason.endswith(".")


class TestSuggestingAModel:
    """The context-limit dialog offers the user a way out, so it needs a
    candidate — chosen by the server, under the same privacy rule. Picking it
    in the browser from the model list would walk straight around the gate."""

    MODELS = [
        _model("small", 32768),
        _model("medium", 131072),
        _model("large", 262144),
        _model("cloud", 1_000_000, privacy="external"),
    ]

    def test_suggests_nothing_when_the_request_already_fits(self):
        assert suggest_document_model(
            current_name="small", current_config=SMALL,
            models=self.MODELS, input_tokens=1000,
        ) is None

    def test_suggests_the_smallest_model_that_fits(self):
        """Least disruptive: jumping straight to the biggest window changes the
        answering model more than the problem requires."""
        s = suggest_document_model(
            current_name="small", current_config=SMALL,
            models=self.MODELS, input_tokens=41213,
        )
        assert s is not None and s["name"] == "medium"

    def test_skips_models_that_would_not_fit_either(self):
        s = suggest_document_model(
            current_name="small", current_config=SMALL,
            models=self.MODELS, input_tokens=200_000,
        )
        assert s is not None and s["name"] == "large"

    def test_never_suggests_weaker_privacy_even_when_it_is_the_only_fit(self):
        s = suggest_document_model(
            current_name="small", current_config=SMALL,
            models=self.MODELS, input_tokens=900_000,
        )
        assert s is None

    def test_never_suggests_the_current_model(self):
        s = suggest_document_model(
            current_name="large", current_config=LARGE,
            models=self.MODELS, input_tokens=300_000,
        )
        assert s is None or s["name"] != "large"

    def test_no_configured_models_is_not_an_error(self):
        assert suggest_document_model(
            current_name="small", current_config=SMALL, models=[], input_tokens=41213,
        ) is None


class TestSizingAgainstTheCandidate:
    """The request is measured once, with the model the user is on.

    That number carries *that* model's safety margin — 1.0 where the count is
    exact (a local vocabulary, or OpenAI), 1.20 where it is an estimate.
    Comparing it against another model's budget mixes rulers: a request
    measured exactly looks like it fits a model whose own count comes out 20%
    higher, the router switches, and the model rejects the request. That is the
    "estimate reads low, so we hard-fail" failure the margin exists to prevent,
    relocated to the routing boundary.
    """

    def test_an_exact_count_is_inflated_before_it_is_offered_to_an_estimated_model(self):
        # gpt-4o counts exactly (margin 1.0). The candidate has no local
        # vocabulary, so its own count would run ~20% higher.
        current = _model("gpt-4o", 32768)
        candidate = _model("some-hosted-model", 100_000)

        # Sized on the current model's ruler this sits just inside the
        # candidate's budget; on the candidate's own ruler it does not.
        tokens = 88_000

        d = choose_document_model(
            current_name="gpt-4o",
            current_config=current,
            candidate_name="some-hosted-model",
            candidate_config=candidate,
            input_tokens=tokens,
        )
        assert d.switched is False, (
            "routed to a model that would have rejected the request"
        )
        assert "does not fit" in d.reason

    def test_a_request_that_genuinely_fits_still_routes(self):
        current = _model("gpt-4o", 32768)
        candidate = _model("some-hosted-model", 262_144)
        d = choose_document_model(
            current_name="gpt-4o",
            current_config=current,
            candidate_name="some-hosted-model",
            candidate_config=candidate,
            input_tokens=41_213,
        )
        assert d.switched is True
        assert d.model_name == "some-hosted-model"

    def test_a_stricter_candidate_ruler_never_shrinks_the_estimate(self):
        # Reverse direction: current is estimated (1.20), candidate exact (1.0).
        # Rescaling down would make the request look smaller than measured, so
        # the number is left alone — over-stating costs a bigger model, while
        # under-stating hard-fails.
        current = _model("some-hosted-model", 32768)
        candidate = _model("gpt-4o", 50_000)
        d = choose_document_model(
            current_name="some-hosted-model",
            current_config=current,
            candidate_name="gpt-4o",
            candidate_config=candidate,
            input_tokens=45_000,
        )
        # 45k already exceeds gpt-4o's usable budget; it must not be scaled down
        # into fitting.
        assert d.switched is False

    def test_the_suggestion_list_uses_each_candidate_ruler(self):
        current = _model("gpt-4o", 32768)
        estimated = _model("hosted-a", 100_000)
        suggestion = suggest_document_model(
            current_name="gpt-4o",
            current_config=current,
            models=[estimated],
            input_tokens=88_000,
        )
        assert suggestion is None, (
            "offered a model whose own count would not fit the request"
        )
