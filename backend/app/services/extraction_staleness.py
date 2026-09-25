"""The one definition of "this extraction lock is dead".

Text extraction takes a lock on the document — ``processing=True``,
``task_status="extracting"``, ``raw_text=""`` — and stamps ``updated_at`` when
it does. Two callers must agree on how old that stamp has to be before the
worker behind it is presumed dead:

* the retry route (``routers/documents.py``), which lets a user force a retry
  past an in-flight lock once it is stale rather than answering 409 forever;
* the ``tasks.document.reap_stuck`` sweep (``tasks/document_tasks.py``), which
  marks such a document failed so the library stops saying "Reading text…".

Two clocks for one lock is the class of bug #835 complains about: a route
that allows a retry while the reaper still considers the lock live (or the
reverse) puts two extractions on the same document. Both import from here.

This module deliberately imports nothing from Celery or the task modules —
the router must not pull the worker stack in at import time.
"""

from __future__ import annotations

import datetime

# ``celery.conf.task_time_limit`` in ``app/celery_app.py``. The extraction
# task sets no limit of its own, so the global hard limit is its ceiling.
# Hard-coded rather than imported so this module stays Celery-free;
# ``tests/test_document_tasks.py`` pins the two together.
EXTRACTION_TASK_HARD_TIME_LIMIT_SECONDS = 3660

# A task cannot legitimately outlive its hard time limit — Celery SIGKILLs it
# there — so a lock older than twice that belongs to a worker that died
# without writing anything back (OOM, a deploy replacing the container, the
# hard limit itself). Twice, not once, is the same margin the workflow-run
# reaper uses: it absorbs clock skew between beat and workers and a retry
# that was still backing off. Anything shorter risks reaping a large OCR job
# that is still running, whose worker would then overwrite the error with a
# completion — or, worse, letting a user's retry dispatch a second extraction
# alongside it.
EXTRACTION_STALE_AFTER = datetime.timedelta(
    seconds=2 * EXTRACTION_TASK_HARD_TIME_LIMIT_SECONDS,
)


def extraction_is_stale(
    updated_at: datetime.datetime | None,
    created_at: datetime.datetime | None = None,
    *,
    now: datetime.datetime | None = None,
) -> bool:
    """True when an in-flight extraction lock is older than the window.

    ``updated_at`` is the lock stamp. A row that has none predates the
    stamping; fall back to ``created_at`` so an old stranded row is still
    reaped while a brand-new one is not. A row with neither is treated as
    stale — there is nothing to say it is alive.
    """
    stamp = updated_at if updated_at is not None else created_at
    if stamp is None:
        return True
    if now is None:
        now = (
            datetime.datetime.now(stamp.tzinfo)
            if stamp.tzinfo
            else datetime.datetime.now()
        )
    return now - stamp > EXTRACTION_STALE_AFTER
