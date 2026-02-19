from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.database import init_db
from app.routers import activity, auth, chat, config, documents, extractions, feedback, files, folders, library, office, spaces, teams, verification, workflows


@lru_cache
def get_settings() -> Settings:
    return Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(get_settings())
    yield


app = FastAPI(title="Vandalizer Next", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-UUID", "X-Activity-ID"],
)

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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
