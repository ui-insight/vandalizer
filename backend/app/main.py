from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.database import init_db
from app.rate_limit import limiter
from app.routers import activity, admin, auth, automations, browser_automation, chat, config, demo, documents, extractions, feedback, files, folders, graph_webhooks, knowledge, library, office, spaces, teams, verification, workflows


@lru_cache
def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(get_settings())
    yield


app = FastAPI(title="Vandalizer", lifespan=lifespan)
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173"],
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
app.include_router(spaces.router, prefix="/api/spaces", tags=["spaces"])
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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
