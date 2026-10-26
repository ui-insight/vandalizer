# RA expected-checks run 2, 2026-10-26 (#1005)

The second run of the 12 hand-graded RA questions in [`expected-checks.json`](../../backend/tests/fixtures/ra_usability_sources/expected-checks.json), after [the 2026-10-08 run](2026-10-08-ra-expected-checks.md). It repeats paths (a) and (b) to check stability and to see whether #1011 (multi-document page chips, `【…】` cleanup) and #1012 (silence ≠ permission) show up in real answers. It also grades the first path (c) workflow output. All source material is the fictional QA set; no real institutional data was used.

## Setup

| | |
|---|---|
| Server | `vandalizer-dev.insight.uidaho.edu`, development environment |
| Build | `v4.15.0-454-g686b7ec3` (`major/agentic-chat` head). Includes #1011 (`76f752d8`) and #1012 (`bcbd21d5`). |
| Model | `openai/gpt-oss-120b`, named on every turn. This is production's `default_model`. Dev's default is now `moonshotai/kimi-k3`, so a dev run that doesn't name the model doesn't test production's. |
| Account | A logged-in browser session as a non-admin dev user. That account can't see run 1's folder or KB, which belong to the dev admin, so the three fixtures were uploaded again into folder `RA acceptance run 2 (fictional QA)` (`5bdac4a6…`), plus a KB of the same name (`c25b2231…`, 4 chunks). Both are left in place. |
| Sources | Built from the fixture text with the same page layout as run 1. `sponsor-notice`: 4 pages, the header and section 1 on page 1, then one section per page. `sponsor-amendment`: 1 page. `proposal-draft`: 3 pages (header, budget, readiness notes). The em dash in the header became a hyphen. |
| Paths | **(a) attached:** each question with only its listed sources attached. **(b) KB:** all three files in the KB. **(c) workflow:** Budget Analyzer on `proposal-draft` (run through the management API by the first attempt at this run; output read through the session). |
| Run | 24 chat turns, each in a new conversation, 2026-10-26. 1–4 s each, all HTTP 200, no errors. Answers, chips and grounding flags were read back from each conversation's saved history. |

Grading follows run 1. **Pass** means the substance matches `expected`. **Partial** means correct facts plus an unsupported inference, or a missing caveat the expected answer requires. **Fail** means a wrong fact, a made-up rule, or no answer to the question.

## Results: chat

| Case | (a) attached | (b) KB | Notes |
|---|---|---|---|
| deadline-original | Pass | Pass† | † Same as run 1: with the amendment in scope, (b) gives Nov 19 and notes that Nov 12 was replaced. |
| deadline-amended | Pass | Pass | The amendment supersedes; the draft still shows the earlier date. |
| internal-deadline | Pass | Pass | Nov 9 at noon PT, unchanged. |
| project-period | Pass | Pass‡ | ‡ (b) cites `proposal-draft.pdf, p. 3`; the dates are on p. 1. |
| direct-cost-cap | Pass‡ | Pass | ‡ (a) cites p. 4; the cap is on p. 3. **The chip marked it not found**, which is correct. |
| budget-exception | Pass | Pass | $200,000 is over $180,000. Neither adds "no exception is documented" (same as run 1). |
| budget-arithmetic | Pass | Pass | Sums to $200,000; $250,000 with indirect costs. |
| indirect-rate | Pass | Pass | 25% is within the limit, and the direct costs still exceed the cap. (a) puts the equipment rule on p. 4; it's on p. 3. |
| missing-page-limit | **Pass** | **Pass** | Was partial both ways in run 1 ("may be any length"). Both now just say the notice doesn't specify one. |
| missing-eligibility | **Partial** | Pass | (a) again says the notice "does **not** require the PI to be a U.S. citizen", then "not specified". **The #1012 silence flag fired on this answer.** |
| required-material | Pass | Pass | Budget justification and the signed partner letter (promised is not received). |
| missing-exception | Pass | Pass | No waiver can be assumed. |

**(a) 11 pass, 1 partial. (b) 12 pass. No failures.** Run 1 had 10 + 11 passes and 3 partials. No dates, figures, rules or waivers were made up, and the unsupported-figure warning stayed silent, correctly, on all 24.

## Results: path (c), Budget Analyzer on `proposal-draft`

**Fail, but an honest one.** Run `7c728f4f`: 2/2 steps, `openai/gpt-oss-120b`.

- **Extraction step.** The seed's fields didn't match the draft's labels, and only `Equipment` ($0) and `Indirect Costs` ($50,000) were filled. All the rest came back null:

  | Draft label | Seed field |
  |---|---|
  | Personnel | Senior / Other Personnel Costs |
  | Supplies | Materials and Supplies |
  | Subaward | Subcontracts |
  | Direct-cost total | Total Direct Costs |
  | Total request | Total Project Cost |

- **Rule checks.** All four came back `unparseable` because their inputs were empty: category sum, direct + indirect = total, rate × base, and base exclusions.
- **Analysis step.** It read the amounts from the document and listed every line as "NOT CHECKED". It didn't do the arithmetic itself, which is the behaviour #1013 §4 asked for, but it never answers whether the costs add up. Expected: yes, $200,000 direct and $250,000 total.

The first draft of this note predicted PASS for the two sum rules. That was wrong: the prediction assumed the extraction would map the draft's categories onto the seed's fields.

## Trust signals

**#998 page chips on attached answers (path a).**
- **Coverage.** 8 of 12 answers had chips, against 4 of 12 in run 1. #1011's file-name attribution gave chips to three multi-document answers (deadline-amended, internal-deadline, missing-exception) that had none before.
- **Accuracy.** 13 chips: 11 found and 2 not found.
  - **direct-cost-cap:** correctly not found. The model cited p. 4 for a figure on p. 3.
  - **budget-arithmetic:** **wrongly not found.** The model quoted "Direct‑cost total" with a non-breaking hyphen (U+2011). The grounding check only treated the en and em dashes as hyphens, so the quote didn't match its own page. Reproduced locally and **fixed in f16d289d**; the new test fails against the old normaliser.
- **Gap.** 4 multi-document answers still had no chips: project-period, budget-exception, indirect-rate and required-material. Each wrote a bare `[p. 2]` or `(p. 3)` with no file name, so there was nothing to attribute the page to.

**`【…】` markup.** None in 24 answers. Run 1 showed it raw.

**#1012 silence inference.**
- It fired once, on missing-eligibility (a), the one answer that turned "not specified" into "does not require".
- It stayed silent on the other 23, including both missing-page-limit answers, which no longer read permission into silence.
- The flag warns; it doesn't change the answer. The answer still says "does not require".

**KB answers (path b).** Every answer had four retrieval chips, and the chips are right. Page numbers the model writes in the text are still not checked: project-period (b) cites the draft's p. 3, and several answers cite "p. 1–3".

## What this measures, and what it doesn't

- **The sources are easy:** 1–4 short pages with one fact per sentence. Like run 1, this sets a floor, not a ceiling.
- **It is two runs of one model.** The improvement on missing-page-limit could be #1012's prompt rule or ordinary variation between runs. The silence flag firing on exactly the bad answer is the stronger evidence.
- **Path (c) is one workflow.** Sponsor Compliance Checker, Proposal Readiness Review and the RFA checklist weren't run: the catalog copies aren't in this account's library, and adding them would have meant changing the user's workspace.

## Effect on the grade

**Chat, on short clean sources:** 23 of 24 pass. The inspectable-evidence gap from run 1 has mostly closed: chips on 8 of 12 attached answers, raw markup gone, and wrong pages caught. That supports the **B** run 1 said fixing both problems would earn, with the remaining weak spots listed below.

**Workflow path:** Budget Analyzer is honest but not useful on a budget that uses ordinary labels. That is the weakest result in this run.

## Follow-ups

- **Budget Analyzer extraction misses common budget labels.** See the field table above. The extraction (or its field descriptions) needs to map everyday category names onto the seed's fields, or the rules never run. Filed as #1057.
- **Bare page references in multi-document answers get no chip** (4 of 12), #1058. This needs a prompt rule asking for the file name with every page, or attribution by the nearest file name the answer mentions.
- **Page numbers written in KB answers are unchecked** (#1058) (project-period (b) cites p. 3 for p. 1).
- **Repeat for stability** once the dash fix (f16d289d) is deployed, and include the catalog workflows for path (c).

## Run 3: the fixes, deployed (same day)

Dev was redeployed at `v4.15.0-466-g67fbb37a`, which includes #1057, #1058 and f16d289d, with catalog 1.3.13 applied. The run used the same account, files, KB and model (`openai/gpt-oss-120b`).

**Path (c): Budget Analyzer, run `deaae2f0`. Now a pass.**
- **Extraction:** all 8 figures in the draft were read (2 in run 2): Personnel $120,000, Travel, Supplies, Subaward, Equipment $0, Total Direct Costs $200,000, Indirect $50,000, Total Project Cost $250,000.
- **Rate:** left empty rather than derived, since the draft states none.
- **Rule checks:**
  - both sums **pass**;
  - rate × base and the base exclusions are `unparseable`, correctly, because no base is stated.
- **Answer:** the analysis says the direct costs add up ($200,000, PASS) and the total adds up ($250,000, PASS), and marks the indirect calculation NOT CHECKED.

**Chat, 24 turns**
- **Chips:** 12 of 12 attached answers had chips (8 in run 2).
  - The model named the file every time, so the content-based fallback never fired.
  - budget-arithmetic's chip, the run-2 false alarm, is now **found**.
  - 7 chips were not found:
    - **4 correct catches.** A notice figure on p. 3 cited as p. 4: direct-cost cap, budget-exception, missing-exception, indirect-rate. The run 2 answers made the same mistake.
    - **1 strict but arguable** (deadline-amended): the sentence carries the amendment's and draft's dates, which the cited notice page doesn't have.
    - **2 in indirect-rate** not yet examined.
- **Regressions found and fixed in 94cb3332:**
  - **Document IDs in the text.** One answer in 24 cited a document's ID beside its name; the page note now asks for "its file name (never its UUID)".
  - **Raw snippet numbers.** 7 of 12 KB answers left "(S1)" or "[**S1**]" unexpanded, so the reader saw raw snippet numbers. Both forms are now expanded.
  - **Wrong page on a summary sentence.** project-period (b) still cited the draft as p. 3. The citation closed a summary sentence with nothing to locate, so the question-matched page stood. Such a citation now shows the chunk's full range (p. 1–3).
- **Silence answers**
  - missing-page-limit: (a) passes; (b) reads "may be any length" again, and the warning fired.
  - missing-eligibility: partial both ways. (a) was flagged. (b) concluded under a "**Conclusion:**" label two sentences after the silence statement and was not flagged. **Fixed in 4fa41208.** On all 24 run-3 answers, the new rule flags exactly that one and no others.
