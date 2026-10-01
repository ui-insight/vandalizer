# Remaining RA acceptance sessions

Status: **prepared, not conducted**. No participant results or model answers have been recorded. These sessions close the outstanding checklist gates; the heuristic screenshot grades are not substitutes.

Use a separate development workspace with controlled accounts. The [three fictional source files and expected checks](../../backend/tests/fixtures/ra_usability_sources/) are explicitly labeled QA material. Upload the original notice, amendment and proposal draft. The answer key is for the facilitator and automated validation; do not show it to participants before the tasks. Never use real application or institutional data for this exercise.

## Model execution checks

Use the configured development model to answer all 12 cases in `expected-checks.json`. Record model/configuration, exact source scope, answer, cited passage, missing/conflicting evidence, run ID and final outcome. Check dates, time zones, the $20,000 cap overrun and the difference between a promised and a signed letter manually. Mark each mismatch explicitly; a fluent answer or a high quality score is not a pass.

Repeat representative cases through KB, workflow and extraction validation. Verify cancel, refresh/resume, persisted history and apply/revert without manufacturing successful scores. For agent actions, record the persisted before/after state and test approval, rejection/cancellation, denied access, interrupted streaming, refresh and retry. One accepted action must create one intended effect. Complete the model-backed learning labs and course using actual work, not seeded completion flags.

## Five RA participants

Ask each participant to perform these tasks without hints after a neutral introduction to the workspace:

1. Find the current sponsor deadline and explain the conflicting draft date using the sources.
2. Check whether the draft budget meets the sponsor limit, including indirect costs.
3. Verify a returned value against its original passage and identify information that is absent.
4. Find and run a reusable proposal review on the supplied files; recover from one controlled failure.
5. Hand a result to a colleague with source identity, the budget issue and outstanding material intact.

Record device/viewport, assistive technology, task start/end, unaided completion, assistance requested, errors, unnoticed wrong-source or approval errors, source checks and handoff completeness. Use anonymous participant IDs; do not record names or private institutional details in the repository.

Acceptance: at least four of five participants complete **each** task unaided, with no unnoticed wrong-source or unintended-approval error. Record observed friction even when this threshold passes. This is a formative gate, not a statistical estimate of every RA's success rate.

| Participant | Task | Start/end | Unaided? | Source checked? | Error or assistance | Handoff complete? |
|---|---|---|---|---|---|---|
| Not yet observed | | | | | | |

## Specialist sessions

Observe a team owner locating a failed run and explaining member access; a maintainer recovering a failed connection without exposing a stored secret; an examiner inspecting evidence, claiming a submission and returning actionable feedback; and a support agent sending a requester reply versus an internal note. Confirm an ordinary RA can identify the appropriate role and request help. Record actual outcomes separately from the existing fixture-driven lifecycle checks.

## Screen-reader session

Use an actual screen reader and document its name/version and browser. Check workspace landmarks and pane labels; Files/Library composition; row and card opening; nested menus and Escape; dialog focus entry/containment/return; source identity and approximate pages; pending/error announcements; review instructions and approval consequence; and learning completion. Include a short viewport and 200% browser zoom. Record announced text and navigation order, not just an accessibility-tree snapshot. Log and repair any blockers before closing R8-BASE-07.
