import logging
import sys
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.database import init_db
from app.exceptions import AppError
from app.middleware.csrf import CSRFMiddleware
from app.rate_limit import limiter
from app.routers import activity, admin, approvals, audit, auth, automations, browser_automation, certification, chat, config, demo, documents, extractions, feedback, files, folders, graph_webhooks, knowledge, library, notifications, office, organizations, spaces, support, teams, verification, workflows


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
def _configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        from pythonjsonlogger.json import JsonFormatter

        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
    root.handlers = [handler]


# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
def _init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        send_default_pii=False,
    )


_boot_settings = get_settings()
_configure_logging(_boot_settings)
_init_sentry(_boot_settings)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Vandalizer backend")
    await init_db(get_settings())
    yield
    logger.info("Shutting down Vandalizer backend")


app = FastAPI(
    title="Vandalizer",
    lifespan=lifespan,
    docs_url=None if _boot_settings.is_production else "/api/docs",
    redoc_url=None if _boot_settings.is_production else "/api/redoc",
    openapi_url=None if _boot_settings.is_production else "/api/openapi.json",
)
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


app.add_exception_handler(AppError, _app_error_handler)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        if get_settings().is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
settings = get_settings()
_cors_origins = [settings.frontend_url]
if not settings.is_production:
    _cors_origins.append("http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    expose_headers=["X-Conversation-UUID", "X-Activity-ID"],
)

app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(folders.router, prefix="/api/folders", tags=["folders"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(teams.router, prefix="/api/teams", tags=["teams"])
app.include_router(extractions.router, prefix="/api/extractions", tags=["extractions"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(verification.router, prefix="/api/verification", tags=["verification"])
app.include_router(office.router, prefix="/api/office", tags=["office"])
app.include_router(automations.router, prefix="/api/automations", tags=["automations"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(demo.router, prefix="/api/demo", tags=["demo"])
app.include_router(graph_webhooks.router, prefix="/api/webhooks/graph", tags=["webhooks"])
app.include_router(browser_automation.router, prefix="/api/browser-automation", tags=["browser-automation"])
app.include_router(certification.router, prefix="/api/certification", tags=["certification"])
app.include_router(organizations.router, prefix="/api/organizations", tags=["organizations"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(approvals.router, prefix="/api/approvals", tags=["approvals"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(spaces.router, prefix="/api/spaces", tags=["spaces"])
app.include_router(support.router, prefix="/api/support", tags=["support"])


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
from prometheus_fastapi_instrumentator import Instrumentator  # noqa: E402

Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")


@app.get("/api/health")
async def health():
    """Health check that verifies all critical dependencies."""
    checks: dict[str, str] = {}
    settings = get_settings()

    # MongoDB
    try:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(
            settings.mongo_host, serverSelectionTimeoutMS=2000
        )
        await client[settings.mongo_db].command("ping")
        checks["mongodb"] = "ok"
    except Exception as e:
        checks["mongodb"] = f"error: {e}"

    # Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis(
            host=settings.redis_host, port=6379, db=0, socket_timeout=2
        )
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # ChromaDB
    try:
        import chromadb

        chroma = chromadb.PersistentClient(path=settings.chromadb_persist_dir)
        chroma.heartbeat()
        checks["chromadb"] = "ok"
    except Exception as e:
        checks["chromadb"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )
