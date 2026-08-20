# Long-document model routing

## The problem

Document chat puts whole documents in the prompt. When they don't fit,
`plan_and_compact_context` trims the middle out and the model answers from
what's left — correctly, confidently, and from part of the document.

Measured on a real 79-page grant proposal:

```
annotated size : 41,213 tokens
model window   : 32,768        (Qwen3-VL-30B, the configured default)
pages reaching the model : 33 of 79
```

That document cannot fit that model. Not with better settings, not with a
bigger share of the budget — the whole window is smaller than the document.

The same deployment had a 262,144-token model configured, which holds that
document four times over.

The failure is quiet in the way that matters. A wrong page number is checkable.
An answer drawn from 42% of a proposal looks exactly like an answer drawn from
all of it, and "the proposal doesn't mention X" can mean "X was in the part you
didn't show me."

## What it does

When a request won't fit the chosen model but *would* fit a nominated one, it
is answered with the nominated model instead of being trimmed.

The decision lives in `app/services/model_routing.py`, kept free of I/O so it
can be tested on its own. It is deliberately conservative — every path that
isn't a clear improvement stays on the model the user chose:

| Situation | Result |
|---|---|
| Request fits the current model | stay — nothing to gain |
| No long-document model nominated | stay — routing is off |
| Nominated model was deleted or renamed | stay — don't guess |
| Nominated model is the current model | stay — no-op |
| Request wouldn't fit the nominated model either | stay — trimmed either way, and switching would only cost the user their choice |
| Nominated model has weaker privacy | **refuse**, however well it would fit |
| Otherwise | route, and say so |

## Two things that make this dangerous if built naively

**Privacy.** Model choice has always been a human decision. This is the first
feature where the product picks a model on the user's behalf, so
"whichever window is big enough" could mean shipping a confidential grant
proposal to an external API.

`privacy` is stored on every model and shown in the admin UI, but **nothing in
the backend has ever enforced it** — the only references were copying it into
an API response. This is the first code that treats it as load-bearing. An
unlabelled model ranks as *less* protected than one marked `internal`: blank
means "nobody said", not "safe".

For the same reason the fallback is nominated explicitly by an admin rather
than discovered by scanning for the biggest context window. An unattended pick
is exactly the thing that would go wrong quietly.

**Silence.** Switching models without saying so is the same failure shape as
trimming a document without saying so — the answer looks identical either way.
Routing emits a `context_notice` on the existing channel, with action
`model_routed`, naming both models and the request size.

## Configuring it

Admin → Config → Available Models → **Long-document model**.

Off by default: with nothing nominated, behaviour is exactly as before. Pick a
model with a large context window; the picker lists every configured model.

Stored as `SystemConfig.long_document_model`; set via
`PUT /api/admin/config/models/long-document` (superadmin only, audited).

## What this does not solve

**A model that can hold the document may not be the one you want answering.**
On the deployment measured here, the 262k model emits its reasoning scratchpad
into the answer body — every fact right, output not presentable. Capacity and
quality are separate axes, and routing only addresses capacity.

**Documents larger than every configured model.** Routing declines rather than
pretending; the request is trimmed as before. That is the case a Knowledge Base
is for — chunked retrieval instead of whole-document context.

**The context-budget share.** Documents get a fixed 65% of the remaining budget
with unused history and attachment shares never reclaimed, so a single-document
chat with no history wastes about a third of its window. Independent of this
change and worth fixing separately.

## Tests

- `backend/tests/test_model_routing.py` — the decision table above, including
  both privacy cases
- `backend/tests/test_context_budget.py` — `estimate_input_tokens` agrees with
  what the planner counts, so routing triggers at the right size
- `frontend/src/components/admin/config/ModelEditor.test.tsx` — the picker
  nominates, clears, and lists every configured model
