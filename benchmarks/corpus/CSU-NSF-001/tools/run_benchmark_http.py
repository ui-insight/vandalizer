#!/usr/bin/env python3
"""Run CSU-NSF-001 against a deployment over the product's real HTTP path.

This is the harness that produced the *Measured results* tables in the corpus
README. It does what a person does in the UI — log in, upload the packet, wait
for ingestion, then ask the corpus's own 30 questions with the packet attached —
and records what the **server said it did** while answering, not just the
answer text. Its output feeds `score.py` and `citation_accuracy.py` unchanged.

    NOT A CI TOOL. It needs a running Vandalizer instance with at least one
    registered model, it uploads documents and builds a knowledge base in that
    instance, and a full pass costs real GPU minutes. It is a manual
    integration tool in the same sense as the tier-3 `INTEGRATION_LLM` suite,
    and nothing in `.github/workflows/` invokes it.

Why the control chunks are recorded, and why that is the point
-------------------------------------------------------------
A document that never reached the model still streams a confident answer, and
the stream gives no hint: the answer looks the same either way. So every row
carries the server's own `context_notice` and `context_budget` chunks —
whether a document was dropped, whether the packet overflowed the budget,
and **which model actually served the request**. On the published run four of
five requested models never answered anything in attach mode; the request was
routed to the long-document model and only these fields say so.

Where the documents come from, and why not from a directory
-----------------------------------------------------------
Files are read straight out of the release tarball named in `manifest.json`,
after that tarball's sha256 is verified against the manifest. Nothing is
uploaded from a loose directory. This is not ceremony: an older release of this
corpus carries a retired budget total, and a stale PDF sitting in a working
directory would quietly fail a third of the questions for a reason that reads
exactly like a model error.

Credentials
-----------
Read from the environment — `VANDALIZER_URL`, `VANDALIZER_USER`,
`VANDALIZER_PASS` — or from a `KEY=VALUE` file passed with `--env-file`, which
should live outside the repository. They are never printed and never written to
the run directory. Use a benchmark account, not your own: this uploads 16
documents and creates a knowledge base.

Usage
-----
    export VANDALIZER_URL=http://localhost:8001
    export VANDALIZER_USER=... VANDALIZER_PASS=...

    # ingest and verify only; ask nothing, spend no GPU time
    uv run --with requests python \\
      benchmarks/corpus/CSU-NSF-001/tools/run_benchmark_http.py \\
      --assets-dir /tmp/corpus-assets --mode attach --preflight-only

    # one scored pass
    uv run --with requests python \\
      benchmarks/corpus/CSU-NSF-001/tools/run_benchmark_http.py \\
      --assets-dir /tmp/corpus-assets --mode attach --model <tag> \\
      --repeat 3 --warmup --run-id 20260101T000000Z

`--mode merged` and citation scoring
------------------------------------
`merged` attaches one composite PDF of the same packet, to separate "many
documents" from "much text". Answer scoring works on those rows. **Citation
scoring does not**: the composite paginates 1..N continuously, so a cited page
does not correspond to any page the key lists per document, and there is no
ground truth in the shipped key for that mapping. `citation_accuracy.py`
refuses rows stamped `"mode": "merged"` with a non-zero exit rather than
producing numbers that look fine and are not. `merged` was never used for a
published table.

What differs from the harness that produced the published evidence
------------------------------------------------------------------
This is a port, and a run of it will not diff clean against
`evidence/corpus-v050-*`. Every difference, so nobody has to work them out:

* **Machine-specific paths and secrets removed.** Hardcoded home directories,
  a fixed Mongo container name, a credentials file at a fixed path, and a
  16-entry per-file digest table all became flags, environment variables, and
  a single verified tarball. Nothing else about what is asked changed.
* **Model inventory and routing come over HTTP** (`/api/config/models`, and
  `/api/admin/config` behind `--admin-config`) instead of reading the
  deployment's database directly. Consequence: `meta.model_config` has no
  `temperature` — that endpoint does not expose one. The per-model temperature
  is still recorded as the row's `temperature_config` when `--admin-config` is
  passed.
* **Page truth is gone.** `page_texts()`, `resolve_page_truth()` and the row's
  `truth_pages` column needed `SmartDocument.text_markers`, which is on no HTTP
  response. Neither scorer reads them; `citation_accuracy.py` scores against
  the key's own `sources` / `corroborating_sources`. It is why `merged` cannot
  be citation-scored — see above.
* **Renamed keys.** `diag.expected_figures` → `diag.key_figures`, and
  `meta.digital_tarball_sha256` → `meta.digital_asset_sha256`. `key_figures`
  also changed meaning: it now normalises the key answer and applies
  `score.py`'s identifier lookbehind, so `CSU-RSP-204` no longer contributes a
  required figure `204`.
* **`routed` has three states, not two.** `null` means "not derivable" — see
  the derivation at the row build for why that is not the same as `false`. The
  published evidence has only `true`/`false`, because a Mongo read always
  supplied a default model to compare against.
* **`meta.started_utc` is now populated.** The original always wrote `null`
  there.
* **Text chunks of kind `content` and `delta` are no longer accepted.**
  `chat_service` emits only `text`; the other two were dead branches.
* **A 15 s pause before a 401 re-login**, which the original did not have.
  Login is rate-limited per address, and an immediate retry earns a 429 on top
  of the expiry.
* **`_ABSTAIN` is byte-identical to the original** and is meant to stay that
  way — see the comment on it.

See the corpus README, *Reproducing the measured results*, for the full
sequence and for what the run costs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:                                        # pragma: no cover
    sys.exit("this tool needs `requests`: "
             "uv run --with requests python <this file> ...")

#: The tool sits in the corpus's `tools/`, so the keys are its own parent.
KEYS_DEFAULT = Path(__file__).resolve().parent.parent

WARMUP_QUESTION = "What is the title of this proposal?"

#: Modes and the document set each one needs. `merged` is a single composite
#: PDF of the same packet, used to separate "many documents" from "much text";
#: it is not a release asset, so it is supplied by path and its digest is
#: recorded rather than pinned.
DOCSET_FOR_MODE = {"attach": "digital", "kb": "digital", "merged": "merged"}


# --------------------------------------------------------------------------
# Environment / session
# --------------------------------------------------------------------------


def load_credentials(env_file: Path | None, url_override: str | None) -> dict:
    """URL/user/password from the environment, optionally seeded from a file.

    The file is `KEY=VALUE` per line, `#` comments allowed. Values already in
    the environment win, so a shell export can override a stale file.
    """
    values = {}
    if env_file:
        if not env_file.exists():
            sys.exit(f"--env-file {env_file} does not exist")
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    for key in ("VANDALIZER_URL", "VANDALIZER_USER", "VANDALIZER_PASS"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    if url_override:
        values["VANDALIZER_URL"] = url_override
    values.setdefault("VANDALIZER_URL", "http://localhost:8001")
    missing = [k for k in ("VANDALIZER_USER", "VANDALIZER_PASS")
               if not values.get(k)]
    if missing:
        sys.exit(f"missing credential(s): {', '.join(missing)} — set them in "
                 f"the environment or pass --env-file")
    return values


def relax_secure_cookies(session: requests.Session, url: str) -> None:
    """Let this session's cookies travel over plain http.

    An instance configured for production sets `Secure` on the auth and CSRF
    cookies, and `requests` then refuses to send them over `http://` — which is
    how you reach an instance directly, behind whatever terminates TLS. This is
    a client-side relaxation only and is skipped for an https URL.
    """
    if url.startswith("https://"):
        return
    for cookie in session.cookies:
        cookie.secure = False


def sync_csrf(session: requests.Session) -> str | None:
    """Mirror the CSRF cookie into the header (double-submit).

    Re-read before every write rather than cached once: the middleware may
    rotate the cookie, and a stale header is a 403 halfway through a run.
    """
    for name in ("__Host-csrf_token", "csrf_token"):
        token = session.cookies.get(name)
        if token:
            session.headers["X-CSRF-Token"] = token
            return token
    return None


def login(session: requests.Session, creds: dict) -> dict:
    try:
        response = session.post(
            f"{creds['VANDALIZER_URL']}/api/auth/login",
            json={"user_id": creds["VANDALIZER_USER"],
                  "password": creds["VANDALIZER_PASS"]},
            timeout=30)
    except requests.RequestException as error:
        # The first failure a reader following the README hits is a URL that
        # points at nothing. A fourteen-line urllib3 traceback reads like a bug
        # in the tool; every other pre-flight failure here exits with one line,
        # and so does this one. The password is never in the message.
        sys.exit(f"cannot reach {creds['VANDALIZER_URL']} — "
                 f"{type(error).__name__}: {error}\n"
                 f"  check VANDALIZER_URL (or --url) and that the instance is "
                 f"up and reachable from here.")
    if response.status_code in (401, 403):
        sys.exit(f"login rejected by {creds['VANDALIZER_URL']} "
                 f"(HTTP {response.status_code}) — check VANDALIZER_USER and "
                 f"VANDALIZER_PASS")
    response.raise_for_status()
    relax_secure_cookies(session, creds["VANDALIZER_URL"])
    if not sync_csrf(session):
        print("warning: no CSRF cookie after login — writes will likely 403")
    return response.json()


# --------------------------------------------------------------------------
# Model inventory — over HTTP, no database access
# --------------------------------------------------------------------------


def registered_models(session: requests.Session, url: str) -> list[dict]:
    """[{tag, name, context_window}] for the models this instance offers."""
    response = session.get(f"{url}/api/config/models", timeout=60)
    response.raise_for_status()
    return [{"tag": m.get("tag"), "name": m.get("name"),
             "context_window": m.get("context_window")}
            for m in response.json()]


def routing_config(session: requests.Session, url: str) -> dict | None:
    """Which model is the default and which handles long documents.

    Only an administrator can read this, so it is opt-in (`--admin-config`).
    Without it the run still records what the server *did* — `plan.model` names
    the model that actually answered — it just cannot print the configuration
    that explains why. Three keys are taken from the response; the rest of it,
    which includes masked credential fields, is never stored or printed.

    Every failure here degrades to `None`. This is an optional diagnostic, and
    an instance that answers 401, 404 or 500 on an admin endpoint must not kill
    a run that has already paid for ingestion.
    """
    try:
        response = session.get(f"{url}/api/admin/config", timeout=60)
    except requests.RequestException as error:
        print(f"  --admin-config: {type(error).__name__} reading "
              f"/api/admin/config; routing configuration not recorded")
        return None
    if response.status_code != 200:
        print(f"  --admin-config: HTTP {response.status_code} from "
              f"/api/admin/config (403 means this account is not an "
              f"administrator); routing configuration not recorded")
        return None
    body = response.json()
    return {"default_model": body.get("default_model"),
            "long_document_model": body.get("long_document_model"),
            "temperatures": {m.get("tag"): m.get("temperature")
                             for m in (body.get("available_models") or [])
                             if isinstance(m, dict)}}


# --------------------------------------------------------------------------
# Corpus assets
# --------------------------------------------------------------------------


def load_key(keys_dir: Path) -> tuple[dict, dict]:
    """(manifest, ground truth), cross-checked so they cannot drift apart."""
    manifest = json.loads((keys_dir / "manifest.json").read_text())
    truth = json.loads((keys_dir / "ground_truth.json").read_text())
    if manifest.get("version") != truth.get("version"):
        sys.exit(f"manifest is v{manifest.get('version')} but ground_truth.json "
                 f"is v{truth.get('version')} — refusing to run against a "
                 f"mismatched key")
    return manifest, truth


def digital_asset(manifest: dict) -> dict:
    """The manifest entry for the tarball holding `pdf/` and `source/`."""
    for asset in (manifest.get("release_assets") or {}).get("assets", []):
        if "pdf/" in (asset.get("contents") or []):
            return asset
    sys.exit("manifest release_assets lists no asset containing pdf/")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def documents_from_release(manifest: dict, assets_dir: Path) -> dict[str, bytes]:
    """{filename: bytes} for the PDFs, read out of the verified tarball.

    The manifest pins the archive, so the archive is what gets checked; the
    members are then whatever that verified archive contains, which is a
    stronger guarantee than a second list of per-file digests that can go stale
    against it. `system_input_files` decides which members are the packet — the
    workbooks in it are supplied to a system under test as spreadsheets, and
    the published run attached the 16 PDFs only.
    """
    asset = digital_asset(manifest)
    path = assets_dir / asset["name"]
    if not path.exists():
        sys.exit(f"missing {path} — download the release asset listed in "
                 f"manifest.json (tag {manifest['release_assets'].get('tag')})")
    digest = sha256_file(path)
    if digest != asset["sha256"]:
        sys.exit(f"{asset['name']} sha256 {digest}\n"
                 f"  manifest pins  {asset['sha256']}\n"
                 f"refusing to run: this is not the release the key was "
                 f"written against.")
    print(f"  {asset['name']}: sha256 verified against manifest")

    wanted = [name for name in manifest["system_input_files"]
              if name.lower().endswith(".pdf")]
    blobs: dict[str, bytes] = {}
    with tarfile.open(path, "r:gz") as archive:
        members = {Path(m.name).name: m for m in archive.getmembers()
                   if m.isfile() and m.name.startswith("pdf/")}
        for name in wanted:
            member = members.get(name)
            if member is None:
                sys.exit(f"{asset['name']} has no pdf/{name}, which "
                         f"manifest.system_input_files requires")
            blobs[name] = archive.extractfile(member).read()
    print(f"  {len(blobs)}/{len(wanted)} packet PDFs read from the archive")
    return blobs


def questions_for(truth: dict, selection: str) -> list[dict]:
    questions = truth["questions"]
    if selection == "all":
        return questions
    wanted = {q.strip() for q in selection.split(",")}
    chosen = [q for q in questions if q["id"] in wanted]
    missing = wanted - {q["id"] for q in chosen}
    if missing:
        sys.exit(f"unknown question id(s): {sorted(missing)}")
    return chosen


# --------------------------------------------------------------------------
# Answer diagnostics — observations, never verdicts
# --------------------------------------------------------------------------

#: Typographic characters models emit where the key has ASCII.
#: Written as escapes rather than glyphs on purpose: nobody can tell U+00A0
#: from U+2009 by looking, and a plain space typed into this table would
#: silently fold nothing.
_UNICODE_FOLD = {
    "\u2018": "'", "\u2019": "'",          # single quotation marks
    "\u201c": '"', "\u201d": '"',          # double quotation marks
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-",          # hyphens, en and em dashes
    "\u00a0": " ", "\u2007": " ",          # no-break space, figure space
    "\u2009": " ", "\u202f": " ",          # thin, narrow no-break space
    "\u200b": "",                          # zero-width space
}


def normalize(text: str) -> str:
    for src, dst in _UNICODE_FOLD.items():
        text = text.replace(src, dst)
    return text


def strip_md(text: str) -> str:
    return re.sub(r"[*_`]+", "", text)


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[float]:
    """Every number as a float — 58, 58.0 and "58 %" are one fact."""
    out = set()
    for match in _NUMBER.finditer(text):
        try:
            out.add(float(match.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


_PAGE = re.compile(
    r"(?:pages?|pp?)\.?\s*~?\s*(\d{1,3}(?:\s*(?:-|–|to|and|,|&)\s*~?\d{1,3})*)",
    re.I)
_PAGE_RUN = re.compile(r"\d{1,3}")


def pages_in(text: str) -> list[int]:
    """Every page number cited, ranges and lists expanded.

    "pp. 1-2" is two citations and "pages 20 and 21" is two citations; taking
    only the first number silently discards the one that was right.
    """
    out: set[int] = set()
    for group in _PAGE.findall(text):
        numbers = [int(n) for n in _PAGE_RUN.findall(group)]
        if len(numbers) == 2 and re.search(r"-|–|to", group):
            low, high = sorted(numbers)
            if high - low <= 20:
                out.update(range(low, high + 1))
                continue
        out.update(numbers)
    return sorted(n for n in out if n <= 200)


#: Ways an answer says "this is not in the documents", for the `abstained`
#: diagnostic column. **Verbatim from the harness that produced the published
#: evidence** — every branch below is one the audit read, and the column is only
#: comparable across runs if the vocabulary does not move under it. Replayed
#: over all 900 published rows this agrees with `score.py`'s `REFUSAL` on
#: 830/900; a narrower copy of it agreed on 819, which is how the fidelity of
#: this constant is checked (`test_run_benchmark_http.py`).
#:
#: It is deliberately *not* `score.py`'s `REFUSAL`, and the two are not
#: interchangeable: `REFUSAL` decides verdicts and may widen whenever the audit
#: finds a phrasing it missed, while this one is a diagnostic pinned to the
#: published run. `score.py` is the authority on whether a row declined; this
#: column is a sorting aid for the human pass. Where they disagree, `score.py`
#: wins by construction — nothing reads `abstained` to produce a verdict.
_ABSTAIN = re.compile(
    r"(do(es)? ?n[o']?t (contain|specify|state|provide|include|mention|list"
    r"|define|give|appear)"
    r"|(is|are|was|were) ?n[o']?t (specified|stated|provided|mentioned|included"
    r"|listed|given|defined|applied|present|available|discussed|found)"
    r"|^\s*[-*\s]*not (applied|applicable|specified|stated|provided|included"
    r"|listed|given)"
    r"|:\s*not (applied|applicable|specified|stated|provided|included|listed"
    r"|given)"
    r"|not (found|present|available|defined|applied|discussed|addressed"
    r"|included) in"
    r"|no \w+(\s+\w+)? (is|are|was|were) (included|listed|provided|given"
    r"|mentioned|specified)"
    r"|no (mention|reference|information|indication|record|data|entry|entries"
    r"|line items?|subaward|off.campus|orcid|budget|figure|value|such)"
    r"|there (is|are|was|were) no|isn'?t (any|listed)"
    r"|cannot (find|locate|determine|be determined)"
    r"|unable to (find|locate|determine)"
    r"|(could|can|do|did)( ?n[o']?t| not) (find|locate|determine|see|identify)"
    r"|does not exist|do not exist|no such|nothing in the (document|text))",
    re.I | re.M)

#: Reasoning emitted as the answer body — every fact right, the output
#: unusable. The server routes real `<think>` blocks to `thinking` chunks, so
#: anything caught here leaked past that as plain prose. Recorded, never
#: stripped: `got` stays verbatim so the scorers see what a user would see.
_THINK_LEAK = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?\s*thinking(?:\s+process)?\s*(?:\*\*)?\s*[:\n]"
    r"|</?think(?:ing)?>",
    re.I | re.M)

_STRIP_NUM = re.compile(r"[,$\s]")
_FIGURE = re.compile(r"(?<![A-Za-z0-9-])\$?\d[\d,]*\.?\d*%?")


def key_figures(expected: str) -> list[str]:
    """Figure tokens in the key answer, by `score.py`'s token rule.

    The token pattern, the identifier lookbehind and the three-character
    minimum are `score.py`'s `figures()` verbatim. Two things are *not* the
    same and must not be read as such: this folds Unicode punctuation but does
    not strip markdown (no key answer contains `*`, `_` or a backtick, so it
    makes no difference on the shipped key), and it runs over the whole key
    answer rather than `score.py`'s decisive clause. This is a diagnostic —
    "which of the key's numbers appear anywhere in the answer" — not the
    required set. `score.py` decides what is required.
    """
    text = normalize(expected or "")
    out = []
    for match in _FIGURE.finditer(text):
        trailing = text[match.end():match.end() + 1]
        if trailing and (trailing.isalnum() or trailing == "-"):
            continue
        token = match.group(0).rstrip(".")
        if len(token.strip("$%.,")) >= 3:
            out.append(token)
    return out


def derive_routed(served: str | None, requested: str | None,
                  actions: list[str]) -> bool | None:
    """Did the request end up on a different model than the one asked for?

    Three states, and `None` is not `False`. `None` means *unknown*: with
    neither `--model` nor `--admin-config` there is no `requested` value to
    compare `served` against, and a diagnostic that degrades to the reassuring
    answer is worse than one that says it cannot tell. `model_served` — the
    field the published routing finding was actually derived from — is
    recorded either way.

    `model_routed` settles it upward whatever else is known. Its absence
    settles nothing: `model_not_routed` is not emitted for the long-document
    model itself, so the plan's model is the authority and the notice only ever
    confirms it.
    """
    if "model_routed" in actions:
        return True
    if served and requested:
        return served != requested
    return None


def diagnostics(answer: str, expected: str) -> dict:
    """Structural observations that make the adjudication pass cheap.

    Deliberately not a verdict: `score.py` and `citation_accuracy.py` decide,
    and a human decides the rows they defer. These are the measurements that
    let a reviewer sort 900 rows without re-reading all of them.
    """
    clean = strip_md(normalize(answer or ""))
    numbers = numbers_in(clean)
    want = key_figures(expected or "")
    found = []
    for token in want:
        try:
            if float(_STRIP_NUM.sub("", token).rstrip("%")) in numbers:
                found.append(token)
        except ValueError:
            continue
    return {
        "key_figures": want,
        "figures_found": found,
        "figures_all_present": bool(want) and len(found) == len(want),
        "pages_named": pages_in(clean),
        "abstained": bool(_ABSTAIN.search(clean)),
        "thinking_leak": bool(_THINK_LEAK.search(answer or "")),
        "answer_chars": len(answer or ""),
    }


# --------------------------------------------------------------------------
# Run state — so five model passes do not each pay for ingestion
# --------------------------------------------------------------------------


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {"docsets": {}, "knowledge_bases": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


# --------------------------------------------------------------------------
# Upload / ingest
# --------------------------------------------------------------------------


def create_folder(session: requests.Session, url: str, name: str) -> str:
    sync_csrf(session)
    response = session.post(f"{url}/api/folders/create",
                            json={"name": name, "parent_id": "0",
                                  "folder_type": "individual"},
                            timeout=60)
    response.raise_for_status()
    return response.json()["uuid"]


def upload(session: requests.Session, url: str, filename: str, blob: bytes,
           folder: str) -> dict:
    body = {
        "contentAsBase64String": base64.b64encode(blob).decode(),
        "fileName": filename,
        "extension": Path(filename).suffix.lstrip("."),
        "folder": folder,
    }
    sync_csrf(session)
    response = session.post(f"{url}/api/files/upload", json=body, timeout=600)
    response.raise_for_status()
    return response.json()


def wait_ready(session: requests.Session, url: str, uuid: str,
               timeout: int = 1800) -> dict:
    """Poll until extraction and ingestion finish; return the final status."""
    start = time.time()
    last = ""
    while time.time() - start < timeout:
        response = session.get(f"{url}/api/documents/poll_status",
                               params={"docid": uuid}, timeout=30)
        if response.status_code == 404:
            time.sleep(3)
            continue
        response.raise_for_status()
        status = response.json()
        state = status.get("status") or ""
        if state != last:
            print(f"      {uuid[:8]} … {state}")
            last = state
        if status.get("complete") or state in ("complete", "error"):
            return status
        time.sleep(5)
    return {"status": "timeout", "complete": False}


def ingest(session: requests.Session, url: str, docset: str,
           blobs: dict[str, bytes], state_path: Path, label: str) -> dict:
    """Upload whatever this docset has not ingested yet; return {name: uuid}.

    Keyed by (docset, filename) so the packet and the composite keep distinct
    uuid sets, and so a second model pass re-uses the first pass's documents
    instead of paying for ingestion again.
    """
    state = load_state(state_path)
    uploads = dict(state["docsets"].get(docset) or {})
    todo = [name for name in blobs if name not in uploads]
    if uploads:
        print(f"  already ingested ({docset}): {len(uploads)}")
    if not todo:
        print("  nothing new to upload")
        return uploads

    folder = create_folder(session, url, f"{label}-{docset}")
    print(f"  folder {folder[:8]} '{label}-{docset}'")
    print(f"  uploading + ingesting {len(todo)} file(s) …")
    for name in sorted(todo):
        result = upload(session, url, name, blobs[name], folder)
        uuid = (result.get("uuid") or result.get("document_uuid")
                or (result.get("document") or {}).get("uuid"))
        if not uuid:
            print(f"    {name}: upload returned no uuid: {str(result)[:200]}")
            continue
        print(f"    {name[:46]:46s} -> {uuid[:8]}")
        status = wait_ready(session, url, uuid)
        if status.get("status") != "complete":
            print(f"      NOT usable: {status.get('status')} "
                  f"{str(status.get('error_message') or '')[:120]}")
            continue
        uploads[name] = uuid
        state = load_state(state_path)
        state["docsets"].setdefault(docset, {})[name] = uuid
        save_state(state_path, state)
    return uploads


def verify_ingested(session: requests.Session, url: str, uploads: dict) -> dict:
    """Every attached document must be complete with non-empty text.

    A row where a document never reached the model is not a benchmark result,
    and nothing downstream can tell: the answer reads the same either way.
    """
    report: dict = {}
    all_ok = True
    for name, uuid in sorted(uploads.items()):
        response = session.get(f"{url}/api/documents/poll_status",
                               params={"docid": uuid}, timeout=30)
        response.raise_for_status()
        status = response.json()
        chars = len(status.get("raw_text") or "")
        good = status.get("status") == "complete" and chars > 0
        report[name] = {"uuid": uuid, "status": status.get("status"),
                        "raw_text_chars": chars,
                        "low_quality": bool(status.get("extraction_low_quality")),
                        "ok": good}
        all_ok = all_ok and good
        flag = "ok " if good else "BAD"
        low = "  LOW-QUALITY" if status.get("extraction_low_quality") else ""
        print(f"    {flag} {name[:46]:46s} {str(status.get('status')):>10s} "
              f"{chars:>7d} chars{low}")
    report["_all_ok"] = all_ok
    return report


# --------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------


def kb_find(session: requests.Session, url: str, title: str) -> str | None:
    response = session.get(f"{url}/api/knowledge/list", timeout=60)
    response.raise_for_status()
    for kb in response.json():
        if kb.get("title") == title:
            return kb["uuid"]
    return None


def kb_prepare(session: requests.Session, url: str, docset: str, title: str,
               uploads: dict, state_path: Path, timeout: int = 3600) -> str:
    """Create the KB, add the packet, wait for every source to finish.

    Driven over HTTP exactly as a user would — create, add_documents, poll
    status — and re-used across model passes via the state file, so five passes
    do not each rebuild the same vector index.
    """
    state = load_state(state_path)
    kb_uuid = (state.get("knowledge_bases") or {}).get(docset)
    if kb_uuid:
        if session.get(f"{url}/api/knowledge/{kb_uuid}/status",
                       timeout=60).status_code != 200:
            kb_uuid = None
    if not kb_uuid:
        kb_uuid = kb_find(session, url, title)
    if not kb_uuid:
        sync_csrf(session)
        response = session.post(
            f"{url}/api/knowledge/create",
            json={"title": title,
                  "description": "CSU-NSF-001 benchmark packet, retrieval mode."},
            timeout=120)
        if response.status_code == 409:
            kb_uuid = kb_find(session, url, title)
            if not kb_uuid:
                sys.exit("knowledge-base title is taken but not listable — "
                         "resolve by hand or pass a different --label")
        else:
            response.raise_for_status()
            kb_uuid = response.json()["uuid"]
    print(f"  knowledge base {kb_uuid[:8]} '{title}'")

    status = session.get(f"{url}/api/knowledge/{kb_uuid}/status",
                         timeout=60).json()
    if int(status.get("total_sources") or 0) < len(uploads):
        sync_csrf(session)
        response = session.post(f"{url}/api/knowledge/{kb_uuid}/add_documents",
                                json={"document_uuids": list(uploads.values())},
                                timeout=300)
        response.raise_for_status()
        print(f"  add_documents: {response.json()}")

    start = time.time()
    last = ""
    while time.time() - start < timeout:
        status = session.get(f"{url}/api/knowledge/{kb_uuid}/status",
                             timeout=60).json()
        total = int(status.get("total_sources") or 0)
        ready = int(status.get("sources_ready") or 0)
        failed = int(status.get("sources_failed") or 0)
        line = (f"{ready}/{total} ready, {failed} failed, "
                f"{status.get('total_chunks')} chunks")
        if line != last:
            print(f"      kb … {line}")
            last = line
        if total and ready + failed >= total:
            if failed:
                sys.exit(f"knowledge base has {failed} failed source(s) — "
                         f"fix before running")
            if ready < len(uploads):
                sys.exit(f"knowledge base ready={ready} but {len(uploads)} "
                         f"documents were added")
            state = load_state(state_path)
            state.setdefault("knowledge_bases", {})[docset] = kb_uuid
            save_state(state_path, state)
            return kb_uuid
        time.sleep(10)
    sys.exit("knowledge-base ingestion timed out")


# --------------------------------------------------------------------------
# Ask
# --------------------------------------------------------------------------


def ask(session: requests.Session, url: str, question: str, *,
        document_uuids: list | None = None,
        knowledge_base_uuid: str | None = None,
        model_name: str | None = None,
        timeout: int = 900,
        relogin=None) -> dict:
    """One chat turn. Returns everything the server said, not just the text."""
    # Both fields at once puts a knowledge base *and* the full documents in the
    # prompt, competing for the same document allocation. Asserted, not merely
    # avoided: it would produce plausible numbers for a context nobody chose.
    if document_uuids and knowledge_base_uuid:
        raise AssertionError(
            "document_uuids and knowledge_base_uuid must never be sent together")
    if not document_uuids and not knowledge_base_uuid:
        raise AssertionError("nothing attached — refusing to ask")

    body: dict = {"message": question}
    if document_uuids:
        body["document_uuids"] = list(document_uuids)
        body["folder_uuids"] = []
    if knowledge_base_uuid:
        body["knowledge_base_uuid"] = knowledge_base_uuid
    if model_name:
        body["model"] = model_name

    out = {"answer": "", "error": "", "notices": [], "plan": None,
           "suggested_model": None, "usage": None, "sources": [],
           "raw": "", "ttft_s": None, "http_status": None}

    started = time.perf_counter()
    response = None
    try:
        for attempt in range(1, 6):
            sync_csrf(session)
            response = session.post(f"{url}/api/chat", json=body, stream=True,
                                    timeout=timeout)
            if response.status_code == 429:
                # Chat is rate-limited per client address and the window is per
                # minute, so waiting it out is the only thing that helps. A 429
                # recorded as a verdict would punch holes in the matrix that
                # bias against whichever model was answering fastest.
                wait = 30 * attempt
                print(f"[429 {wait}s]", end="", flush=True)
                time.sleep(wait)
                continue
            if response.status_code == 401 and relogin and attempt < 5:
                # The access token outlives about half an hour; a five-model
                # pass does not. Without this, every request after expiry is a
                # silent hole. Login is itself rate-limited, hence the pause.
                time.sleep(15)
                relogin()
                continue
            break
        out["http_status"] = response.status_code
        if response.status_code != 200:
            out["error"] = f"HTTP {response.status_code}: {response.text[:300]}"
            return out

        parts, lines = [], []
        first_token = None
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            lines.append(line)
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = chunk.get("kind")
            if kind == "text":
                if first_token is None:
                    first_token = time.perf_counter()
                parts.append(chunk.get("content", ""))
            elif kind == "context_notice":
                out["notices"].append({
                    "action": chunk.get("action"),
                    "detail": chunk.get("content"),
                    "tokens_dropped": chunk.get("tokens_dropped")})
            elif kind == "context_budget":
                out["plan"] = chunk.get("plan")
                out["suggested_model"] = chunk.get("suggested_model")
            elif kind == "sources":
                out["sources"] = chunk.get("sources") or []
            elif kind == "usage":
                out["usage"] = {k: v for k, v in chunk.items() if k != "kind"}
            elif kind == "error":
                out["error"] = str(chunk.get("content")
                                   or chunk.get("message") or chunk)[:400]
        out["answer"] = "".join(parts).strip()
        out["raw"] = "\n".join(lines)
        out["ttft_s"] = (round(first_token - started, 2)
                         if first_token else None)
    except requests.RequestException as error:
        out["error"] = f"{type(error).__name__}: {error}"
    return out


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run CSU-NSF-001 against a deployment over its chat API.")
    parser.add_argument("--mode", choices=tuple(DOCSET_FOR_MODE), default="attach",
                        help="attach: every packet document on document_uuids. "
                             "kb: the same packet as a knowledge base (vector "
                             "retrieval). merged: a single composite PDF — "
                             "answer scoring works, but merged rows must NOT "
                             "be citation-scored (its pages run 1..N across "
                             "the whole composite and do not map to the key's "
                             "per-document pages; citation_accuracy.py refuses "
                             "them).")
    parser.add_argument("--keys", type=Path, default=KEYS_DEFAULT,
                        help="corpus directory holding manifest.json and "
                             "ground_truth.json (default: this tool's own)")
    parser.add_argument("--assets-dir", type=Path,
                        help="directory holding the downloaded release "
                             "tarballs; required unless --mode merged")
    parser.add_argument("--merged", type=Path,
                        help="composite PDF for --mode merged (not a release "
                             "asset; its digest is recorded, not pinned)")
    parser.add_argument("--out-dir", type=Path, default=Path("benchmark-runs"),
                        help="where evidence directories are written "
                             "(default: ./benchmark-runs)")
    parser.add_argument("--state", type=Path,
                        help="uuid re-use state file "
                             "(default: <out-dir>/uploads-state.json)")
    parser.add_argument("--label", default="csu-nsf-001-bench",
                        help="names the folder and the knowledge base created "
                             "in the instance")
    parser.add_argument("--url", help="instance base URL "
                                      "(default: $VANDALIZER_URL)")
    parser.add_argument("--env-file", type=Path,
                        help="KEY=VALUE file holding VANDALIZER_URL / _USER / "
                             "_PASS; keep it outside the repository")
    parser.add_argument("--model", metavar="TAG",
                        help="model tag as registered on the instance. Omit "
                             "for the instance default.")
    parser.add_argument("--admin-config", action="store_true",
                        help="also record the routing configuration; needs an "
                             "administrator account")
    parser.add_argument("--repeat", type=int, default=1,
                        help="ask every question N times (the published run "
                             "used 3; run-to-run variance is about one item)")
    parser.add_argument("--pace", type=float, default=2.5,
                        help="seconds between requests; chat is rate-limited "
                             "per client address")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-request timeout. A short one turns a cold "
                             "model load into an empty answer.")
    parser.add_argument("--warmup", action="store_true",
                        help="ask one unscored throwaway first at the full "
                             "timeout and record it as cold_start — its wall "
                             "time IS the user-facing cold start, and it keeps "
                             "model ignition from holing scored item 1")
    parser.add_argument("--run-id", default=None,
                        help="share one evidence directory across model passes "
                             "(default: a fresh UTC stamp)")
    parser.add_argument("--questions", default="all",
                        help="'all' or a comma-separated list of question ids")
    parser.add_argument("--preflight-only", action="store_true",
                        help="upload, ingest, verify, write the state file, "
                             "ask nothing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    docset = DOCSET_FOR_MODE[args.mode]

    manifest, truth = load_key(args.keys)
    questions = questions_for(truth, args.questions)
    print(f"corpus  : {manifest.get('case_id')} v{manifest.get('version')}  "
          f"({len(questions)} question(s) of {len(truth['questions'])})")
    print(f"mode    : {args.mode}  (docset {docset})")

    print("corpus assets:")
    if args.mode == "merged":
        if not args.merged or not args.merged.exists():
            sys.exit("--mode merged needs --merged pointing at the composite PDF")
        blobs = {args.merged.name: args.merged.read_bytes()}
        merged_digest = sha256_bytes(blobs[args.merged.name])
        print(f"  {args.merged.name}: sha256 {merged_digest[:16]}… "
              f"(recorded, not pinned — the composite is not a release asset)")
    else:
        if not args.assets_dir:
            sys.exit("--assets-dir is required: point it at the directory "
                     "holding the release tarballs named in manifest.json")
        blobs = documents_from_release(manifest, args.assets_dir)
        merged_digest = None

    creds = load_credentials(args.env_file, args.url)
    url = creds["VANDALIZER_URL"].rstrip("/")
    session = requests.Session()
    me = login(session, creds)
    print(f"instance: {url}")
    print(f"logged in as {me.get('user_id')}\n")

    models = registered_models(session, url)
    by_tag = {m["tag"]: m for m in models if m.get("tag")}
    model = None
    if args.model:
        model = by_tag.get(args.model)
        if not model:
            sys.exit(f"unknown model tag {args.model!r}; this instance "
                     f"registers {sorted(by_tag)}")
    print(f"models  : {len(models)} registered "
          f"({', '.join(sorted(by_tag))})")
    routing = routing_config(session, url) if args.admin_config else None
    if routing:
        print(f"routing : default={routing['default_model']} "
              f"long_document={routing['long_document_model']}")
    if not model and not (routing or {}).get("default_model"):
        # There is nothing to compare the served model against, so `routed`
        # will be null on every row unless the server volunteers a
        # `model_routed` notice. Said once here rather than discovered in the
        # rows afterwards.
        print("routing : cannot be derived — no --model and no readable "
              "default_model; rows will record routed=null unless the server "
              "emits a model_routed notice. model_served is recorded either "
              "way. Pass --admin-config from an administrator account to "
              "resolve it.")
    if model:
        print(f"asking  : {model['tag']} -> {model['name']} "
              f"(context window {model['context_window']})")

    state_path = args.state or (args.out_dir / "uploads-state.json")

    print("\ningestion:")
    uploads = ingest(session, url, docset, blobs, state_path, args.label)
    if len(uploads) != len(blobs):
        sys.exit(f"only {len(uploads)}/{len(blobs)} documents ingested — stopping")
    print("verifying extracted text:")
    ingest_report = verify_ingested(session, url, uploads)
    if not ingest_report["_all_ok"]:
        sys.exit("at least one document is not complete with non-empty text")

    kb_uuid = None
    if args.mode == "kb":
        print("knowledge base:")
        kb_uuid = kb_prepare(session, url, docset,
                             f"{args.label} knowledge base", uploads, state_path)

    run_id = args.run_id or utc_stamp()
    root = args.out_dir / f"run-{run_id}"
    (root / "answers").mkdir(parents=True, exist_ok=True)
    (root / "streams").mkdir(parents=True, exist_ok=True)
    tag = model["tag"] if model else "default"
    stem = f"{args.mode}_{tag}"
    print(f"\nrun {run_id} -> {root}")
    (root / "uploads.json").write_text(json.dumps(
        {"docset": docset, "uploads": uploads, "kb_uuid": kb_uuid,
         "ingest_report": ingest_report}, indent=2, sort_keys=True))

    if args.preflight_only:
        print("\n--preflight-only: ingestion verified, nothing asked")
        print(f"state file: {state_path}")
        return 0

    attached = ({"knowledge_base_uuid": kb_uuid} if args.mode == "kb"
                else {"document_uuids": list(uploads.values())})
    model_name = model["name"] if model else None
    #: What was asked for, as opposed to what answered. Loop-invariant,
    #: and the row column and the meta block must not disagree about it:
    #: on a default-model run the rows named the model while the meta
    #: said null, which is a diff nobody can interpret.
    requested = model_name or (routing or {}).get("default_model")

    def relogin():
        login(session, creds)
        sync_csrf(session)

    cold_start = None
    if args.warmup:
        print(f"warmup: unscored, {args.timeout}s timeout …")
        started = time.perf_counter()
        result = ask(session, url, WARMUP_QUESTION, model_name=model_name,
                     timeout=args.timeout, relogin=relogin, **attached)
        cold_start = {"seconds": round(time.perf_counter() - started, 2),
                      "ts_end": utc_iso(),
                      "answer_chars": len(result["answer"]),
                      "error": result["error"] or None,
                      "served": (result["plan"] or {}).get("model")}
        (root / "streams" / f"{stem}_warmup.ndjson").write_text(result["raw"])
        print(f"warmup: {cold_start['seconds']}s  served={cold_start['served']}"
              + (f"  ERROR {result['error'][:100]}" if result["error"] else "")
              + "\n")

    plan_items = [(q, rep) for rep in range(1, args.repeat + 1) for q in questions]
    print(f"asking {len(plan_items)} question(s) "
          f"({len(questions)} x {args.repeat} repeat(s))\n")

    rows: list[dict] = []
    out_path = root / f"raw_{stem}.json"
    counts = {"answered": 0, "errors": 0, "routed": 0,
              "routed_unknown": 0, "leaks": 0}
    run_started = time.perf_counter()
    started_utc = utc_iso()

    for index, (question, repeat) in enumerate(plan_items, 1):
        if index > 1:
            time.sleep(args.pace)
        started = time.perf_counter()
        ts_start = utc_iso()
        result = ask(session, url, question["question"], model_name=model_name,
                     timeout=args.timeout, relogin=relogin, **attached)
        elapsed = round(time.perf_counter() - started, 2)
        plan = result["plan"] or {}
        served = plan.get("model")
        actions = [n["action"] for n in result["notices"]]
        routed = derive_routed(served, requested, actions)

        answer = result["answer"]
        if result["error"] and not answer:
            # score.py reads this prefix as a request error rather than a wrong
            # answer, which keeps a transport hole from reading as a mistake.
            answer = f"<<ERROR: {result['error']}>>"
            counts["errors"] += 1
        elif answer:
            counts["answered"] += 1
        if routed:
            counts["routed"] += 1
        elif routed is None:
            counts["routed_unknown"] += 1

        diag = diagnostics(result["answer"], question.get("answer") or "")
        if diag["thinking_leak"]:
            counts["leaks"] += 1

        rows.append({
            # --- the score.py / citation_accuracy.py contract ---------------
            "id": question["id"],
            "type": question["type"],
            "answerable": question.get("answerable", True),
            "question": question["question"],
            "expected": question.get("answer"),
            "got": answer,
            # --- what the server said it did --------------------------------
            "compaction": [a for a in actions
                           if a not in ("model_routed", "model_not_routed")],
            "input_tokens": plan.get("total_input_tokens"),
            "budget": plan.get("input_budget"),
            "context_notices": result["notices"],
            "notice_actions": actions,
            "plan": plan or None,
            "usage": result["usage"],
            "kb_sources": result["sources"],
            # --- how this row was obtained ----------------------------------
            "mode": args.mode,
            "repeat": repeat,
            "model_requested": model["tag"] if model else "(instance default)",
            "model_requested_name": requested,
            "model_served": served,
            "routed": routed,
            "suggested_model": result["suggested_model"],
            "temperature_config": ((routing or {}).get("temperatures") or {})
                                  .get(model["tag"]) if model else None,
            "documents_attached": 0 if args.mode == "kb" else len(uploads),
            "knowledge_base_uuid": kb_uuid,
            "difficulty": question.get("difficulty"),
            "elapsed_s": elapsed,
            "ttft_s": result["ttft_s"],
            "ts_start": ts_start,
            "ts_end": utc_iso(),
            "http_status": result["http_status"],
            "error": result["error"] or None,
            "diag": diag,
        })
        out_path.write_text(json.dumps(rows, indent=1))
        (root / "answers" / f"{stem}_{question['id']}_r{repeat}.md").write_text(
            f"# {stem} / {question['id']} / repeat {repeat}\n\n"
            f"**Q:** {question['question']}\n\n"
            f"**Expected:** {question.get('answer')}\n\n"
            f"**Served by:** {served}  (requested {requested}, "
            f"routed={routed})\n\n**Answer**\n\n{result['answer']}\n")
        (root / "streams"
         / f"{stem}_{question['id']}_r{repeat}.ndjson").write_text(result["raw"])

        flags = "".join(["R" if routed else ("?" if routed is None else " "),
                         "T" if diag["thinking_leak"] else " ",
                         "E" if result["error"] else " ",
                         "C" if rows[-1]["compaction"] else " "])
        print(f"[{index:>3}/{len(plan_items)}] {question['id']} r{repeat} "
              f"{flags} {elapsed:>6.1f}s "
              f"tok={plan.get('total_input_tokens')}/{plan.get('input_budget')} "
              f"{question['type'][:20]:20s} "
              f"{(result['answer'] or '(empty)')[:60]!r}")

    meta = {
        "run_id": run_id, "mode": args.mode, "docset": docset,
        "corpus": manifest.get("case_id"),
        "corpus_version": manifest.get("version"),
        "release_tag": (manifest.get("release_assets") or {}).get("tag"),
        "digital_asset_sha256": (None if args.mode == "merged"
                                 else digital_asset(manifest)["sha256"]),
        "merged_sha256": merged_digest,
        "model_requested": model["tag"] if model else "(instance default)",
        "model_requested_name": requested,
        "model_config": model,
        "routing_config": routing,
        "repeat": args.repeat, "pace_s": args.pace, "timeout_s": args.timeout,
        "questions": len(questions), "rows": len(rows),
        "cold_start": cold_start,
        "counts": counts,
        "wall_seconds": round(time.perf_counter() - run_started, 1),
        "uploads": uploads, "knowledge_base_uuid": kb_uuid,
        "started_utc": started_utc,
        "finished_utc": utc_iso(),
        "harness": Path(__file__).name,
    }
    (root / f"meta_{stem}.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True))

    print(f"\n{'=' * 66}")
    print(f"rows {len(rows)}  answered {counts['answered']}  "
          f"errors {counts['errors']}  routed {counts['routed']}  "
          f"routing-unknown {counts['routed_unknown']}  "
          f"thinking-leaks {counts['leaks']}")
    print(f"wall {meta['wall_seconds']}s")
    print(f"raw  : {out_path}")
    print(f"meta : {root / f'meta_{stem}.json'}")
    print("legend: R routed  ? routing not derivable (see --admin-config)  "
          "T thinking leaked into the answer  E request error  "
          "C context compaction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
