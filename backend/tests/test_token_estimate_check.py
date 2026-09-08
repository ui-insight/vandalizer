"""The estimate is checked against what the model actually charged.

Every successful response reports `usage.input_tokens`. That is ground truth,
it is free, and until now it was never compared against what the planner
believed. The defect #648 fixed hid for months because nothing made that comparison.
"""

from __future__ import annotations

from app.services.token_estimate_check import evaluate_estimate


class TestEvaluateEstimate:
    def test_an_estimate_above_the_charge_is_not_reported(self):
        """The safe direction. Erring high is the intended behaviour."""
        assert evaluate_estimate(
            model="m", estimated=25_877, charged=25_402, input_budget=24_576
        ) is None

    def test_an_exact_estimate_is_not_reported(self):
        assert evaluate_estimate(
            model="m", estimated=1_000, charged=1_000, input_budget=24_576
        ) is None

    def test_an_estimate_below_the_charge_is_a_warning(self):
        """Read low but still fit: latent, not yet user-visible."""
        result = evaluate_estimate(
            model="m", estimated=2_154, charged=2_527, input_budget=24_576
        )
        assert result is not None
        assert result.severity == "warning"
        assert result.shortfall == 373

    def test_an_estimate_that_hid_an_overflow_is_critical(self):
        """The #648 failure exactly: planner said 23,592 against a 24,576
        budget -- 'fits, 984 spare' -- and the model charged 25,402 and
        rejected it. If this recurs it must be loud immediately."""
        result = evaluate_estimate(
            model="m", estimated=23_592, charged=25_402, input_budget=24_576
        )
        assert result is not None
        assert result.severity == "critical"
        assert result.shortfall == 1_810

    def test_a_charge_that_exactly_fills_the_budget_still_fit(self):
        """The severity boundary, which the cases above sit far away from.

        24,576 charged against a 24,576 budget fits exactly -- the request was
        answered -- so the low estimate is latent, not the #648 failure. Pins
        the comparison as ``>`` and not ``>=``, which an off-by-one refactor
        would otherwise flip without failing a single other test.
        """
        result = evaluate_estimate(
            model="m", estimated=24_000, charged=24_576, input_budget=24_576
        )
        assert result is not None
        assert result.severity == "warning"
        assert result.shortfall == 576

    def test_carries_the_numbers_needed_to_act(self):
        result = evaluate_estimate(
            model="Qwen/Qwen3.5-9B", estimated=100, charged=150, input_budget=1_000
        )
        assert result.model == "Qwen/Qwen3.5-9B"
        assert result.estimated == 100
        assert result.charged == 150
        assert result.input_budget == 1_000

    def test_missing_usage_is_not_a_shortfall(self):
        """Providers that report no usage must not look like an under-count."""
        assert evaluate_estimate(
            model="m", estimated=100, charged=0, input_budget=1_000
        ) is None


import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.token_estimate_check import EstimateShortfall, record_shortfall


def _shortfall(severity="warning"):
    return EstimateShortfall(
        model="Qwen/Qwen3.5-9B", estimated=2_154, charged=2_527,
        input_budget=24_576, severity=severity,
    )


def _critical_shortfall():
    """The #648 defect's own numbers: 23,592 planned, 25,402 charged, 24,576 budget.

    Unlike `_shortfall("critical")`, the severity here follows from the
    numbers, so assertions about what the message *says* about them hold.
    """
    return EstimateShortfall(
        model="Qwen/Qwen3.5-9B", estimated=23_592, charged=25_402,
        input_budget=24_576, severity="critical",
    )


class TestRecordShortfall:
    @pytest.mark.asyncio
    async def test_creates_an_alert_when_none_is_outstanding(self):
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=None)
            MockAlert.return_value.insert = AsyncMock()

            await record_shortfall(_shortfall())

            MockAlert.assert_called_once()
            kwargs = MockAlert.call_args.kwargs
            assert kwargs["alert_type"] == "token_undercount"
            assert kwargs["item_kind"] == "model"
            assert kwargs["item_id"] == "Qwen/Qwen3.5-9B"
            assert kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_does_not_duplicate_an_unacknowledged_alert(self):
        """Dedupe-by-unacknowledged is the convention in quality_tasks.py.
        Chat volume would otherwise bury the alerts table."""
        existing = MagicMock(severity="warning")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)

            await record_shortfall(_shortfall())

            MockAlert.assert_not_called()

    @pytest.mark.asyncio
    async def test_escalates_an_existing_warning_to_critical(self):
        """Otherwise the first mild case masks the real failure — which is
        the exact shape of bug this feature exists to catch."""
        existing = MagicMock(severity="warning")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)

            await record_shortfall(_shortfall(severity="critical"))

            assert existing.severity == "critical"
            existing.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_escalation_refreshes_the_message_too(self):
        """The escalated row is the most severe thing this feature raises, and
        it is the one an admin opens first. Flipping only `severity` leaves it
        showing the latent first occurrence's numbers, and describing a request
        that has already been rejected as one that might fail later."""
        existing = MagicMock(severity="warning", message="stale first-occurrence text")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)

            await record_shortfall(_critical_shortfall())

            assert "25,402" in existing.message  # what the model really charged
            assert "1,810" in existing.message  # by how much the estimate read low
            assert "rejected" in existing.message  # past tense: it already failed
            assert "stale" not in existing.message

    @pytest.mark.asyncio
    async def test_a_deduped_repeat_leaves_the_message_alone(self):
        """Only a state change rewrites the row. A no-op repeat that saved
        would turn dedupe into a write per chat turn."""
        existing = MagicMock(severity="warning", message="first-occurrence text")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)

            await record_shortfall(_shortfall())

            assert existing.message == "first-occurrence text"
            existing.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_downgrade_an_existing_critical(self):
        existing = MagicMock(severity="critical")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)

            await record_shortfall(_shortfall(severity="warning"))

            assert existing.severity == "critical"
            existing.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_database_failure_does_not_propagate(self, caplog):
        """This runs off the back of a chat response. A diagnostic must never
        break the product it is diagnosing.

        Swallowing is only defensible while the observation survives it. This
        is the one path that writes no alert row, so the numbers have to reach
        the log or the measurement is lost outright — and "nothing escaped" on
        its own is equally satisfied by ``except Exception: pass``.
        """
        import logging as _logging

        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(side_effect=RuntimeError("mongo down"))

            with caplog.at_level(_logging.DEBUG, logger=_LOGGER):
                await record_shortfall(_shortfall())  # must not raise

        errors = [r for r in caplog.records if r.levelno == _logging.ERROR]
        assert len(errors) == 1
        line = errors[0].getMessage()
        assert "2154" in line and "2527" in line and "24576" in line
        assert "Qwen/Qwen3.5-9B" in line
        # The traceback is what says *why* the write failed.
        assert errors[0].exc_info is not None


from app.services.token_estimate_check import check_and_record


class TestCheckAndRecord:
    @pytest.mark.asyncio
    async def test_records_when_the_estimate_read_low(self):
        with patch(
            "app.services.token_estimate_check.record_shortfall",
            new_callable=AsyncMock,
        ) as rec:
            await check_and_record(
                model="m", estimated=2_154, charged=2_527, input_budget=24_576
            )
            rec.assert_awaited_once()
            # Not just "something was recorded": the numbers have to survive
            # the hand-off intact. Swapping estimated/charged, or attributing
            # the shortfall to the wrong model, would otherwise pass.
            handed_over = rec.await_args[0][0]
            assert handed_over.model == "m"
            assert handed_over.estimated == 2_154
            assert handed_over.charged == 2_527
            assert handed_over.input_budget == 24_576
            assert handed_over.severity == "warning"

    @pytest.mark.asyncio
    async def test_records_nothing_when_the_estimate_was_safe(self):
        with patch(
            "app.services.token_estimate_check.record_shortfall",
            new_callable=AsyncMock,
        ) as rec:
            await check_and_record(
                model="m", estimated=25_877, charged=25_402, input_budget=24_576
            )
            rec.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_never_raises_into_the_caller(self):
        """The caller is mid-response to a user."""
        with patch(
            "app.services.token_estimate_check.evaluate_estimate",
            side_effect=RuntimeError("boom"),
        ):
            await check_and_record(
                model="m", estimated=1, charged=2, input_budget=3
            )  # must not raise

    @pytest.mark.asyncio
    async def test_a_failure_while_recording_does_not_raise_either(self):
        """Pins the docstring's "wrapped end to end" claim.

        `record_shortfall` opens its own `try` only around the database block,
        so its logging sits outside its never-raises guarantee. The guard here
        has to cover the await as well as the evaluate, and without this test
        shrinking it to the first statement passes unnoticed.
        """
        with patch(
            "app.services.token_estimate_check.record_shortfall",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await check_and_record(
                model="m", estimated=2_154, charged=2_527, input_budget=24_576
            )  # must not raise


import logging

_LOGGER = "app.services.token_estimate_check"


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestShortfallLoggingIsCoalesced:
    """Chat calls `record_shortfall` once per response. Warning on every call
    would emit a line per turn, forever, for a defect one alert row already
    captures -- the per-request noise this feature exists to remove."""

    @pytest.mark.asyncio
    async def test_the_first_occurrence_warns(self, caplog):
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=None)
            MockAlert.return_value.insert = AsyncMock()
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                await record_shortfall(_shortfall())

        assert len(_warnings(caplog)) == 1
        assert "estimate read low" in _warnings(caplog)[0].getMessage()

    @pytest.mark.asyncio
    async def test_a_deduped_repeat_does_not_warn_again(self, caplog):
        """The second and every later response for an already-alerted model."""
        existing = MagicMock(severity="warning")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                await record_shortfall(_shortfall())

        assert _warnings(caplog) == []
        # Still recorded, just quietly: the per-request numbers are what you
        # calibrate a model from.
        assert any(r.levelno == logging.DEBUG for r in caplog.records)

    @pytest.mark.asyncio
    async def test_an_escalation_warns_because_it_changed_something(self, caplog):
        existing = MagicMock(severity="warning")
        existing.save = AsyncMock()
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(return_value=existing)
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                await record_shortfall(_shortfall(severity="critical"))

        assert len(_warnings(caplog)) == 1


@pytest.fixture(autouse=True)
def _reset_failure_coalescing():
    """Per-process coalescing is process state, and pytest shares a process.

    Without this, whether a failure is ERROR or DEBUG depends on which test ran
    first — the assertions below would pass or fail on collection order.
    """
    from app.services.token_estimate_check import _FAILED_MODELS_LOGGED

    _FAILED_MODELS_LOGGED.clear()
    yield
    _FAILED_MODELS_LOGGED.clear()


class TestTheAlertMessageAnAdminReads:
    """The alert is the whole product of this feature; its text is the part an
    operator acts on."""

    def test_it_states_the_shortfall_and_the_budget(self):
        from app.services.token_estimate_check import _alert_message

        msg = _alert_message(_critical_shortfall())
        assert "23,592" in msg and "25,402" in msg
        assert "1,810" in msg, "the shortfall is the number an operator acts on"
        assert "24,576" in msg, "a shortfall means nothing without the budget"

    def test_it_names_a_control_that_exists(self):
        """Saying "Calibrate the model" pointed at a second, unwritten plan.
        The lever
        that exists today is `token_safety_margin` on the model config, which
        `context_budget.token_safety_margin` honours ahead of every other rung.
        """
        from app.services.token_estimate_check import _alert_message

        msg = _alert_message(_shortfall())
        assert "token_safety_margin" in msg
        assert "Calibrate" not in msg

    def test_severity_decides_the_tense(self):
        from app.services.token_estimate_check import _alert_message

        assert "rejected" in _alert_message(_critical_shortfall())
        assert "rejected" not in _alert_message(_shortfall())


class TestCheckFailuresAreCoalescedToo:
    """The shortfall WARNING was coalesced so a persistent under-count does not
    log once per chat turn. Both `except` handlers reintroduced that shape one
    level up, at ERROR and with a full traceback: a Mongo outage specific to
    `quality_alerts`, or a regressed coercion at the call site, is systemic and
    would repeat on every single response, indefinitely."""

    @pytest.mark.asyncio
    async def test_a_repeated_write_failure_drops_to_debug(self, caplog):
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(side_effect=RuntimeError("mongo down"))
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                for _ in range(4):
                    await record_shortfall(_shortfall())

        assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1
        # Still recorded, and still with a traceback: a later failure that is a
        # *different* exception is exactly what "already reported" would hide.
        debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debugs) == 3
        assert all(r.exc_info is not None for r in debugs)

    @pytest.mark.asyncio
    async def test_a_second_model_is_still_reported_loudly(self, caplog):
        """Coalescing is per model, so one broken model cannot silence the
        next one."""
        other = EstimateShortfall(
            model="other-model", estimated=1, charged=2, input_budget=3,
            severity="warning",
        )
        with patch("app.models.quality_alert.QualityAlert") as MockAlert:
            MockAlert.find_one = AsyncMock(side_effect=RuntimeError("mongo down"))
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                await record_shortfall(_shortfall())
                await record_shortfall(other)

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 2
        assert "other-model" in errors[1].getMessage()

    @pytest.mark.asyncio
    async def test_a_repeated_outer_failure_drops_to_debug(self, caplog):
        """The second handler, in `check_and_record`. Two handlers in two
        tasks' code, which is why neither task's review caught the pair."""
        with patch(
            "app.services.token_estimate_check.record_shortfall",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with caplog.at_level(logging.DEBUG, logger=_LOGGER):
                for _ in range(4):
                    await check_and_record(
                        model="m", estimated=2_154, charged=2_527,
                        input_budget=24_576,
                    )

        assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1
        assert len([r for r in caplog.records if r.levelno == logging.DEBUG]) == 3

    @pytest.mark.asyncio
    async def test_the_outer_failure_line_survives_a_non_numeric_argument(
        self, caplog
    ):
        """A regressed coercion at the call site is one of the failures this
        handler exists for, so its own line must not be the thing that breaks
        on it: `%d` against a string formats to nothing but a logging error."""
        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            await check_and_record(
                model="m", estimated="not-a-number", charged=2_527,
                input_budget=24_576,
            )

        errors = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert "not-a-number" in errors[0].getMessage()
