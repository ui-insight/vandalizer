# Quality Signals — Explained

*What the badges, scores, and alerts in your chat replies actually mean, and how to raise them.*

Every result from a validated extraction template carries a **quality metadata sidecar** — a small object that tells you how much you should trust the answer. This doc explains every field.

---

## The badge at a glance

When you see a colored pill next to a result like:

> **Extracted 20 fields · Verified · 94%**

…that's the `QualityBadge`. The pill encodes four things:

1. **Tier** — the color and label (Excellent / Good / Fair / Poor)
2. **Score** — a 0–100 unified number
3. **Grade** (optional) — A/B/C letter grade, shown on validation runs
4. **Alert flag** — a small icon if the template has active quality alerts

Hover the badge to see the full breakdown.

---

## The full metadata (what hover shows)

Every validated result carries this shape:

| Field | What it means |
|---|---|
| `tier` | One of `excellent`, `good`, `fair`, `poor` — derived from `score` |
| `score` | 0–100 unified score (weighted average of accuracy + consistency) |
| `grade` | Letter grade assigned at the last validation run |
| `accuracy` | 0–1 — how often the template matches the ground-truth test cases |
| `consistency` | 0–1 — how often repeated runs produce identical values |
| `num_test_cases` | How many ground-truth examples back this score |
| `num_runs` | How many validation runs have executed |
| `last_validated_at` | When the score was last refreshed |
| `active_alerts` | Unacknowledged QualityAlert records (severity: `critical`, `warning`) |

If a field is `null`, that signal hasn't been generated yet — usually because the template hasn't been validated or no test cases exist.

---

## Tier thresholds

| Tier | Score | Visual | Meaning |
|---|---|---|---|
| **Excellent** | 90–100 | Green | Validated against many test cases with high recent accuracy. Safe to act on. |
| **Good** | 75–89 | Blue | Reliable. Review before high-stakes use. |
| **Fair** | 50–74 | Yellow | Use with care. Add more test cases to improve. |
| **Poor** | 0–49 | Red | Needs attention. Accuracy or consistency is below threshold. |

Tiers are thresholds over `score`. The score itself is a weighted combination of accuracy (correctness of extracted values) and consistency (stability across repeated runs).

---

## How a template earns a score

1. Someone creates an **extraction set** (in chat: *"Propose an extraction for NIH R01s"*).
2. That template has no score yet — results carry no badge.
3. You or a teammate **promote a result to a test case** (*"Propose a test case from this proposal"*) and confirm each field in the guided verification modal.
4. Repeat for 3+ documents to build a minimum ground-truth set.
5. **Run validation** (*"Validate the NSF extractor"*) — the system runs the template N times (default 3) against every test case, measures accuracy and consistency, and computes a unified score.
6. The `ValidationRun` is persisted. The extraction set's `quality_tier` is updated. From now on, results from this template carry a `QualityBadge`.
7. Re-run validation on a schedule to keep the score current. Scores age — the badge shows `last_validated_at` so you know how fresh it is.

**Two things raise a score:**
- More test cases (broader coverage)
- Fewer mismatches between extracted values and ground truth (tighter prompts, better field names)

**One thing lowers it:**
- Consistency failures — the same extraction returning different values across runs. Usually fixed by constraining the template (enums, stricter prompts, better examples).

---

## Active alerts

If a template has been behaving badly, `active_alerts` carries one or more:

- **`critical`** — accuracy dropped below an acceptable floor or a validation run errored out. The badge shows a red dot.
- **`warning`** — consistency degraded, or it's been a while since the last validation. The badge shows a yellow dot.

Acknowledge alerts from the Quality panel once you've investigated. Unacknowledged alerts count against the tier.

---

## Where quality signals appear

- **Inline in chat** — on every result from a validated template
- **Below extraction tables** — with accuracy/consistency breakout when you run `run_extraction`
- **In validation run summaries** — the full score breakdown with accuracy %, consistency %, test-case count, and grade
- **On extraction-set listings** (`list_extraction_sets` tool) — the tier is the primary sort key so the most trusted templates surface first
- **On workflow results** (when the workflow includes an extraction step) — propagated from the underlying template

---

## Why the LLM doesn't see the sidecar

Quality metadata is kept in `deps.quality_annotations` — a server-side dict — and stripped from the LLM's tool-result before the model sees it. The LLM is told *that* a result is validated (via system-prompt guidance) but not allowed to inflate or fabricate numbers.

The practical consequence: the badge you see is computed from stored validation runs, not from the LLM's opinion. If the number looks wrong, the bug is in validation data, not in chat.

---

## FAQ

**"Why does this result have no badge?"**
The extraction template has no validation runs yet, or none of its fields match the document enough to score. Ask the agent to start a guided verification.

**"What's a good minimum of test cases?"**
Three is the floor for a score to appear. Five or more gives a meaningful Good/Excellent tier. The audit log on the template shows exactly which cases contributed.

**"Can I trust a new template that scored Excellent on 3 cases?"**
Treat that as provisional. Excellent with 3 cases means "consistent with the ground truth we have" — not "bulletproof across your whole document corpus." Add more cases from edge-case documents before relying on it for high-stakes decisions.

**"Does the tier change if I re-run validation?"**
Yes. The stored score reflects the most recent run. Stale scores surface via `last_validated_at` — if it's been weeks and nothing has changed, the badge color is still accurate but you may want to re-run to refresh the timestamp.
