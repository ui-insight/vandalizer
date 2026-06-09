# KB Autovalidate — v2 Follow-ups

Tracking the gaps and deferrals from KB Autovalidate v1 (shipped 2026-05-07).
v1 ships cheap-track optimization (retrieval-time knobs only). Plan lives at
`~/.claude/plans/autovalidate.md`; the design decisions resolved with the user
on 2026-05-07 are captured there and in `~/.claude/projects/.../memory/project_kb_autovalidate.md`.

## ✅ Done in v1.1 (2026-05-07)

- ✅ **Real token accounting via pydantic-ai `run.usage()`** — wired through
  `_generate_kb_answer`, `_generate_baseline_answer`, `_judge_answer`,
  `_maybe_rewrite_query`, `_sample_judge_variance`. `judge_test_queries`
  surfaces an aggregate `tokens_used` consumed by `kb_optimizer` for accurate
  budget enforcement. Falls back to estimate when `usage()` is unavailable
  (e.g. test mocks). 7 new tests in `test_kb_validation_service.py`.
- ✅ **Orphan-run janitor** — `tasks.passive.kb_optimization_janitor` beat-
  scheduled hourly; reaps `KBOptimizationRun` docs in `queued`/`running`
  status older than 3 hours (2× the optimizer's soft time limit). 5 new tests
  in `test_kb_optimization_janitor.py`.
- ✅ **Route integration tests for /optimize endpoints** — 13 new tests in
  `test_kb_optimization_routes.py` covering the 5 routes including the
  409 active-run conflict, budget validation, cross-KB 404, cancel idempotency,
  and apply guards.

## ✅ Done in v1.2 (2026-05-07)

- ✅ **Notification on completion** — `KBOptimizer._notify_terminal` emits a
  `Notification` document (kind=`kb_optimization_completed|cancelled|failed`)
  to the run's `user_id`. Link goes to `/?mode=knowledge&kb={uuid}`. Best-
  effort: notification failures never break the optimizer's terminal flow.
  6 new tests in `test_kb_optimizer.py`.
- ✅ **Past-runs history view** — `GET /knowledge/{uuid}/optimize` returns
  paged compact summaries (no per-trial detail). Frontend
  `OptimizationHistoryPanel` is a collapsible component mounted in both the
  idle hero and the results view. 3 new route tests in
  `test_kb_optimization_routes.py`.
- ✅ **Past-run click-through** — clicking a row in the history panel fetches
  the full run via `getKBOptimization` and renders it in `OptimizationResults`
  in read-only mode (no apply / re-run buttons). A `PastRunBanner` at the
  top makes the historical context obvious and offers a "Back to current"
  exit. Available from both the idle hero and the post-run results view.
- ✅ **Dollar cost display** — added `cost_per_1m_input` / `cost_per_1m_output`
  to admin add/edit-model schema, `SystemConfig.available_models` dict,
  `ModelInfo` schema, frontend `ModelInfo` type. `AutovalidateModal` loads
  user config on mount and passes the resolved model into
  `formatBudgetEstimate` so each tier card shows tokens **and** dollars when
  admins have populated the cost fields. Tokens-only fallback preserved
  when fields are unset.

## Lower-priority / explicit deferrals

### 7. Indexing track (re-chunking + re-embedding)

**Status:** explicit v2 deferral per design decision 2026-05-07. The
expensive-track configs (chunk_size, chunk_overlap, embedding_fn) need
ephemeral Chroma collections per trial and a canonical re-embed on apply.
Highest-impact knob but most complex to ship safely.

**Note:** when this lands, the verified-KB rule changes: indexing-track
applies must mark a verified KB as `pending-verification` because the
retrieval substrate changes.

### 8. Cancellation responsiveness

**Today:** worker checks `cancel_requested` only between trials. A cancel
mid-trial waits up to ~2 min for the current trial to finish. Documented
behaviour; not a bug.

**Possible fix:** thread cancellation into `judge_test_queries` so it can
short-circuit the asyncio.gather. Risk: leaves partial token spend
unaccounted-for. Worth it only if users complain.

### 9. Polling backoff

**Today:** `AutovalidateTab` polls every 3s for the lifetime of the panel
session. ~600 requests over a 30-min Thorough run. Cheap on the server but
suboptimal.

**Possible fix:** exponential backoff that scales with elapsed run time
(start at 3s, climb to 15s once the run is past its first-trial mark).

### 10. Named optimization profiles

**Today:** one `rag_config_override` per KB. Applying overwrites the previous.

**Possible fix:** `KnowledgeBase.rag_config_profiles: list[{name, config,
applied_at}]` so users can A/B compare or revert. Adds UI surface.

