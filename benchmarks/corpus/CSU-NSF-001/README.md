# CSU-NSF-001 Synthetic Proposal Benchmark (v0.5.0)

## Purpose

This package is a synthetic NSF proposal case for testing document ingestion, OCR, retrieval, context compression, citations, calculations, refusal behavior, and cross-document reasoning. It is not a valid proposal or institutional record. The institutions, sites, addresses, agreements, preliminary results, proposed experiments, and project records are fictional. Synthetic roles use stable non-person identifiers and do not represent real people. The scientific literature and open-license image sources cited in the revised narrative are real.

## What changed in v0.5.0

An external sponsor-policy review of v0.4.0 found that the packet modelled
requirements that the sponsor has since retired. Five findings were verified
independently against the NSF *Proposal & Award Policies & Procedures Guide*
(PAPPG 24-1) and the 2024 Uniform Guidance, and all five are corrected here.

- **The MTDC subaward threshold was the retired $25,000.** 2 CFR 200.1 (89 FR 30046, effective for rate proposals submitted on or after October 1, 2024) sets it at the first **$50,000** of each subaward, regardless of the period of performance. The rate agreement, budget policy, budget justification, and budget workbook now state and apply that rule, which moves the budget — see the table below.
- **The mentoring plan covered the postdoctoral scholar only.** PAPPG 24-1 II.D.2.i(i) requires one plan covering both postdoctoral scholars and graduate students, so `09_Postdoc_Mentoring_Plan` is replaced by a single one-page `09_Mentoring_Plan` with shared and group-specific components for each.
- **Facilities, Equipment and Other Resources carried dollar figures.** PAPPG 24-1 II.D.2.g bars quantifiable financial information there, so the $2.4 million genomics-core investment and the $62,000 instrument price are gone from `08_Facilities_Equipment_Resources`, which now describes the same resources narratively. Those institutional figures move to a new internal document, `16_CSU_Research_Infrastructure_Summary`, which is where the cross-document questions now find them.
- **Senior-personnel documents used the retired combined forms.** PAPPG 24-1 II.D.2.h(i–iv) requires four documents per person, so the combined `10_Biographical_Sketches` and `11_Current_Pending_Support` are replaced by per-person Biographical Sketches (10, 11), Current and Pending (Other) Support (12, 13) with no "recently completed" category, Synergistic Activities (14, 15), and a Collaborators and Other Affiliations workbook each.
- **The rate agreement imposed a provisional successor rate.** 2 CFR 200 Appendix III §C.7 applies negotiated rates for the life of each competitive segment, and Section III.D now states that instead.

The proposal is also framed explicitly as unsolicited under PAPPG 24-1 — the Budget Justification's cost-sharing statement follows from that framing — and §3 of the Project Description is retitled "Preliminary Studies".

### Corrected budget

| Line | v0.4.0 | v0.5.0 |
|---|---|---|
| Total direct costs | $807,485.77 | $807,485.77 |
| Subaward included in MTDC | $25,000 | **$50,000** — $30,000 in Year 1, $20,000 in Year 2 |
| Subaward excluded from MTDC | $35,000 | **$10,000** — Year 3 |
| MTDC exclusions | $182,636.20 | **$157,636.20** |
| MTDC base | $624,849.57 | **$649,849.57** |
| F&A at 58% of the MTDC base | $362,412.75 | **$376,912.75** |
| **Total amount requested** | $1,169,898.51 | **$1,184,398.51** |

The authoritative total is 1,184,398.51428; $1,184,398.51 is the displayed value, and every document, key, workbook cell, and validator constant agrees on it.

### Keys and comparability

The 30 question IDs and the question count are unchanged. Q021 is rewritten for the combined mentoring-plan requirement, and every answer, source page, and corroborating page was re-derived against the v0.5.0 renders rather than carried forward. **Published model-benchmark tables for this corpus were measured against the v0.3.3 answer key and predate this recomputation**, so they are not comparable on the budget questions or on the questions that cited the retired senior-personnel documents. That caveat still stands and is not retired by anything below: the *Measured results* section is a new run against the v0.5.0 key over a different code path, and its numbers must not be diffed against the older tables in either direction — see caveat 5 in *How to read these numbers*.

### Packaging note

The DOCX and XLSX sources edited for this release keep the zip member timestamps they were written with. They were deliberately not re-saved to normalize those timestamps, because re-saving risks content and hash drift against renders that are already verified. One exception is metadata only: the budget workbook's `docProps` members were rewritten in place so that all three workbooks carry the same fixed document properties — a generic synthetic-generator creator and a fixed created and modified date of 2026-08-20 — in place of the build-time values a library had written. Only those two members changed; every other member of that file is byte-identical to the one the verified renders were made from, and no workbook was re-saved. The sha256 of every release asset is pinned in `manifest.json`.

## Measured results (v0.5.0, end-to-end)

Every number in this section comes from one run: 30 questions × 3 repeats ×
5 models × 2 modes = **900 answers**, all obtained over the application's real
chat API — the same path a person uses in the UI — with 0 transport errors.
The scoring key is the v0.5.0 key that ships in this package. The harness that
produced every table below, and the scorers that graded it, are in the
vandalizer repository under `benchmarks/corpus/CSU-NSF-001/tools/` — see
*Reproducing the measured results*. Read *How to read these numbers* at the end
of this section before quoting any of it.

### Answer accuracy, knowledge-base retrieval

Each model answered its own requests; requested and served model matched on all
450 rows. 27 answerable questions, majority of 3 repeats.

| model | served model (verified) | answers correct (majority of 3) | per-repeat | refusals correct | negative controls |
|---|---|---|---|---|---|
| Qwen3-VL-8B | `Qwen/Qwen3-VL-8B-Instruct` | 24/27 (88.9 %) | 72/81 (88.9 %) | 9/9 | 12/12 |
| Qwen3.5-9B | `Qwen/Qwen3.5-9B` | 25/27 (92.6 %) | 74/81 (91.4 %) | 9/9 | 12/12 |
| Qwen3-VL-30B-A3B | `Qwen/Qwen3-VL-30B-A3B-Instruct` | 25/27 (92.6 %) | 75/81 (92.6 %) | 9/9 | 12/12 |
| gpt-oss-20b | `openai/gpt-oss-20b` | 25/27 (92.6 %) | 75/81 (92.6 %) | 9/9 | 12/12 |
| gpt-oss-120b | `openai/gpt-oss-120b` | 25/27 (92.6 %) | 75/81 (92.6 %) | 9/9 | 12/12 |

Five models, one question set, one retrieval configuration. The spread is one
question. Two of the three failures every model shares are not model failures at
all: retrieval returns the same eight chunks to every model, and for two
questions those chunks do not contain the answer (*Where knowledge-base mode
loses*, below). With those two removed the practical ceiling for this retrieval
configuration is 25/27, and four of five models reach it.

### Attached-document mode: the model you ask for is not the model you get

All 16 documents attached to a single chat turn.

| model requested | **model that actually answered** | rows routed away | notice shown to the user |
|---|---|---|---|
| Qwen3-VL-8B | **Qwen3.5-9B** | 90/90 | yes — `model_routed` |
| Qwen3.5-9B | **Qwen3.5-9B** | 0/90 | n/a — it is the long-document model |
| Qwen3-VL-30B-A3B | **Qwen3.5-9B** | 90/90 | yes — `model_routed` |
| gpt-oss-20b | **Qwen3.5-9B** | 90/90 | yes — `model_routed` |
| gpt-oss-120b | **Qwen3.5-9B** | 90/90 | yes — `model_routed` |

The measurement behind it:

| quantity | value |
|---|---|
| assembled packet | **31,881 – 31,900 tokens** (31,144 of them document text) |
| input budget of the four non-9B models | **24,576 tokens** |
| overage | **+30 %** |
| input budget of the model that answered | 253,952 tokens |
| context compaction / truncation events | **0** |

At v0.5.0 the 16-document packet is about 31.9k tokens and does not fit the
24.6k input budget of four of the five registered models. The long-document
router redirects those requests to the one model that can hold the packet, tells
the user it did so, and keeps the whole document in view — nothing was truncated
or compacted in 450 rows. The correct engineering behaviour also means
**attached-document mode cannot compare models on this corpus**: all five
columns are the same model. Any five-model table over a packet this size is five
samples of one model. Accuracy in this mode was 26–27 of 27 answerable questions
(majority of 3) for every requested model — that is one model's score, sampled
five times, and the 1-question spread is its run-to-run variance.

This measurement is what retires the context-limit caveat earlier releases of
this README carried; see *Limits*, below.

### Refusal behaviour on unanswerable questions

Three questions have no answer in the documents: the PI's Social Security
number, the specific make and model of the imaging flow cytometer, and the name
of the postdoctoral researcher. A row passes only if it states the information
is absent **and** invents no specific.

| mode | model | correct refusals /9 | fabricated a specific |
|---|---|---|---|
| knowledge base | Qwen3-VL-8B | 9/9 | 0 |
| knowledge base | Qwen3.5-9B | 9/9 | 0 |
| knowledge base | Qwen3-VL-30B-A3B | 9/9 | 0 |
| knowledge base | gpt-oss-20b | 9/9 | 0 |
| knowledge base | gpt-oss-120b | 9/9 | 0 |
| attached docs | Qwen3-VL-8B | 8/9 | 0 |
| attached docs | Qwen3.5-9B | 6/9 | **1** |
| attached docs | Qwen3-VL-30B-A3B | 8/9 | 0 |
| attached docs | gpt-oss-20b | 9/9 | 0 |
| attached docs | gpt-oss-120b | 8/9 | 0 |

84 of 90 unanswerable rows refused correctly. The Social Security number
question was refused 30/30 — no model ever produced a digit string. Five of the
six failures are the same shape and are worth separating from hallucination:
asked which model of imaging flow cytometer will be purchased, the answer
describes the instrument, the $62,000 cost and the Year-1 timing, and never says
that no manufacturer or model is named. Nothing is invented; the absence is
simply not flagged. **One row in 900 fabricated a specific**: it answered "what
is the name of the postdoctoral researcher" by presenting the PI's role
identifier as the postdoc's identity.

A related behaviour worth knowing about: four knowledge-base rows correctly
declined on the instrument question and then, under an explicit "beyond the
retrieved sources" heading, listed real instrument brands as examples of the
kind of name the documents do **not** contain. One of those examples appears to
be invented outright. None asserts that any of them will be purchased, so all
four count as correct refusals — but a careless reader could carry a brand name
out of the answer.

### Negative controls

Four questions plant a plausible wrong figure or a superseded fact and ask the
system to reject it: a $1.25M regional-loss figure offered as the request
amount, a closed $20,000 internal seed award, absent committed cost sharing, and
a $2.4M institutional facility investment.

| model | knowledge base | attached docs |
|---|---|---|
| Qwen3-VL-8B | 12/12 | 12/12 |
| Qwen3.5-9B | 12/12 | 12/12 |
| Qwen3-VL-30B-A3B | 12/12 | 12/12 |
| gpt-oss-20b | 12/12 | 12/12 |
| gpt-oss-120b | 12/12 | 12/12 |

**120 of 120.** Every model, both modes, all three repeats. On this question set
and this path the negative controls no longer separate the models.

### Page-citation accuracy

Scored by document-aware citation matching against the answer key.
**Defensible** = document and page both canonical, or a corroborating source, or
a page number with no document named. **Strict** = document named and both
document and page correct.

Attached-document mode (all five columns are the same served model):

| model requested | rows naming a page | citations emitted | defensible | strict |
|---|---|---|---|---|
| Qwen3-VL-8B | 81/90 (90 %) | 285 | 66 % | 29 % |
| Qwen3.5-9B | 83/90 (92 %) | 308 | 70 % | 27 % |
| Qwen3-VL-30B-A3B | 84/90 (93 %) | 276 | 61 % | 20 % |
| gpt-oss-20b | 81/90 (90 %) | 289 | 61 % | 22 % |
| gpt-oss-120b | 83/90 (92 %) | 302 | 63 % | 20 % |

Knowledge-base mode:

| model | rows naming a page | citations emitted | defensible | strict |
|---|---|---|---|---|
| Qwen3-VL-8B | 33/90 (37 %) | 78 | 73 % | 63 % |
| Qwen3.5-9B | 10/90 (11 %) | 26 | 85 % | 77 % |
| Qwen3-VL-30B-A3B | 19/90 (21 %) | 39 | 72 % | 64 % |
| gpt-oss-20b | 35/90 (39 %) | 62 | 89 % | 77 % |
| gpt-oss-120b | 7/90 (8 %) | **6** | *(n too small)* | *(n too small)* |

Two different regimes. With the whole packet attached, models cite a page for
roughly nine of every ten answers but are right about which document that page
belongs to only 20–29 % of the time — the dominant error is a correct page
number attached to the wrong document. With knowledge-base retrieval, citations
are much more often exactly right (63–77 % strict) but appear far less often.
The gpt-oss-120b knowledge-base row rests on six citations and must not be
quoted as a percentage.

Because all five attached-document columns are the same served model, the
9-point defensible spread across them is that model's run-to-run variance at
production temperature — a useful calibration figure when reading any
single-run citation number.

**The knowledge-base citation gap is a presentation gap, not a retrieval gap.**
Every retrieved chunk carried a page number (3,600 of 3,600), and the response
payload exposes the document and page for each one. The models simply do not
surface that page in the answer text for most questions.

### Where knowledge-base mode loses, and why

| question | every model's result | cause |
|---|---|---|
| "Where did the PI earn the Ph.D., and in what field?" | 0/15 | the retriever returned the **Co-PI's** biographical sketch and never the PI's |
| "What are the three field sites?" | 0/15 | the retriever returned the project-description page describing the field schedule, never the page naming the sites |

Retrieval in knowledge-base mode is deterministic and model-independent: for all
30 questions the same eight chunks were returned to every model on every repeat.
These two questions therefore carry no model signal — the models are answering a
question whose evidence was never handed to them, and most of them say so
plainly rather than guessing. Both questions do far better in attached-document
mode, where the whole packet is in view: the field-sites question is answered
correctly 15 times out of 15, and the Ph.D. question 13 times out of 15 if a
truncated form of the institution's name is accepted (4 of 15 if it is not — see
caveat 8). That contrast is the strongest single argument in this run for
attaching documents when completeness matters more than speed.

Retrieval coverage overall was good: for 26 of 27 answerable questions the top-8
chunks contained a canonical or corroborating page from the answer key.

### Latency — reported, not benchmarked

| mode | cold start (first question after model load) | warm question, median | warm question, p90 |
|---|---|---|---|
| knowledge base | 55 – 101 s | 1.1 – 2.6 s | 1.7 – 4.0 s |
| attached docs (16 PDFs, ~31.9k tokens) | 91 s for the first pass only | 3.9 – 4.0 s | 5.2 – 5.8 s |

The distribution is sharply bimodal: a model load, then everything else.
**These numbers characterise one run on one shared host and should not be read
as a latency benchmark** — the box also runs an OCR stack and the GPU sampler
showed sustained 100 % utilisation throughout. This is the corpus's own
shared-host latency caveat (see *Limits*) applying to its own results. The
attached-document cold start looks low for four of the five models for the
reason given above: their requests were routed, so their models were never
loaded. Slowest single answer in 900: 8.8 s. No question came within two orders
of magnitude of the 900-second timeout.

### How to read these numbers

1. **Temperature was left unset**, matching production configuration rather than
   pinned to 0. These are the numbers the deployed system produces, not a
   determinism-controlled experiment. Run-to-run variation is real and visible:
   see the 9-point citation spread across five columns that are the same model.
2. **3 repeats per question.** Enough to see variance, not enough to rank models
   whose scores differ by one question. Nothing here supports a ranking claim.
3. **Single host, single run.** All 900 answers come from one box on one
   evening. Nothing has been replicated on independent hardware.
4. **Shared GPU.** Latency figures are indicative only, for the reason above.
5. **Not comparable to the earlier published tables.** The previously published
   accuracy and citation tables for this corpus used a **different answer key
   (v0.3.3, since revised — 12 of 30 answers changed)**, a **different code
   path** (a harness posting directly to the model gateway, bypassing the
   application), a **different document scope** (one document per question, or a
   smaller packet), a **different question set**, and **different repeat
   counts**. Deltas against them are indicative of direction at best and should
   never be quoted as a regression or an improvement.
6. **Attached-document mode is not a model comparison on this corpus.** All five
   columns are the same served model. Do not read them as five models.
7. **Two knowledge-base questions carry no model signal** because retrieval
   never supplied the evidence.
8. **Scoring was adjudicated, not purely automatic.** The automatic scorer is
   deliberately conservative and deferred 327 of 900 rows for human review;
   68 of the 76 verdicts the human pass overturned were mechanical defects in
   the scorer, since repaired — see *Reproducing the measured results* below
   for what they were and what the repair does and does not cover; all
   327 were adjudicated against the key, and so were the 573 it did not defer.
   That second pass overturned 76 automatic verdicts — 68 correct answers the
   scorer had failed and 8 wrong answers it had passed. The published numbers
   are the adjudicated verdicts. The rubric was: *the decisive content is what
   answers the question as asked; supporting detail the question did not request
   is not required; for unanswerable questions the answer must state the absence
   and invent nothing.* The strictest single call in that rubric: a question
   asking where a degree was earned requires the institution's **exact** name.
   Nine attached-document rows named a recognisable but truncated form of it and
   were failed; accepting the truncation would raise every attached-document
   column by roughly two questions. It is flagged here so a reader can apply a
   different standard deliberately rather than by accident.
9. **The corpus is fully synthetic.** No real people, institutions, awards, or
   dollar figures appear in it; the identifiers are role labels, not names.

## Reproducing the measured results

The tables above are reproducible from what the repository ships. Three tools
do it, all under `benchmarks/corpus/CSU-NSF-001/tools/`:

| tool | what it does |
|---|---|
| `run_benchmark_http.py` | asks the 30 questions over the deployment's own chat API and writes one row per answer, carrying the server's `context_notice` and `context_budget` chunks alongside the text |
| `score.py` | triages answer correctness against the key and defers anything it cannot decide mechanically |
| `citation_accuracy.py` | scores page citations per document, separating a wrong page from a wrong document from a correct citation to a corroborating page |

None of the three is **part of the release package**: it ships only the two
release validators, because those are what a person checks a download with, and
all three of these need a harness run's output (or a whole deployment) before
they do anything. Nothing under `.github/workflows/` **invokes** any of the
three either — but the two scorers are not untested. CI runs `pytest` over this
whole `tools/` directory on every change, and `test_score.py` and
`test_citation_accuracy.py` import and exercise both of them; `run_benchmark_http.py`
has `test_run_benchmark_http.py` covering its pure functions the same way.

Only the *asking* path is genuinely off CI, because it needs a running
deployment and real GPU minutes. That puts it where the repository's tier-3
`INTEGRATION_LLM` suite already is: not on the pull-request path, run on a
schedule and on demand rather than never.

### What you need

A running Vandalizer instance with at least one registered model, an account on
it that is not your own (the harness uploads 16 documents and creates a
knowledge base), and the release tarball named in `manifest.json`. The harness
reads the documents straight out of that tarball after verifying its sha256
against the manifest — it never uploads from a loose directory, because a PDF
left over from an earlier release carries the retired $1,169,898.51 total and
would fail a third of the questions in a way that reads exactly like a model
error.

### Running it

```bash
export VANDALIZER_URL=https://your-instance.example
export VANDALIZER_USER=... VANDALIZER_PASS=...     # or --env-file, kept outside the repo

KEYS=benchmarks/corpus/CSU-NSF-001
ASSETS=/tmp/corpus-assets                          # holds the downloaded tarballs
RUN=$(date -u +%Y%m%dT%H%M%SZ)

# ingest and verify first; this asks nothing and spends no GPU time
uv run --with requests python $KEYS/tools/run_benchmark_http.py \
  --assets-dir $ASSETS --mode attach --preflight-only --run-id $RUN
uv run --with requests python $KEYS/tools/run_benchmark_http.py \
  --assets-dir $ASSETS --mode kb --preflight-only --run-id $RUN

# one scored pass per model per mode; --run-id shares one evidence directory
for mode in attach kb; do
  for model in <tag> <tag> …; do
    uv run --with requests python $KEYS/tools/run_benchmark_http.py \
      --assets-dir $ASSETS --mode "$mode" --model "$model" \
      --repeat 3 --pace 2.5 --timeout 900 --warmup --run-id $RUN
  done
done
```

`--warmup` is not optional if you intend to quote a latency number: it asks one
unscored throwaway at the full timeout and records its wall time as
`cold_start`, which keeps model ignition out of scored item 1. `--repeat 3` is
what the published tables used. Pass `--admin-config` from an administrator
account to record the routing configuration in each run's metadata; without it
the run still records which model actually served every request, which is the
part that matters.

The run writes to `<out-dir>/run-<run-id>/`, so from the same working directory
(the repository root, where `$KEYS` resolves) score each `raw_<mode>_<tag>.json`
in place:

```bash
RUN_DIR=benchmark-runs/run-$RUN                    # --out-dir default

python $KEYS/tools/score.py $RUN_DIR/raw_attach_<tag>.json \
  --json $RUN_DIR/verdicts_attach_<tag>.json
python $KEYS/tools/citation_accuracy.py --keys $KEYS $RUN_DIR/raw_attach_<tag>.json
```

`benchmark-runs/` is gitignored. Citation scoring is valid for `attach` and `kb`
rows only: `--mode merged` paginates the whole composite 1..N, which does not
map to the key's per-document pages, so `citation_accuracy.py` refuses those
rows rather than scoring them against the wrong scale.

### The scoring is adjudicated, and that is deliberate

`score.py` triages; it does not adjudicate. It auto-marks a row PASS only when
the decisive content is unambiguously present by a mechanical test, and defers
everything else to a human — 327 of 900 rows on the published run, every one of
which was read before any number here was published. **A REVIEW count is not a
failure count.** The rubric the human pass applies:

> **Decisive content** is the minimal set of assertions that answers the
> question *as asked*. Supporting breakdowns that appear in the key but that the
> question did not request are **not** required. A row **PASSes** iff every
> decisive element is present and correct and nothing in the answer contradicts
> it. A row **FAILs** otherwise. For the unanswerable questions a row PASSes iff
> it states that the information is absent **and** invents no specific;
> inventing a specific is a hard fail regardless of the rest of the answer.

Two halves of that are not mechanically checkable and are left to the human
rather than guessed at. The first is whether a prose claim beside a correct
figure is wrong. The second is fabrication, and it is worth being exact about
what the tool does and does not do, because this is the paragraph a sceptic
will weigh its honesty by.

**`score.py` contains no fabrication check.** An answer that states the absence
and then invents a specific auto-PASSes there as a correct abstention. Four
rows in the published run have exactly that shape — the four knowledge-base
rows described under *Refusal behaviour on unanswerable questions*, which
decline on the instrument question and then name instrument brands as examples
of what the packet does not contain, one of those names apparently invented.
All four pass automatically, and the human pass passed them too, under the
rubric, because none asserts the proposal will buy one.

The run's one hard fabrication is the opposite shape: it never states that the
name is absent, so the refusal branch FAILs it mechanically. That is a
coincidence of shape, not a check — a fabrication that had declined first would
have passed. The gap is stated here rather than closed, and
`tools/test_score.py` pins both shapes so it cannot close, or widen, without a
test saying so.

Scoring that run also exposed three mechanical defects in `score.py` itself —
matching against raw model output so that bolded figures went unfound, a
refusal vocabulary too narrow for the ways models phrase an absence, and
treating every figure in a key answer as required when the question had asked
for one of them. All three are fixed in the version that ships here, and
`tools/test_score.py` pins each fix against the pattern that produced it.
Caveat 8 above describes the published run, which was scored before the fixes
and adjudicated by hand; the numbers in this README are those adjudicated
verdicts and are unchanged by the repair.

### What it costs

On the hardware that produced the published tables — one shared GPU host —
an `attach` pass was **9.7–10.0 minutes** and a `kb` pass **5.5–7.8 minutes**;
ten passes (five models × two modes) took about 90 minutes end to end plus
ingestion. The dominant cost is model
loading, not answering: cold starts ran 55–101 s while the slowest single
scored answer in 900 was 8.8 s. Budget for one cold load per model switch.
Ingesting the packet and building the knowledge base happens once and is
re-used across passes through the harness's state file, so a second run against
the same instance skips it.

## What changed in v0.4.0

- **Corroborating sources added.** Every question now carries a `corroborating_sources` field listing pages that also state the decisive fact but fall outside the minimal canonical `sources` set. The field is present on all 30 questions and populated on 15 of them — the questions whose decisive fact is restated on a page outside the canonical set; it is empty on the other 15.
- **Citation scoring made fair.** The key now records these pages so a scorer can accept a true citation to one instead of punishing it. This is the failure mode measured in `ui-insight/vandalizer#628`, where all five of one model's apparent citation failures were correct citations to unlisted pages.
- **Questions, answers, and existing sources lists are unchanged.** v0.3.3 benchmark results remain valid and comparable.
- **README caveats added.** The shipped README now states the synthetic-degradation, context-limit, and shared-GPU-latency caveats.

## What changed in v0.3.3

- **Synthetic identities removed.** PI, Co-PI, research-administration, and federal-negotiator roles now use stable non-person identifiers: `CSU-PI-001`, `CSU-COI-001`, `CSU-VPR-001`, and `FED-NEG-001`.
- **Fictional publication records made non-bibliographic.** Biosketch products now use `SYN-PUB-*` identifiers and are explicitly labeled as fictional benchmark products. They have no human authors, journal assignments, DOIs, volumes, or pages.
- **Metadata sanitized.** Personal names were removed from Word and Excel metadata. Generic synthetic-generator metadata is used instead.
- **Benchmark keys synchronized.** Q023 and Q030 were regenerated in both `ground_truth.json` and `benchmark_questions.csv` to use the new role identifiers.
- **Real scholarship preserved.** Verified authors in References Cited and genuine open-license figure credits remain accurately attributed.

## Identity-safety policy

No natural-person name may represent a synthetic investigator, administrator, negotiator, signatory, credential holder, project participant, or fictional publication author. Stable role identifiers are used instead. Real personal names are permitted only when accurately attributing a verified scholarly reference or an open-license source. This distinction is release-gating and is checked by `tools/validate_identity_safety.py`.

## Release validation

From the package root, run `python tools/validate_identity_safety.py .` and `python tools/validate_release.py .`. The first command checks identity policy across Word, PDF, Excel, JSON, CSV, and Markdown files. The second checks question-key parity, source-page bounds, fixed PDF pagination, the complete 24-reference citation set, manifest inputs, and the authoritative budget total. It also checks the `corroborating_sources` entries against six rules: every question carries the field; each listed document exists in the package; each listed page is an integer within that document's page range; no entry duplicates a document-and-page pair already in the question's canonical `sources`; an unanswerable question's list is empty; and a workbook entry carries no page number. With the documents present it also checks the sponsor-policy invariants this release turns on: that Facilities, Equipment and Other Resources states no dollar amount, that the subaward threshold stated in the rate agreement, the budget policy, and the budget justification is the same figure and matches the workbook's inclusion constant, and that neither Current and Pending document carries a "recently completed" category. (In the vandalizer repository the validators take explicit paths instead of a package directory — see `benchmarks/corpus/README.md`, *Running the validators*.)

## What changed in v0.3.2

- **Explicit citation token** added for reference [14] in Section 5.2. The earlier `[13-15]` range already included reference [14], but the validation-method citation now reads `[13,14,15]` so literal-token validators cannot misclassify the reference as uncited.
- **Word-first generation** repeated for the Project Description and References Cited, followed by fresh PDF rendering and full-page visual inspection.
- **Pagination and keys** remain unchanged. The Project Description is still 13 pages, and all existing ground-truth page mappings remain valid.

## What changed in v0.3.1

- **References Cited** audited against publisher, DOI, and official agency records. Incorrect author lists and titles were corrected, missing persistent identifiers were added, and a generic quality-control webpage was replaced with a specific NOAA manual.
- **NSF reference completeness** improved by listing every author for all 24 references instead of abbreviating author lists with *et al.*
- **Narrative-reference consistency** verified so that all 24 listed sources are cited in the Project Description and every in-text citation resolves to a listed source.
- **Formatting** standardized to 11-point Times New Roman in the References Cited document. The Project Description remains 13 pages, so benchmark ground-truth page mappings are unchanged.

## What changed in v0.3.0

- **Project Description** rewritten as a realistic 13-page NSF-style narrative using 11-point Times New Roman, one-inch margins, four figures, real peer-reviewed literature, and explicit intellectual-merit and broader-impacts arguments.
- **Scientific scope** now separates organism detection from toxin measurement and treats autonomous molecular observations as an advisory data stream, not an automated regulatory decision.
- **Methods** now include multiplex-qPCR validation, inhibition and contamination controls, field blanks, blinded external verification, daily event-window sampling, missingness categories, and a pre-registered Bayesian state-space analysis.
- **Model evaluation** now uses held-out site-years, prevents tuning leakage, and includes a frozen prospective Year 3 evaluation.
- **Feasibility** now correctly states that 28 multiplex cartridges at four cycles per day support seven days and therefore require weekly service.
- **Figures and references** now include three open-license taxon images, three original benchmark diagrams or plots, and 24 real scientific or operational sources.
- **Ground-truth citations** were updated to match the revised Project Description pagination.

## What changed in v0.2.0

The packet was revised for realism in formatting and content while keeping every v0.1.0 dollar figure, rate, date, and answer intact:

- **Project Description** expanded from ~2.5 pages to a full-length 13-page NSF-style narrative with numbered literature citations, preliminary results, embedded figures and tables, and detailed methods.
- **F&A rate agreement** reformatted in federal NICRA style (Sections I–IV, rate table, special remarks).
- **Budget policy** rewritten as a proposal-agnostic institutional policy (CSU-RSP-204). Proposal-specific figures now live only in the proposal documents, so policy questions require genuine cross-document reasoning.
- **Five documents added** that a real NSF packet would include: References Cited, Facilities/Equipment/Other Resources, Postdoctoral Mentoring Plan (required when a postdoc is budgeted), Biographical Sketches, and Current & Pending Support.
- **Prominent "SYNTHETIC" banner tables removed** from body content; every page now carries a discreet footer disclaimer instead, so document appearance matches real proposals.
- **Ten new questions (Q021–Q030)** covering the new documents, including new distractor, unanswerable, and cross-document items. Q001–Q020 are unchanged in wording and answer; their source page citations were updated to the new layouts.

## Case design

- Fictional applicant: Coastal State University; synthetic investigator roles use non-person identifiers; fictional subrecipient
- Three-year organized-research project, 09/01/2027–08/31/2030
- 58% MTDC F&A rate (predetermined, on-campus organized research)
- $62,000 equipment purchase (excluded from MTDC)
- $30,000 participant-support program, 20 non-CSU participants (excluded from MTDC)
- $55,636.20 graduate tuition remission (excluded from MTDC)
- $60,000 subaward with the first $50,000 included in MTDC as incurred — $30,000 in Year 1 and $20,000 in Year 2 — and the remaining $10,000 (Year 3) excluded
- $34,000 internal service-center charges (included in MTDC)
- Formula-driven authoritative budget total: $1,184,398.51
- Distractor figures: $1.25 million economic-loss example, $20,000 prior internal seed award, $2.4 million institutional genomics-core investment. The seed award is stated in the Project Description and the internal Research Infrastructure Summary; the genomics-core investment now only in the latter

## Files supplied to the system under test

1. `01_CSU_Synthetic_FA_Rate_Agreement.pdf`
2. `02_CSU_Synthetic_Budget_Policy.pdf`
3. `03_Project_Summary.pdf`
4. `04_Project_Description.pdf`
5. `05_Budget_Justification.pdf`
6. `06_Data_Management_Plan.pdf`
7. `07_References_Cited.pdf`
8. `08_Facilities_Equipment_Resources.pdf`
9. `09_Mentoring_Plan.pdf`
10. `10_Biographical_Sketch_PI.pdf`
11. `11_Biographical_Sketch_CoPI.pdf`
12. `12_Current_Pending_PI.pdf`
13. `13_Current_Pending_CoPI.pdf`
14. `14_Synergistic_Activities_PI.pdf`
15. `15_Synergistic_Activities_CoPI.pdf`
16. `16_CSU_Research_Infrastructure_Summary.pdf`
17. `CSU_NSF_001_Budget.xlsx`
18. `COA_PI.xlsx`
19. `COA_CoPI.xlsx`

Sixteen PDFs, 42 pages, plus three workbooks. Editable DOCX versions are included for controlled scan generation and later revisions.

## Files withheld from the system under test

- `ground_truth.json`
- `benchmark_questions.csv`
- `manifest.json`

## Recommended test modes

1. Clean digital PDF and XLSX files
2. Light degradation at 200 dpi with slight skew and contrast loss (`scanned/light/`)
3. Moderate degradation at 150 dpi (`scanned/medium/`)
4. Severe but readable degradation at 100 dpi (`scanned/heavy/`)
5. Full-document chat
6. Knowledge-base retrieval
7. Current Vandalizer context truncation
8. Experimental Headroom compression

Earlier releases of this README listed modes 2–4 as 300 / 200 / 150 dpi. The
three severities the generator produces are and always were **200 / 150 / 100
dpi**, as each `scanned/*/degradation_manifest.json` records in its `config`
block. The README figures were wrong, not the files; nothing about the shipped
renders changed. There is no 300 dpi variant, and none is planned — see the
first bullet under *Limits* for what these files are and are not.

## Scoring dimensions

- Answer correctness
- Numeric exactness
- Citation document correctness
- Citation page correctness
- Refusal on unanswerable questions
- Preservation of distinctions among requested funds, prior support, contextual figures, and institutional investments
- OCR transcription accuracy
- Tokens and processing time

## Synthetic-data notice

Every institution, address, agreement, preliminary result, proposed experiment, and project record in this package is fictional. Synthetic investigator and administrative roles use non-person identifiers. Biosketch products are explicitly labeled synthetic benchmark records rather than publications. References Cited and open-license image sources in the Project Description are real and accurately attributed. Sponsor forms and policies used as design references are not reproduced as purported official documents. Every page carries a synthetic-document footer.

## Limits — read before citing results from this corpus

- **The scanned variants are synthetic degradation, not scanner output.** They
  rasterize the digital PDFs with per-page seeded blur, noise, skew, uneven
  illumination, and JPEG compression, and no text layer survives at any level —
  so they genuinely force the OCR path. But they are not paper that passed
  through a physical scanner: no real sensor noise, feed distortion, staples,
  or toner artifacts. Do not cite OCR results from these files as real-scan
  performance.
- **Long-document routing is exercised; compaction and silent truncation are
  not.** Earlier releases of this README said the packet was "~26k tokens", fit
  a 32k window, and therefore could not reproduce long-document routing,
  compaction, or silent-truncation failures. At v0.5.0 that is measured and
  wrong on the first two counts. Two different figures matter and they are not
  interchangeable. The **extracted document text** of the 16 shipped PDFs is
  **28,272 tokens** (cl100k, 124,519 characters) — that is what the old "~26k"
  was reaching for, and it was about 8 % low. The **packet the application
  actually assembles** when all 16 are attached to one chat turn is **31,881 –
  31,900 tokens**, 31,144 of them document text; the difference is the
  per-document markers and prompt scaffolding the product adds, and it is the
  assembled figure, not the extracted one, that a model has to hold. That packet
  is 30 % over the 24,576-token input budget of four of the five models
  measured, and long-document routing fired on 90 of 90 rows for each of them
  (see *Measured results*). What still cannot reproduce against this corpus is
  compaction and silent truncation — 0 events in 450 rows, precisely because
  routing moved every oversize request to a model that holds the packet whole.
  Reproducing those needs a packet larger than *every* configured model.
- **Latency must not be measured on a shared or single-GPU host.** Timings
  there are bimodal — warm inference is sub-2s while a cold model load is
  minutes — so any speed number includes the scheduler, not the model.
  Measured during the #628 benchmark: 139 of 350 timings were model-load.
- **The corpus detects breakage; it does not rank good configurations.** That
  much survives the v0.5.0 end-to-end run, but the earlier form of this
  bullet — "strong models answer 30/30; citation accuracy and refusal on
  unanswerable questions are the discriminating columns" — overstates both
  halves. Measured over the real chat API, knowledge-base accuracy is 24–25 of
  27 answerable questions with a one-question spread across five models, and two
  of the three shared failures are retrieval failures rather than model
  failures. Nor did the columns that were supposed to discriminate do so: the
  negative controls came back 120/120 for every model in both modes, refusals
  84 of 90 overall, and the citation spread across the five attached-document
  columns is one model's run-to-run variance, because all five were served by
  the same model. Treat any single-run difference of one question as noise.

## Planned for the next release

- A question set weighted toward absence. The earlier justification for this —
  recall-style questions at ceiling with a 2-point spread while negative
  controls spread 25 points — came from the older key and the older harness and
  **did not reproduce** end-to-end at v0.5.0, where every model scored 120/120
  on the negative controls in both modes. The item stands for a different
  reason: with recall near ceiling and absence no longer separating anything
  either, this corpus needs harder unanswerable and superseded-fact items before
  it can rank configurations at all.
- One oversize *single* document per packet. The 16-document packet already
  exceeds the input budget of a 32k-context model and does exercise
  long-document routing, so that half of the item is discharged. What is left is
  compaction and silent truncation, which need a document larger than every
  configured model — including the long-document model — and nothing in the
  corpus is that big.
- Additional packets in distinct sponsor styles (federal-vs-match budget
  columns, modular budgets, cost-share commitments, multi-institution
  subawards).
