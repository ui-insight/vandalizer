# Optional: a local code graph for review

`make review-graph` builds a local, queryable graph of this codebase using
[code-review-graph](https://github.com/tirth8205/code-review-graph) (MIT, on
PyPI, third-party). It answers structural questions — callers, callees,
imports, tests-for, impact radius, affected flows, architecture overview,
dead-code candidates — without opening files, which matters most for
agent-assisted review, where reading whole files to answer "who calls this?"
is the dominant context cost.

**It is entirely optional.** No other make target depends on it, nothing in CI
touches it, and the tool is not a project dependency. If it is not installed,
`make review-graph` says so and exits; nothing else changes.

## Setup

```bash
uv tool install code-review-graph     # once
make review-graph                     # build (first run) or refresh
```

The graph lives in `.code-review-graph/graph.db` — roughly 135 MB for this
repo. It never leaves your machine, and it is not committed (the tool ships
its own `.gitignore`, and the repo's `*.db` rule covers it regardless).
Delete the directory to walk away.

To refresh after pulling someone else's work, run `make review-graph` again.
It diffs from `ORIG_HEAD` (which git sets across a pull) rather than the
tool's `HEAD~1` default, so a pull of several commits is indexed in full, not
just its last commit. Override with `CRG_BASE=<ref> make review-graph`.

If you want it refreshed automatically after a pull, install a hook yourself:

```bash
printf '#!/bin/sh\nexec make review-graph\n' \
  > "$(git rev-parse --git-path hooks)/post-merge" && chmod +x "$_"
```

Know what that does and does not cover: `post-merge` fires on a plain `git
pull`, on a true merge, and on `git pull --rebase` when it fast-forwards. It
does **not** fire when a rebase replays local commits (that is `post-rewrite`),
and neither hook fires for a conflicted merge or for `git switch`/`git
checkout`. So the graph still goes stale on any tree change that is not a
clean pull, and `make review-graph` remains the reliable refresh.

## For coding agents

`code-review-graph install` registers an MCP server so an agent can query the
graph directly. Run it as:

```bash
code-review-graph install --no-instructions
```

`--no-instructions` matters: without it, the installer edits `CLAUDE.md`,
which is a tracked file in this repo. It also writes MCP config into the repo
root — `.mcp.json`, and per-editor files such as `.cursor/`, `.kiro/`,
`.qoder/`. Those are gitignored here, but they are yours, not the project's;
do not commit them.

## What it gets wrong

A confidently incomplete answer is worse than no answer, so know the blind
spots before trusting one in review:

- **Dynamic dispatch is invisible.** Celery `.delay()`/`apply_async`, FastAPI
  `Depends()` injection, Beanie's document-list registration in
  `database.py`, routers registered by string, pydantic-ai agents built at
  runtime — none of these produce edges. A `callers_of` answer can be silently
  missing the Celery path.
- **No HTTP edges.** The graph has no route-to-handler concept, so "which
  routes reach this service function" is `scripts/map_ui_endpoints.py`'s job,
  not the graph's. The two compose; neither replaces the other.
- **`TESTED_BY` is heuristic** — a lead on coverage, not an authority. Check
  the test.
- **Semantic search needs an extra** (`sentence-transformers`, a multi-GB
  install) and is not part of the base install.
- **Network.** The default install makes no network calls. The tool also
  ships optional embedding backends (MiniMax, an OpenAI-compatible endpoint,
  Google) that would send code-derived text to a third-party API. They are
  inert without an explicitly configured API key. Leave them off — the graph
  is built from your working tree, which on this product may sit beside
  unpublished proposals.

Treat it as a fast way to navigate and to scope a change, and confirm anything
load-bearing by reading the code.
