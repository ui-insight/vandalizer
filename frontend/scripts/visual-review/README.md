# Vandalizer visual and UX review harness

Deterministic Playwright capture of the real React UI with synthetic API fixtures. Each state produces a PNG, an accessible-tree snapshot, and axe findings. `manifest.json` records viewports, horizontal overflow, browser errors, fixture misses, and interaction observations.

The rubric and section grades in `scorecard.json` are authored after screenshot inspection and interaction review. They are **not automatically generated scores**. Re-running screenshots does not regrade the product.

## Run

From `frontend`, install the repository dependencies and browser:

```bash
npm ci
npx playwright install chromium
npx vite build --outDir /private/tmp/vandalizer-visual-review-build
npx vite preview --outDir /private/tmp/vandalizer-visual-review-build --host 127.0.0.1 --port 5181 --strictPort
```

In another terminal, still in `frontend`:

```bash
REVIEW_BASE_URL=http://127.0.0.1:5181 \
REVIEW_OUTPUT=../artifacts/visual-review/new-run \
node scripts/visual-review/run.mjs
```

Use a new output directory for every run. `REVIEW_CHROMIUM=/absolute/path/to/chromium` optionally selects an existing browser executable. The September 25 review used the locally cached Chromium headless shell build 1223 because the default Playwright browser was not installed.

Prefer a production preview. Development StrictMode currently leaves `KBValidationPanel`'s `mountedRef` false after effect cleanup, so validation can remain in its loading state even with a completed fixture result. No product code is patched or bypassed by this harness.

For a targeted run, set `REVIEW_ONLY` to comma-separated scenario names:

```bash
REVIEW_ONLY=wizard-keyboard,chat-upload,validation-results \
REVIEW_BASE_URL=http://127.0.0.1:5181 \
REVIEW_OUTPUT=../artifacts/visual-review/recheck \
node scripts/visual-review/run.mjs
```

Available scenario names are the `scene(...)` calls in `run.mjs`. The full run also includes baseline, empty and mobile states. Main desktop viewport is 1440×1000; mobile is 390×844. Screenshots are full-page: a wider PNG on mobile is evidence of document overflow. Animations are disabled for capture; some in-product demo illustrations may consequently show an intermediate frame.

## Build the report

After reviewing the screenshots, revise the rubric, evidence references, findings and commit in `scorecard.json`, then run:

```bash
node scripts/visual-review/build-report.mjs \
  ../artifacts/visual-review/2026-09-25 \
  ../artifacts/visual-review/2026-09-25-production
```

The first directory receives `index.html`, `report.md` and `review-summary.json`. Later directories supplement earlier evidence; repeated state names use the later capture. The report builder rejects a changed commit, missing evidence, fixture misses, uncaught page errors or blocked scenes. Keep the evidence directories together so relative links work.

Optional rendered report verification:

```bash
node scripts/visual-review/verify-report.mjs \
  ../artifacts/visual-review/2026-09-25/index.html
```

## What is and is not verified

- API traffic matching `/api/` is intercepted; unknown endpoints receive 501 and fail the run. No backend is required. Use only a local target. Requests for Vite source modules such as `/src/api/auth.ts` continue normally.
- Synthetic account, team, documents, projects, folder-watch automation, KB sources, validation responses, library/catalog and chat/tool streams cover the requested frontend surfaces.
- User actions exercise file selection, wizard progression, keyboard behavior, file upload success/failure, KB attachment, and agent approval/completion/error presentation.
- The original baseline recorded upload and wizard defects as observations. Upgrade runs now enforce both as failing regression assertions. A successful capture exit is not a product quality pass.
- Screenshot grades, accessibility findings, and reproduction steps are separate evidence. Axe node counts include repeats across states; a clean axe result would not establish full accessibility.
- No model, retrieval, ingestion, agent execution, real automation, permissions, security, or production data is tested. Validation scores and chat answers are fixtures. Source citation accuracy and optimizer apply/revert are outside this review.
- Local storage is reset on navigation for independent scenarios, and the guided-tour overlay is dismissed. The basic first-session chat screen is reviewed separately.

## Published September 25 evidence

- Core run: 53 states on the development server, commit `560ccd5`.
- Production recheck: 8 captures, including 2 additional validation states and repeat checks of chat upload and wizard keyboard behavior. Both workflow defects reproduce in the production build.
- Published set: 55 distinct states / 61 capture executions; zero fixture misses or uncaught page errors in those two runs.
- No product UI changes were made. The generated scores describe this commit and reviewed fixture states only.


## Upgrade implementation evidence

The original scorecard and published baseline remain unchanged. The first implementation pass is recorded in `artifacts/visual-review/upgrade-review`, including working grades, limitations, a before/after gallery and the exact source/fixture fingerprints for each included run. The 8/10 acceptance target is still open.

After building and serving the production preview, set `REVIEW_BUILD=production`, `REVIEW_BASE_URL` and a fresh `REVIEW_OUTPUT`, then run `run.mjs` for the main suite or `responsive.mjs` for the five-width matrix and narrow dialogs. `REVIEW_ONLY` filters named main-suite scenes. Never reuse a baseline output directory.

Rebuild the first-pass report from its preserved captures with `python3 artifacts/visual-review/upgrade-review/build.py` from the repository. It checks artifact paths, completed runs, overflow and the latest axe results before generating the gallery. Later capture IDs supersede earlier duplicates; each run's source fingerprint remains visible rather than pretending all screenshots came from one build.


### Follow-up interaction coverage

`journeys.mjs` asserts automation save failure/retry/reopen, partial deletion and retry of only failed files, validation completion across tab switches, stored question evidence, Library type/view filtering with keyboard activation, valid citation previews, first-session upload scope/evidence and agent cancellation. `files-mobile.mjs` checks 320px/390px folder-name space, bulk-action bounds and clearing selection. They use the same `REVIEW_BASE_URL`, `REVIEW_OUTPUT`, `REVIEW_BUILD` and `REVIEW_CHROMIUM` variables as `run.mjs`.

The latest combined report is generated with `python3 artifacts/visual-review/upgrade-review/build.py` from the repository root. Its explicit run list preserves earlier evidence and lets later captures supersede matching IDs. It fails on missing evidence, unmatched API requests, page errors, overflow or axe findings in the selected captures. Grades remain manually authored after inspection.

### Recovery review (September 26)

`recovery.mjs` exercises catalog save failure/retry, an already-saved reference, opening the saved artifact, KB adoption failure/retry, proposed → applied → reverted optimization settings, regression acknowledgment, and interrupted chat with partial artifacts preserved through retry. Chat uses a controlled open NDJSON stream with real reader/abort handling; no backend action is executed.

`recovery-layout.mjs` checks long catalog details and retained search context, save dialogs, apply-review actions and expanded provenance at 320×568, 768×600 and 1440×900. It asserts primary controls can scroll into the viewport. The reviewed apply/revert operations use fixture responses; real optimizer changes remain unverified.

Run both against a fresh production build with the same environment variables above and separate new output directories. Inspect screenshots and axe files before adding a successful run to the report. A successful browser exit checks interaction assertions, errors, unknown API requests and page overflow; the report builder additionally rejects axe findings. Preserve earlier blocked/contrast-failing runs as diagnostic evidence.

### Wizard continuation (September 28)

`wizard-continuation.mjs` covers name/field guidance, folder filter retention across trigger changes, folder/API/schedule review, long action names, selected picker state, no-results recovery, picker load failure/retry, nested picker Escape, schedule preview failure/retry, and the API editor endpoint/key guidance with Python/cURL examples. It captures at 320×568, 768×600, 1440×900 and targeted 390×844 recovery states. Every capture rejects page overflow and axe findings; final controls must fit after scrolling. Use `REVIEW_BUILD=production`, a fresh `REVIEW_OUTPUT`, `REVIEW_BASE_URL`, and optional `REVIEW_CHROMIUM` as above.

This script adds local route fixtures for action search and schedule previews; it never creates a real automation. Component tests separately assert that only the active trigger configuration is submitted, invalid output requirements prevent creation, the default workflow output format is supported, and old schedule previews disappear immediately when timing changes. Full API credential use, actual scheduled execution, M365 setup, and complete assistive-technology journeys remain outside this pass.
