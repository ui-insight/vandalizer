"""Compare what the planner believed against what the model charged.

Every successful chat response reports the model's own input token count, read
off the usage object as `usage.input_tokens` (see `chat_service.py`; some
providers call the same number `prompt_tokens` on the wire, but that is not the
attribute this code reads). It is exact, it is already arriving, and comparing
against it costs nothing. The defect #648 fixed — a budget computed with
``cl100k_base`` for models that do not use it, under-counting a currency-dense
budget table by 43% and hard-failing ordinary documents — survived because no
code ever made this comparison.

Split deliberately: `evaluate_estimate` is arithmetic and is tested without a
database, while recording the result needs patched Beanie documents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Models whose self-check has already failed loudly, so a broken check reports
# once per process rather than once per chat response. Same rationale, and the
# same shape, as `context_budget._ESTIMATED_MODELS_WARNED`.
_FAILED_MODELS_LOGGED: set[str] = set()


def _log_failure_once(model: str, message: str, *args: object) -> None:
    """Report a failure of the check itself once per model per process.

    Both callers run off the back of a chat response, so an unconditional
    ``logger.exception`` here re-creates at ERROR — with a full traceback —
    exactly the per-turn noise the shortfall WARNING was coalesced to avoid.
    The failures this catches are systemic (``quality_alerts`` unreachable, a
    regressed coercion at the call site): they say the same thing on every
    turn, forever. Loud once, DEBUG thereafter, and it resets on restart, so a
    deploy or a config change is still visible.

    The traceback is kept on both branches — the DEBUG line is the only record
    of occurrences two onward, and a repeat that is a *different* exception is
    exactly what a bare "already reported" would hide.
    """
    first_time = model not in _FAILED_MODELS_LOGGED
    _FAILED_MODELS_LOGGED.add(model)
    log = logger.error if first_time else logger.debug
    log(message, *args, exc_info=True)


@dataclass
class EstimateShortfall:
    """An estimate that came in under what the model actually charged."""

    model: str
    estimated: int
    charged: int
    input_budget: int
    severity: str  # "warning" | "critical"

    @property
    def shortfall(self) -> int:
        return self.charged - self.estimated


def evaluate_estimate(
    *, model: str, estimated: int, charged: int, input_budget: int
) -> Optional[EstimateShortfall]:
    """Return a shortfall when the estimate read low, else None.

    Two severities, because two different things are being reported:

    * ``warning`` — the estimate was under but the request still fit. Latent:
      nothing broke, but the budget is optimistic and will bite nearer the
      boundary.
    * ``critical`` — the estimate said it fit and the charge exceeded the input
      budget. That is the #648 failure, and it means a user got an error
      instead of an answer.

    A charge that exactly fills the budget still fit, so the critical test is
    strictly ``>``, not ``>=``.

    ``charged`` of zero means the provider reported no usage; that is an absence
    of evidence, not an under-count. The ``charged <= 0`` clause states that
    intent, but note what it actually does: to change the result it would need
    ``estimated < charged <= 0``, i.e. a negative ``estimated``. Both operands
    are token counts and cannot go negative, so no input the system can produce
    reaches it — a no-usage response is already returned as ``None`` by
    ``estimated >= charged``. Keep it as an executable statement of the rule,
    but do not mistake it for a live branch, and do not write a test claiming to
    cover it: such a test would pass identically with the clause deleted.
    """
    if charged <= 0 or estimated >= charged:
        return None

    severity = "critical" if charged > input_budget else "warning"
    return EstimateShortfall(
        model=model,
        estimated=estimated,
        charged=charged,
        input_budget=input_budget,
        severity=severity,
    )


def _alert_message(shortfall: EstimateShortfall) -> str:
    """The sentence an admin reads in the Quality tab.

    Built in one place because it is written twice: on the first occurrence,
    and again when a warning escalates to critical. An escalated row that kept
    the first occurrence's text would show warning-sized numbers, and describe
    a request that has already failed as one that might.

    States the shortfall itself — the number an operator acts on ("read low by
    1,810") — and names the one control that exists today:
    ``token_safety_margin`` on the model config, which ``context_budget``
    honours ahead of every other rung. Stored calibration is a separate,
    unwritten plan; naming it here would point at a control that is not there.
    """
    if shortfall.severity == "critical":
        consequence = (
            f"That exceeded the input budget of {shortfall.input_budget:,}, "
            f"so this request was rejected instead of answered."
        )
    else:
        consequence = (
            f"It still fit the input budget of {shortfall.input_budget:,}, "
            f"but budgets for this model are optimistic and will fail nearer "
            f"the context limit."
        )
    return (
        f"Token estimate read low for {shortfall.model}: estimated "
        f"{shortfall.estimated:,} but the model charged "
        f"{shortfall.charged:,}, read low by {shortfall.shortfall:,} tokens. "
        f"{consequence} Raise token_safety_margin on this model's config, or "
        f"check that its name matches its published identifier."
    )


async def record_shortfall(shortfall: EstimateShortfall) -> None:
    """Raise (or escalate) an admin-visible alert for an optimistic estimate.

    Deduped by unacknowledged alert for the same model, which is the
    convention in ``quality_tasks.py``. ``QualityAlert`` has no
    occurrence-counting — that belongs to ``Notification`` — and adding a
    second coalescing mechanism here would be two ways to do one thing.

    An existing warning escalates to critical, but never the reverse: if the
    mild case were allowed to mask the severe one, this alert would reproduce
    the failure it exists to report.

    Never raises. It is called off the back of a chat response, and a
    diagnostic that can break the product is worse than no diagnostic.

    Logging is coalesced on the same key as the alert, deliberately. Chat calls
    this once per response, so warning on entry would emit a line per turn,
    forever, for a defect a single alert row already captures — the per-request
    noise this feature exists to avoid. A WARNING marks a state change (a new
    alert, or an escalation); a repeat that changes nothing goes to DEBUG,
    where the per-request numbers are still available for calibrating a model.
    """
    summary = (
        "token estimate read low for %s: estimated %d, charged %d "
        "(budget %d, severity %s)"
    )
    details = (
        shortfall.model, shortfall.estimated, shortfall.charged,
        shortfall.input_budget, shortfall.severity,
    )
    try:
        import datetime

        from app.models.quality_alert import QualityAlert

        existing = await QualityAlert.find_one(
            QualityAlert.alert_type == "token_undercount",
            QualityAlert.item_kind == "model",
            QualityAlert.item_id == shortfall.model,
            QualityAlert.acknowledged == False,  # noqa: E712
        )
        if existing is not None:
            if shortfall.severity == "critical" and existing.severity != "critical":
                existing.severity = "critical"
                # Refresh the text along with the severity: the escalated row
                # is the most severe thing this feature raises, and leaving it
                # describing the latent first occurrence makes exactly that row
                # wrong. `created_at` stays first-seen; admin sorting reads it.
                existing.message = _alert_message(shortfall)
                await existing.save()
                logger.warning(summary, *details)
            else:
                logger.debug(summary, *details)
            return

        await QualityAlert(
            alert_type="token_undercount",
            item_kind="model",
            item_id=shortfall.model,
            item_name=shortfall.model,
            severity=shortfall.severity,
            message=_alert_message(shortfall),
            created_at=datetime.datetime.now(tz=datetime.timezone.utc),
        ).insert()
        logger.warning(summary, *details)
    except Exception:
        # Carry the measurement into the failure line. This is the one path
        # where no alert row is written, so if the numbers do not appear here
        # they appear nowhere at all — and swallowing the exception is only
        # defensible while the observation survives it.
        _log_failure_once(
            shortfall.model,
            "could not record token-estimate alert; " + summary,
            *details,
        )


async def check_and_record(
    *, model: str, estimated: int, charged: int, input_budget: int
) -> None:
    """Entry point for callers holding a completed response.

    Wrapped end to end: a diagnostic must never surface as a chat failure.
    """
    try:
        shortfall = evaluate_estimate(
            model=model, estimated=estimated,
            charged=charged, input_budget=input_budget,
        )
        if shortfall is not None:
            await record_shortfall(shortfall)
    except Exception:
        # %s, not %d: the failures that reach here include a caller handing
        # over something that is not a number, and a log line that cannot
        # format itself is no diagnostic at all.
        _log_failure_once(
            model,
            "token estimate self-check failed for %s "
            "(estimated %s, charged %s, budget %s)",
            model, estimated, charged, input_budget,
        )
