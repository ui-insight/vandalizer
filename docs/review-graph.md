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
uv tool install 'code-review-graph[embeddings]'  # once
make review-graph                                # build (first run) or refresh
code-review-graph embed --repo "$(git worktree list --porcelain | sed -n '1s/^worktree //p')"
```

`embed` needs `--repo` for the same reason `make review-graph` passes it: run
from a worktree, the tool discovers the worktree and creates a second graph
there rather than adding vectors to the shared one — so `search` would keep
answering in `fts` mode with nothing saying why. From the main checkout, a bare
`code-review-graph embed` is equivalent.

The `[embeddings]` extra is worth taking even though it is a multi-GB install:
without it `search` still returns results and still reports `"status": "ok"`,
but as keyword matching — see *What it gets wrong* below. `embed` is a
separate step because building the graph does not populate vectors; re-run it
after a rebuild.

The graph lives in `.code-review-graph/graph.db` — roughly 175 MB for this
repo once embedded, 135 MB without the vectors. It never leaves your machine,
and it is not committed (the tool ships its own `.gitignore`, and the repo's
`*.db` rule covers it regardless). Delete the directory to walk away.

**One graph, shared by every worktree.** `make review-graph` passes `--repo`
pinned to the main working tree. Left to itself the tool discovers the repo
from the current directory, which under `git worktree` is the worktree — so a
run from one builds a second index there holding only that worktree's files,
and answers from it with `"status": "ok"`. If you have run the tool by hand
from a worktree, delete any `.code-review-graph/` directories outside the main
checkout. Note that `detect-changes` reads its diff from the same `--repo`
path, so run it from the main checkout or set `GIT_DIR`/`GIT_WORK_TREE`
yourself; otherwise it reports on the main branch rather than yours.

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

Two consequences of pinning the graph to the main checkout are worth knowing.
The graph reflects the **main checkout's** HEAD, so a symbol you just added on a
worktree branch is simply absent — and an absent node and a real "no callers"
answer look identical, so `callers_of` on it returns nothing rather than an
error. And because every worktree now drives one database, two `make
review-graph` runs at the same time contend for it: the recipe takes an
`flock` where one is available, but macOS ships no `flock`, so on a Mac refresh
from one worktree at a time rather than several at once.

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
- **Semantic search degrades silently, it does not fail.** It needs the
  `[embeddings]` extra (`sentence-transformers`, a multi-GB install). Without
  it, `search` does not error: it returns `"status": "ok"` with
  `"search_mode": "fts"` — plain keyword matching under a semantic name. The
  results look plausible, because a query whose terms appear literally matches
  either way; what breaks is the conceptual query, and a *miss* reads as
  "nothing there" rather than "this search cannot do that". Check
  `search_mode` on anything load-bearing. Three values are normal:
  `semantic`, `hybrid` (literal hits present, blended scoring — also correct),
  and `fts` (degraded).
- **A missing node and an empty result look the same.** `callers_of` on a
  symbol the graph never indexed returns no callers, which reads as "nothing
  depends on this". Version 2.3.8 and later add a `confidence` field saying so
  in as many words; on earlier versions the response is bare. Prefer 2.3.8+,
  and treat any 0 as unconfirmed until you know the symbol is in the graph.
- **Network.** The base install makes no network calls. The `[embeddings]`
  extra downloads its model (`all-MiniLM-L6-v2`) from Hugging Face on first
  use and then runs locally; no repository content is sent anywhere. That is
  different from the tool's optional *remote* embedding backends (MiniMax, an
  OpenAI-compatible endpoint, Google), which would send code-derived text to a
  third-party API. Those are inert without an explicitly configured API key.
  Leave them off — the graph is built from your working tree, which on this
  product may sit beside unpublished proposals.

Treat it as a fast way to navigate and to scope a change, and confirm anything
load-bearing by reading the code.
