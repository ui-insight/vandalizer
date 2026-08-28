"""What the "Optimized" badge on a knowledge base means — and whether it is
still true.

A KB is *Optimized* when KB Autovalidate found RAG settings (retrieval depth,
model, prompt variant, …) that beat the defaults on the KB's own test
questions, and those settings were **applied** — they now live in
``KnowledgeBase.rag_config_override`` and are what chat uses at runtime. It
is unrelated to *Verified*, which is an administrator publishing the KB to
the shared catalog: Verified vouches for the content, Optimized for the
settings.

That badge went stale silently. The settings were tuned against the sources
and test questions that existed when the run started; add a third of the
corpus, or rewrite the eval set, and the badge still said Optimized. This
module decides, per KB, one of:

* ``applied``   — tuned settings are live and the corpus / eval set are
                  materially what they were when tuned;
* ``stale``     — tuned settings are live, but the sources or the test
                  questions have changed materially since (re-run
                  Validate & improve);
* ``available`` — a completed optimization has settings that were never
                  applied, or were reverted.

"Materially" is ``STALE_FRACTION`` of what the run saw: at least one change,
and at least 10% of the sources (added or removed) or 10% of the test
questions (added, removed, or an expected answer edited). A 3-source KB is
stale after one change; a 50-source KB after five.

``compute_optimization_status`` is pure so it is unit-testable; the loaders
around it batch the lookups for a listing page.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel

STALE_FRACTION = 0.10

OptimizationState = Literal["applied", "stale", "available"]


@dataclass
class OptimizationStatus:
    state: OptimizationState
    applied_at: Optional[datetime.datetime] = None
    applied_run_uuid: Optional[str] = None
    # Most recent completed optimization run, applied or not.
    last_run_at: Optional[datetime.datetime] = None
    last_run_uuid: Optional[str] = None
    # Which RAG settings the applied override actually changes.
    tuned_keys: list[str] = field(default_factory=list)
    stale: bool = False
    stale_reasons: list[str] = field(default_factory=list)
    # What changed since the applied run started (0 when state != applied/stale).
    sources_at_run: int = 0
    sources_added: int = 0
    sources_removed: int = 0
    queries_at_run: int = 0
    queries_added: int = 0
    queries_removed: int = 0
    queries_edited: int = 0


@dataclass(frozen=True)
class SourceStamp:
    uuid: str
    created_at: Optional[datetime.datetime]


@dataclass(frozen=True)
class QueryStamp:
    uuid: str
    created_at: Optional[datetime.datetime]
    updated_at: Optional[datetime.datetime]
    expected_answer: Optional[str]


def _utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Mongo hands back naive datetimes; treat them as UTC so comparisons
    against the tz-aware values Beanie writes don't raise."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.timezone.utc)


def _answer_hash(expected: Optional[str]) -> Optional[str]:
    # Same digest ``kb_optimizer._snapshot_test_queries`` stores.
    if not expected:
        return None
    return hashlib.sha256(expected.encode("utf-8")).hexdigest()[:16]


def _material(changed: int, baseline: int) -> bool:
    return changed >= 1 and changed / max(baseline, 1) >= STALE_FRACTION


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def compute_optimization_status(
    *,
    rag_config_override: Optional[dict],
    override_set_at: Optional[datetime.datetime],
    override_run_uuid: Optional[str],
    applied_run,
    latest_completed_run,
    sources: list[SourceStamp],
    queries: list[QueryStamp],
) -> Optional[OptimizationStatus]:
    """Decide the KB's optimization state. Returns None when there is nothing
    to say — no applied override and no completed run with settings to apply.

    ``applied_run`` is the ``KBOptimizationRun`` named by
    ``override_run_uuid`` (may be None for overrides written before that was
    recorded); ``latest_completed_run`` the newest completed run for the KB.
    Both are read for ``uuid``, ``started_at``, ``completed_at``,
    ``best_config`` and ``test_query_snapshot`` only.
    """
    has_override = isinstance(rag_config_override, dict) and bool(rag_config_override)
    latest = latest_completed_run
    last_run_at = _utc(getattr(latest, "completed_at", None)) if latest else None
    last_run_uuid = getattr(latest, "uuid", None) if latest else None

    if not has_override:
        if latest is not None and getattr(latest, "best_config", None):
            return OptimizationStatus(
                state="available", last_run_at=last_run_at, last_run_uuid=last_run_uuid,
            )
        return None

    # The settings were tuned against the corpus and eval set as of the run's
    # start, so that is the reference point — fall back to the apply time for
    # overrides that predate ``rag_config_override_run_uuid``.
    ref_time = _utc(getattr(applied_run, "started_at", None)) if applied_run else None
    ref_time = ref_time or _utc(override_set_at)
    snapshot = (getattr(applied_run, "test_query_snapshot", None) or {}) if applied_run else {}

    status = OptimizationStatus(
        state="applied",
        applied_at=_utc(override_set_at),
        applied_run_uuid=override_run_uuid,
        last_run_at=last_run_at,
        last_run_uuid=last_run_uuid,
        tuned_keys=sorted(rag_config_override.keys()),
    )

    # --- sources -----------------------------------------------------------
    if ref_time is not None:
        present_before = sum(1 for s in sources if (_utc(s.created_at) or ref_time) <= ref_time)
        status.sources_added = len(sources) - present_before
    else:
        present_before = len(sources)
    snap_total_sources = snapshot.get("total_sources")
    status.sources_at_run = (
        int(snap_total_sources) if isinstance(snap_total_sources, int) else present_before
    )
    status.sources_removed = max(0, status.sources_at_run - present_before)

    # --- test questions ----------------------------------------------------
    snap_uuids = snapshot.get("query_uuids")
    if isinstance(snap_uuids, list) and snap_uuids:
        snap_set = set(snap_uuids)
        cur = {q.uuid: q for q in queries if q.uuid}
        status.queries_at_run = len(snap_set)
        status.queries_added = len(set(cur) - snap_set)
        status.queries_removed = len(snap_set - set(cur))
        hashes = snapshot.get("expected_answer_hashes") or {}
        edited = 0
        for uid in snap_set & set(cur):
            then, now = hashes.get(uid), _answer_hash(cur[uid].expected_answer)
            if then is not None and now is not None:
                edited += then != now
            elif ref_time is not None and (_utc(cur[uid].updated_at) or ref_time) > ref_time:
                edited += 1
        status.queries_edited = edited
    elif ref_time is not None:
        before = [q for q in queries if (_utc(q.created_at) or ref_time) <= ref_time]
        status.queries_at_run = len(before)
        status.queries_added = len(queries) - len(before)
        status.queries_edited = sum(
            1 for q in before if (_utc(q.updated_at) or ref_time) > ref_time
        )
    else:
        status.queries_at_run = len(queries)

    # --- verdict -----------------------------------------------------------
    src_changed = status.sources_added + status.sources_removed
    if _material(src_changed, status.sources_at_run):
        bits = []
        if status.sources_added:
            bits.append(f"{status.sources_added} added")
        if status.sources_removed:
            bits.append(f"{status.sources_removed} removed")
        status.stale_reasons.append(
            f"Sources changed since the settings were tuned: {', '.join(bits)} "
            f"(had {_plural(status.sources_at_run, 'source')})."
        )
    q_changed = status.queries_added + status.queries_removed + status.queries_edited
    if _material(q_changed, status.queries_at_run):
        bits = []
        if status.queries_added:
            bits.append(f"{status.queries_added} added")
        if status.queries_removed:
            bits.append(f"{status.queries_removed} removed")
        if status.queries_edited:
            bits.append(f"{_plural(status.queries_edited, 'expected answer')} edited")
        status.stale_reasons.append(
            f"Test questions changed since the settings were tuned: {', '.join(bits)} "
            f"(had {_plural(status.queries_at_run, 'question')})."
        )
    if status.stale_reasons:
        status.stale = True
        status.state = "stale"
    return status


# ---------------------------------------------------------------------------
# Batch loader for list/detail endpoints.
# ---------------------------------------------------------------------------


class _SourceRow(BaseModel):
    uuid: str = ""
    knowledge_base_uuid: str
    created_at: Optional[datetime.datetime] = None


class _QueryRow(BaseModel):
    uuid: str = ""
    knowledge_base_uuid: str
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    expected_answer: Optional[str] = None


async def optimization_status_by_kb(kbs: list) -> dict[str, OptimizationStatus]:
    """Optimization state for each KB in ``kbs``, keyed by uuid; KBs with
    nothing to report are absent. Four queries for the whole batch."""
    from app.models.kb_optimization_run import KBOptimizationRun
    from app.models.kb_test_query import KBTestQuery
    from app.models.knowledge import KnowledgeBaseSource

    if not kbs:
        return {}
    uuids = [kb.uuid for kb in kbs]

    latest: dict[str, KBOptimizationRun] = {}
    by_uuid: dict[str, KBOptimizationRun] = {}
    runs = await KBOptimizationRun.find({
        "kb_uuid": {"$in": uuids},
        "status": "completed",
    }).sort("-completed_at").to_list()
    for r in runs:
        by_uuid[r.uuid] = r
        latest.setdefault(r.kb_uuid, r)

    # An applied run is normally completed, but fetch any that aren't in the
    # completed set (e.g. auto-applied during finalizing) so staleness has
    # its snapshot.
    wanted = {
        kb.rag_config_override_run_uuid
        for kb in kbs
        if getattr(kb, "rag_config_override_run_uuid", None)
    } - set(by_uuid)
    if wanted:
        for r in await KBOptimizationRun.find({"uuid": {"$in": list(wanted)}}).to_list():
            by_uuid[r.uuid] = r

    overridden = [
        kb.uuid for kb in kbs
        if isinstance(getattr(kb, "rag_config_override", None), dict) and kb.rag_config_override
    ]
    sources: dict[str, list[SourceStamp]] = {u: [] for u in overridden}
    queries: dict[str, list[QueryStamp]] = {u: [] for u in overridden}
    if overridden:
        for s in await KnowledgeBaseSource.find(
            {"knowledge_base_uuid": {"$in": overridden}},
        ).project(_SourceRow).to_list():
            sources[s.knowledge_base_uuid].append(SourceStamp(s.uuid, s.created_at))
        for q in await KBTestQuery.find(
            {"knowledge_base_uuid": {"$in": overridden}},
        ).project(_QueryRow).to_list():
            queries[q.knowledge_base_uuid].append(
                QueryStamp(q.uuid, q.created_at, q.updated_at, q.expected_answer),
            )

    out: dict[str, OptimizationStatus] = {}
    for kb in kbs:
        run_uuid = getattr(kb, "rag_config_override_run_uuid", None)
        status = compute_optimization_status(
            rag_config_override=getattr(kb, "rag_config_override", None),
            override_set_at=getattr(kb, "rag_config_override_set_at", None),
            override_run_uuid=run_uuid,
            applied_run=by_uuid.get(run_uuid) if run_uuid else None,
            latest_completed_run=latest.get(kb.uuid),
            sources=sources.get(kb.uuid, []),
            queries=queries.get(kb.uuid, []),
        )
        if status is not None:
            out[kb.uuid] = status
    return out
