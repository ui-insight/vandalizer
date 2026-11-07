# RA expected-checks run, 2026-10-08 (#1005)

The first measured run of the 12 hand-graded RA questions in [`expected-checks.json`](../../backend/tests/fixtures/ra_usability_sources/expected-checks.json) against a deployed v5 build. Until now the RA-helpfulness grade came from reading the code. All source material is the fictional QA set; no real institutional data was used.

## Setup

| | |
|---|---|
| Server | `vandalizer-dev.insight.uidaho.edu`, development environment |
| Build | `v4.14.0-236-g45fcf331` (`major/agentic-chat` head, including #995–#998) |
| Model | `openai/gpt-oss-120b`, requested on every turn. Same as production's `default_model` (confirmed through the production management API). |
| Account | dev admin account. Folder `RA acceptance (fictional QA)` (`290241b2…`), KB of the same name (`6f02e33d…`). Both are left in place for inspection. |
| Sources | `sponsor-notice` (4 pages, one numbered section per page), `sponsor-amendment` (1 page), `proposal-draft` (3 pages: header, budget, readiness notes). PDFs carry the fixture text unchanged, apart from one em dash in the "FICTIONAL QA MATERIAL" header that became a hyphen. Page breaks were added so page citations can be checked. |
| Paths | **(a) attached:** each question with only its listed sources attached. **(b) KB:** all three files in one knowledge base. Path (c), extraction or workflow, is not run yet. |
| Run | 24 chat turns, one per fresh conversation, 2026-10-08 23:08–23:10 UTC. 1–7 s each, no errors, no context notices, no tool calls. |

Grading is by hand against `expected`. **Pass** means the answer's substance matches. **Partial** means correct facts plus an unsupported inference or a missing caveat the expected answer requires. **Fail** means a wrong fact or a made-up rule.

## Results

| Case | (a) attached | (b) KB | Notes |
|---|---|---|---|
| deadline-original | Pass | Pass† | (a) Nov 12, 5 pm PT, p. 2. (b) has the amendment in scope, so it correctly gives Nov 19, without mentioning that Nov 12 was replaced. |
| deadline-amended | Pass | Pass | Nov 19 replaces Nov 12; the proposal kept the earlier date because it was drafted before the amendment. |
| internal-deadline | Pass | Pass | Nov 9 at noon PT, unchanged. |
| project-period | Pass | Pass | July 1, 2027 – June 30, 2028. Neither says outright that these aren't submission deadlines (the question didn't ask). |
| direct-cost-cap | Pass | Pass | $180,000. Neither adds "indirect costs are additional". |
| budget-exception | Pass | Pass | $200,000 is over the cap by $20,000. Neither says "no exception is documented". |
| budget-arithmetic | Pass | Pass | Sums to $200,000. |
| indirect-rate | Pass | Pass‡ | 25% meets the cap, but the direct costs still exceed it. ‡ (b) cites "proposal-draft.pdf (p. 3)" for the $50,000; the budget is on p. 2. |
| missing-page-limit | **Partial** | **Partial** | Correctly says the notice sets no page limit, then concludes "it may be any length". Expected: don't invent a limit, ask the sponsor. Silence was turned into permission. |
| missing-eligibility | **Partial** | Pass | (a) "does **not require** the PI to be a U.S. citizen", then "not specified". Same pattern of reading permission into silence. (b) says only that the notice doesn't list it. |
| required-material | Pass | Pass | Budget justification and the signed partner letter (promised is not received). |
| missing-exception | Pass | Pass | No waiver can be assumed; quotes the notice's "does not give an exception or waiver process". |

**(a) 10 pass, 2 partial. (b) 11 pass, 1 partial. No failures.** No dates, figures, rules or waivers were made up. Every dollar figure and percentage in all 24 answers appears in the sources. The figure warning (#998) stayed silent, which was correct each time.

## Trust signals

- **#998 page chips:** made on 4 of 12 attached answers (deadline-original, direct-cost-cap, budget-arithmetic, missing-eligibility). All 4 are **found**, each correctly, and previews show the supporting sentence. There were no wrong citations to catch, so this run doesn't measure the "not found" side.
- **The other 8 attached answers had no chips at all.** Each had two or three files attached, and `derive_document_citations` only makes chips when exactly one attached document has pages. The model did name the file every time: "sponsor-amendment.pdf, p. 1", `【sponsor-notice.pdf†p. 2】`, "[p. 3 of proposal-draft.pdf]". So the attribution was available but went unused. **Multi-document chats, the normal case for an RA comparing a solicitation, an amendment and a draft, get no inspectable sources.**
- **The model's own citation formatting leaks into answers:** `【p. 1】`, `【sponsor-notice.pdf†p. 2】`. This is gpt-oss's built-in citation syntax, and the chat shows it as raw text.
- **KB answers** always had four retrieval chips, which is fine for a three-file KB. The page numbers the model writes in the answer text are not checked. That's how the wrong "p. 3" for the budget got through.

## What this measures, and what it doesn't

- **These are easy documents:** 1–4 pages, one fact per sentence, no tables, no scanned pages, no conflicting sections. Long solicitations (#1007), tables and real award packets will do worse. This run sets a floor for the model, not a ceiling for the product.
- **One model, one run each.** Answers vary between runs, so a repeated run would show how stable they are.
- **Path (c), extraction and workflow, is not covered yet.**

## Effect on the 2026-10-07 grade

The chat grade (C+ after #997/#998) was a code-reading estimate. On short, clean sources the production model is **accurate and grounded**: 21 of 24 pass, none fail. What holds the grade down is the evidence an RA can check, not the answers themselves:

1. Multi-document answers carry no inspectable citations.
2. The model turns "the sources don't say" into "it's allowed".

Fix both and chat is a credible **B** for short documents.

## Follow-ups

- #1011: page chips for multi-document answers, attributed by the file name the model writes, plus cleanup of the `【…】` citation markup.
- #1012: "not specified" must never become "allowed". Prompt rule plus a check, using missing-page-limit and missing-eligibility as regression cases.
- Path (c) extraction/workflow run, and a repeat run for stability, once #1007 lands.
