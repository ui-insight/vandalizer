"""Helpers for extraction runtime metrics."""

from app.models import ActivityEvent, ActivityStatus, ActivityType


def get_extraction_runtime_stats(
    search_set_uuid: str | None, sample_limit: int = 20
) -> dict:
    """Return average runtime stats for recent completed extraction runs."""
    if not search_set_uuid:
        return {"avg_runtime_seconds": None, "sample_size": 0, "sample_limit": sample_limit}

    runs = (
        ActivityEvent.objects(
            type=ActivityType.SEARCH_SET_RUN.value,
            search_set_uuid=search_set_uuid,
            status=ActivityStatus.COMPLETED.value,
            started_at__ne=None,
            finished_at__ne=None,
        )
        .order_by("-started_at")
        .limit(sample_limit)
    )

    durations_ms = [run.duration_ms for run in runs if run.duration_ms is not None]
    if not durations_ms:
        return {"avg_runtime_seconds": None, "sample_size": 0, "sample_limit": sample_limit}

    avg_ms = sum(durations_ms) / len(durations_ms)
    return {
        "avg_runtime_seconds": round(avg_ms / 1000, 1),
        "sample_size": len(durations_ms),
        "sample_limit": sample_limit,
    }
