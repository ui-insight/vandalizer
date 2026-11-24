"""The UI-to-endpoint map's frontend scanner (scripts/map_ui_endpoints.py)."""

import importlib.util
import signal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "map_ui_endpoints.py"


def _scanner():
    spec = importlib.util.spec_from_file_location("map_ui_endpoints", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scan_with_timeout(scanner, path, seconds=10):
    def _timeout(*_):
        raise TimeoutError(f"scanner stalled on {path.name}")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(seconds)
    try:
        return list(scanner._calls_in(path.read_text(errors="replace")))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_every_api_module_scans_without_stalling():
    # A quote inside a regex literal (extractions.ts parses Content-Disposition
    # with /filename="([^"]+)"/) read as an unterminated string, and the scan
    # stopped advancing: `make endpoint-map` never finished.
    scanner = _scanner()
    for path in sorted((ROOT / "frontend" / "src" / "api").glob("*.ts")):
        if not path.name.endswith(".test.ts"):
            _scan_with_timeout(scanner, path)


def test_backend_map_includes_nested_mounts_and_inherited_auth():
    from fastapi import APIRouter, Depends, FastAPI

    app = FastAPI()
    inner = APIRouter()
    outer = APIRouter()

    def require_user():
        return "test-user"

    def require_team():
        return "test-team"

    @inner.get("/items/{item_id}", dependencies=[Depends(require_team)])
    def get_item(item_id: str):
        return {"id": item_id}

    @app.get("/health")
    def health():
        return {"ok": True}

    outer.include_router(inner, prefix="/nested", dependencies=[Depends(require_user)])
    app.include_router(outer, prefix="/api")
    app.include_router(outer, prefix="/other")

    records = _scanner()._route_records(app)
    assert [(r["method"], r["path"], r["handler"], r["auth_deps"]) for r in records] == [
        ("GET", "/api/nested/items/{item_id}", "get_item", ["require_team", "require_user"]),
        ("GET", "/health", "health", []),
        ("GET", "/other/nested/items/{item_id}", "get_item", ["require_team", "require_user"]),
    ]
