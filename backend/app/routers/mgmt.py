"""Management API (/api/mgmt/v1).

Read-only surface for service consumers (dashboards, agentic tooling)
authenticated via scoped ApiKey records. Each endpoint declares the
scope it requires via require_mgmt_scope; calls are recorded in the
audit log with actor_type='api_key'.
"""

import datetime
from typing import Optional

from bson.decimal128 import Decimal128
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.dependencies import require_mgmt_scope
from app.models.activity import ActivityEvent
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.search_set import SearchSet
from app.models.system_config import SystemConfig
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.models.validation_run import ValidationRun
from app.models.workflow import Workflow, WorkflowResult
from app.rate_limit import limiter, mgmt_key_func

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _coerce_int(value: object) -> int:
    """Best-effort conversion of a Mongo aggregation scalar to a Python int.

    Aggregation accumulators can hand back ints, floats, BSON Decimal128 (when
    legacy records stored a numeric field as NumberDecimal), or None on an empty
    group. int() chokes on Decimal128 and None, so normalize first.
    """
    if value is None:
        return 0
    if isinstance(value, Decimal128):
        return int(value.to_decimal())
    return int(value)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class StatsResponse(BaseModel):
    users_total: int
    users_active_30d: int
    teams_total: int
    documents_total: int
    documents_size_bytes_total: int
    workflows_total: int
    workflow_runs_total: int
    workflow_runs_running: int
    workflow_runs_failed_30d: int
    activity_events_30d: int
    generated_at: datetime.datetime


class PageMeta(BaseModel):
    skip: int
    limit: int
    total: int


class UserItem(BaseModel):
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    is_admin: bool
    is_staff: bool
    organization_id: Optional[str] = None
    last_login_at: Optional[datetime.datetime] = None
    is_demo_user: bool
    demo_status: Optional[str] = None


class UserListResponse(BaseModel):
    items: list[UserItem]
    page: PageMeta


class TeamItem(BaseModel):
    id: str
    name: str
    member_count: int
    created_at: Optional[datetime.datetime] = None


class TeamListResponse(BaseModel):
    items: list[TeamItem]
    page: PageMeta


class WorkflowItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    num_executions: int
    verified: bool
    version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class WorkflowListResponse(BaseModel):
    items: list[WorkflowItem]
    page: PageMeta


class WorkflowRunItem(BaseModel):
    id: str
    workflow_id: Optional[str] = None
    session_id: str
    status: str
    num_steps_completed: int
    num_steps_total: int
    start_time: datetime.datetime
    trigger_type: Optional[str] = None
    is_passive: bool
    document_title: Optional[str] = None


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunItem]
    page: PageMeta


class DocumentItem(BaseModel):
    id: str
    uuid: str
    title: str
    extension: str
    user_id: str
    team_id: Optional[str] = None
    folder: Optional[str] = None
    classification: Optional[str] = None
    num_pages: int
    token_count: int
    soft_deleted: bool
    created_at: datetime.datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentItem]
    page: PageMeta


class ActivityItem(BaseModel):
    id: str
    type: str
    status: str
    title: Optional[str] = None
    user_id: str
    team_id: Optional[str] = None
    started_at: datetime.datetime
    finished_at: Optional[datetime.datetime] = None
    tokens_input: int
    tokens_output: int
    error: Optional[str] = None


class ActivityListResponse(BaseModel):
    items: list[ActivityItem]
    page: PageMeta


class AuditItem(BaseModel):
    uuid: str
    timestamp: datetime.datetime
    actor_user_id: str
    actor_type: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    team_id: Optional[str] = None
    organization_id: Optional[str] = None
    detail: dict


class AuditListResponse(BaseModel):
    items: list[AuditItem]
    page: PageMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


async def _user_for_key(api_key: ApiKey) -> User:
    """Resolve the User that owns this API key for downstream authorization.

    Run/write endpoints reuse the existing get_authorized_* helpers, which
    require a User. The actor is the admin who issued the key.
    """
    user = await User.find_one(User.user_id == api_key.created_by)
    if not user:
        raise HTTPException(
            status_code=403,
            detail="API key issuer no longer exists; revoke this key.",
        )
    if user.is_demo_user and user.demo_status == "locked":
        raise HTTPException(
            status_code=403,
            detail="API key issuer account is locked.",
        )
    return user


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=StatsResponse)
async def stats(_: ApiKey = Depends(require_mgmt_scope("metrics:read"))):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    cutoff_30d = now - datetime.timedelta(days=30)

    users_total = await User.find_all().count()
    teams_total = await Team.find_all().count()
    documents_total = await SmartDocument.find_all().count()
    workflows_total = await Workflow.find_all().count()
    workflow_runs_total = await WorkflowResult.find_all().count()
    workflow_runs_running = await WorkflowResult.find(
        WorkflowResult.status == "running"
    ).count()
    workflow_runs_failed_30d = await WorkflowResult.find(
        {"status": "failed", "start_time": {"$gte": cutoff_30d}}
    ).count()
    activity_events_30d = await ActivityEvent.find(
        {"started_at": {"$gte": cutoff_30d}}
    ).count()

    # Aggregate token-count bytes proxy: doc reader doesn't store size, so use
    # a coarse aggregate of token_count (proxy for content volume). Run this
    # in MongoDB rather than materializing every SmartDocument — older stub
    # records in production are missing required fields and would trip Beanie
    # validation on the way through `to_list()`.
    token_agg = await SmartDocument.aggregate(
        [{"$group": {"_id": None, "total_tokens": {"$sum": "$token_count"}}}],
    ).to_list()
    # $sum's result type follows the operands: if even one legacy stub record
    # stored token_count as a NumberDecimal, Mongo promotes the whole sum to a
    # Decimal128, and int(Decimal128) raises TypeError (likewise for None).
    # Coerce defensively so bad legacy data can't 500 the endpoint.
    total_tokens = _coerce_int(token_agg[0].get("total_tokens")) if token_agg else 0
    documents_size_bytes_total = total_tokens * 4  # ~4 bytes/token

    # Beanie's FindMany has no `.distinct()`; go through the motor collection,
    # which takes the filter as its second argument.
    active_user_ids = await ActivityEvent.get_motor_collection().distinct(
        "user_id", {"started_at": {"$gte": cutoff_30d}}
    )

    return StatsResponse(
        users_total=users_total,
        users_active_30d=len(active_user_ids),
        teams_total=teams_total,
        documents_total=documents_total,
        documents_size_bytes_total=documents_size_bytes_total,
        workflows_total=workflows_total,
        workflow_runs_total=workflow_runs_total,
        workflow_runs_running=workflow_runs_running,
        workflow_runs_failed_30d=workflow_runs_failed_30d,
        activity_events_30d=activity_events_30d,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# /users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    organization_id: Optional[str] = None,
    _: ApiKey = Depends(require_mgmt_scope("users:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if organization_id:
        filters["organization_id"] = organization_id

    query = User.find(filters) if filters else User.find_all()
    total = await query.count()
    users = await query.skip(skip).limit(limit).to_list()
    return UserListResponse(
        items=[
            UserItem(
                user_id=u.user_id,
                email=u.email,
                name=u.name,
                is_admin=u.is_admin,
                is_staff=u.is_staff,
                organization_id=u.organization_id,
                last_login_at=u.last_login_at,
                is_demo_user=u.is_demo_user,
                demo_status=u.demo_status,
            )
            for u in users
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


@router.get("/users/{user_id}", response_model=UserItem)
async def get_user(
    user_id: str,
    _: ApiKey = Depends(require_mgmt_scope("users:read")),
):
    u = await User.find_one(User.user_id == user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserItem(
        user_id=u.user_id,
        email=u.email,
        name=u.name,
        is_admin=u.is_admin,
        is_staff=u.is_staff,
        organization_id=u.organization_id,
        last_login_at=u.last_login_at,
        is_demo_user=u.is_demo_user,
        demo_status=u.demo_status,
    )


# ---------------------------------------------------------------------------
# /teams
# ---------------------------------------------------------------------------

@router.get("/teams", response_model=TeamListResponse)
async def list_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    _: ApiKey = Depends(require_mgmt_scope("teams:read")),
):
    limit = _clamp_limit(limit)
    total = await Team.find_all().count()
    teams = await Team.find_all().skip(skip).limit(limit).to_list()

    items: list[TeamItem] = []
    for t in teams:
        member_count = await TeamMembership.find(TeamMembership.team == t.id).count()
        items.append(
            TeamItem(
                id=str(t.id),
                name=getattr(t, "name", "") or "",
                member_count=member_count,
                created_at=getattr(t, "created_at", None),
            )
        )
    return TeamListResponse(
        items=items,
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


# ---------------------------------------------------------------------------
# /workflows
# ---------------------------------------------------------------------------

@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    team_id: Optional[str] = None,
    user_id: Optional[str] = None,
    _: ApiKey = Depends(require_mgmt_scope("workflows:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if team_id:
        filters["team_id"] = team_id
    if user_id:
        filters["user_id"] = user_id

    query = Workflow.find(filters) if filters else Workflow.find_all()
    total = await query.count()
    workflows = (
        await query.sort(-Workflow.updated_at).skip(skip).limit(limit).to_list()
    )
    return WorkflowListResponse(
        items=[
            WorkflowItem(
                id=str(w.id),
                name=w.name,
                description=w.description,
                user_id=w.user_id,
                team_id=w.team_id,
                num_executions=w.num_executions,
                verified=w.verified,
                version=w.version,
                created_at=w.created_at,
                updated_at=w.updated_at,
            )
            for w in workflows
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


@router.get("/workflows/runs", response_model=WorkflowRunListResponse)
async def list_workflow_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    status_eq: Optional[str] = Query(None, alias="status"),
    workflow_id: Optional[str] = None,
    _: ApiKey = Depends(require_mgmt_scope("workflows:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if status_eq:
        filters["status"] = status_eq
    if workflow_id:
        filters["workflow"] = workflow_id

    query = WorkflowResult.find(filters) if filters else WorkflowResult.find_all()
    total = await query.count()
    results = (
        await query.sort(-WorkflowResult.start_time)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return WorkflowRunListResponse(
        items=[
            WorkflowRunItem(
                id=str(r.id),
                workflow_id=str(r.workflow) if r.workflow else None,
                session_id=r.session_id,
                status=r.status,
                num_steps_completed=r.num_steps_completed,
                num_steps_total=r.num_steps_total,
                start_time=r.start_time,
                trigger_type=r.trigger_type,
                is_passive=r.is_passive,
                document_title=r.document_title,
            )
            for r in results
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


# ---------------------------------------------------------------------------
# /documents
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    team_id: Optional[str] = None,
    include_deleted: bool = False,
    _: ApiKey = Depends(require_mgmt_scope("documents:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if team_id:
        filters["team_id"] = team_id
    if not include_deleted:
        filters["soft_deleted"] = {"$ne": True}

    query = SmartDocument.find(filters) if filters else SmartDocument.find_all()
    total = await query.count()
    docs = await query.sort(-SmartDocument.created_at).skip(skip).limit(limit).to_list()
    return DocumentListResponse(
        items=[
            DocumentItem(
                id=str(d.id),
                uuid=d.uuid,
                title=d.title,
                extension=d.extension,
                user_id=d.user_id,
                team_id=d.team_id,
                folder=d.folder,
                classification=d.classification,
                num_pages=d.num_pages,
                token_count=d.token_count,
                soft_deleted=d.soft_deleted,
                created_at=d.created_at,
            )
            for d in docs
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


# ---------------------------------------------------------------------------
# /activity
# ---------------------------------------------------------------------------

@router.get("/activity", response_model=ActivityListResponse)
async def list_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    type_eq: Optional[str] = Query(None, alias="type"),
    status_eq: Optional[str] = Query(None, alias="status"),
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    since: Optional[datetime.datetime] = None,
    _: ApiKey = Depends(require_mgmt_scope("activity:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if type_eq:
        filters["type"] = type_eq
    if status_eq:
        filters["status"] = status_eq
    if user_id:
        filters["user_id"] = user_id
    if team_id:
        filters["team_id"] = team_id
    if since:
        filters["started_at"] = {"$gte": since}

    query = ActivityEvent.find(filters) if filters else ActivityEvent.find_all()
    total = await query.count()
    events = (
        await query.sort(-ActivityEvent.started_at).skip(skip).limit(limit).to_list()
    )
    return ActivityListResponse(
        items=[
            ActivityItem(
                id=str(e.id),
                type=e.type,
                status=e.status,
                title=e.title,
                user_id=e.user_id,
                team_id=e.team_id,
                started_at=e.started_at,
                finished_at=e.finished_at,
                tokens_input=e.tokens_input,
                tokens_output=e.tokens_output,
                error=e.error,
            )
            for e in events
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


# ---------------------------------------------------------------------------
# /audit
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=AuditListResponse)
async def list_audit(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    action: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    since: Optional[datetime.datetime] = None,
    _: ApiKey = Depends(require_mgmt_scope("audit:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if action:
        filters["action"] = action
    if actor_user_id:
        filters["actor_user_id"] = actor_user_id
    if resource_type:
        filters["resource_type"] = resource_type
    if since:
        filters["timestamp"] = {"$gte": since}

    query = AuditLog.find(filters) if filters else AuditLog.find_all()
    total = await query.count()
    entries = (
        await query.sort(-AuditLog.timestamp).skip(skip).limit(limit).to_list()
    )
    return AuditListResponse(
        items=[
            AuditItem(
                uuid=e.uuid,
                timestamp=e.timestamp,
                actor_user_id=e.actor_user_id,
                actor_type=e.actor_type,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                team_id=e.team_id,
                organization_id=e.organization_id,
                detail=e.detail,
            )
            for e in entries
        ],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


# ---------------------------------------------------------------------------
# /config (redacted)
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_system_config(
    _: ApiKey = Depends(require_mgmt_scope("config:read")),
):
    """Return the system config with all secret fields redacted."""
    cfg = await SystemConfig.get_config()
    raw = cfg.model_dump()

    # Redact known secret-bearing fields. The admin router already has
    # _sanitize_models / _sanitize_providers helpers for this; mirror their
    # contract here so the mgmt surface never leaks decryptable secrets.
    for m in raw.get("models", []) or []:
        if m.get("api_key"):
            m["api_key"] = "***"
    for p in raw.get("oauth_providers", []) or []:
        if p.get("client_secret"):
            p["client_secret"] = "***"
    for k in (
        "graph_token_key",
        "graph_client_state_secret",
        "config_encryption_key",
        "smtp_password",
    ):
        if raw.get(k):
            raw[k] = "***"

    return raw


# ---------------------------------------------------------------------------
# /validation — read
# ---------------------------------------------------------------------------

class ValidationRunItem(BaseModel):
    uuid: str
    item_kind: str
    item_id: str
    item_name: str
    run_type: str
    accuracy: Optional[float] = None
    consistency: Optional[float] = None
    grade: Optional[str] = None
    score: float
    model: Optional[str] = None
    num_runs: int
    num_test_cases: int
    num_checks: int
    checks_passed: int
    checks_failed: int
    config_hash: Optional[str] = None
    user_id: str
    created_at: datetime.datetime


class ValidationRunDetail(ValidationRunItem):
    score_breakdown: dict
    result_snapshot: dict
    extraction_config: dict


class ValidationRunListResponse(BaseModel):
    items: list[ValidationRunItem]
    page: PageMeta


class TestCaseItem(BaseModel):
    uuid: str
    search_set_uuid: str
    label: str
    source_type: str
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: dict[str, str]
    user_id: str
    created_at: datetime.datetime


class TestCaseListResponse(BaseModel):
    items: list[TestCaseItem]
    page: PageMeta


class ExtractionPlanResponse(BaseModel):
    search_set_uuid: str
    title: str
    cross_field_rules: list[dict]
    test_cases: list[TestCaseItem]


class WorkflowPlanResponse(BaseModel):
    workflow_id: str
    name: str
    validation_plan: list[dict]
    validation_inputs: list[dict]


def _testcase_to_item(tc: ExtractionTestCase) -> TestCaseItem:
    return TestCaseItem(
        uuid=tc.uuid,
        search_set_uuid=tc.search_set_uuid,
        label=tc.label,
        source_type=tc.source_type,
        source_text=tc.source_text,
        document_uuid=tc.document_uuid,
        expected_values=tc.expected_values,
        user_id=tc.user_id,
        created_at=tc.created_at,
    )


def _vrun_to_item(r: ValidationRun) -> ValidationRunItem:
    return ValidationRunItem(
        uuid=r.uuid,
        item_kind=r.item_kind,
        item_id=r.item_id,
        item_name=r.item_name,
        run_type=r.run_type,
        accuracy=r.accuracy,
        consistency=r.consistency,
        grade=r.grade,
        score=r.score,
        model=r.model,
        num_runs=r.num_runs,
        num_test_cases=r.num_test_cases,
        num_checks=r.num_checks,
        checks_passed=r.checks_passed,
        checks_failed=r.checks_failed,
        config_hash=r.config_hash,
        user_id=r.user_id,
        created_at=r.created_at,
    )


@router.get("/validation/runs", response_model=ValidationRunListResponse)
async def list_validation_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    item_kind: Optional[str] = Query(None, description="search_set | workflow"),
    item_id: Optional[str] = None,
    model: Optional[str] = None,
    since: Optional[datetime.datetime] = None,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if item_kind:
        filters["item_kind"] = item_kind
    if item_id:
        filters["item_id"] = item_id
    if model:
        filters["model"] = model
    if since:
        filters["created_at"] = {"$gte": since}

    query = ValidationRun.find(filters) if filters else ValidationRun.find_all()
    total = await query.count()
    runs = (
        await query.sort(-ValidationRun.created_at).skip(skip).limit(limit).to_list()
    )
    return ValidationRunListResponse(
        items=[_vrun_to_item(r) for r in runs],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


@router.get("/validation/runs/{uuid}", response_model=ValidationRunDetail)
async def get_validation_run(
    uuid: str,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    r = await ValidationRun.find_one(ValidationRun.uuid == uuid)
    if not r:
        raise HTTPException(status_code=404, detail="Validation run not found")
    base = _vrun_to_item(r).model_dump()
    return ValidationRunDetail(
        **base,
        score_breakdown=r.score_breakdown,
        result_snapshot=r.result_snapshot,
        extraction_config=r.extraction_config,
    )


@router.get("/validation/test-cases", response_model=TestCaseListResponse)
async def list_test_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    search_set_uuid: Optional[str] = None,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    limit = _clamp_limit(limit)
    filters: dict = {}
    if search_set_uuid:
        filters["search_set_uuid"] = search_set_uuid

    query = (
        ExtractionTestCase.find(filters)
        if filters
        else ExtractionTestCase.find_all()
    )
    total = await query.count()
    cases = (
        await query.sort(-ExtractionTestCase.created_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )
    return TestCaseListResponse(
        items=[_testcase_to_item(c) for c in cases],
        page=PageMeta(skip=skip, limit=limit, total=total),
    )


@router.get("/validation/test-cases/{uuid}", response_model=TestCaseItem)
async def get_test_case(
    uuid: str,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    tc = await ExtractionTestCase.find_one(ExtractionTestCase.uuid == uuid)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    return _testcase_to_item(tc)


@router.get(
    "/validation/extractions/{search_set_uuid}/plan",
    response_model=ExtractionPlanResponse,
)
async def get_extraction_plan(
    search_set_uuid: str,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="Search set not found")
    cases = await ExtractionTestCase.find(
        ExtractionTestCase.search_set_uuid == search_set_uuid
    ).to_list()
    return ExtractionPlanResponse(
        search_set_uuid=ss.uuid,
        title=ss.title,
        cross_field_rules=ss.normalized_cross_field_rules(),
        test_cases=[_testcase_to_item(c) for c in cases],
    )


@router.get(
    "/validation/workflows/{workflow_id}/plan",
    response_model=WorkflowPlanResponse,
)
async def get_workflow_plan(
    workflow_id: str,
    _: ApiKey = Depends(require_mgmt_scope("validation:read")),
):
    from beanie import PydanticObjectId

    try:
        oid = PydanticObjectId(workflow_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid workflow id")
    wf = await Workflow.get(oid)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowPlanResponse(
        workflow_id=str(wf.id),
        name=wf.name,
        validation_plan=wf.validation_plan,
        validation_inputs=wf.validation_inputs,
    )


# ---------------------------------------------------------------------------
# /validation — write
# ---------------------------------------------------------------------------

class CreateTestCaseBody(BaseModel):
    search_set_uuid: str
    label: str
    source_type: str
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: dict[str, str] = {}


class BulkCreateTestCasesBody(BaseModel):
    cases: list[CreateTestCaseBody]


class UpdateTestCaseBody(BaseModel):
    label: Optional[str] = None
    source_type: Optional[str] = None
    source_text: Optional[str] = None
    document_uuid: Optional[str] = None
    expected_values: Optional[dict[str, str]] = None


class UpdateCrossFieldRulesBody(BaseModel):
    rules: list[dict]


class UpdateWorkflowPlanBody(BaseModel):
    validation_plan: Optional[list[dict]] = None
    validation_inputs: Optional[list[dict]] = None


@router.post("/validation/test-cases", response_model=TestCaseItem)
async def create_test_case(
    body: CreateTestCaseBody,
    api_key: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    user = await _user_for_key(api_key)
    tc = ExtractionTestCase(
        search_set_uuid=body.search_set_uuid,
        label=body.label,
        source_type=body.source_type,
        source_text=body.source_text,
        document_uuid=body.document_uuid,
        expected_values=body.expected_values,
        user_id=user.user_id,
    )
    await tc.insert()
    return _testcase_to_item(tc)


@router.post(
    "/validation/test-cases/bulk", response_model=TestCaseListResponse
)
async def create_test_cases_bulk(
    body: BulkCreateTestCasesBody,
    api_key: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    user = await _user_for_key(api_key)
    if not body.cases:
        raise HTTPException(status_code=400, detail="cases must not be empty")
    created: list[ExtractionTestCase] = []
    for c in body.cases:
        tc = ExtractionTestCase(
            search_set_uuid=c.search_set_uuid,
            label=c.label,
            source_type=c.source_type,
            source_text=c.source_text,
            document_uuid=c.document_uuid,
            expected_values=c.expected_values,
            user_id=user.user_id,
        )
        await tc.insert()
        created.append(tc)
    return TestCaseListResponse(
        items=[_testcase_to_item(c) for c in created],
        page=PageMeta(skip=0, limit=len(created), total=len(created)),
    )


@router.put("/validation/test-cases/{uuid}", response_model=TestCaseItem)
async def update_test_case(
    uuid: str,
    body: UpdateTestCaseBody,
    _: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    tc = await ExtractionTestCase.find_one(ExtractionTestCase.uuid == uuid)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(tc, field, value)
    await tc.save()
    return _testcase_to_item(tc)


@router.delete("/validation/test-cases/{uuid}")
async def delete_test_case(
    uuid: str,
    _: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    tc = await ExtractionTestCase.find_one(ExtractionTestCase.uuid == uuid)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    await tc.delete()
    return {"uuid": uuid, "deleted": True}


@router.put("/validation/extractions/{search_set_uuid}/cross-field-rules")
async def update_cross_field_rules(
    search_set_uuid: str,
    body: UpdateCrossFieldRulesBody,
    _: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    from app.services.cross_field_rules import normalize_rules, validate_rule_shape

    ss = await SearchSet.find_one(SearchSet.uuid == search_set_uuid)
    if not ss:
        raise HTTPException(status_code=404, detail="Search set not found")

    for r in body.rules:
        ok, err = validate_rule_shape(r)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

    existing_by_id = {r.get("id"): r for r in ss.cross_field_rules if r.get("id")}
    merged: list[dict] = []
    for incoming in body.rules:
        rid = incoming.get("id")
        if rid and rid in existing_by_id:
            base = dict(existing_by_id[rid])
            base.update(incoming)
            merged.append(base)
        else:
            merged.append(incoming)
    ss.cross_field_rules = normalize_rules(merged)
    await ss.save()
    return {"search_set_uuid": ss.uuid, "rules": ss.cross_field_rules}


@router.put(
    "/validation/workflows/{workflow_id}/plan",
    response_model=WorkflowPlanResponse,
)
async def update_workflow_plan(
    workflow_id: str,
    body: UpdateWorkflowPlanBody,
    _: ApiKey = Depends(require_mgmt_scope("validation:write")),
):
    from beanie import PydanticObjectId

    try:
        oid = PydanticObjectId(workflow_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid workflow id")
    wf = await Workflow.get(oid)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if body.validation_plan is not None:
        wf.validation_plan = body.validation_plan
    if body.validation_inputs is not None:
        wf.validation_inputs = body.validation_inputs
    wf.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
    await wf.save()
    return WorkflowPlanResponse(
        workflow_id=str(wf.id),
        name=wf.name,
        validation_plan=wf.validation_plan,
        validation_inputs=wf.validation_inputs,
    )


# ---------------------------------------------------------------------------
# Run endpoints — spend tokens / kick off Celery work
# ---------------------------------------------------------------------------

class RunValidationBody(BaseModel):
    search_set_uuid: str
    sources: list[dict]
    num_runs: int = 1
    model: Optional[str] = None


class RunWorkflowBody(BaseModel):
    document_uuids: list[str]
    model: Optional[str] = None
    batch_mode: bool = False


class RunExtractionBody(BaseModel):
    search_set_uuid: str
    document_uuids: list[str]
    model: Optional[str] = None
    extraction_config_override: Optional[dict] = None
    combined_context: bool = False


@router.post("/validation/run")
@limiter.limit("10/minute", key_func=mgmt_key_func)
async def run_validation(
    request: Request,
    body: RunValidationBody,
    api_key: ApiKey = Depends(require_mgmt_scope("validation:run")),
):
    from app.services import extraction_validation_service as val_svc
    from app.services.access_control import get_authorized_search_set

    user = await _user_for_key(api_key)
    ss = await get_authorized_search_set(body.search_set_uuid, user, manage=True)
    if not ss:
        raise HTTPException(status_code=404, detail="Search set not found")
    try:
        result = await val_svc.run_validation_v2(
            search_set_uuid=body.search_set_uuid,
            user_id=user.user_id,
            sources=body.sources,
            num_runs=body.num_runs,
            model=body.model,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workflows/{workflow_id}/run")
@limiter.limit("20/minute", key_func=mgmt_key_func)
async def run_workflow_endpoint(
    request: Request,
    workflow_id: str,
    body: RunWorkflowBody,
    api_key: ApiKey = Depends(require_mgmt_scope("workflows:run")),
):
    from beanie import PydanticObjectId

    from app.models.activity import ActivityStatus, ActivityType
    from app.services import activity_service
    from app.services import workflow_service as wf_svc
    from app.services.access_control import get_authorized_workflow

    user = await _user_for_key(api_key)
    wf = await get_authorized_workflow(workflow_id, user)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    num_steps = max(0, len(wf.steps) - 1) if wf.steps else 0
    activity = await activity_service.activity_start(
        type=ActivityType.WORKFLOW_RUN,
        title=wf.name,
        user_id=user.user_id,
        team_id=str(user.current_team) if user.current_team else None,
        workflow=PydanticObjectId(workflow_id),
        steps_total=num_steps,
    )

    try:
        if body.batch_mode and len(body.document_uuids) > 1:
            batch_id = await wf_svc.run_workflow_batch(
                workflow_id,
                body.document_uuids,
                user.user_id,
                body.model,
                activity_id=str(activity.id),
                user=user,
            )
            return {"batch_id": batch_id, "activity_id": str(activity.id)}
        session_id = await wf_svc.run_workflow(
            workflow_id,
            body.document_uuids,
            user.user_id,
            body.model,
            activity_id=str(activity.id),
            user=user,
        )
        activity.workflow_session_id = session_id
        await activity.save()
        return {"session_id": session_id, "activity_id": str(activity.id)}
    except ValueError as e:
        await activity_service.activity_finish(
            activity.id, ActivityStatus.FAILED, error=str(e)
        )
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/extractions/run")
@limiter.limit("30/minute", key_func=mgmt_key_func)
async def run_extraction(
    request: Request,
    body: RunExtractionBody,
    api_key: ApiKey = Depends(require_mgmt_scope("extractions:run")),
):
    from app.models.activity import ActivityStatus, ActivityType
    from app.services import activity_service
    from app.services import search_set_service as ss_svc
    from app.services.access_control import get_authorized_search_set

    user = await _user_for_key(api_key)
    ss = await get_authorized_search_set(body.search_set_uuid, user)
    if not ss:
        raise HTTPException(status_code=404, detail="Search set not found")

    activity = await activity_service.activity_start(
        type=ActivityType.SEARCH_SET_RUN,
        title=ss.title,
        user_id=user.user_id,
        team_id=str(user.current_team) if user.current_team else None,
        search_set_uuid=body.search_set_uuid,
    )
    try:
        results = await ss_svc.run_extraction_sync(
            search_set_uuid=body.search_set_uuid,
            document_uuids=body.document_uuids,
            user_id=user.user_id,
            model=body.model,
            extraction_config_override=body.extraction_config_override,
            combined_context=body.combined_context,
        )
        await activity_service.activity_finish(activity.id, ActivityStatus.COMPLETED)
        await activity_service.activity_update(
            activity.id,
            documents_touched=len(body.document_uuids),
        )
        return {"results": results, "activity_id": str(activity.id)}
    except Exception as e:
        await activity_service.activity_finish(
            activity.id, ActivityStatus.FAILED, error=str(e)
        )
        raise
