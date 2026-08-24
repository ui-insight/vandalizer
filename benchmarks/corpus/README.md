# Benchmark corpora

Shareable synthetic document sets with verified answer keys, for measuring
ingestion, OCR, retrieval, page-citation accuracy, and refusal behaviour
against known-correct answers. Everything here is synthetic — see each
corpus's README and IDENTITY_SAFETY.md. Contributed via
[#628](https://github.com/ui-insight/vandalizer/issues/628).

## Layout

What lives in the tree is what people need to read, review, and diff: each
corpus's README, manifest, blind question set, answer key, and validators.
The documents themselves (PDF/DOCX/XLSX and the rasterized scanned variants)
are **release assets**, listed by name and sha256 in the corpus manifest and
attached to the release tagged in it (`corpus-v*`). They stay out of the tree
deliberately: they are large binaries, and they look exactly like the real
proposals search engines index.

## Validation

`.github/workflows/corpus-validate.yaml` runs two jobs:

- **tree-validate** (every PR/push touching `benchmarks/corpus/**`, or either
  of the two backend modules the corpus tools import): structural key checks,
  the retired-identity denylist, a structural person-name scan over every file
  in the corpus's own directory, and the unit tests in `tools/`.
- **asset-validate** (on publishing a `corpus-v*` release, or manually via
  workflow_dispatch): downloads the assets, verifies each sha256 against the
  manifest with `verify_assets.py` — a mismatch, a missing asset, or a tarball
  the manifest does not list fails before anything is scanned — then runs the
  person-name scan over the actual PDF/DOCX/XLSX binaries, verifies the
  scanned variants carry zero residual text, and re-verifies every answer-key
  citation against the extracted text using the product's own extraction
  helpers.

Both jobs are wired to CSU-NSF-001 by path: a second corpus added here needs
its own steps in `.github/workflows/corpus-validate.yaml` before anything
validates it.

`validate_keys.py` imports five symbols out of
`backend/app/services/document_readers.py` and
`backend/app/services/extraction_sources.py`, deliberately, so the keys are
checked against what the product actually extracts. That makes a backend
rename able to break a corpus tool from outside `benchmarks/`, which is why
both modules are in the workflow's paths filter and why
`tools/test_backend_contract.py` imports the same five and smoke-calls the
pure ones: a backend-only pull request runs the corpus job, and that test is
what fails there.

The gates are also tested against planted defects rather than only against a
clean corpus, in `tools/test_validator_failure_paths.py` — a corrupted byte, a
missing and an unlisted release asset, a corroborating page past the end of a
document, a corroborating source duplicating a canonical one, an unanswerable
question carrying corroboration, a deleted `corroborating_sources` key, a
retired identity, a new name-shaped string against a baseline, a citation
no pass can verify that is not pinned, and one violation of each sponsor-policy
invariant CSU-NSF-001 v0.5.0 turns on: a dollar amount in Facilities, Equipment
and Other Resources, a subaward threshold that disagrees between the documents
or with the workbook, and a "recently completed" category in a Current and
Pending document. Both identity scanners are exercised on
generated `.docx` and `.xlsx` files as well as text, in each of the four shapes
the corpus itself once shipped: a name in a body paragraph, a name in a
signature-block table cell, a name in a section header, and a name present only
in `docProps` metadata. The table-cell case found a live bug in
`scan_person_names.py`, fixed here — `docx_lines()` yields a cell as one string
including its newlines, and `NAME` separated its groups on `\s+`, so a cell
reading `<name>` over `Vice President for Research` matched First-Middle-Last
across the line break, landed the last group on a non-person token, and dropped
the candidate. `NAME` now separates on `[ \t]+`. Every fixture is generated at
test time in a temporary directory: a checked-in file carrying a retired name or
a broken key would be scanned by the tree gates themselves.

The person-name scan is the load-bearing check: the denylist can only catch
names already known to be wrong, while the structural scan finds every
name-shaped string in text, tables, headers, footers, and metadata and
subtracts the permitted locations (genuine scholarly attribution in
References Cited). See each corpus's IDENTITY_SAFETY.md for why this policy
exists.

## Running the validators

These are the in-tree tools, which take every path as an argument. Note that a
corpus's own README describes the **unpacked release package** — a single flat
directory holding the documents, the keys, and a bundled copy of the validators
— and the tools bundled there take that package directory positionally
(`python tools/validate_release.py .`); the in-tree tools below do not, because
in the tree the keys and the documents live in different places.

Set `KEYS=benchmarks/corpus/CSU-NSF-001`, and `BIN` to the directory the release
tarballs were unpacked into (holding `pdf/`, `source/`, `scanned/`). `BIN` must
be an **absolute** path: the examples below `cd backend` partway through, so a
relative `BIN` would resolve against the wrong directory.

Eleven non-test tools live there. Two of them —
`validate_release.py` and `validate_identity_safety.py` — need only pypdf and
python-docx, so they run from the repository root against an ephemeral
environment. Five need PyMuPDF — `scan_person_names.py`,
`check_references.py`, `check_scans.py`, `validate_keys.py`, and
`validate_keys2.py` — and `validate_keys.py` additionally imports the product's
own extraction helpers, so all five run from `backend/` against its
environment. Three more, `citation_accuracy.py`, `score.py` and
`verify_assets.py`, import only the standard library and run anywhere —
`verify_assets.py` by design, since it is what stands between a downloaded
tarball and anything that parses it. The eleventh, `run_benchmark_http.py`,
is the benchmark harness and is the only one needing a third-party package none
of the others do (`requests`); it also needs a running deployment, so it has
its own section below rather than a place in this list.

Keys only — everything a pull request can check without the assets:

```bash
uv run --with pypdf --with python-docx python $KEYS/tools/validate_release.py --keys $KEYS
uv run --with pypdf --with python-docx python $KEYS/tools/validate_identity_safety.py $KEYS

cd backend
uv run python ../$KEYS/tools/scan_person_names.py ../$KEYS \
  --baseline ../$KEYS/tools/name_scan_baseline_tree.json
```

With the release assets — hashes first, since every check below reads what is
inside these tarballs (`ASSETS` is the directory the tarballs were downloaded
to):

```bash
python3 $KEYS/tools/verify_assets.py --manifest $KEYS/manifest.json --assets-dir $ASSETS

uv run --with pypdf --with python-docx python $KEYS/tools/validate_release.py --keys $KEYS --binaries $BIN
uv run --with pypdf --with python-docx python $KEYS/tools/validate_identity_safety.py $KEYS $BIN

cd backend
uv run python ../$KEYS/tools/check_references.py --binaries $BIN
uv run python ../$KEYS/tools/check_scans.py --binaries $BIN
uv run python ../$KEYS/tools/scan_person_names.py $BIN \
  --baseline ../$KEYS/tools/name_scan_baseline_assets.json
uv run python ../$KEYS/tools/validate_keys.py --keys ../$KEYS --binaries $BIN
uv run python ../$KEYS/tools/validate_keys2.py --keys ../$KEYS --binaries $BIN
```

Scoring a harness run — `raw.json` is a list of one row per answer. Both
scorers read `id` and `got`; `score.py` also reads `expected`, `answerable`,
`question` and `type`, which `run_benchmark_http.py` copies out of the key:

```bash
python $KEYS/tools/score.py raw.json --json verdicts.json
python $KEYS/tools/citation_accuracy.py --keys $KEYS raw.json
```

`run_benchmark_http.py` writes its `raw_<mode>_<tag>.json` under
`<out-dir>/run-<run-id>/`, so give the commands that path rather than a bare
filename. Citation scoring is only meaningful for per-document runs: rows
stamped `"mode": "merged"` are refused, because a composite PDF paginates
1..N across the whole packet and the key's pages are per document.

`score.py` is deliberately conservative and defers every row it cannot decide
mechanically to a REVIEW bucket for a human to read. **A REVIEW count is not a
failure count**; the adjudication rubric it defers under is stated in the
corpus README under *Reproducing the measured results*, and in the tool's own
docstring.

Every *validator* exits non-zero on failure. The two scorers are not gates and
do not behave that way: `score.py` reports its buckets and always exits 0,
because a REVIEW is a request for a human and not a failure, and
`citation_accuracy.py` prints its ladder and exits 0 whatever the numbers are —
it exits non-zero only when it refuses to score at all, which today means a raw
file containing `--mode merged` rows. Three of the validators take a reviewed
exception set, so
that a *new* exception is the thing that fails rather than the standing ones:
`scan_person_names.py --baseline` (name-shaped strings already read and cleared
— invented place names, mostly), `validate_keys2.py --allow QID:FILE:PAGE`
(citations already adjudicated — empty as of v0.5.0, since the one pinned
citation no longer flags), and `validate_keys.py --allow-unverifiable
QID:FILE`, which extends a set pinned in the tool itself. Widening any of the
three is a visible diff.

The tools carry 185 unit tests in five files — `test_citation_accuracy.py`
(the citation scorer's document attribution, outcome ladder, and its refusal to
score composite-document rows), `test_score.py` (the answer scorer, against the
wrong-verdict patterns a real run produced, plus the fabrication gap it does
*not* close), `test_run_benchmark_http.py` (the harness's pure functions:
argument defaults, question selection, the abstention vocabulary, the routing
derivation, and the row shape the scorers read), `test_backend_contract.py`
(the five backend symbols `validate_keys.py` depends on), and
`test_validator_failure_paths.py` (each validator against a planted defect). CI
runs the directory, so a new `test_*.py` here needs no workflow change. Only
`test_*.py` files are collected *as test modules*; the tools themselves are
imported by those tests, which is how the two scorers and the harness are
covered without any of them being run by CI.

```bash
cd backend && uv run --with pytest pytest ../benchmarks/corpus/CSU-NSF-001/tools/ -q
```

`test_validator_failure_paths.py` runs each tool as a subprocess. It uses the
backend environment where that is enough and falls back to the same ephemeral
environment the workflow uses for the pypdf-only tools, so `uv` must be on
`PATH`.

## Running a corpus against a deployment

`CSU-NSF-001/tools/run_benchmark_http.py` is the harness that produced the
*Measured results* tables in that corpus's README. It logs in, uploads the
packet, waits for ingestion, asks the corpus's own questions over
`POST /api/chat`, and records what the server said it did while answering —
the `context_notice` and `context_budget` chunks, and so which model actually
served each request — not just the answer text.

It is a **manual** tool. It needs a running deployment with a registered model,
it uploads documents and builds a knowledge base there, and a full pass costs
real GPU minutes, so nothing under `.github/workflows/` invokes it — the corpus
job above runs the validators and the unit tests, and the unit tests include
`test_run_benchmark_http.py`, which covers everything in the harness that does
not need a network. That is the same shape as the backend's tier-3
`INTEGRATION_LLM` suite, which is off the pull-request path but not out of CI:
`.github/workflows/integration-llm.yaml` runs it on demand and on a weekly
cron. The corpus README's *Reproducing the measured results* has the full
sequence, the credentials it reads from the environment, and what a run costs.

The keys remain the contribution: any harness that produces rows per question
can be scored with `tools/score.py` and `tools/citation_accuracy.py` instead.
