#!/usr/bin/env python3
"""map_ui_endpoints.py — join backend routes to the frontend calls that hit them.

AST call graphs (e.g. code-review-graph) trace each side of the app precisely
but stop at the HTTP boundary: a `fetch("/api/chat/truncate")` is a string, not
a code reference, so no edge connects it to `@router.post("/truncate")`. This
script builds exactly that missing edge and nothing else:

  backend route  (method, full path, handler, auth deps — from walking
                  app.routes on the real FastAPI app, so router prefixes and
                  mount order are resolved, not guessed from decorators)
  frontend call  (exported function in frontend/src/api/*.ts, URL pattern,
                  method — parsed from the apiFetch/rawFetch wrapper calls)

joined by URL shape (`{param}` and `${expr}` both normalize to `*`), plus the
orphan lists that make it a review tool rather than an inventory:

  * frontend calls matching no route  → almost always a real bug
  * routes with no frontend caller    → dead surface, or external-API-only
                                        (cross-tagged against docs/api.md and
                                        docs/mgmt-api.md so those read as
                                        intentional)
  * calls whose URL is built at runtime → cannot be joined by URL shape, so
                                        they are listed separately: they are
                                        the error bar on the uncalled list

Anything above the api layer (which components call which api function) and
below the route (what a handler touches) is the call graph's job; compose the
two for full UI-to-database blast radius.

Run from the repo root:

    cd backend && uv run python ../scripts/map_ui_endpoints.py

Writes scripts/ui_endpoint_map.md and scripts/ui_endpoint_map.json.
`--check` exits 1 when a frontend call matches no backend route (CI mode);
`--stdout` prints the Markdown instead of writing files.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
API_DIR = REPO / "frontend" / "src" / "api"
SRC_DIR = REPO / "frontend" / "src"
DOCS = [REPO / "docs" / "api.md", REPO / "docs" / "mgmt-api.md"]

WRAPPERS = ("apiFetch", "rawFetch")


# ── backend: walk the real app ───────────────────────────────────────────────

def scan_backend():
    import os

    # The map documents the full mountable surface, so routers gated behind
    # deployment flags (trial system, telemetry collector) are force-enabled
    # for the walk. A deployment with them off simply doesn't serve them.
    os.environ.setdefault("ENABLE_TRIAL_SYSTEM", "true")
    os.environ.setdefault("TELEMETRY_COLLECTOR_ENABLED", "true")
    sys.path.insert(0, str(REPO / "backend"))
    from fastapi.routing import APIRoute
    from app.main import app, get_settings

    # setdefault loses to a shell or .env that already sets these false; the
    # map is then missing those routers, so say so instead of walking quietly.
    settings = get_settings()
    for flag, value in (
        ("ENABLE_TRIAL_SYSTEM", settings.enable_trial_system),
        ("TELEMETRY_COLLECTOR_ENABLED", settings.telemetry_collector_enabled),
    ):
        if not value:
            print(f"warning: {flag} resolved false (set in your shell or .env) "
                  f"— its routes are missing from this map", file=sys.stderr)

    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        fn = route.endpoint
        try:
            src_file = str(Path(inspect.getfile(fn)).relative_to(REPO))
            src_line = inspect.getsourcelines(fn)[1]
        except (TypeError, OSError, ValueError):
            src_file, src_line = "?", 0
        deps = sorted(
            {
                d.call.__name__
                for d in route.dependant.dependencies
                if d.call is not None and hasattr(d.call, "__name__")
            }
        )
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            routes.append(
                {
                    "method": method,
                    "path": route.path,
                    "handler": fn.__name__,
                    "file": src_file,
                    "line": src_line,
                    "auth_deps": deps,
                }
            )
    return sorted(routes, key=lambda r: (r["path"], r["method"]))


# ── frontend: parse the api layer ────────────────────────────────────────────

FN_DEF = re.compile(
    r"export\s+(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=)"
)
STRING = re.compile(r"""(['"`])""")
METHOD = re.compile(r"""method\s*:\s*['"](\w+)['"]""")


def _skip_generic(text: str, i: int) -> int:
    """Return index after a balanced <...> starting at i, or i if none."""
    if i >= len(text) or text[i] != "<":
        return i
    depth, j = 0, i
    while j < len(text):
        if text[j] == "<":
            depth += 1
        elif text[j] == ">":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return i


def _read_string(text: str, i: int):
    """Read a JS string/template literal starting at text[i]; return (value, end).

    Template literals get real handling: a `${...}` interpolation (which may
    itself contain nested template literals and braces) collapses to the
    placeholder `${...}`, so a URL like `/x/${q ? `?a=${a}` : ''}` parses
    instead of ending at the first nested backtick.
    """
    quote = text[i]
    j = i + 1
    out = []
    while j < len(text):
        ch = text[j]
        if ch == "\\":
            j += 2
            continue
        if quote == "`" and ch == "$" and text[j : j + 2] == "${":
            depth, k = 0, j + 1
            while k < len(text):
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif text[k] == "`":  # nested template literal
                    _, k2 = _read_string(text, k)
                    k = k2 - 1
                k += 1
            out.append("${...}")
            j = k + 1
            continue
        if ch == quote:
            return "".join(out), j + 1
        out.append(ch)
        j += 1
    return None, i


def _call_span(text: str, i: int) -> int:
    """Given index just past the call's opening paren, return the index of its
    matching close paren (string-aware), so option lookups stay in this call."""
    depth = 1
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            _, i = _read_string(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return i


def _calls_in(text: str, wrappers=WRAPPERS):
    """Yield (offset, url, method) for every wrapper call with a literal URL."""
    for m in re.finditer(r"\b(%s)\s*" % "|".join(wrappers), text):
        if re.search(r"function\s+$", text[max(0, m.start() - 12):m.start()]):
            continue  # the wrapper's own definition, not a call
        i = _skip_generic(text, m.end())
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text) or text[i] != "(":
            continue
        i += 1
        open_paren = i
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text) or text[i] not in "'\"`":
            # URL built at runtime (e.g. `let url = ...; url += ...`) — no
            # literal to join on. Yield it with url=None so callers can list
            # it as the error bar on the uncalled-routes section.
            close = _call_span(text, i)
            m2 = METHOD.search(text[i:close])
            yield m.start(), None, (m2.group(1).upper() if m2 else "GET")
            continue
        url, end = _read_string(text, i)
        if url is None:
            continue
        close = _call_span(text, open_paren)
        window = text[end:close]
        method = (METHOD.search(window).group(1).upper() if METHOD.search(window) else "GET")
        yield m.start(), url, method


def scan_frontend():
    calls, dynamic = [], []
    for ts in sorted(API_DIR.glob("*.ts")):
        if ts.name.endswith(".test.ts"):
            continue
        text = ts.read_text(errors="replace")
        fn_spans = [
            (m.start(), m.group(1) or m.group(2)) for m in FN_DEF.finditer(text)
        ]
        for offset, url, method in _calls_in(text):
            fn = "?"
            for start, name in fn_spans:
                if start <= offset:
                    fn = name
                else:
                    break
            if url is None:
                dynamic.append(
                    {
                        "function": fn,
                        "method": method,
                        "file": str(ts.relative_to(REPO)),
                        "line": text.count("\n", 0, offset) + 1,
                    }
                )
                continue
            if not url.startswith("/"):
                continue  # absolute/external URL — not a backend route
            calls.append(
                {
                    "function": fn,
                    "url": url,
                    "method": method,
                    "file": str(ts.relative_to(REPO)),
                    "line": text.count("\n", 0, offset) + 1,
                }
            )
    return calls, dynamic


def scan_out_of_layer():
    """Wrapper/fetch calls outside frontend/src/api — the layer violation list."""
    hits = []
    for ts in sorted(SRC_DIR.rglob("*.ts*")):
        if API_DIR in ts.parents or ".test." in ts.name:
            continue
        text = ts.read_text(errors="replace")
        for offset, url, method in _calls_in(text, WRAPPERS + ("fetch",)):
            if url is not None and url.startswith("/api"):
                hits.append(
                    {
                        "url": url,
                        "method": method,
                        "file": str(ts.relative_to(REPO)),
                        "line": text.count("\n", 0, offset) + 1,
                    }
                )
    return hits


# ── the join ─────────────────────────────────────────────────────────────────

def norm(url: str) -> str:
    url = url.split("?")[0]
    # A trailing interpolation glued to the last segment (`...suite${qs}`) is a
    # query-string builder — drop it. One that follows a slash (`/${id}`) is a
    # real path parameter — keep it.
    url = re.sub(r"(?<=[^/])(\$\{[^}]*\})+$", "", url)
    url = url.rstrip("/") or "/"
    url = re.sub(r"\$\{[^}]*\}", "*", url)
    url = re.sub(r"\{[^}]*\}", "*", url)
    return url


def _match(a: str, b: str) -> bool:
    if a == b:
        return True
    pat_a = re.escape(a).replace(r"\*", "[^/]+")
    pat_b = re.escape(b).replace(r"\*", "[^/]+")
    return bool(re.fullmatch(pat_a, b) or re.fullmatch(pat_b, a))


def documented_paths():
    found = set()
    for doc in DOCS:
        if doc.exists():
            for m in re.finditer(r"`(?:GET|POST|PUT|PATCH|DELETE)?\s*(/api/[^`\s]+)`", doc.read_text()):
                found.add(norm(m.group(1)))
    return found


def join(routes, calls):
    for r in routes:
        r["norm"] = norm(r["path"])
        r["callers"] = []
    for c in calls:
        c["norm"] = norm(c["url"])
        c["matched"] = False
    for r in routes:
        for c in calls:
            if c["method"] == r["method"] and _match(r["norm"], c["norm"]):
                r["callers"].append(c)
                c["matched"] = True

    docs = documented_paths()
    uncalled, unmatched = [], [c for c in calls if not c["matched"]]
    for r in routes:
        if not r["callers"]:
            r["documented_external"] = any(_match(r["norm"], d) for d in docs)
            uncalled.append(r)
    return uncalled, unmatched


# ── output ───────────────────────────────────────────────────────────────────

def render_md(routes, calls, dynamic, out_of_layer, uncalled, unmatched):
    L = []
    L.append("# UI ↔ Endpoint Map")
    L.append("")
    L.append(f"_Generated by `scripts/map_ui_endpoints.py` on "
             f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
             f"Regenerate: `cd backend && uv run python ../scripts/map_ui_endpoints.py`_")
    L.append("")
    L.append("| | count |")
    L.append("|---|---|")
    L.append(f"| Backend routes | {len(routes)} |")
    L.append(f"| Frontend api-layer calls | {len(calls)} |")
    L.append(f"| Routes with no frontend caller | {len(uncalled)} |")
    L.append(f"| Frontend calls matching no route | {len(unmatched)} |")
    L.append(f"| Calls with runtime-built URLs (not mapped) | {len(dynamic)} |")
    L.append(f"| Calls outside the api layer | {len(out_of_layer)} |")
    L.append("")

    if unmatched:
        L.append(f"## Frontend calls matching no route ({len(unmatched)}) — investigate first")
        L.append("")
        L.append("| Method | URL | Function | File:Line |")
        L.append("|---|---|---|---|")
        for c in sorted(unmatched, key=lambda c: c["url"]):
            L.append(f"| {c['method']} | `{c['url']}` | `{c['function']}` | `{c['file']}:{c['line']}` |")
        L.append("")

    L.append(f"## Routes and their frontend callers ({len(routes)})")
    L.append("")
    L.append("| Method | Path | Handler | Auth | Frontend callers |")
    L.append("|---|---|---|---|---|")
    for r in routes:
        who = "<br>".join(
            f"`{c['function']}` ({Path(c['file']).name})" for c in r["callers"]
        ) or "—"
        auth = ", ".join(r["auth_deps"]) or "—"
        L.append(f"| {r['method']} | `{r['path']}` | `{r['handler']}` | {auth} | {who} |")
    L.append("")

    if dynamic:
        L.append(f"## Calls with runtime-built URLs ({len(dynamic)}) — not mapped")
        L.append("")
        L.append("These build their URL at runtime (e.g. `url += ...`), so they "
                 "cannot be joined by URL shape. Any route they call shows up "
                 "under \"Routes with no frontend caller\" — this list is that "
                 "section's error bar.")
        L.append("")
        L.append("| Method | Function | File:Line |")
        L.append("|---|---|---|")
        for c in sorted(dynamic, key=lambda c: (c["file"], c["line"])):
            L.append(f"| {c['method']} | `{c['function']}` | `{c['file']}:{c['line']}` |")
        L.append("")

    L.append(f"## Routes with no frontend caller ({len(uncalled)})")
    L.append("")
    L.append("Documented-external routes are expected here; anything else is "
             "server-to-server, webhook, or dead surface — modulo the "
             "runtime-built-URL calls above, which may cover some of these.")
    L.append("")
    L.append("| Method | Path | Handler | File | External-API doc? |")
    L.append("|---|---|---|---|---|")
    for r in sorted(uncalled, key=lambda r: (not r["documented_external"], r["path"])):
        tag = "yes" if r["documented_external"] else ""
        L.append(f"| {r['method']} | `{r['path']}` | `{r['handler']}` | `{r['file']}` | {tag} |")
    L.append("")

    if out_of_layer:
        L.append(f"## API calls outside `src/api/` ({len(out_of_layer)})")
        L.append("")
        L.append("| Method | URL | File:Line |")
        L.append("|---|---|---|")
        for c in sorted(out_of_layer, key=lambda c: c["file"]):
            L.append(f"| {c['method']} | `{c['url']}` | `{c['file']}:{c['line']}` |")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stdout", action="store_true", help="print Markdown, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any frontend call matches no backend route")
    args = ap.parse_args()

    routes = scan_backend()
    calls, dynamic = scan_frontend()
    out_of_layer = scan_out_of_layer()
    uncalled, unmatched = join(routes, calls)

    md = render_md(routes, calls, dynamic, out_of_layer, uncalled, unmatched)
    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "routes": [{k: v for k, v in r.items() if k != "callers"}
                   | {"callers": [{"function": c["function"], "file": c["file"], "line": c["line"]}
                                  for c in r["callers"]]}
                   for r in routes],
        "frontend_calls": calls,
        "dynamic_url_calls": dynamic,
        "out_of_layer_calls": out_of_layer,
        "uncalled_routes": [r["method"] + " " + r["path"] for r in uncalled],
        "unmatched_calls": [c["method"] + " " + c["url"] for c in unmatched],
    }

    if args.stdout:
        print(md)
    else:
        (REPO / "scripts" / "ui_endpoint_map.md").write_text(md)
        (REPO / "scripts" / "ui_endpoint_map.json").write_text(json.dumps(data, indent=1))
        print(f"routes={len(routes)} calls={len(calls)} "
              f"uncalled={len(uncalled)} unmatched={len(unmatched)} "
              f"dynamic={len(dynamic)} out_of_layer={len(out_of_layer)}")
        print("wrote scripts/ui_endpoint_map.md and scripts/ui_endpoint_map.json")

    if args.check and unmatched:
        print(f"CHECK FAILED: {len(unmatched)} frontend call(s) match no backend route",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
