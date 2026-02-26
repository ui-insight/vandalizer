"""Helpers for canonical user identity resolution and duplicate merges."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

import mongoengine as me
from bson import ObjectId
from flask import current_app, has_app_context
from mongoengine.queryset.visitor import Q


_ROLE_RANK = {"owner": 0, "admin": 1, "member": 2}
_DAILY_USAGE_SUM_FIELDS = (
    "conversations",
    "searches",
    "workflows_started",
    "workflows_completed",
    "workflows_failed",
    "tokens_input",
    "tokens_output",
    "documents_touched",
    "workflow_duration_ms",
    "conversation_messages",
)


@dataclass
class MergeStats:
    """Tracks per-collection updates during duplicate-user merge."""

    canonical_user_id: str
    merged_user_ids: list[str] = field(default_factory=list)
    reassigned_counts: dict[str, int] = field(default_factory=dict)

    def bump(self, key: str, count: int = 1) -> None:
        if count <= 0:
            return
        self.reassigned_counts[key] = self.reassigned_counts.get(key, 0) + count


def normalize_identity(value: str | None) -> str | None:
    """Normalize an identity value (email/UPN/user_id) for matching."""
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _log_info(message: str) -> None:
    if has_app_context():
        current_app.logger.info(message)
    else:
        print(message)


def _log_warning(message: str) -> None:
    if has_app_context():
        current_app.logger.warning(message)
    else:
        print(f"WARNING: {message}")


def _candidate_identity_values(*values: str | None) -> set[str]:
    candidates: set[str] = set()
    for value in values:
        if not value:
            continue
        stripped = value.strip()
        if not stripped:
            continue
        candidates.add(stripped)
        lowered = stripped.lower()
        if lowered != stripped:
            candidates.add(lowered)
    return candidates


def find_identity_matches(
    *, user_id_hint: str | None = None, email_hint: str | None = None
) -> list["User"]:
    """Find users matching either user_id or email for the provided hints."""
    from app.models import User

    values = _candidate_identity_values(user_id_hint, email_hint)
    if not values:
        return []

    query: Q | None = None
    for value in values:
        clause = (
            Q(user_id=value)
            | Q(email=value)
            | Q(user_id__iexact=value)
            | Q(email__iexact=value)
        )
        query = clause if query is None else (query | clause)

    if query is None:
        return []

    users = list(User.objects(query))
    deduped_by_id: dict[str, "User"] = {str(user.id): user for user in users}
    return list(deduped_by_id.values())


def _user_created_at(user: "User") -> dt.datetime:
    pk = getattr(user, "pk", None)
    if isinstance(pk, ObjectId):
        return pk.generation_time
    return dt.datetime.max.replace(tzinfo=dt.timezone.utc)


def _pick_canonical_user(users: list["User"]) -> "User":
    if not users:
        raise ValueError("Cannot choose canonical user from an empty list.")

    max_dt = dt.datetime.max.replace(tzinfo=dt.timezone.utc)

    def sort_key(user: "User") -> tuple[int, int, int, int, float]:
        created_at = _user_created_at(user)
        created_ts = created_at.timestamp() if created_at != max_dt else float("inf")
        return (
            1 if bool(getattr(user, "is_admin", False)) else 0,
            1 if bool(getattr(user, "is_examiner", False)) else 0,
            1 if bool(getattr(user, "password_hash", None)) else 0,
            1 if bool(getattr(user, "current_team", None)) else 0,
            -created_ts,
        )

    return max(users, key=sort_key)


def _best_role(*roles: str | None) -> str:
    current = "member"
    current_rank = _ROLE_RANK[current]
    for role in roles:
        candidate = (role or "member").strip().lower()
        rank = _ROLE_RANK.get(candidate, _ROLE_RANK["member"])
        if rank < current_rank:
            current = candidate
            current_rank = rank
    return current


def _merge_team_memberships(
    canonical_user_id: str,
    duplicate_user_id: str,
    stats: MergeStats,
) -> None:
    from app.models import TeamMembership

    duplicate_memberships = list(TeamMembership.objects(user_id=duplicate_user_id))
    for duplicate_membership in duplicate_memberships:
        existing_membership = TeamMembership.objects(
            team=duplicate_membership.team, user_id=canonical_user_id
        ).first()

        if existing_membership:
            merged_role = _best_role(existing_membership.role, duplicate_membership.role)
            if existing_membership.role != merged_role:
                existing_membership.role = merged_role
                existing_membership.save()
            duplicate_membership.delete()
            stats.bump("TeamMembership.merged", 1)
            continue

        duplicate_membership.user_id = canonical_user_id
        duplicate_membership.save()
        stats.bump("TeamMembership.user_id", 1)


def _merge_personal_libraries(
    canonical_user_id: str,
    duplicate_user_id: str,
    stats: MergeStats,
) -> None:
    from app.models import Library, LibraryScope

    canonical_library = Library.objects(
        scope=LibraryScope.PERSONAL, owner_user_id=canonical_user_id
    ).first()
    duplicate_libraries = list(
        Library.objects(scope=LibraryScope.PERSONAL, owner_user_id=duplicate_user_id)
    )

    for duplicate_library in duplicate_libraries:
        if canonical_library and duplicate_library.id == canonical_library.id:
            continue

        if canonical_library:
            existing_item_ids = {str(item.id) for item in canonical_library.items}
            moved_items = 0
            for item in duplicate_library.items:
                item_id = str(item.id)
                if item_id in existing_item_ids:
                    continue
                canonical_library.items.append(item)
                existing_item_ids.add(item_id)
                moved_items += 1

            if moved_items:
                canonical_library.updated_at = dt.datetime.now(dt.timezone.utc)
                canonical_library.save()
                stats.bump("Library.items", moved_items)

            duplicate_library.delete()
            stats.bump("Library.deleted", 1)
            continue

        duplicate_library.owner_user_id = canonical_user_id
        duplicate_library.save()
        canonical_library = duplicate_library
        stats.bump("Library.owner_user_id", 1)


def _merge_daily_usage_aggregates(
    canonical_user_id: str,
    duplicate_user_id: str,
    stats: MergeStats,
) -> None:
    from app.models import DailyUsageAggregate

    duplicate_aggregates = list(
        DailyUsageAggregate.objects(scope="user", user_id=duplicate_user_id)
    )
    for duplicate_agg in duplicate_aggregates:
        canonical_agg = DailyUsageAggregate.objects(
            scope="user", date=duplicate_agg.date, user_id=canonical_user_id
        ).first()
        if canonical_agg:
            for field in _DAILY_USAGE_SUM_FIELDS:
                current_value = getattr(canonical_agg, field, 0) or 0
                duplicate_value = getattr(duplicate_agg, field, 0) or 0
                setattr(canonical_agg, field, current_value + duplicate_value)
            canonical_agg.updated_at = dt.datetime.utcnow()
            canonical_agg.save()
            duplicate_agg.delete()
            stats.bump("DailyUsageAggregate.merged", 1)
            continue

        duplicate_agg.user_id = canonical_user_id
        duplicate_agg.save()
        stats.bump("DailyUsageAggregate.user_id", 1)


def _iter_generic_user_id_targets():
    from app import models as app_models

    handled = {
        ("TeamMembership", "user_id"),
        ("Library", "owner_user_id"),
        ("DailyUsageAggregate", "user_id"),
    }

    for value in vars(app_models).values():
        if not isinstance(value, type):
            continue
        if not issubclass(value, me.Document):
            continue
        if value.__module__ != "app.models":
            continue
        if value.__name__ == "User":
            continue

        for field_name, field in value._fields.items():
            if not isinstance(field, me.StringField):
                continue
            if field_name != "user_id" and not field_name.endswith("_user_id"):
                continue
            if (value.__name__, field_name) in handled:
                continue
            yield value, field_name


def _reassign_generic_user_id_fields(
    canonical_user_id: str,
    duplicate_user_id: str,
    stats: MergeStats,
) -> None:
    for doc_cls, field_name in _iter_generic_user_id_targets():
        selector = {field_name: duplicate_user_id}
        update_clause = {f"set__{field_name}": canonical_user_id}
        try:
            updated = int(doc_cls.objects(**selector).update(**update_clause))
        except Exception as exc:  # pragma: no cover - defensive logging path
            _log_warning(
                f"Failed to reassign {doc_cls.__name__}.{field_name} for duplicate "
                f"user '{duplicate_user_id}' -> '{canonical_user_id}': {exc}"
            )
            continue
        stats.bump(f"{doc_cls.__name__}.{field_name}", updated)


def _merge_user_profile_fields(canonical_user: "User", duplicate_user: "User") -> None:
    changed = False

    if getattr(duplicate_user, "is_admin", False) and not getattr(
        canonical_user, "is_admin", False
    ):
        canonical_user.is_admin = True
        changed = True

    if getattr(duplicate_user, "is_examiner", False) and not getattr(
        canonical_user, "is_examiner", False
    ):
        canonical_user.is_examiner = True
        changed = True

    if getattr(duplicate_user, "password_hash", None) and not getattr(
        canonical_user, "password_hash", None
    ):
        canonical_user.password_hash = duplicate_user.password_hash
        changed = True

    if getattr(duplicate_user, "current_team", None) and not getattr(
        canonical_user, "current_team", None
    ):
        canonical_user.current_team = duplicate_user.current_team
        changed = True

    duplicate_email = normalize_identity(getattr(duplicate_user, "email", None))
    canonical_email = normalize_identity(getattr(canonical_user, "email", None))
    if duplicate_email and not canonical_email:
        canonical_user.email = duplicate_email
        changed = True

    if getattr(duplicate_user, "name", None) and not getattr(canonical_user, "name", None):
        canonical_user.name = duplicate_user.name
        changed = True

    if changed:
        canonical_user.save()


def merge_user_into_canonical(canonical_user: "User", duplicate_user: "User") -> MergeStats:
    """Merge duplicate_user into canonical_user and delete duplicate_user."""
    if str(canonical_user.id) == str(duplicate_user.id):
        return MergeStats(canonical_user_id=canonical_user.user_id)

    stats = MergeStats(canonical_user_id=canonical_user.user_id)

    # If both docs already share the same user_id, only merge profile flags and
    # remove the duplicate user document. No foreign-key style rewrites are needed.
    if canonical_user.user_id == duplicate_user.user_id:
        _merge_user_profile_fields(canonical_user, duplicate_user)
        duplicate_user.delete()
        stats.merged_user_ids.append(duplicate_user.user_id)
        return stats

    _log_info(
        f"Merging duplicate user '{duplicate_user.user_id}' into "
        f"canonical user '{canonical_user.user_id}'."
    )

    _merge_team_memberships(canonical_user.user_id, duplicate_user.user_id, stats)
    _merge_personal_libraries(canonical_user.user_id, duplicate_user.user_id, stats)
    _merge_daily_usage_aggregates(canonical_user.user_id, duplicate_user.user_id, stats)
    _reassign_generic_user_id_fields(canonical_user.user_id, duplicate_user.user_id, stats)
    _merge_user_profile_fields(canonical_user, duplicate_user)

    duplicate_user_id = duplicate_user.user_id
    duplicate_user.delete()
    stats.merged_user_ids.append(duplicate_user_id)
    return stats


def resolve_user_identity(
    *,
    user_id_hint: str | None = None,
    email_hint: str | None = None,
    name_hint: str | None = None,
    create_if_missing: bool = True,
    auto_merge_duplicates: bool = True,
) -> "User | None":
    """Resolve and optionally create/merge user records for a login identity."""
    from app.models import User

    normalized_user_id = normalize_identity(user_id_hint)
    normalized_email = normalize_identity(email_hint) or normalized_user_id

    matches = find_identity_matches(
        user_id_hint=normalized_user_id,
        email_hint=normalized_email,
    )

    if not matches:
        if not create_if_missing:
            return None
        new_user_id = normalized_user_id or normalized_email
        if not new_user_id:
            return None
        new_user = User(
            user_id=new_user_id,
            email=normalized_email or new_user_id,
            name=name_hint,
        ).save()
        return new_user

    canonical_user = _pick_canonical_user(matches)
    duplicate_users = [u for u in matches if str(u.id) != str(canonical_user.id)]

    if auto_merge_duplicates and duplicate_users:
        for duplicate_user in duplicate_users:
            try:
                merge_user_into_canonical(canonical_user, duplicate_user)
            except Exception as exc:  # pragma: no cover - defensive logging path
                _log_warning(
                    f"Failed to merge duplicate user '{duplicate_user.user_id}' into "
                    f"'{canonical_user.user_id}': {exc}"
                )
        canonical_user.reload()

    changed = False
    if normalized_email and normalize_identity(canonical_user.email) != normalized_email:
        canonical_user.email = normalized_email
        changed = True

    if name_hint and not canonical_user.name:
        canonical_user.name = name_hint
        changed = True

    if changed:
        canonical_user.save()

    return canonical_user


def find_duplicate_identity_keys() -> list[str]:
    """Return identity keys (typically email) that map to >1 user rows."""
    from app.models import User

    counts: dict[str, int] = defaultdict(int)
    for user in User.objects.only("email", "user_id"):
        key = normalize_identity(user.email) or normalize_identity(user.user_id)
        if not key:
            continue
        counts[key] += 1
    return sorted([key for key, count in counts.items() if count > 1])
